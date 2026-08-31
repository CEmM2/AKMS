# Stress Integration (Stress_Update6) — Objective corotational J2-CPP + PF + optional EOS

This document specifies the **exact** stress update pipeline used by this codebase, as implemented and documented in `Stress update.md` and used with the `TLCorotated` kinematics utilities in `Kinematics.md`. 

## Contents
1. Unified interface (I/O contract)
2. Objective (midpoint corotational) wrapper
3. J2 Closest-Point Projection (CPP) in corotational frame
4. PF degradation (`ω_s`, `ω_t`)
5. EOS-coupled hydrostatic stress mode
6. Work/temperature bookkeeping
7. Implementation gotchas + required invariants
8. Minimal validation tests

---

## 1) Unified interface (I/O contract)

All stress update modes expose the same **6-output** interface: 

\[
(\hat{\sigma}^{n+1},\; \bar{\varepsilon}_p^{n+1},\; \dot{\bar{\varepsilon}}_p^{n+1},\; T^{n+1},\; \sigma_{eq}^{n+1},\; \Delta\varepsilon_p )
\]

Notes:
- “Hat” quantities (`σ̂`) live in the **corotational (objective) frame**.
- Extra bookkeeping (stored/dissipated work, EOS pressure, \(J\), internal energy) is written to fields or returned by a separate `Stress_Update_Full`. 

---

## 2) Objectivity wrapper (midpoint corotational update)

### Midpoint kinematics
At the midpoint configuration, build: 
- \( \mathbf{L} = \nabla \dot{\mathbf{u}} \)
- \( \mathbf{D} = \tfrac12(\mathbf{L} + \mathbf{L}^T) \)
- \( \mathbf{W} = \tfrac12(\mathbf{L} - \mathbf{L}^T) \)

### Hughes–Winget / Cayley incremental rotation
Compute incremental rotation via Cayley transform: 
\[
\mathbf{R}_\Delta = \left(\mathbf{I}-\frac{\Delta t}{2}\mathbf{W}\right)^{-1}\left(\mathbf{I}+\frac{\Delta t}{2}\mathbf{W}\right)
\]

In code, `TLCorotated` provides:
- `hw_deltaR_from_L(L, dt)`
- `hw_halfstep_R(L, dt)`

### Rotate stress into corotational frame, integrate, rotate back
- Rotate input stress:
\[
\hat{\sigma}^n = \mathbf{R}_\Delta^T \sigma^n \mathbf{R}_\Delta
\]
- Constitutive update happens using `D̂` and `σ̂`.
- Rotate output back:
\[
\sigma^{n+1} = \mathbf{R}_\Delta \hat{\sigma}^{n+1} \mathbf{R}_\Delta^T
\] 

### Canonical kernel call pattern
The element kernel wraps constitutive update like this:

- Compute `L, D, R_delta`
- Convert spatial stress to corotational Voigt and rotate `D`:
  - `sigma_hat_n, D_hat = Kinematics.stress_to_voigt_MID(Stress[n], D, R_delta)`
- Call constitutive update:
  - `sigma_hat_np1, peeq_np1, edot, T_np1, vm_np1, dep = Constit.Stress_Update6(...)`
- Rotate back to spatial:
  - `sigma_np1 = Kinematics.update_stress_voigt_from_MID(sigma_hat_np1, R_delta)`

---

## 3) Constitutive model: J2 Closest-Point Projection (CPP) in corotational frame

### Sign conventions (must match everywhere)
Mean stress (tension positive) and pressure (compression positive): 
\[
m=\frac13\mathrm{tr}(\sigma),\qquad p=-m
\]
Deviatoric:
\[
s=\sigma-m\mathbf{I}
\]
Von Mises:
\[
\sigma_{eq}=\sqrt{\frac32\,s:s}
\] 

### Elastic predictor (trial)
Given rotated stress `σ̂^n` and corotational strain-rate `D̂`: 
\[
\hat{\sigma}^{tr} = \hat{\sigma}^{n} + \mathbb{C}:\mathbf{D}\Delta t,
\quad
\hat{s}^{tr}=\mathrm{dev}(\hat{\sigma}^{tr}),
\quad
\sigma_{eq}^{tr}=\sqrt{\tfrac32 \hat{s}^{tr}:\hat{s}^{tr}}
\]

### Yield check
If:
\[
\sigma_{eq}^{tr} \le \sigma_y(\bar{\varepsilon}_p^n,\dot{\bar{\varepsilon}}_p,T^n)\,T_{soft}\,\omega_s
\]
then **elastic step** (return trial). Otherwise **plastic correction**. 

