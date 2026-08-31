---
id: thermal-softening
title: Thermal Softening in Constitutive Models
domain: computational-mechanics
subdomain: thermal
tags:
- thermal
- softening
- taylor-quinney
- dynamic-plasticity
- johnson-cook
status: established
confidence: 0.9
source: hybrid
edges:
- to: constit-thermodynamic-framework
  type: requires
  weight: 0.9
- to: plasticity-johnson-cook
  type: feeds-into
  weight: 1.0
- to: thermal-coupled-mechanics
  type: feeds-into
  weight: 1.0
- to: thermal-adiabatic-shear
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Thermal Softening in Constitutive Models

## Summary

Thermal softening reduces material flow stress as temperature increases due to plastic work dissipation or thermal environmental loading.

## 1. Core Concept

Thermal softening represents the degradation of material flow stress caused by increasing temperature in dynamic plasticity and thermoplasticity. Under high-strain-rate adiabatic deformation, mechanical plastic work is converted into heat via the Taylor-Quinney coefficient \beta_0, raising temperature according to c_V \dot{T} = \beta_0 \bm{\sigma} : \dot{\bm{\varepsilon}}^p. This temperature rise competes against strain and strain-rate hardening. Standard constitutive models capture thermal softening using power-law functions [\theta / \theta_0]^\nu (\nu < 0) or homologous temperature functions [1 - (\theta(T))^m], where \theta(T) = (T - T_r)/(T_m - T_r).

## 2. Mathematical Formulation

**Power-Law Thermal Softening Flow Stress**
$$
Y(\gamma, \theta, \dot{\gamma}) = g_0 \left( 1 + \frac{\gamma}{\gamma_0} \right)^n \left[ \frac{\theta}{\theta_0} \right]^\nu \left[ \frac{\dot{\gamma}}{\dot{\gamma}_0} \right]^m
$$
_Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 18_

**Homologous Temperature Thermal Softening Function**
$$
g_t(T) = 1 - \left( \theta(T) \right)^m, \quad \theta(T) = \frac{T - T_r}{T_m - T_r}
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 198_

**Adiabatic Plastic Heat Generation Rate Equation**
$$
c_V \dot{T} = \beta_0 \bm{\sigma} : \dot{\bm{\varepsilon}}^p
$$
_Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 7; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 280_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; \dot{\bm{\varepsilon}}^p: plastic strain rate tensor; Y: flow stress; g_0: initial yield stress; \gamma: plastic shear strain; \dot{\gamma}: shear strain rate; \theta, T: absolute temperature; T_r: reference room temperature; T_m: melting temperature; \theta(T): homologous temperature; \nu: power-law thermal softening exponent; m: thermal softening exponent; c_V: volumetric heat capacity; \beta_0: Taylor-Quinney dissipation coefficient.


## 3. Algorithmic Implementation

**Adiabatic Thermal Softening and Temperature Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: stress } \bm{\sigma}_n, \text{ plastic strain } \bar{\varepsilon}_n, \text{ temperature } T_n, \text{ strain increment } \Delta \bm{\varepsilon}, \text{ and heat capacity } c_V$
\State $\theta_n = \frac{T_n - T_r}{T_m - T_r}, \quad Y_n = Y_0(\bar{\varepsilon}_n, \dot{\bar{\varepsilon}}_n) \left[ 1 - \theta_n^m \right]$
\State $\bm{\sigma}^{\mathrm{tr}} = \bm{\sigma}_n + \mathbf{D}^e : \Delta \bm{\varepsilon}, \quad f^{\mathrm{tr}} = \bar{\sigma}^{\mathrm{tr}} - Y_n$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}}, \quad T_{n+1} = T_n, \quad \bar{\varepsilon}_{n+1} = \bar{\varepsilon}_n$
\Return $\text{Step is elastic; return trial state}$
\Else
\EndIf
\State $\Delta W_p = \bm{\sigma}_{n+1} : \Delta \bm{\varepsilon}^p_{n+1}$
\State $\Delta T = \frac{\beta_0 \Delta W_p}{c_V}, \quad T_{n+1} = T_n + \Delta T$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ plastic strain } \bar{\varepsilon}_{n+1}, \text{ and temperature } T_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 7, 18; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 280-281; Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277-278_


## 4. Known Pitfalls

- **Extrapolation Beyond Material Melting Temperature**: Evaluating thermal softening functions at temperatures T \ge T_m causes homologous temperature \theta \ge 1, driving flow stress to zero or negative unphysical values unless phase transformation latent heat absorption is enforced. _(Source: Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 30; Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277)_
- **Neglecting Thermal Heat Conduction in Quasi-Static Softening Regimes**: Assuming fully adiabatic conditions (\kappa = 0) during low-strain-rate deformation overpredicts temperature rise and thermal softening, underestimating material load capacity. _(Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 280; Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 7)_

## References

- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
