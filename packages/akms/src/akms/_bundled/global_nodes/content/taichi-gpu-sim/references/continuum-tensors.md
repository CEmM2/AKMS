# Continuum Tensors & Conventions (Implementation-Truth)

This document defines the **exact tensor conventions** used by this codebase for FEM/MPM-style constitutive updates in Taichi. If any other doc or snippet disagrees, this file wins (because it matches the implementation).

Primary sources:
- `Kinematics.md` (Taichi class TLCorotated)
- `Stress update.md` (stress update + J2 CPP + PF + EOS coupling)

---

## 1) Frames, measures, and what gets updated

### Updated stress measure
We update **Cauchy stress** `σ` using a **corotational (midpoint) objective scheme**.

The constitutive integration is performed in a rotated “mid/corotational” frame, then rotated back to spatial at the end of the step.

### TL FEM conversions (material measures)
For Total Lagrangian (TL) assembly variants, we provide:
- **PK2** conversion from spatial Cauchy stress:
  - `S = J * F^{-1} σ F^{-T}`
- Push of spatial tangent to material tangent compatible with PK2:
  - `C_mat = J * (F^{-1} ⊗ F^{-1}) : c_spatial : (F^{-1} ⊗ F^{-1})`
(Implementation uses explicit 4th-order expansion / contraction.)

---

## 2) Voigt conventions (this is where bugs breed)

### Tensorial Voigt (2nd-order) packing order
We use **tensorial Voigt** (NOT engineering shear) with ordering:

`v = [A_xx, A_yy, A_zz, A_xy, A_xz, A_yz]`

- Shears are **unscaled**: `A_xy` not `2A_xy`.
- Unpack restores symmetry by setting both off-diagonal entries.

> If you paste code using `[xx, yy, zz, yz, xz, xy]` or engineering shear factors, it is wrong for this repo.

---

## 3) Mandel conventions (used for 6×6 tangent rotation)

We rotate 6×6 tangents via a Mandel-space similarity transform.

### Mandel basis
Mandel basis uses shear components scaled by `1/√2`:
- `E_3` has `(0,1)` and `(1,0)` entries `1/√2`, etc.

### Tensorial-Voigt ⇄ Mandel mapping for 6×6
Let `P = diag([1,1,1, √2, √2, √2])`.

- `C_M = P * C_V * P^{-1}`
- `C_V = P^{-1} * C_M * P`

This keeps 6×6 tangent rotation correct while the code stores tangents in **tensorial Voigt**.

---

## 4) Kinematics (midpoint / corotational)

Given nodal velocity gradients evaluated at the midpoint configuration, we build the **spatial velocity gradient**:

- `L = ∇_x v`
- `D = sym(L) = 1/2 (L + L^T)`
- `W = skew(L) = 1/2 (L - L^T)`

### Hughes–Winget / Cayley incremental rotation
Incremental rotation is computed using the Cayley transform of `W`:

`R_Δ = (I - (Δt/2) W)^{-1} (I + (Δt/2) W)`

Implementation provides:
- full-step `dR` from `L, dt`
- half-step `R_half` from `L, dt` (uses `0.5*dt`)

---

## 5) Objective stress update (how stress is rotated)

### Rotate stress and strain-rate to mid frame
Given spatial Cauchy stress at `n` in tensorial-Voigt, the code:
1) unpacks to 3×3
2) rotates to mid frame using `R_half` (or `R_Δ` per call site)
3) rotates strain-rate `D` similarly
4) returns tensorial-Voigt versions for constitutive integration in the mid frame

Conceptually:
- `σ̂^n = R^T σ^n R`
- `D̂ = R^T D R`

### Rotate updated stress back to spatial
After constitutive update provides `σ̂^{n+1}` in the corotational frame:
- `σ^{n+1} = R σ̂^{n+1} R^T`

### Rotate tangents (6×6) back to spatial
The spatial tangent is rotated via Mandel mapping and `T(Q)` operator:
- `C_Mr = T_M C_M T_M^T`
- then mapped back to tensorial-Voigt.

---

## 6) Stress decomposition and sign conventions

From the stress update spec:

Mean stress:
- `m = (1/3) tr(σ)` with **tension positive**

Pressure:
- `p = -m` with **compression positive**

Deviatoric stress:
- `s = σ - m I`

Von Mises equivalent stress:
- `σ_eq = sqrt( (3/2) s:s )`

---

## 7) Damage / PF degradation conventions

Two degradation scalars:
- `ω_s(d_s)` applies to **deviatoric** response (shear / ASB degradation)
- `ω_t(d_t)` applies to **tensile-only** volumetric part (spall degradation)

Implementation intent:
- Deviatoric: `s ← ω_s s`
- Mean stress gate: apply `ω_t` only when in tensile regime (details differ for EOS mode).

---

## 8) EOS-coupled hydrostatic stress (when enabled)

When EOS mode is active:
- deviatoric still comes from constitutive update (then degraded by `ω_s`)
- hydrostatic stress comes from EOS pressure `p_EOS` (positive in compression)

Stress reconstruction:
- `σ̂^{n+1} = ω_s ŝ^{n+1} - p_phys I`

Tensile-only spall gate on pressure (tension means `p_EOS < 0`):
- `p_phys = [ ω_t H(-p_EOS) + H(p_EOS) ] p_EOS`

---

## 9) What the constitutive interface returns (Stress_Update6)

All stress update modes expose the same 6 outputs in the corotational frame:

`(σ̂^{n+1}, p̄^{n+1}, p̄dot^{n+1}, T^{n+1}, σ_eq^{n+1}, Δε_p)`

Additional bookkeeping (stored/dissipated work, EOS pressure, J, energy) is stored to fields or returned by a separate “full” interface.

---

## 10) TL tangent operator application (PK1 form)

For TL assembly using PK1 linearization, the code implements a delta-operator:

`δP = J [ c : sym(dF F^{-1}) + σ tr(sym(dF F^{-1})) ] F^{-T}  -  τ F^{-T} dF^T F^{-T}`

with `τ = J σ` and spatial tangent `c` provided in tensorial-Voigt (converted internally to 4th order).

This is used to build element stiffness contributions via virtual gradients `dF` assembled from shape gradients.

---

## 11) Hard “do not violate” rules for generated code

1) Tensorial-Voigt order is `[xx, yy, zz, xy, xz, yz]` with **unscaled** shears.
2) Tangent rotation uses Mandel-space similarity transforms; do not rotate a 6×6 Voigt tangent by naive 3×3 ops.
3) Objective update uses Cayley/Hughes–Winget rotation from `W = skew(L)`.
4) Mean stress sign convention: tension-positive `m`, compression-positive pressure `p=-m`.