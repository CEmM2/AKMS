# Numerical Safeguards — preventing NaNs, negative volumes, and other avoidable tragedies

This doc defines repo-wide numerical safety policies for FEM/FD/MPM/spectral code in Taichi.
The goal is not “never fail,” it’s “fail loudly when physics is impossible, and degrade gracefully when it’s just numerics.”

This repo uses:
- Objective corotational stress update (Hughes–Winget / Cayley)
- Cauchy stress in tensorial Voigt `[xx, yy, zz, xy, xz, yz]`
- Pressure sign: compression positive, mean stress tension positive

(See `reference/continuum-tensors.md` and `reference/stress-integration.md`.)

---

## 1) Universal safety kernels (cheap and worth it)

### A) NaN/Inf scan
Have a debug-only kernel to scan critical fields:
- nodal `x, v`
- particle `x, v, F` (MPM)
- quad-point stress/state
- solver vectors (CG)

Policy:
- run every N steps in debug mode
- set a global flag (0D `ti.field(i32)`) if any NaN/Inf is detected

### B) Range clamp counters
When clamping is enabled, count clamp events:
- count how many points hit `J_min` / `J_max`
- how many times Newton iteration hit fallback
- how many times yield solve failed

This makes it obvious when the sim is “alive” vs “surviving.”

---

## 2) Deformation gradient / volume safeguards (finite strain)

### Determinant clamp policy
If you compute `J = det(F)`:
- Define constants:
  - `J_min` small positive (e.g., 1e-6 or problem-scaled)
  - optional `J_max` to prevent extreme expansion

Policy options (choose one and be consistent):
1) **Hard fail** (debug): if `J <= 0` set error flag and bail
2) **Clamp** (production): `J = max(J, J_min)` and optionally project F

Important:
- clamping J without adjusting F is physically inconsistent but can prevent total blow-up.
- if you clamp, track how often it happens.

### Safe inverse
Avoid explicit `F.inverse()` when possible in hot paths.
Prefer solving systems for `F^{-T} v` etc. when feasible.
If inverse is required:
- guard against near-singular matrices
- fall back to damped inverse or early-exit with error flag

---

## 3) Stress update safeguards (J2 CPP + PF + EOS)

### A) Plastic multiplier and Newton solve
For CPP solve of `g(Δλ)=0`:
- enforce `Δλ >= 0`
- cap Newton iterations `it_max`
- require `|g| < tol` for convergence

Fallback policy (recommended):
- if Newton fails: fallback to bisection/secant on `[0, Δλ_max]` (robust)
- if fallback fails: clamp Δλ to a safe value and flag the point

### B) Equivalent stress stability
- enforce `σ_eq >= 0`
- guard normalization `n = s / ||s||` with eps:
  - if `||s|| < eps`, set `n = 0` and treat as purely volumetric

### C) Temperature update (plastic heating)
- compute scalar plastic work increment once
- guard division by `ρ Cp` (no zero / negative)
- clamp temperature to reasonable bounds if your EOS requires it
- track any clamp events

### D) PF degradation bounds
- ensure `ω_s, ω_t ∈ (0, 1]`
- if damage field produces values outside range, clamp and flag
- preserve the tensile-only gate logic:
  - EOS pressure uses compression-positive; tensile is `p_EOS < 0`

### E) EOS pressure sign gate (critical)
When EOS mode is active:
- `p_EOS > 0` compression (no tensile degradation)
- `p_EOS < 0` tension (apply ω_t)

Reconstruct:
- `σ = ω_s s_dev - p_phys I`
- `p_phys = ( ω_t * H(-p_EOS) + H(p_EOS) ) * p_EOS`

This sign convention must be consistent everywhere in the codebase.

---

## 4) Time integration safeguards

### Explicit stability
For explicit updates:
- enforce a CFL-like dt restriction where applicable:
  - wave speed / grid spacing (FEM, elastodynamics)
  - particle-to-grid dt (MPM)
- if dt is adaptive, limit max dt growth per step

### Substepping triggers
Substep when any of these occur:
- stress update Newton fails at too many points
- clamp counters exceed threshold
- temperature or J excursions exceed threshold
- damage evolution becomes unstable (e.g., too large Δd)

Policy:
- substep factor chosen to restore stability (e.g., 2x, 4x)
- do not substep forever: cap retries and fail loudly if necessary

---

## 5) Solver safeguards (CG/PCG)

### SPD checks (CG requirement)
During CG:
- if `p·Ap <= 0`:
  - system is not SPD (or numerical corruption)
  - bail and flag
  - optionally fall back to damped update or different solver

### Residual sanity
- if residual becomes NaN/Inf: abort the solve
- if residual increases catastrophically: apply damping or restart

### Host sync minimization
Don’t read convergence scalars to host every iteration unless you accept the sync cost.
If you do fixed-iter solves, use:
- periodic host checks (every k iterations)
- or purely fixed iteration counts for performance-critical paths

---

## 6) Debug vs production modes

### Debug mode
- frequent NaN scans
- hard fails on invalid J (<=0)
- strict Newton tolerances
- more expensive validation invariants

### Production mode
- clamping enabled (with counters)
- fewer scans
- robust fallbacks enabled (bisection)
- keep enough flags/counters to diagnose failures

---

## 7) Minimal invariants to track (cheap and helpful)

MPM:
- total grid mass conservation (after P2G)
- max |v| bounds
- count of particles with invalid F/J

FEM:
- rigid motion should not create stress (objectivity test)
- patch test error bounds
- Newton residual monotonic decrease (or line search effectiveness)

FD/spectral:
- stability bounds, max/min of fields
- energy-like invariant if applicable