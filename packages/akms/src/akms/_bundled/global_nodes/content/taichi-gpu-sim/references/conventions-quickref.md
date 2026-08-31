# Conventions Quick Reference (Repo Truth)

This is the short list of conventions that generated code must follow. If anything conflicts, **this wins**.

---

## 1) Voigt conventions (2nd-order tensors)

### Tensorial Voigt order (unscaled shear)
All symmetric 3×3 tensors use **tensorial Voigt** ordering:

`v = [xx, yy, zz, xy, xz, yz]`

- Shears are **unscaled** (NOT engineering shear).
- Unpack restores symmetry by mirroring off-diagonals.

---

## 2) Mandel conventions (6×6 tangents)

We rotate 6×6 tangents via Mandel similarity transforms.

Define:
`P = diag([1, 1, 1, sqrt(2), sqrt(2), sqrt(2)])`

Mappings:
- `C_M = P * C_V * P^{-1}`
- `C_V = P^{-1} * C_M * P`

**Do not** rotate a 6×6 Voigt tangent using naive 3×3 operations.

---

## 3) Stress measures and signs

### Mean stress and pressure sign
- Mean stress (tension positive): `m = (1/3) tr(σ)`
- Pressure (compression positive): `p = -m`

### Deviatoric and von Mises
- `s = σ - m I`
- `σ_eq = sqrt( (3/2) * (s:s) )`

---

## 4) Objectivity (corotational / midpoint)

### Velocity gradient split
- `L = ∇ v`
- `D = sym(L) = 0.5 (L + L^T)`
- `W = skew(L) = 0.5 (L - L^T)`

### Hughes–Winget / Cayley incremental rotation
`R_delta = (I - (dt/2) W)^{-1} (I + (dt/2) W)`

Stress update:
- rotate into corotational frame
- integrate constitutive model there
- rotate back to spatial

---

## 5) `Stress_Update6` return contract

Constitutive update returns (corotational frame):
`(sigma_hat_np1, peeq_np1, peeqdot_np1, T_np1, vm_np1, dep)`

Where:
- `sigma_hat_np1` is Cauchy stress in corotational frame (tensorial Voigt)
- `vm_np1` is von Mises equivalent stress
- `dep` is plastic strain increment tensor (Voigt) or equivalent per implementation

---

## 6) PF degradation + EOS gate (when enabled)

Two scalars:
- `ws = ω_s(d_s)` applies to **deviatoric** response
- `wt = ω_t(d_t)` applies to **tensile-only** volumetric response

EOS mode reconstruction:
- `sigma = ws * s_dev - p_phys * I`
- EOS pressure convention: `p_EOS > 0` compression, `p_EOS < 0` tension
- tensile-only gate:
  `p_phys = (wt * H(-p_EOS) + H(p_EOS)) * p_EOS`

---

## 7) Hard “do not violate” rules

1) Voigt order is `[xx, yy, zz, xy, xz, yz]` with unscaled shears.
2) Pressure is compression-positive: `p = -mean(σ)`.
3) Objective stress update uses Hughes–Winget/Cayley rotation from `W = skew(L)`.
4) Tangent rotation uses Mandel-space similarity transforms, not naive methods.
5) EOS tensile-only degradation triggers when `p_EOS < 0`.