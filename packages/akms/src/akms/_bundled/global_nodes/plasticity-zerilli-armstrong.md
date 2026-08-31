---
id: plasticity-zerilli-armstrong
title: Zerilli-Armstrong Model
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- zerilli-armstrong
- dislocation-mechanics
- rate-dependent
- bcc-fcc
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-johnson-cook
  type: contradicts
  weight: 0.6
- to: plasticity-isotropic-hardening
  type: refines
  weight: 0.6
- to: plasticity-von-mises
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Zerilli-Armstrong Model

## Summary

Rate-dependent constitutive formulations model flow stress as a function of plastic strain, strain rate, and temperature in dynamic inelasticity.

## 1. Core Concept

In dynamic impact and high-strain-rate metal plasticity, flow stress exhibits strong sensitivity to strain rate and thermal softening. Rate-dependent constitutive models represent flow stress Y(\bar{\varepsilon}, \dot{\bar{\varepsilon}}, T) as a function of equivalent plastic strain \bar{\varepsilon}, plastic strain rate \dot{\bar{\varepsilon}}, and temperature T. Integrated within finite-strain multiplicative elastoplasticity (\mathbf{F} = \mathbf{F}^e \mathbf{F}^p) or inelastic equation of state (IEOS) frameworks, rate-dependent flow stress laws govern plastic dissipation, dynamic return mapping, and thermal softening under high-velocity loading.

## 2. Mathematical Formulation

**Rate-Dependent Flow Stress Functional Form**
$$
Y(\bar{\varepsilon}, \dot{\bar{\varepsilon}}, T) = Y_0(\bar{\varepsilon}) \cdot g_r(\dot{\bar{\varepsilon}}) \cdot g_t(T)
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 198_

**Finite-Strain Rate-Dependent Yield Condition**
$$
F(\bm{\tau}, \bar{\varepsilon}, T) = \bar{\tau} - Y(\bar{\varepsilon}, \dot{\bar{\varepsilon}}, T) = 0
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 278, 281_

**Rate-Dependent Plastic Multiplier Evolution**
$$
\dot{\bar{\varepsilon}} = \dot{\lambda}, \quad \dot{\mathbf{F}}^p = \dot{\lambda} \mathbf{R}_e^T \cdot \frac{\partial F}{\partial \bm{\tau}} \cdot \mathbf{R}_e \cdot \mathbf{F}^p
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 276, 278_

**Notation:**
Y: rate-dependent flow stress; Y_0: static strain-hardening stress; g_r: strain rate sensitivity function; g_t: thermal softening function; \bar{\varepsilon}: equivalent plastic strain; \dot{\bar{\varepsilon}}: equivalent plastic strain rate; T: absolute temperature; \bm{\tau}: Kirchhoff stress tensor; \bar{\tau}: equivalent von Mises Kirchhoff stress; F: yield function; \mathbf{F}^p: plastic deformation gradient tensor; \mathbf{R}_e: elastic rotation tensor; \dot{\lambda}: plastic consistency parameter rate.


## 3. Algorithmic Implementation

**Rate-Dependent Flow Stress Return-Mapping Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: elastic strain } \bm{\varepsilon}^e_n, \text{ plastic strain } \bar{\varepsilon}_n, \text{ temperature } T_n, \text{ and total strain increment } \Delta \bm{\varepsilon}$
\State $\bm{\varepsilon}^{e,tr} = \bm{\varepsilon}^e_n + \Delta \bm{\varepsilon}, \quad \bm{\tau}^{tr} = \mathbf{D}^e : \bm{\varepsilon}^{e,tr}, \quad \bar{\tau}^{tr} = \sqrt{\frac{3}{2}\bm{s}^{tr}:\bm{s}^{tr}}$
\State $Y^{tr} = Y\left(\bar{\varepsilon}_n, \frac{\Delta \bar{\varepsilon}}{\Delta t}, T_n\right), \quad F^{tr} = \bar{\tau}^{tr} - Y^{tr}$
\If{$F^{tr} \le 0$}
\State $\bm{\sigma}_{n+1} = J^{-1} \bm{\tau}^{tr}, \quad \bar{\varepsilon}_{n+1} = \bar{\varepsilon}_n, \quad T_{n+1} = T_n$
\Return $\text{Step is elastic; accept trial state}$
\Else
\EndIf
\State $\bar{\varepsilon}_{n+1} = \bar{\varepsilon}_n + \Delta \lambda, \quad \bm{\varepsilon}^e_{n+1} = \bm{\varepsilon}^{e,tr} - \Delta \lambda \mathbf{N}_{n+1}, \quad \bm{\sigma}_{n+1} = J_{n+1}^{-1} \bm{\tau}_{n+1}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ plastic strain } \bar{\varepsilon}_{n+1}, \text{ and temperature } T_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 278, 283-285; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 198_


## 4. Known Pitfalls

- **Singularity at Low Strain Rates in Logarithmic Rate Formulations**: Evaluating rate-dependent flow stress models with logarithmic rate terms as plastic strain rate approaches zero (\dot{\bar{\varepsilon}} \to 0) produces minus infinity numerical singularities unless bounded by a reference rate floor. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 198)_
- **Neglecting Thermal Softening at Elevated Temperatures**: Omitted thermal softening terms in rate-dependent flow stress functions underpredicts thermal softening during adiabatic plastic heating, causing artificial overestimation of stress levels. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277, 280; Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 8)_
- **Thermodynamic Inconsistency in Uncoupled Pressure-Flow Stress Integration**: Evaluating hydrostatic pressure from an uncoupled EOS while applying rate-dependent flow stress models to deviatoric stress updates violates thermodynamic energy balance during thermo-mechanical return mapping. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 280, 284)_

## References

- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
