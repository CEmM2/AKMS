---
id: constit-elastic-predictor
title: Elastic Trial State Computation
domain: computational-mechanics
subdomain: constitutive
tags:
- constitutive
- elastic-predictor
- trial-stress
- plasticity
- return-mapping
status: established
confidence: 0.9
source: hybrid
edges:
- to: constit-stress-update-architecture
  type: requires
  weight: 1.0
- to: kinematics-multiplicative-decomp
  type: requires
  weight: 0.8
- to: plasticity-general-return-mapping
  type: feeds-into
  weight: 1.0
- to: plasticity-von-mises
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Elastic Trial State Computation

## Summary

Elastic trial state computation forms the operator-split prediction phase in elastoplastic state determination, freezing plastic flow to evaluate candidate stress and yield function admissibility.

## 1. Core Concept

The elastic predictor step freezes all plastic internal state variables and evaluates a trial stress state based on the assumption that the given strain increment is entirely elastic. In small-strain formulations, the elastic trial stress is computed from the linear elastic stiffness tensor and strain increment. In finite-strain multiplicative hyperelastic formulations, the elastic trial state is computed in the spatial configuration using the elastic left Cauchy-Green tensor and trial Kirchhoff stress. Evaluating the trial yield function against this elastic trial stress determines whether the material remains elastic or requires a plastic return-mapping correction.

## 2. Mathematical Formulation

**Infinitesimal Elastic Trial Stress**
$$
\bm{\sigma}^{tr} = \bm{\sigma}^n + \mathbf{D}^e : \Delta \bm{\varepsilon}
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 260, 271_

**Infinitesimal Trial Yield Function**
$$
f^{tr} = f(\bm{\sigma}^{tr}, \bm{q}_n) = \|\bm{s}^{tr} - \bm{\alpha}_n\| - \sqrt{\frac{2}{3}} \sigma_y(\bar{\varepsilon}^p_n)
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.2, p. 124_

**Finite-Strain Trial Elastic Left Cauchy-Green Tensor**
$$
\bm{b}_e^{tr} = \bm{f} \cdot \bm{b}_e^n \cdot \bm{f}^T
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 9.1, p. 320; Kim_FEA for Elastoplastic Problems.pdf p. 293, 294_

**Finite-Strain Trial Kirchhoff Stress**
$$
\bm{\tau}^{tr} = 2 \frac{\partial \Psi(\bm{b}_e^{tr})}{\partial \bm{b}_e^{tr}} \cdot \bm{b}_e^{tr} = p_{n+1}^{tr} J_{n+1} \mathbf{I} + \mu \mathrm{dev}(\bar{\bm{b}}_e^{tr})
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 318, 320_

**Notation:**
\bm{\sigma}^{tr}: elastic trial Cauchy stress tensor; \mathbf{D}^e: fourth-order elastic stiffness tensor; \Delta \bm{\varepsilon}: total incremental strain tensor; f^{tr}: trial yield function value; \bm{s}^{tr}: trial deviatoric stress tensor; \bm{\alpha}: back-stress tensor for kinematic hardening; \sigma_y: isotropic yield stress; \bar{\varepsilon}^p: equivalent plastic strain; \bm{b}_e: elastic left Cauchy-Green deformation tensor; \bm{f}: relative spatial deformation gradient increment; \bm{\tau}^{tr}: trial Kirchhoff stress tensor; \Psi: hyperelastic strain energy density function; J: determinant of the deformation gradient \mathbf{F}.


## 3. Algorithmic Implementation

