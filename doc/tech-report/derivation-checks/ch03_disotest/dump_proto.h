/* force-included into the renamed test_cdisort copy: declares the dump wrapper */
#ifdef CDISORT_HEADER_ONLY
#include "cdisort.hpp"
#else
#include "cdisort.h"
#endif
int dump_c_disort(disort_state *ds, disort_output *out, emission_func_t f);
