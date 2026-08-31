---
id: eos-overview
title: Equations of State for Solids
domain: computational-mechanics
subdomain: eos
tags:
- eos
- hugoniot
- shock-physics
- high-pressure
- dynamic-loading
status: established
confidence: 0.9
source: hybrid
edges:
- to: stress-cauchy-kirchhoff
  type: feeds-into
  weight: 1.0
- to: eos-mie-gruneisen
  type: feeds-into
  weight: 1.0
- to: eos-polynomial
  type: feeds-into
  weight: 1.0
- to: damage-spall
  type: feeds-into
  weight: 0.9
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Equations of State for Solids

## Summary

Equations of state (EOS) for solids establish thermodynamic relations between pressure, volumetric strain, internal energy, and temperature, unifying hydrodynamic response with solid strength in finite-strain computational physics.

## 1. Core Concept

Equations of State (EOS) for solids govern material behavior under volumetric compression and thermomechanical loading by relating hydrostatic pressure, volumetric Jacobian ratio J = det(F_e), temperature, and internal energy. Traditional shock hydrocodes utilize a combined model approach, evaluating an EOS for pressure and temperature alongside an independent solid mechanics constitutive model for deviatoric stress. However, this decoupling can predict inconsistent pressure values and violate thermodynamic consistency when coupled with damage or pressure-dependent yield. Inelastic Equation of State (IEOS) frameworks resolve these ambiguities by constructing a single unified thermodynamic potential, partitioning Helmholtz free energy or internal energy into cold isotherm compression, thermal lattice vibration, and damage-degraded hyperelastic shear components.

## 2. Mathematical Formulation

**Total Stress Volumetric-Deviatoric Decomposition**
$$
\bm{\sigma} = -p \mathbf{I} + \bm{s}, \quad p = -\frac{1}{3} \mathrm{tr}(\bm{\sigma})
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 276; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 19_

**Unified Inelastic Equation of State Helmholtz Potential**
$$
\tilde{\Psi}(\bm{\varepsilon}^e, D, T) = \Psi_c(J) + \Psi_l(J, T) + (1 - D) \Psi_{iso}(\bm{\varepsilon}^e_{dev})
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 309, 310_

**Cauchy Stress Tensor Derived from Inelastic Energy Potential**
$$
\bm{\sigma} = J^{-1} \frac{\partial \tilde{\Psi}(\bm{\varepsilon}^e, D, T)}{\partial \bm{\varepsilon}^e}
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 310, 312_

**Pressure-Dependent Bulk Response (Murnaghan Non-Linear Volume Relation)**
$$
B(p) = B_0 + B_0' p, \quad p(J) = \frac{B_0}{B_0'}\left[ J^{-B_0'} - 1 \right]
$$
_Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 8; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; p: hydrostatic pressure (-1/3 tr(\bm{\sigma})); \bm{s}: deviatoric Cauchy stress tensor; J: elastic volumetric Jacobian ratio \det(\mathbf{F}^e); \bm{\varepsilon}^e: logarithmic elastic strain tensor; D: scalar damage parameter (0 \le D \le 1); T: absolute temperature; \tilde{\Psi}: unified damage-degraded Helmholtz free energy density; \Psi_c: cold volumetric energy; \Psi_l: thermal lattice energy; \Psi_{iso}: isochoric hyperelastic strain energy density; B(p): pressure-dependent bulk modulus; B_0: initial bulk modulus; B_0': pressure derivative parameter of bulk modulus.


## 3. Algorithmic Implementation

**Unified Inelastic Equation of State (IEOS) Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: elastic deformation gradient } \mathbf{F}^e_n, \text{ internal energy } E_n, \text{ temperature } T_n, \text{ damage } D_n, \text{ and deformation gradient increment } \mathbf{F}$
\State $\mathbf{F}^e_{tr} = \mathbf{F} \cdot \mathbf{F}^e_n, \quad J_{tr} = \det(\mathbf{F}^e_{tr}), \quad \bm{\varepsilon}^{e,tr} = \frac{1}{2} \ln(\mathbf{F}^e_{tr} \cdot \mathbf{F}^{eT}_{tr})$
\State $\bm{\tau}^{tr} = \frac{\partial \tilde{\Psi}}{\partial \bm{\varepsilon}^{e,tr}}, \quad \bar{\tau}^{tr} = \sqrt{\frac{3}{2}\bm{s}^{tr}:\bm{s}^{tr}}$
\State $\tilde{F}^{tr} = \bar{\tau}^{tr} - (1 - D_n) Y(\bar{\varepsilon}_n, T_n)$
\If{$\tilde{F}^{tr} \le 0$}
\State $\bm{\sigma}_{n+1} = J_{tr}^{-1} \bm{\tau}^{tr}, \quad E_{n+1} = \tilde{E}(\bm{\varepsilon}^{e,tr}, D_n, T_n), \quad T_{n+1} = T_n$
\Return $\text{Step is elastic; accept trial IEOS state}$
\Else
\EndIf
\State $\bm{\varepsilon}^e_{n+1} = \bm{\varepsilon}^{e,tr} - \Delta \lambda \mathbf{n}_{n+1}, \quad \bar{\varepsilon}_{n+1} = \bar{\varepsilon}_n + \Delta \lambda$
\State $\bm{\sigma}_{n+1} = J_{n+1}^{-1} \frac{\partial \tilde{\Psi}(\bm{\varepsilon}^e_{n+1}, D_{n+1}, T_{n+1})}{\partial \bm{\varepsilon}^e_{n+1}}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ temperature } T_{n+1}, \text{ and internal energy } E_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 312-316_


## 4. Known Pitfalls

- **Thermodynamic Inconsistency in Uncoupled Combined Models**: Evaluating hydrostatic pressure from an independent equation of state (EOS) while computing deviatoric stress from a separate solid mechanics model predicts conflicting pressure values for a given deformation, introducing ad-hoc adjustments that violate energy conservation. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 276, 280)_
- **Neglecting Pressure Dependency of Bulk Modulus Under High Shock Pressures**: Assuming a constant bulk modulus B_0 under multi-gigapascal dynamic impact causes severe errors in shock wave speed and volumetric deformation; non-linear pressure-dependent volume relations (e.g., Murnaghan EOS B(p) = B_0 + B_0' p) are required. _(Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 8; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231)_
- **Unphysical Energy Residuals from Decoupling Damage from Thermal Potentials**: Applying scalar damage degradation to solid strength without coupling damage to the thermodynamic stored energy potentials creates unphysical energy generation during finite strain plasticity iterations. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 280, 312-314)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
