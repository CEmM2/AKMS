---
id: plasticity-lode-triaxiality
title: Stress Triaxiality & Lode Angle in Plasticity
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- triaxiality
- lode-angle
- ductile-fracture
- bai-wierzbicki
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-invariants
  type: requires
  weight: 1.0
- to: plasticity-von-mises
  type: refines
  weight: 0.6
- to: damage-continuum-framework
  type: feeds-into
  weight: 0.9
- to: damage-gtn-void-evolution
  type: feeds-into
  weight: 0.8
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Stress Triaxiality & Lode Angle in Plasticity

## Summary

Stress triaxiality and Lode angle parameterize three-dimensional stress states, governing void evolution, yield surface shape, and Lode-dependent ductile material failure.

## 1. Core Concept

In continuum mechanics and plasticity, characterising three-dimensional stress states requires three scalar stress invariants beyond hydrostatic pressure alone: hydrostatic stress \sigma_m = \frac{1}{3}\mathrm{tr}(\bm{\sigma}) (or pressure p = -\sigma_m), von Mises equivalent stress \sigma_e = \sqrt{3 J_2}, and the third deviatoric stress invariant J_3 = \det(\bm{s}). Stress triaxiality \eta = \sigma_m / \sigma_e governs volumetric void growth and compaction, while Lode angle \theta = \frac{1}{3} \arccos\left( \frac{3\sqrt{3}}{2} \frac{J_3}{J_2^{3/2}} \right) measures the normalized third invariant, distinguishing between pure shear, axisymmetric extension, and axisymmetric compression stress states.

## 2. Mathematical Formulation

**Stress Triaxiality Ratio**
$$
\eta = \frac{\sigma_m}{\sigma_e} = \frac{\mathrm{tr}(\bm{\sigma})}{3 \sqrt{3 J_2}}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 19; Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 104468_

**Lode Angle and Third Invariant Relation**
$$
\theta = \frac{1}{3} \arccos\left( \frac{3\sqrt{3}}{2} \frac{J_3}{J_2^{3/2}} \right)
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 226, 261-262; Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 104468_

**Lode-Dependent Mohr-Coulomb Yield Surface**
$$
f(\bm{s}, p, \theta) = \sqrt{J_2} \cos\theta - \left( \frac{2}{\sqrt{3}}\sqrt{J_2} - p \right) \sin\phi - c \cos\phi = 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 261-262_

**Normalized Lode Stress Parameter**
$$
L = \frac{2\sigma_2 - \sigma_1 - \sigma_3}{\sigma_1 - \sigma_3}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 226; Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 104468_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; \bm{s}: deviatoric stress tensor; \sigma_m: mean hydrostatic stress; p: hydrostatic pressure (-1/3 tr(\bm{\sigma})); \sigma_e: von Mises equivalent stress; J_2: second invariant of deviatoric stress; J_3: third invariant of deviatoric stress; \eta: stress triaxiality ratio; \theta: Lode angle; L: normalized Lode parameter; \phi: friction angle; c: cohesion.


## 3. Algorithmic Implementation

**Lode Angle and Stress Triaxiality Computation Algorithm**
$$
\begin{algorithmic}
\State $\text{Given Cauchy stress tensor } \bm{\sigma}$
\State $p = -\frac{1}{3} \mathrm{tr}(\bm{\sigma}), \quad \sigma_m = \frac{1}{3} \mathrm{tr}(\bm{\sigma})$
\State $\bm{s} = \bm{\sigma} - \sigma_m \mathbf{I}$
\State $J_2 = \frac{1}{2} \bm{s} : \bm{s}, \quad \sigma_e = \sqrt{3 J_2}$
\If{$J_2 \le \text{TOL}$}
\State $\eta = 0, \quad \theta = 0, \quad L = 0$
\Return $\text{Hydrostatic stress state; return zero deviatoric invariants}$
\Else
\EndIf
\State $\eta = \frac{\sigma_m}{\sigma_e}$
\State $\xi_3 = \frac{3\sqrt{3}}{2} \frac{J_3}{J_2^{3/2}}$
\State $\xi_{clamped} = \max\left(-1, \min\left(1, \xi_3\right)\right)$
\State $\theta = \frac{1}{3} \arccos\left(\xi_{clamped}\right)$
\Return $\text{Return stress triaxiality } \eta, \text{ Lode angle } \theta, \text{ and invariants } J_2, J_3$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 19, 226, 261-262_


## 4. Known Pitfalls

- **Arccosine Argument Domain Violations from Floating-Point Roundoff**: Evaluating arccosine functions when numerical errors push the argument \xi_3 slightly outside [-1, 1] causes NaN domain exceptions unless clamped prior to evaluation. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 261-262)_
- **Division by Zero at Hydrostatic Stress States**: Evaluating stress triaxiality \eta = \sigma_m / \sqrt{3 J_2} or Lode angle when J_2 \to 0 produces floating-point division by zero; hydrostatic check thresholds must be enforced. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 261-262)_
- **Neglecting Lode Angle Dependence in Ductile Void Coalescence Models**: Assuming void evolution depends purely on stress triaxiality \eta without accounting for Lode angle \theta mispredicts failure mode transitions between tensile internal necking and localized shear band coalescence. _(Source: Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 104468; Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 011001)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf
- Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf
