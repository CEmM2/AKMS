---
id: eos-polynomial
title: Polynomial & Tabulated EOS
domain: computational-mechanics
subdomain: eos
tags:
- eos
- polynomial
- sesame
- tabulated
- high-pressure
status: established
confidence: 0.9
source: hybrid
edges:
- to: eos-overview
  type: requires
  weight: 1.0
- to: eos-mie-gruneisen
  type: refines
  weight: 0.7
- to: damage-spall
  type: feeds-into
  weight: 0.8
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Polynomial & Tabulated EOS

## Summary

Polynomial and tabulated equation of state (EOS) formulations relate hydrostatic pressure, internal energy, and volumetric deformation through empirical curve-fits, logarithmic strain expansions, or tabular material lookups.

## 1. Core Concept

Polynomial and tabulated equations of state (EOS) serve as constitutive models for hydrostatic response under extreme high-pressure dynamic loading. In classical shock hydrocodes, tabular EOS formulations store pre-computed thermodynamic states, interpolating pressure and temperature as functions of density and internal energy. Alternatively, analytic non-linear EOS models represent volumetric stored energy through polynomial expansions in volumetric logarithmic strain or compression measures, such as Murnaghan pressure functions p(J) = (B_0/B_0')(J^{-B_0'} - 1). Within unified Inelastic Equation of State (IEOS) frameworks, tabulated and polynomial cold curves combine with thermal lattice potentials and damage-degraded hyperelastic shear potentials to maintain thermodynamic consistency.

## 2. Mathematical Formulation

**Polynomial Volumetric Energy Expansion in Logarithmic Strain**
$$
W_V(J_E) = \frac{1}{2} B_0 (\ln J_E)^2 \left[ 1 - \frac{1}{3}(B_0' - 2) \ln J_E \right]
$$
_Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 8_

**Non-Linear Murnaghan Pressure-Volume Relation**
$$
p(J) = \frac{B_0}{B_0'}\left[ J^{-B_0'} - 1 \right]
$$
_Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 8; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231_

**Tabular Internal Energy Potential Coupling in IEOS**
$$
E(\bm{\varepsilon}^e, D, T) = E_c(J) + E_l(J, T) + (1 - D) \Psi_{iso}(\bm{\varepsilon}^e_{dev})
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 309, 310_

**Cauchy Stress Tensor from Polynomial Energy Potential**
$$
\bm{\sigma} = J^{-1} \frac{\partial \tilde{\Psi}(\bm{\varepsilon}^e, D, T)}{\partial \bm{\varepsilon}^e}
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 310, 312_

**Notation:**
W_V: volumetric elastic strain energy density; B_0: initial bulk modulus; B_0': dimensionless pressure derivative of bulk modulus; J, J_E: elastic volumetric Jacobian ratio \det(\mathbf{F}^e); p: hydrostatic pressure (-1/3 tr(\bm{\sigma})); E: specific internal energy density; E_c(J): cold compression energy function; E_l(J, T): thermal lattice energy function; D: scalar damage parameter; \Psi_{iso}: isochoric hyperelastic strain energy; \bm{\sigma}: Cauchy stress tensor; \bm{\varepsilon}^e: logarithmic elastic strain tensor; \tilde{\Psi}: unified Helmholtz free energy density.


## 3. Algorithmic Implementation

**Polynomial and Tabulated Inelastic Equation of State Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: elastic strain } \bm{\varepsilon}^e_n, \text{ internal energy } E_n, \text{ temperature } T_n, \text{ damage } D_n, \text{ and strain increment } \Delta \bm{\varepsilon}$
\State $\bm{\varepsilon}^{e,tr} = \bm{\varepsilon}^e_n + \Delta \bm{\varepsilon}, \quad J^{tr} = \exp(\mathrm{tr}(\bm{\varepsilon}^{e,tr}))$
\If{$\text{Material model uses tabular EOS look-up}$}
\State $p^{c,tr} = \text{TableLookup}(J^{tr}), \quad E_c^{tr} = \text{TableLookup}(J^{tr})$
\Else
\EndIf
\State $\bm{\tau}^{tr} = \frac{\partial \tilde{\Psi}}{\partial \bm{\varepsilon}^{e,tr}}, \quad \tilde{F}^{tr} = \bar{\tau}^{tr} - (1 - D_n) Y(\bar{\varepsilon}_n, T_n)$
\If{$\tilde{F}^{tr} \le 0$}
\State $\bm{\sigma}_{n+1} = (J^{tr})^{-1} \bm{\tau}^{tr}, \quad E_{n+1} = E^{tr}, \quad T_{n+1} = T_n$
\Return $\text{Step is elastic; accept trial state}$
\Else
\EndIf
\State $\bm{\sigma}_{n+1} = J_{n+1}^{-1} \frac{\partial \tilde{\Psi}(\bm{\varepsilon}^e_{n+1}, D_{n+1}, T_{n+1})}{\partial \bm{\varepsilon}^e_{n+1}}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ internal energy } E_{n+1}, \text{ and temperature } T_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 312-316; Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 8_


## 4. Known Pitfalls

- **Thermodynamic Discontinuity from Uncoupled Tabular Pressure Modification**: Evaluating hydrostatic pressure from an uncoupled tabular EOS while computing deviatoric stress independently introduces artificial stress modifications that violate thermodynamic energy balance during dynamic plastic deformation. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 276, 280)_
- **Underpredicting Bulk Stiffening Under Severe Shock Compression**: Truncating polynomial energy expansions to linear terms (constant bulk modulus B_0) underestimates wave speeds and miscalculates shock arrival times under multi-gigapascal compression; non-linear pressure derivatives B_0' are required. _(Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 8; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231)_
- **Spurious Energy Residuals in Tabular Temperature Lookups**: Updating temperature from uncoupled tabular EOS routines without enforcing internal energy conservation creates numerical energy residuals during coupled thermo-mechanical return mapping. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 312, 314)_

## References

- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
