---
id: plasticity-johnson-cook
title: Johnson-Cook Model
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- johnson-cook
- rate-dependent
- thermal-softening
- dynamic
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-isotropic-hardening
  type: refines
  weight: 0.9
- to: plasticity-von-mises
  type: requires
  weight: 1.0
- to: constit-thermodynamic-framework
  type: requires
  weight: 0.8
- to: plasticity-zerilli-armstrong
  type: contradicts
  weight: 0.5
- to: plasticity-lode-triaxiality
  type: feeds-into
  weight: 0.8
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Johnson-Cook Model

## Summary

The Johnson-Cook constitutive model formulates rate- and temperature-dependent plastic flow stress using strain hardening, strain rate sensitivity, and thermal softening terms within finite-strain plasticity.

## 1. Core Concept

The Johnson-Cook model governs dynamic plasticity by expressing flow stress Y(\bar{\varepsilon}, \dot{\bar{\varepsilon}}, T) through multiplicative contributions accounting for isotropic strain hardening [A + B \bar{\varepsilon}^n], logarithmic strain rate sensitivity [1 + C \ln(\dot{\bar{\varepsilon}} / \dot{\varepsilon}_0)], and thermal softening [1 - \theta^m] based on homologous temperature \theta = (T - T_r) / (T_m - T_r). Integrated within finite-strain multiplicative elastoplasticity (\mathbf{F} = \mathbf{F}^e \mathbf{F}^p) or inelastic equation of state (IEOS) hydrocode frameworks, the Johnson-Cook yield criterion controls plastic dissipation under dynamic impact, shock loading, and thermomechanical deformation.

## 2. Mathematical Formulation

**Johnson-Cook Plastic Flow Stress Equation**
$$
Y(\bar{\varepsilon}, \dot{\bar{\varepsilon}}, T) = \left[ A + B \bar{\varepsilon}^n \right] \left[ 1 + C \ln\left( \frac{\dot{\bar{\varepsilon}}}{\dot{\varepsilon}_0} \right) \right] \left[ 1 - \left( \theta(T) \right)^m \right]
$$
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 198; Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277_

**Homologous Temperature Definition**
$$
\theta(T) = \frac{T - T_r}{T_m - T_r}
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 198_

**Finite-Strain Yield Consistency Condition**
$$
F(\bm{\tau}, \bar{\varepsilon}, T) = \bar{\tau} - Y(\bar{\varepsilon}, \dot{\bar{\varepsilon}}, T) = 0
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 278, 281_

**Plastic Evolution and Temperature Update**
$$
\dot{\mathbf{F}}^p = \dot{\lambda} \mathbf{R}_e^T \cdot \frac{\partial F}{\partial \bm{\tau}} \cdot \mathbf{R}_e \cdot \mathbf{F}^p, \quad \dot{\bar{\varepsilon}} = \dot{\lambda}
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 276, 278_

**Notation:**
Y: equivalent plastic flow stress; A: yield strength parameter; B: strain hardening coefficient; n: strain hardening exponent; C: strain rate sensitivity parameter; \dot{\bar{\varepsilon}}: equivalent plastic strain rate; \dot{\varepsilon}_0: reference strain rate; \theta(T): homologous temperature; T: temperature; T_r: reference room temperature; T_m: melting temperature; m: thermal softening exponent; \bm{\tau}: Kirchhoff stress tensor; \bar{\tau}: equivalent Kirchhoff stress; \bar{\varepsilon}: equivalent plastic strain history variable; \mathbf{F}^p: plastic deformation gradient.


## 3. Algorithmic Implementation

**Johnson-Cook Plasticity Return-Mapping Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: elastic strain } \bm{\varepsilon}^e_n, \text{ equivalent plastic strain } \bar{\varepsilon}_n, \text{ temperature } T_n, \text{ and deformation gradient increment } \mathbf{F}$
\State $\mathbf{F}^{e,tr} = \mathbf{F} \cdot \mathbf{F}^e_n, \quad \bm{\varepsilon}^{e,tr} = \frac{1}{2} \ln(\mathbf{F}^{e,tr} \cdot \mathbf{F}^{e,tr T}), \quad \bm{\tau}^{tr} = \frac{\partial \Psi}{\partial \bm{\varepsilon}^{e,tr}}$
\State $\theta_n = \frac{T_n - T_r}{T_m - T_r}, \quad Y_n = [A + B (\bar{\varepsilon}_n)^n]\left[1 + C \ln\left(\frac{\Delta \bar{\varepsilon}}{\Delta t \dot{\varepsilon}_0}\right)\right](1 - \theta_n^m)$
\State $F^{tr} = \bar{\tau}^{tr} - Y_n$
\If{$F^{tr} \le 0$}
\State $\bm{\sigma}_{n+1} = J^{-1} \bm{\tau}^{tr}, \quad \bar{\varepsilon}_{n+1} = \bar{\varepsilon}_n, \quad T_{n+1} = T_n$
\Return $\text{Step is elastic; accept trial state}$
\Else
\EndIf
\State $\Delta \bar{\varepsilon} = \Delta \lambda, \quad \bar{\varepsilon}_{n+1} = \bar{\varepsilon}_n + \Delta \bar{\varepsilon}$
\State $\bm{\varepsilon}^e_{n+1} = \bm{\varepsilon}^{e,tr} - \Delta \lambda \mathbf{N}_{n+1}, \quad \bm{\sigma}_{n+1} = J_{n+1}^{-1} \bm{\tau}_{n+1}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ plastic strain } \bar{\varepsilon}_{n+1}, \text{ and temperature } T_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 278, 283-285; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 198_


## 4. Known Pitfalls

- **Extrapolation to Temperatures Exceeding Material Melting Point**: Evaluating thermal softening (1 - \theta^m) when temperature T approaches or exceeds the melting temperature T_m causes homologous temperature \theta \ge 1, driving flow stress to zero or negative unphysical values unless bounded. _(Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 198; Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277)_
- **Singularity at Zero Plastic Strain Rates in Logarithmic Rate Sensitivity**: Evaluating the logarithmic rate sensitivity term \ln(\dot{\bar{\varepsilon}} / \dot{\varepsilon}_0) when plastic strain rate approaches zero (\dot{\bar{\varepsilon}} \to 0) produces minus infinity singularities; a reference floor or rate-independent fallback must be enforced. _(Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 198; Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 277)_
- **Thermodynamic Inconsistency in Uncoupled Equation of State Updates**: Evaluating hydrostatic pressure from an uncoupled EOS while using Johnson-Cook flow stress for deviatoric updates violates energy conservation during coupled thermo-mechanical return mapping. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 280, 284)_

## References

- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
