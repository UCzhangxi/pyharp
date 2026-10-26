// Test-only adapters exercise the unmodified, compiled RadiationBand::forward.
#include <harp/radiation/radiation_band.hpp>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <ATen/Parallel.h>

using Dict = std::map<std::string, torch::Tensor>;
struct ManufacturedOpacity : torch::nn::Module {
  torch::Tensor data;
  explicit ManufacturedOpacity(torch::Tensor t) : data(t) {}
  torch::Tensor forward(torch::Tensor, Dict const&) { return data; }
};
struct CaptureSolver : torch::nn::Module {
  torch::Tensor seen;
  torch::Tensor forward(torch::Tensor prop, Dict*, std::string) {
    seen = prop.clone();
    return torch::zeros({prop.size(0), prop.size(1), prop.size(2)+1, 4}, prop.options());
  }
};

int main(int argc, char** argv) {
  at::set_num_threads(1);
  if (argc != 3) return 2;
  std::ifstream in(argv[1]);
  std::ofstream out(argv[2]);
  out << std::setprecision(17);
  out << "case,dtype,index,actual,repeat_error,source_error,capture_error\n";
  int count; in >> count;
  for (int c=0;c<count;++c) {
    std::string name; int bits,nw,nc,nl,np,ns,dzdim;
    in >> name >> bits >> nw >> nc >> nl >> np >> ns >> dzdim;
    auto opts=torch::TensorOptions().dtype(bits==64 ? torch::kFloat64 : torch::kFloat32).device(torch::kCPU);
    auto op=harp::RadiationBandOptionsImpl::create();
    op->solver_name("toon").nwave(nw).ncol(nc).nlyr(nl).weight(std::vector<double>(nw,1.0));
    op->toon()=harp::ToonMcKay89OptionsImpl::create();
    harp::RadiationBand band(op);
    band->to(bits==64 ? torch::kFloat64 : torch::kFloat32);
    band->prop.set_(torch::zeros({nw,nc,nl,np},opts));
    auto capture=std::make_shared<CaptureSolver>();
    band->rtsolver=torch::nn::AnyModule(capture);
    std::vector<std::shared_ptr<ManufacturedOpacity>> sources;
    std::vector<torch::Tensor> originals;
    for(int s=0;s<ns;++s) {
      int nps; in >> nps;
      std::vector<double> values(nw*nc*nl*nps);
      for(auto& v:values) in >> v;
      auto data=torch::tensor(values,torch::kFloat64).reshape({nw,nc,nl,nps}).to(opts);
      auto source=std::make_shared<ManufacturedOpacity>(data);
      band->opacities[std::to_string(s)]=torch::nn::AnyModule(source);
      sources.push_back(source); originals.push_back(data.clone());
    }
    std::vector<double> zv(dzdim==1 ? nl : nc*nl);
    for(auto& v:zv) in >> v;
    auto dz=torch::tensor(zv,torch::kFloat64).to(opts);
    if(dzdim==2) dz=dz.reshape({nc,nl});
    auto conc=torch::ones({nc,nl,1},opts);
    Dict bc,atm;
    band->forward(conc,dz,&bc,&atm);
    auto first=band->prop.clone();
    double capture_error=(first-capture->seen).abs().max().item<double>();
    band->forward(conc,dz,&bc,&atm);
    double repeat_error=(first-band->prop).abs().max().item<double>();
    double source_error=0;
    for(size_t s=0;s<sources.size();++s)
      source_error=std::max(source_error,(sources[s]->data-originals[s]).abs().max().item<double>());
    auto flat=first.to(torch::kFloat64).flatten().contiguous();
    for(int64_t i=0;i<flat.numel();++i)
      out << name << ',' << bits << ',' << i << ',' << flat[i].item<double>() << ',' << repeat_error << ',' << source_error << ',' << capture_error << '\n';
  }
  return in.fail() ? 3 : 0;
}
