---
id: composite-progressive-damage
title: Progressive Damage in Composite Plies
domain: computational-mechanics
subdomain: composites
tags:
- composites
- progressive-damage
- MPDM
- CDM
- mesh-regularization
status: established
confidence: 0.9
source: hybrid
edges:
- to: composite-failure-criteria
  type: requires
  weight: 1.0
- to: composite-laminate-theory
  type: requires
  weight: 1.0
- to: damage-continuum-framework
  type: refines
  weight: 0.7
- to: damage-nonlocal-gradient
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Progressive Damage in Composite Plies

## Summary

Progressive damage in composite plies characterizes the non-linear degradation of constituent elastic stiffness due to gradually accumulated microcracks, fiber-matrix debonding, and fiber breakage. Rather than assuming abrupt zeroing of moduli (ply-discount models), continuum damage mechanics (CDM) and variational phase-field frameworks model continuous material softening. In multiscale thermoelastic formulations, matrix microcracking is governed by hydrostatic stress/strain thresholds and driven by thermal CTE mismatches during manufacturing cool-down, scaling the elastic stiffness matrix via a scalar damage parameter. On the lamina level, regularized diffusive phase-field models describe crack nucleation and growth across length scales by decomposing strain energy into mode-specific components (fiber failure, matrix cracking, and longitudinal/transverse shear) and enforcing damage irreversibility using historical strain energy fields.

## 1. Core Concept

Progressive damage models capture post-initiation material degradation across microstructural and continuum length scales. In multiscale constituent frameworks, quasi-brittle matrix subcells undergo progressive degradation governed by hydrostatic equivalent stress and strain invariants. Once equivalent hydrostatic stress exceeds a temperature- and strain-rate-dependent threshold, a scalar damage parameter scales the elastic stiffness tensor, allowing subcells to continue carrying load during microcrack evolution. Thermal residual stresses from post-manufacturing cool-down initiate microcracking prior to mechanical loading, reducing initial laminate tensile modulus by over 25%.

In regularized phase-field fracture, progressive damage is modeled diffusively using an auxiliary phase-field variable ranging from intact to fully broken states over an internal length scale. Irreversibility is guaranteed by tracking the maximum historical strain energy density. To capture strong anisotropic failure behavior in unidirectional plies, strain energy is decomposed into constituent mode-specific components governing fiber breakage, matrix cracking, in-plane shear, and transverse shear, preventing unphysical damage coupling.

## 2. Mathematical Formulation

**Thermoelastic Continuum Damage Constitutive Relation**
$$
\sigma = (1 - \phi) C (\epsilon - \alpha \Delta T) = (1 - \phi) C \epsilon^e
$$
_Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 2.2, Eq. 2_

**Incremental Matrix Damage Evolution Law**
$$
d k_{n+1} = \frac{n \, dK_0(T_{n+1}) \left[ e^n_{\text{eq}} - \alpha_0(T_n) \Delta T_n \right] + K_0(T_n) \left[ d e^{n+1}_{\text{eq}} - \alpha_0(T_n) d\Delta T_{n+1} - d\alpha_0(T_{n+1}) \Delta T_n \right] - k_n K_0(T_n) \left[ d e^{n+1}_{\text{eq}} - \alpha_0(T_n) d\Delta T_{n+1} - d\alpha_0(T_{n+1}) \Delta T_n \right]}{K_0(T_n) \left[ e^n_{\text{eq}} - \alpha_0(T_n) \Delta T_n \right]}
$$
_Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 2.2, Eq. 17_

**Phase-Field Diffusive Damage Evolution with Viscous Regularization**
$$
2 (1 - d) H - G_c \left( \frac{d}{l_0} - l_0 \Delta d \right) = \eta \dot{d}
$$
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 2.3, Eq. 40_

**Mode-Specific Anisotropic Energy Decomposition for Composite Plies**
$$
\psi_{11} = \frac{\langle \tilde{\sigma}_L \rangle_+^2}{2 E_{11}}, \quad \psi_{22} = \frac{\langle \tilde{p}_T \rangle_+^2}{2 E_T}, \quad \psi_{12} = \frac{\tilde{\tau}_L^2}{2 G_{12}}, \quad \psi_{23} = \frac{\tilde{\tau}_T^2}{2 G_T}
$$
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.6, Eqs. 126-129_

