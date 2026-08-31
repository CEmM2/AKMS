---
id: thermal-coupled-mechanics
title: Thermo-Mechanical Coupling
domain: computational-mechanics
subdomain: thermal
tags:
- thermal
- coupling
- heat-equation
- staggered
- monolithic
status: established
confidence: 0.9
source: hybrid
edges:
- to: thermal-softening
  type: requires
  weight: 1.0
- to: constit-thermodynamic-framework
  type: requires
  weight: 1.0
- to: fem-newton-raphson
  type: feeds-into
  weight: 0.9
- to: thermal-adiabatic-shear
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Thermo-Mechanical Coupling

## Summary

Thermo-mechanical coupling formulates the dynamic interaction between mechanical deformation, plastic strain energy dissipation, thermal expansion, and heat conduction in inelastic solids.

## 1. Core Concept

Thermo-mechanical coupling governs the bidirectional interaction between mechanical strain and thermal energy fields in solid continuum mechanics. Plastic deformation converts mechanical work into heat through the Taylor-Quinney dissipation factor \chi (or \beta_0), generating a thermal heat source \chi W_p that elevates temperature T according to heat conduction principles \rho c_V \dot{T} = \chi W_p + \kappa \nabla^2 T. Thermally induced temperature changes feed back into the mechanical field via volumetric thermal expansion strain \dot{\bm{\varepsilon}}_t = \alpha \dot{T} \mathbf{I} and temperature-dependent flow stress softening. Computational solution frameworks utilize staggered operator-split schemes or coupled internal energy balance equations E_{n+1} - \tilde{E}(\bm{\varepsilon}^e_{n+1}, D_{n+1}, T_{n+1}) = 0 to integrate thermo-mechanical return mapping over discrete time steps.

## 2. Mathematical Formulation

**Coupled Heat Conduction Energy Equation**
$$
\rho \hat{c} \dot{T} = \chi W_p + \kappa \nabla^2 T, \quad W_p = \bm{\sigma} : \dot{\bm{\varepsilon}}^p
$$
_Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 280; Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 7_

**Isotropic Thermal Expansion Strain Rate**
$$
\dot{\bm{\varepsilon}}_t = \alpha \dot{T} \mathbf{I}
$$
_Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 280_

**Internal Energy Balance Equation in IEOS Framework**
$$
E_{n+1} - \tilde{E}(\bm{\varepsilon}^e_{n+1}, D_{n+1}, T_{n+1}) = 0
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 287, 288_

**Thermo-Mechanical Stress Return Mapping**
$$
\bm{\sigma}_{n+1} = J_{n+1}^{-1} \frac{\partial \tilde{\Psi}(\bm{\varepsilon}^e_{n+1}, D_{n+1}, T_{n+1})}{\partial \bm{\varepsilon}^e_{n+1}}
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 285, 288_

**Notation:**
\rho: material density; \hat{c}, c_V: specific heat capacity; T: absolute temperature; \chi, \beta_0: Taylor-Quinney conversion parameter; W_p: plastic dissipation work rate; \kappa: thermal conductivity; \alpha: thermal expansion coefficient; \bm{\varepsilon}_t: thermal strain tensor; \mathbf{I}: identity tensor; E: specific internal energy; \tilde{E}: Helmholtz/internal energy potential; D: damage variable; \bm{\sigma}: Cauchy stress tensor; \bm{\varepsilon}^e: elastic logarithmic strain tensor.


## 3. Algorithmic Implementation

**Staggered Thermo-Mechanical Solution Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: displacement } \mathbf{u}_n, \text{ temperature } T_n, \text{ plastic strain } \bm{\varepsilon}^p_n, \text{ damage } D_n, \text{ and strain increment } \Delta \bm{\varepsilon}$
\State $\Delta \bm{\varepsilon}_t = \alpha (T_n - T_{n-1}) \mathbf{I}, \quad \Delta \bm{\varepsilon}_e = \Delta \bm{\varepsilon} - \Delta \bm{\varepsilon}_t$
\State $\bm{\sigma}^{\mathrm{tr}} = \bm{\sigma}_n + \mathbf{D}^e : \Delta \bm{\varepsilon}_e, \quad F^{\mathrm{tr}} = F(\bm{\sigma}^{\mathrm{tr}}, \bar{\varepsilon}_n, T_n)$
\If{$F^{\mathrm{tr}} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}}, \quad \Delta W_p = 0$
\Else
\State $\Delta W_p = \bm{\sigma}_{n+1} : \Delta \bm{\varepsilon}^p_{n+1}$
\EndIf
\State $\text{Solve thermal heat equation residual } R_T = \rho \hat{c} \frac{T_{n+1} - T_n}{\Delta t} - \frac{\chi \Delta W_p}{\Delta t} - \kappa \nabla^2 T_{n+1} = 0 \text{ for } T_{n+1}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ temperature } T_{n+1}, \text{ and plastic work } W_p$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf Algorithm 1, p. 280-281; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 228_


## 4. Known Pitfalls

- **Unphysical Thermal Softening Extrapolation Above Melting Point**: Evaluating temperature-dependent yield stress functions at temperatures T approaching or exceeding the melting temperature T_m without bounding thermal softening causes flow stress to become negative or singular. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277; Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 30)_
- **Energy Residual Accumulation in Staggered Thermo-Mechanical Solvers**: Updating temperature T independently from stress return mapping without enforcing unified internal energy balance E_{n+1} - \tilde{E} = 0 accumulates numerical energy residuals during dynamic impact simulations. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 280, 284, 287)_

## References

- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