### Plastic corrector (radial return via Δλ solve)
Solve for \(\Delta\lambda\ge 0\) using a scalar nonlinear equation: 
\[
g(\Delta\lambda)
=
\sigma_{eq}^{tr}-3\mu\Delta\lambda
-\sigma_y(\bar{\varepsilon}_p^n+\Delta\lambda,\Delta\lambda/\Delta t,T)\,T_{soft}\,r\,\omega_s
=0
\]

(Implementation uses Newton; details of \(\sigma_y(\cdot)\), \(T_{soft}\), and \(r\) are model-specific but the solve structure is fixed.)

### Post-correction reconstruction (conceptual)
- Direction \( \mathbf{n} = \hat{s}^{tr}/\|\hat{s}^{tr}\|\)
- Deviatoric magnitude reduced by \(3\mu\Delta\lambda\)
- Rebuild \(\hat{\sigma}^{n+1} = \hat{s}^{n+1} + m_{phys}\mathbf{I}\) 
- Equivalent stress and plastic increment reported:
  - \(W_p = \Delta\lambda\,\sigma_{eq}^{n+1}\)
  - \(\Delta\varepsilon_p = \Delta\lambda\,\mathbf{n}\) 

---

## 4) PF degradation (two scalars, two targets)

Two degradation scalars are used: 
- \( \omega_s(d_s)\in(0,1] \): shear/ASB degradation
- \( \omega_t(d_t)\in(0,1] \): spall degradation

Rules:
- Apply **ω_s** to the **deviatoric** response. 
- Apply **ω_t** to **tensile-only** volumetric/mean part (or tensile-only pressure in EOS mode). 

---

## 5) EOS-coupled hydrostatic stress mode

When EOS mode is enabled, hydrostatic stress comes from EOS pressure rather than the constitutive return mapping: 

\[
\hat{\sigma}^{n+1} = \omega_s \hat{s}^{n+1} - p_{phys}\mathbf{I}
\]
\[
p_{phys} = [\omega_t H(-p_{EOS})+H(p_{EOS})]\,p_{EOS}
\]
- \(p_{EOS} > 0\) in compression
- tensile-only degradation: tension corresponds to \(p_{EOS}<0\) 

### Volumetric update for J (when not computed directly from F)
\[
J^{n+1} = J^n \exp(\Delta t\,\mathrm{tr}(\mathbf{D}) + 3\alpha_T \Delta T)
\] 

---

## 6) Work and temperature bookkeeping (do it once, not “twice but spiritually”)

Scalar plastic work increment (important fix):
- \(W_p^{inc} = \Delta\lambda \cdot \sigma_{eq}^{n+1}\) 

Temperature update (single):
\[
T^{n+1} = T^n + \beta \, W_p^{inc}/(\rho C_p)
\] 

Implementation snippet emphasizes:
- compute **scalar** work increment once
- split stored/dissipated via `thermal.QT` without double counting

---

## 7) Implementation gotchas + invariants (non-negotiable)

### Gotcha A: EOS spall gate sign
EOS pressure uses compression-positive convention. Tensile-only degradation must trigger when \(p_{EOS}<0\). The doc includes the corrected implementation pattern: 
- `p_phys = (wt * step(0, -p_eos) + step(0, p_eos)) * p_eos`
- `sigma = ws * s_dev - p_phys * I`

### Gotcha B: Voigt conventions
All 2nd-order tensors in Voigt are **tensorial Voigt**, ordering:
`[xx, yy, zz, xy, xz, yz]` with **unscaled** shear components.

### Invariants to assert (cheap sanity)
- `σ̂` must remain symmetric after pack/unpack/rotation
- `dev(σ)` trace approximately zero (within fp tolerance)
- `Δλ >= 0`
- `σ_eq >= 0`
- For purely elastic steps: `peeq` must not increase

---

## 8) Minimal validation tests (fast, brutal, effective)

1. **Pure rotation test**  
   Apply rigid rotation (nonzero W, D≈0). Stress should rotate objectively, not change in corotational frame. 

2. **Uniaxial strain-rate (elastic)**  
   Small D, yield not exceeded: compare to linear elastic update `σ̂^{n+1}=σ̂^n + C:D dt`. 

3. **Plastic loading (J2 return)**  
   Force plastic step: verify `g(Δλ)≈0` after Newton and `σ_eq` lands on degraded yield surface. 

4. **EOS gate sign test**  
   With `p_eos > 0` compression: no tensile degradation.
   With `p_eos < 0` tension: tensile-only ω_t applied.