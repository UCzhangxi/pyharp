// Chapter 10 probe of RadiationModel (src/integrator/radiation_model.cpp), which has no Python binding and no
// test at the pin: the energy budget of one step and the effect of the temperature clamp.
// usage: model_probe <radiation yaml with one Toon shortwave band "SW" and a jit opacity reading ext, ssa, gg>
// Prints [M1] the budget of one Euler step for surface albedo 0 and 0.3: the energy the step adds to the
// atmosphere and the surface against the radiative energy that enters at the top less the surface emission
// sigma T_s^4 (which leaves a shortwave-only model), tolerance 1e-10 of dt mu0 F0 (20 layers of round-off);
// [M2] the clamp: an atmosphere at 1100 K and at 10 K stepped by dt = 1e-9 s.
#include <cmath>
#include <cstdio>
#include <map>
#include <string>

#include <harp/constants.h>
#include <harp/integrator/radiation_model.hpp>

using namespace harp;

int main(int argc, char** argv) {
  torch::set_default_dtype(caffe2::TypeMeta::Make<double>());
  int const nlyr = 20, nwave = 3;
  double const fbeam = 1000., mu0 = 0.6;
  auto rad = RadiationOptionsImpl::from_yaml(argv[1]);
  rad->bands()[0]->weight({0.2, 0.5, 0.3});

  auto make = [&]() {
    auto op = RadiationModelOptionsImpl::create();
    op->ncol(1).nlyr(nlyr).kappa(0.0).rad(rad);
    op->intg(IntegratorOptionsImpl::create());
    op->intg()->type("euler");
    return RadiationModel(op);
  };

  auto plev = torch::logspace(5, 3, nlyr + 1);
  auto pres = torch::sqrt(plev.narrow(0, 0, nlyr) * plev.narrow(0, 1, nlyr)).view({1, nlyr});
  auto xfrac = torch::ones({1, nlyr, 5}) / 5.;
  auto opts = torch::TensorOptions().dtype(torch::kFloat64);

  auto state = [&](double temp, double albedo, double ssa) {
    std::map<std::string, torch::Tensor> atm, bc;
    atm["pres"] = pres.clone();
    atm["temp"] = torch::full({1, nlyr}, temp, opts);
    // extinction [1/m]: column optical depth 0.04-0.17 with the 2.9 km layers of the default (Mars) gas
    atm["ext"] = torch::tensor({0.5e-6, 1e-6, 2e-6}, opts).view({nwave, 1, 1}).expand({nwave, 1, nlyr}).clone();
    atm["ssa"] = torch::full({nwave, 1, nlyr}, ssa, opts);
    atm["gg"] = torch::full({nwave, 1, nlyr}, 0.5, opts);
    bc["SW/umu0"] = torch::tensor({mu0}, opts);
    bc["SW/fbeam"] = torch::full({nwave, 1}, fbeam, opts);
    bc["SW/albedo"] = torch::full({nwave, 1}, albedo, opts);
    bc["btemp"] = torch::full({1}, std::fmin(std::fmax(temp, 20.), 1000.), opts);
    return std::make_pair(atm, bc);
  };

  for (double albedo : {0.0, 0.3}) {
    auto model = make();
    auto [atm, bc] = state(250., albedo, 0.5);
    double const dt = 10.;
    auto t0 = atm["temp"].clone();
    auto ts0 = bc["btemp"].clone();
    model->forward(xfrac, atm, bc, dt, 0);
    auto net = model->results["netflux"];        // (1, nlyr + 1), level 0 = surface, up - down
    auto dT_atm = model->results["dT_atm"];      // (1, nlyr)
    auto dT_surf = model->results["dT_surf"];    // (1,)
    auto const& o = model->options;
    // what the step adds: atmosphere sum rho c_p dz dT (dz hypsometric, as the step computes it), surface c_s dT_s
    auto lnp = plev.log();
    auto rd = constants::Rgas / o->mean_mol_weight();
    auto dzl = t0.squeeze(0) * (lnp.narrow(0, 0, nlyr) - lnp.narrow(0, 1, nlyr)) * rd / o->grav();
    auto rho = pres.squeeze(0) * o->mean_mol_weight() / (constants::Rgas * t0.squeeze(0));
    double e_atm = (rho * o->cp() * dzl * dT_atm.squeeze(0)).sum().item<double>();
    double e_sfc = o->cSurf() * dT_surf.item<double>();
    double toa_net = net[0][nlyr].item<double>();      // up - down at the top
    double sfc_net = net[0][0].item<double>();         // up - down at the surface
    double emis = constants::stefanBoltzmann * std::pow(ts0.item<double>(), 4);
    // radiative energy into the column + surface: -(TOA net); the surface also emits sigma T_s^4 to nowhere
    // in a shortwave-only model, which the step removes from the surface
    double expect = dt * (-toa_net - emis);
    double fin = mu0 * fbeam;
    std::printf("[M1] RadiationModel step, A = %.1f: atmosphere %.6e J m^-2, surface %.6e J m^-2, expected from the "
                "TOA net minus sigma T_s^4 %.6e J m^-2; residual / (dt mu0 F0) = %.3e; surface-absorbed share "
                "-(F_net,sfc) dt = %.6e, the step credits the surface with F_dn,sfc dt = %.6e\n",
                albedo, e_atm, e_sfc, expect, (e_atm + e_sfc - expect) / (dt * fin), -sfc_net * dt, e_sfc + emis * dt);
    double res = std::fabs(e_atm + e_sfc - expect) / (dt * fin);
    if (albedo == 0.0) {
      std::printf("[M1] %s energy budget of one step closes for a black surface: residual %.1e, tolerance 1e-10\n",
                  res <= 1e-10 ? "PASS" : "FAIL", res);
    } else {
      std::printf("[M1] CANDIDATE %s: with surface albedo %.1f one step adds %.3g of dt mu0 F0 that no flux "
                  "delivers; the surface forcing takes F_dn,sfc where the surface absorbs F_dn,sfc - F_up,sfc "
                  "(the difference, A F_dn,sfc dt, is %.6e J m^-2)\n",
                  res > 1e-10 ? "reproduced" : "not reproduced", albedo, res, e_sfc + emis * dt + sfc_net * dt);
    }
  }

  for (double temp : {1100., 10.}) {
    auto model = make();
    auto [atm, bc] = state(temp, 0.0, 0.5);
    model->forward(xfrac, atm, bc, 1e-9, 0);
    auto dT = model->results["dT_atm"];
    double moved = (atm["temp"] - (torch::full({1, nlyr}, temp, opts) + dT)).abs().max().item<double>();
    std::printf("[M2] RadiationModel clamp: atmosphere at %.0f K, dt = 1e-9 s: radiative dT %.3e K, temperature "
                "after the step %.6g K, moved by the clamp %.6g K\n",
                temp, dT.abs().max().item<double>(), atm["temp"].max().item<double>(), moved);
  }
  return 0;
}
