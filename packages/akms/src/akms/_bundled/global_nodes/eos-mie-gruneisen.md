---
id: eos-mie-gruneisen
title: Mie-Gruneisen EOS
domain: computational-mechanics
subdomain: eos
tags:
- eos
- mie-gruneisen
- hugoniot
- shock-physics
- gruneisen-parameter
status: established
confidence: 0.9
source: hybrid
edges:
- to: eos-overview
  type: requires
  weight: 1.0
- to: eos-polynomial
  type: refines
  weight: 0.8
- to: damage-spall
  type: feeds-into
  weight: 0.9
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Mie-Gruneisen EOS

## Summary

Equation of state (EOS) formulations in shock physics and solid dynamics model pressure, volumetric deformation, and internal energy coupling within inelastic thermodynamic frameworks.

## 1. Core Concept

In high-velocity impact and shock-physics simulations, an Equation of State (EOS) defines the thermodynamic relationship between hydrostatic pressure, volumetric strain J = det(F_e), temperature, and internal energy density. In inelastic equation of state (IEOS) frameworks, thermodynamic potentials partition internal energy into cold compression energy E_c(J), thermal lattice energy E_l(J, T), and elastic shear strain energy. Hydrocodes compute updated pressure, temperature, and Cauchy stress by enforcing internal energy conservation alongside elastoplastic return mapping and damage degradation.

## 2. Mathematical Formulation

**Inelastic Equation of State Internal Energy Decomposition**
$$
E(\bm{\varepsilon}^e, D, T) = E_c(J) + E_l(J, T) + (1 - D) \Psi_{iso}(\bm{\varepsilon}^e_{dev})
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 309, 310_

**Damage-Degraded Helmholtz Energy and Cauchy Stress Relation**
$$
\bm{\sigma} = J^{-1} \frac{\partial \tilde{\Psi}(\bm{\varepsilon}^e, D, T)}{\partial \bm{\varepsilon}^e}
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 310, 312_

**Pressure-Dependent Bulk Modulus (Murnaghan EOS)**
$$
B(p) = B_0 + B_0' p \quad \text{or} \quad \kappa(p) = \kappa_0 + n_0 p
$$
_Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 8; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231_

**Nonlinear Energy Balance Consistency Condition**
$$
E_{n+1} - \tilde{E}(\bm{\varepsilon}^e_{n+1}, D_{n+1}, T_{n+1}) = 0
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 312, 314_

**Notation:**
E: specific internal energy density; E_c(J): cold compression energy function; E_l(J, T): thermal energy function; J: elastic volumetric ratio \det(\mathbf{F}^e); \bm{\varepsilon}^e: logarithmic elastic strain tensor; D: scalar damage variable (0 \le D \le 1); \tilde{\Psi}: Helmholtz free energy density potential; \bm{\sigma}: Cauchy stress tensor; B(p), \kappa(p): pressure-dependent bulk modulus; B_0, \kappa_0: initial bulk modulus; B_0', n_0: pressure derivative parameters; p: hydrostatic pressure; T: absolute temperature.


## 3. Algorithmic Implementation

**Inelastic Equation of State Hydrocode Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: elastic strain } \bm{\varepsilon}^e_n, \text{ internal energy } E_n, \text{ temperature } T_n, \text{ damage } D_n, \text{ and total strain increment } \Delta \bm{\varepsilon}$
\State $\text{Compute trial elastic strain } \bm{\varepsilon}^{e,tr} = \bm{\varepsilon}^e_n + \Delta \bm{\varepsilon} \text{ and trial volumetric Jacobian } J^{tr} = \exp(\mathrm{tr}(\bm{\varepsilon}^{e,tr}))$
\State $\text{Evaluate cold pressure and thermal energy: } p^{c,tr} = p_c(J^{tr}), \quad E_c^{tr} = E_c(J^{tr})$
\State $\text{Compute trial Kirchhoff stress } \bm{\tau}^{tr} = \frac{\partial \tilde{\Psi}}{\partial \bm{\varepsilon}^{e,tr}} \text{ and yield function } \tilde{F}^{tr}(\bm{\tau}^{tr}, D_n, T_n)$
\If{$\tilde{F}^{tr} \le 0$}
\State $\bm{\sigma}_{n+1} = (J^{tr})^{-1} \bm{\tau}^{tr}, \quad E_{n+1} = E^{tr}, \quad T_{n+1} = T_n$
\Return $\text{Step is elastic; accept trial EOS state}$
\Else
\EndIf
\State $\text{Enforce internal energy balance residual } R_E = E_{n+1} - \tilde{E}(\bm{\varepsilon}^e_{n+1}, D_{n+1}, T_{n+1}) = 0$
\State $\text{Update Cauchy stress: } \bm{\sigma}_{n+1} = J_{n+1}^{-1} \frac{\partial \tilde{\Psi}}{\partial \bm{\varepsilon}^e_{n+1}}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ temperature } T_{n+1}, \text{ and internal energy } E_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 312-316_


## 4. Known Pitfalls

- **Decoupling Hydrostatic Pressure EOS from Inelastic Shear Degradation**: Evaluating hydrostatic pressure from an uncoupled EOS while computing shear stress from an independent plastic-damage routine creates thermodynamic inconsistencies, overestimating energy dissipation during dynamic shock loading. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 285, 310)_
- **Ignoring Pressure Stiffening of Bulk Modulus Under Multi-Gigapascal Compression**: Assuming a constant elastic bulk modulus B_0 under large volumetric shocks miscalculates wave propagation speeds and shock arrival times; pressure-dependent EOS models (e.g., Murnaghan B(p) = B_0 + B_0' p) are required. _(Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 8; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231)_
- **Unphysical Energy Generation in Uncoupled Thermal Expansion Updates**: Updating temperature and thermal energy independently of mechanical work balance violates the first law of thermodynamics, introducing spurious energy generation during thermo-mechanical return mapping. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 312, 314)_

## References

- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