**Notation:**
- \sigma: Second-order Cauchy stress tensor
- \epsilon, \epsilon^e: Total strain tensor and elastic strain tensor
- \phi: Scalar damage variable scaling matrix stiffness (0 <= \phi <= 1)
- k: Residual stiffness factor (k = 1 - \phi)
- C: Fourth-order linear elastic stiffness tensor
- \alpha, \alpha_0: Coefficient of thermal expansion tensor and matrix CTE
- \Delta T: Temperature differential relative to stress-free manufacturing state
- e_{\text{eq}}: Hydrostatic equivalent strain invariant
- K_0: Undamaged bulk modulus
- n: Damaged normalized secant modulus parameter
- d: Phase-field damage variable ranging from 0 (intact) to 1 (fully degraded)
- H: Historical driving strain energy density enforcing damage irreversibility
- G_c: Critical strain energy release rate
- l_0: Internal length scale parameter controlling diffusive crack width
- \eta: Viscous regularization parameter
- \psi_{11}, \psi_{22}, \psi_{12}, \psi_{23}: Strain energy components corresponding to constituent failure modes


## 3. Algorithmic Implementation

**UpdateThermoelasticMatrixDamage**
$$
\begin{algorithmic}
\State $e^n_{\text{eq}} = \text{ComputeHydrostaticStrain}(\epsilon_n)$
\State $r^n_{\text{eq}} = 3 k_n K_0(T_n) \left[ e^n_{\text{eq}} - \alpha_0(T_n) \Delta T_n \right]$
\If{$r^n_{\text{eq}} \ge r_{\text{crit}}(T_n)$}
\State $d e^{n+1}_{\text{eq}} = e^{n+1}_{\text{eq}} - e^n_{\text{eq}}$
\State $d k_{n+1} = \frac{n \, dK_0(T_{n+1}) \left[ e^n_{\text{eq}} - \alpha_0(T_n) \Delta T_n \right] + K_0(T_n) \left[ d e^{n+1}_{\text{eq}} - \alpha_0 d\Delta T_{n+1} \right] - k_n K_0(T_n) \left[ d e^{n+1}_{\text{eq}} - \alpha_0 d\Delta T_{n+1} \right]}{K_0(T_n) \left[ e^n_{\text{eq}} - \alpha_0(T_n) \Delta T_n \right]}$
\State $k_{n+1} = k_n + d k_{n+1}$
\State $\phi_{n+1} = 1.0 - k_{n+1}$
\Else
\State $\phi_{n+1} = \phi_n$
\EndIf
\State $\sigma_{n+1} = (1.0 - \phi_{n+1}) C(T_{n+1}) (\epsilon_{n+1} - \alpha_0 \Delta T_{n+1})$
\Return $\sigma_{n+1}, \phi_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 2.2, Eqs. 2, 17_

**ExplicitPhaseFieldDamageUpdate**
$$
\begin{algorithmic}
\State $\psi_+ = \text{ComputeTensileStrainEnergy}(\epsilon_n)$
\State $H_{n+1} = \max\left(H_n, \, \psi_+\right)$
\State $Y = -2 (1 - d_n) H_{n+1} N^d - \frac{G_c}{c_0} \left[ \frac{\alpha'(d_n)}{l_0} N^d + 2 l_0 B^d \nabla d_n \right]$
\State $\dot{d}_{n+1} = \frac{Y}{\eta}$
\State $d_{n+1} = d_n + \Delta t \cdot \dot{d}_{n+1}$
\If{$d_{n+1} > 1.0$}
\State $d_{n+1} = 1.0$
\EndIf
\Return $d_{n+1}, H_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 2.3 & 2.6, Eqs. 40, 56, 61_


## 4. Known Pitfalls

- **ignoring-thermal-cooling-damage-overestimates-stiffness**: Neglecting progressive matrix microcracking during manufacturing thermal cool-down leads to overestimating initial tensile stiffness of composite laminates by at least 25%. _(Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 3)_
- **artificial-viscosity-oversmoothing-dynamic-crack**: In rate-dependent viscous phase-field formulations, choosing an excessively large artificial viscosity parameter eta to stabilize time integration over-damps crack evolution, widening the degraded process zone beyond physical bounds during dynamic crack growth. _(Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 2.3)_
- **uncoupled-fiber-matrix-anisotropic-phasefield-inaccuracy**: In homogenized lamina phase-field models, failing to separate fiber and matrix strain energy contributions into distinct mode-specific degradation functions results in unphysical coupling of fiber breakage and matrix cracking, leading to inaccurate crack path predictions. _(Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.1.2 & 3.6)_

## References

- Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf
- Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf
- Cumbo et al_2022_Design allowables of composite laminates.pdf
