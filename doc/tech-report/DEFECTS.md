# Candidate defects

The authoritative `state/pyharp_defects.md` was not present in the fetched report sources or accessible shared artifacts. Titles are pending that register; identifiers are reserved, not inferred from discussion.

- P1 — CANDIDATE — title pending authoritative register.
- P2 — CANDIDATE — title pending authoritative register.
- P3 — CANDIDATE — title pending authoritative register.
- P4 — CANDIDATE — title pending authoritative register.
- P5 — CANDIDATE — title pending authoritative register.
- P6 — CANDIDATE — title pending authoritative register.
- P7 — CANDIDATE — title pending authoritative register.
- P8 — CANDIDATE — title pending authoritative register.
- P9 — CANDIDATE — title pending authoritative register.
- P11 — CANDIDATE — Planck band function: an edge with v = c2 nu / T exactly 1.5 is in neither series (strict v < 1.5 and v > 1.5 in `bbflux_wavenumber`), giving a wrong or negative band radiance; chapter 4, Limits of the band Planck function; reproduced by `derivation-checks/ch04/defects_pyharp_check.py` [C1].
- P12 — CANDIDATE — Longwave sweep: for lambda dtau >= 35 the plain quotient divides by lambda mu - 1, so a direction with lambda mu = 1 exactly gives infinite fluxes, and the error is large near it and percent-level in thick layers away from it: against 16 sublayers with B linear in tau, the midpoint upward flux of one layer of dtau 40 is off by +0.64 and -1.09 relative at w(1 -+ 1e-2) of the resonant w, and by 4.8e-3 to 9.7e-3 at half the resonant w for lambda dtau 75.7 to 151.4; chapter 4, Limits of the longwave solver; reproduced by `derivation-checks/ch04/defects_pyharp_check.py` [C2] (exact equality) and [C3] (scope).
- D1 — CANDIDATE — title pending authoritative register.
