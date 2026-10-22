/* Print cdisort's band-integrated Planck function c_planck_func2(wnumlo, wnumhi, T) [W m^-2 sr^-1]
   usage: planck_probe WLO WHI T     (built by build.sh against the pydisort source tree) */
#include <stdio.h>
#include <stdlib.h>
#ifdef CDISORT_HEADER_ONLY
#include "cdisort.hpp"
#else
#include "cdisort.h"
#endif
int main(int argc, char **argv) {
  if (argc != 4) return 2;
  printf("%.17g\n", c_planck_func2(atof(argv[1]), atof(argv[2]), atof(argv[3])));
  return 0;
}