**Elastic Trial State Computation Algorithm**
$$
\begin{algorithmic}
\State $\text{Given total strain increment } \Delta \bm{\varepsilon} \text{ (or relative deformation gradient } \bm{f}\text{) and state variables at } t_n\text{: } \bm{\sigma}^n, \bm{\varepsilon}^p_n, \bm{\alpha}_n, \bar{\varepsilon}^p_n \text{ (or } \bm{b}_e^n\text{)}$
\If{$\text{Kinematic formulation is infinitesimal small-strain}$}
\State $\bm{\sigma}^{tr} = \bm{\sigma}^n + \mathbf{D}^e : \Delta \bm{\varepsilon}$
\State $\bm{s}^{tr} = \bm{\sigma}^{tr} - \frac{1}{3} \mathrm{tr}(\bm{\sigma}^{tr}) \mathbf{I}$
\State $\bm{\eta}^{tr} = \bm{s}^{tr} - \bm{\alpha}_n$
\State $f^{tr} = \|\bm{\eta}^{tr}\| - \sqrt{\frac{2}{3}} \sigma_y(\bar{\varepsilon}^p_n)$
\Else
\State $\bm{f} = \mathbf{I} + \frac{\partial \Delta \bm{u}}{\partial \bm{x}_n}$
\State $\bm{b}_e^{tr} = \bm{f} \cdot \bm{b}_e^n \cdot \bm{f}^T$
\State $J_{n+1} = \det(\bm{f}) J_n$
\State $\bar{\bm{b}}_e^{tr} = J_{n+1}^{-2/3} \bm{b}_e^{tr}$
\State $\bm{\tau}^{tr} = \frac{dU(J_{n+1})}{dJ_{n+1}} J_{n+1} \mathbf{I} + \mu \mathrm{dev}(\bar{\bm{b}}_e^{tr})$
\State $f^{tr} = \|\mathrm{dev}(\bm{\tau}^{tr})\| - \sqrt{\frac{2}{3}} \sigma_y(\bar{\varepsilon}^p_n)$
\EndIf
\If{$f^{tr} \le 0$}
\State $\text{Set } \bm{\sigma}^{n+1} = \bm{\sigma}^{tr} \text{ (or } \bm{\tau}^{n+1} = \bm{\tau}^{tr}\text{)}, \bm{\varepsilon}^p_{n+1} = \bm{\varepsilon}^p_n, \bar{\varepsilon}^p_{n+1} = \bar{\varepsilon}^p_n$
\Return $\text{Step is purely elastic; return trial state as converged state}$
\Else
\EndIf
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 260, 271, 293-294; Simo_Hughes_1998_Computational inelasticity.pdf Box 3.2, Box 9.1_


## 4. Known Pitfalls

- **Inappropriate Reference Frame and Stress Measures in Finite-Strain Predictors**: Formulating finite-strain elastic trial states in the reference configuration using the Right Cauchy-Green tensor (C), Second Piola-Kirchhoff stress tensor (S), and Mandel stress tensor (M) fails to preserve spatial objectivity and coaxiality in hyperelasticity-based finite plasticity, which exclusively utilizes the elastic Left Cauchy-Green tensor (b_e) and Kirchhoff stress tensor (\tau). _(Source: Kim_FEA for Elastoplastic Problems.pdf p. 292-294; Simo_Hughes_1998_Computational inelasticity.pdf p. 304, 318-320)_
- **Drift from Yield Surface in Explicit Predictor-Corrector Integration**: Relying on forward Euler explicit integration or substepping for large load increments causes severe drift from the yield surface and potential instability, whereas unconditionally stable implicit return-mapping (backward Euler) ensures plastic admissibility regardless of step size without needing ad-hoc substepping. _(Source: Dunne_Petrinic_2005_Introduction to computational plasticity.pdf p. 146, 149; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 240-241)_
- **Misinterpreting Plastic Flow During Elastic Prediction**: Evaluating history-dependent internal variables or plastic flow parameters during the elastic trial calculation introduces spurious plastic dissipation; the elastic predictor step must strictly freeze all plastic internal state variables (\Delta \bm{\varepsilon}^p = \bm{0}, \Delta \bar{\varepsilon}^p = 0). _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 35, 116, 318)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Dunne_Petrinic_2005_Introduction to computational plasticity.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
