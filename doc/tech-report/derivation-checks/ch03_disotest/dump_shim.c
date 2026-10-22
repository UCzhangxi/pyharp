/* Dump shim for the cdisort 2.1.3 test driver bundled with pydisort (tests/cdisort213).
 * build.sh links a copy of test_cdisort.c, whose c_disort() calls are renamed dump_c_disort(),
 * with this file instead of print_test.c. Every c_disort() call is written as a "run" record (inputs before
 * the call, outputs after); every print_test() call is written as a "check" record holding the
 * reference ("good") values the test compares against and the ids of the runs involved.
 * Output: JSON lines to the file named by env DUMP_FILE (default dump.jsonl). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef CDISORT_HEADER_ONLY  /* pydisort >= 1.8: header-only C++ cdisort */
#include "cdisort.hpp"
#else                       /* pydisort 1.7.x: cdisort.c */
#include "cdisort.h"
#endif

static FILE *fp = NULL;
static int nrun = 0;
#define NMAP 64
static const void *map_ptr[NMAP];
static int map_id[NMAP];

int dump_c_disort(disort_state *ds, disort_output *out, emission_func_t f);

static FILE *dump(void) {
  if (!fp) {
    const char *fn = getenv("DUMP_FILE");
    fp = fopen(fn ? fn : "dump.jsonl", "w");
  }
  return fp;
}

static void arr(FILE *f, const char *name, const double *a, int n) {
  fprintf(f, "\"%s\":[", name);
  for (int i = 0; a && i < n; i++) fprintf(f, "%s%.17g", i ? "," : "", a[i]);
  fprintf(f, "]");
}

static void esc(FILE *f, const char *s) {
  fputc('"', f);
  for (; *s; s++) {
    if (*s == '"' || *s == '\\') fputc('\\', f);
    if (*s >= 32) fputc(*s, f);
  }
  fputc('"', f);
}

static void dump_in(FILE *f, disort_state *ds) {
  disort_flag *g = &ds->flag;
  fprintf(f, "{\"header\":");
  esc(f, ds->header);
  fprintf(f, ",\"flag\":{\"usrtau\":%d,\"usrang\":%d,\"ibcnd\":%d,\"lamber\":%d,\"planck\":%d,"
             "\"spher\":%d,\"onlyfl\":%d,\"brdf_type\":%d,\"quiet\":%d,\"intensity_correction\":%d,"
             "\"old_intensity_correction\":%d,\"general_source\":%d,\"output_uum\":%d}",
          g->usrtau, g->usrang, g->ibcnd, g->lamber, g->planck, g->spher, g->onlyfl, g->brdf_type,
          g->quiet, g->intensity_correction, g->old_intensity_correction, g->general_source,
          g->output_uum);
  fprintf(f, ",\"nlyr\":%d,\"nmom\":%d,\"nstr\":%d,\"nmom_nstr\":%d,\"ntau\":%d,\"numu\":%d,"
             "\"nphi\":%d,\"nphase\":%d,\"wvnmlo\":%.17g,\"wvnmhi\":%.17g,\"accur\":%.17g,"
             "\"radius\":%.17g",
          ds->nlyr, ds->nmom, ds->nstr, ds->nmom_nstr, ds->ntau, ds->numu, ds->nphi, ds->nphase,
          ds->wvnmlo, ds->wvnmhi, ds->accur, ds->radius);
  fprintf(f, ",\"bc\":{\"fbeam\":%.17g,\"umu0\":%.17g,\"phi0\":%.17g,\"fisot\":%.17g,\"fluor\":%.17g,"
             "\"ttemp\":%.17g,\"btemp\":%.17g,\"temis\":%.17g,\"albedo\":%.17g},",
          ds->bc.fbeam, ds->bc.umu0, ds->bc.phi0, ds->bc.fisot, ds->bc.fluor, ds->bc.ttemp,
          ds->bc.btemp, ds->bc.temis, ds->bc.albedo);
  arr(f, "dtauc", ds->dtauc, ds->nlyr); fputc(',', f);
  arr(f, "ssalb", ds->ssalb, ds->nlyr); fputc(',', f);
  arr(f, "pmom", ds->pmom, (ds->nmom_nstr + 1) * ds->nlyr); fputc(',', f);
  arr(f, "temper", g->planck ? ds->temper : NULL, ds->nlyr + 1); fputc(',', f);
  arr(f, "utau", g->usrtau ? ds->utau : NULL, ds->ntau); fputc(',', f);
  arr(f, "umu", (g->usrang || g->ibcnd) ? ds->umu : NULL, ds->numu); fputc(',', f);
  arr(f, "phi", ds->phi, ds->nphi); fputc(',', f);
  arr(f, "zd", g->spher ? ds->zd : NULL, ds->nlyr + 1);
  if (g->brdf_type == BRDF_RPV && ds->brdf.rpv)
    fprintf(f, ",\"rpv\":[%.17g,%.17g,%.17g,%.17g]", ds->brdf.rpv->rho0, ds->brdf.rpv->k,
            ds->brdf.rpv->theta, ds->brdf.rpv->scale);
  fprintf(f, "}");
}

static void dump_out(FILE *f, disort_state *ds, disort_output *out, int is_disort) {
  int nu = ds->numu;
  fprintf(f, "{\"ntau\":%d,\"numu\":%d,\"nphi\":%d,", ds->ntau, ds->numu, ds->nphi);
  fprintf(f, "\"rad\":[");
  for (int i = 0; i < ds->ntau; i++) {
    disort_radiant *r = &out->rad[i];
    fprintf(f, "%s[%.17g,%.17g,%.17g,%.17g,%.17g]", i ? "," : "", r->rfldir, r->rfldn, r->flup,
            r->dfdt, r->uavg);
  }
  fprintf(f, "],");
  arr(f, "uu", (ds->flag.onlyfl || !is_disort) ? NULL : out->uu, nu * ds->ntau * ds->nphi); fputc(',', f);
  arr(f, "umu_out", ds->umu, nu); fputc(',', f);
  arr(f, "utau_out", ds->utau, ds->ntau); fputc(',', f);
  arr(f, "albmed", (ds->flag.ibcnd && is_disort) ? out->albmed : NULL, nu); fputc(',', f);
  arr(f, "trnmed", (ds->flag.ibcnd && is_disort) ? out->trnmed : NULL, nu);
  fprintf(f, "}");
}

static int lookup(const void *p) {
  for (int i = 0; i < NMAP; i++) if (map_ptr[i] == p) return map_id[i];
  return -1;
}

int dump_c_disort(disort_state *ds, disort_output *out, emission_func_t f) {
  FILE *o = dump();
  int id = nrun++;
  fprintf(o, "{\"kind\":\"run\",\"id\":%d,\"in\":", id);
  dump_in(o, ds);
  int ret = c_disort(ds, out, f);
  fprintf(o, ",\"out\":");
  dump_out(o, ds, out, 1);
  fprintf(o, "}\n");
  fflush(o);
  int slot = -1;
  for (int i = 0; i < NMAP && slot < 0; i++) if (map_ptr[i] == out) slot = i;
  for (int i = 0; i < NMAP && slot < 0; i++) if (map_ptr[i] == NULL) slot = i;
  if (slot < 0) slot = id % NMAP;
  map_ptr[slot] = out; map_id[slot] = id;
  return ret;
}

void print_test(disort_state *ds_calc, disort_output *calc, disort_state *ds_good,
                disort_output *good) {
  FILE *o = dump();
  fprintf(o, "{\"kind\":\"check\",\"calc_run\":%d,\"good_run\":%d,\"calc_header\":", lookup(calc),
          lookup(good));
  esc(o, ds_calc->header);
  fprintf(o, ",\"good\":");
  dump_out(o, ds_good, good, 1);
  fprintf(o, ",\"calc\":");
  /* calc of test 14 is a twostr() result: no uu/albmed arrays */
  dump_out(o, ds_calc, calc, lookup(calc) >= 0 || ds_calc == ds_good);
  fprintf(o, "}\n");
  fflush(o);
  /* the test reuses stack addresses for the next case: forget the runs used here */
  for (int i = 0; i < NMAP; i++) if (map_ptr[i] == calc || map_ptr[i] == good) map_ptr[i] = NULL;
}
