---
id: plasticity-consistent-tangent-j2
title: Consistent Tangent for J2 Plasticity
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- consistent-tangent
- j2
- newton
- algorithmic-tangent
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-radial-return
  type: requires
  weight: 1.0
- to: plasticity-von-mises
  type: requires
  weight: 1.0
- to: plasticity-consistent-tangent-general
  type: refines
  weight: 1.0
- to: fem-newton-raphson
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Consistent Tangent for J2 Plasticity

## Summary

The consistent algorithmic tangent operator for J2 von Mises plasticity exacts the derivative of the stress update with respect to strain increments, preserving quadratic Newton-Raphson convergence.

## 1. Core Concept

In non-linear finite element analysis using implicit time integration, solving global equilibrium via Newton-Raphson iterations requires linearizing the residual force vector. For classical J2 von Mises plasticity integrated using the radial return algorithm (backward Euler), differentiating the discrete stress update with respect to the strain increment produces the exact consistent algorithmic tangent operator \mathbf{D}^{\mathrm{alg}}. While the continuum elastoplastic tangent tensor \mathbf{D}^{\mathrm{ep}} represents the instantaneous rate response on the yield surface, \mathbf{D}^{\mathrm{alg}} incorporates the discrete radial return projection scale factor \theta = 1 - 2\mu\Delta \gamma / \|\bm{s}^{\mathrm{tr}}\|. Substituting \mathbf{D}^{\mathrm{alg}} for \mathbf{D}^{\mathrm{ep}} in global stiffness matrices ensures asymptotic quadratic convergence in implicit FE solvers.

## 2. Mathematical Formulation

**J2 Algorithmic Consistent Tangent Tensor**
$$
\mathbf{D}^{\mathrm{alg}} = K \mathbf{I} \otimes \mathbf{I} + 2\mu \theta_{n+1} \left( \mathbf{I}_{\mathrm{dev}} - \mathbf{n}_{n+1} \otimes \mathbf{n}_{n+1} \right) + 2\mu \left( \theta_{n+1} - \bar{\theta}_{n+1} \right) \mathbf{n}_{n+1} \otimes \mathbf{n}_{n+1}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 124; Kim_FEA for Elastoplastic Problems.pdf p. 202-205; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 35_

**Algorithmic Shear Reduction Factors**
$$
\theta_{n+1} = 1 - \frac{2\mu \Delta \gamma}{\|\bm{\xi}^{\mathrm{tr}}_{n+1}\|}, \quad \bar{\theta}_{n+1} = \frac{1}{1 + \frac{H + K^{\prime}}{3\mu}} - (1 - \theta_{n+1})
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 124; Kim_FEA for Elastoplastic Problems.pdf p. 202-204_

**Explicit Matrix Representation of J2 Tangent Modulus**
$$
\mathbf{D}^{\mathrm{alg}} = \mathbf{D}^e - (c_1 - c_2) \mathbf{N} \otimes \mathbf{N} - c_2 \mathbf{I}_{\mathrm{dev}}, \quad c_1 = \frac{4\mu^2}{2\mu + \frac{2}{3}H}, \quad c_2 = \frac{4\mu^2 \Delta \gamma}{\|\bm{\eta}^{\mathrm{tr}}\|}
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 204, 209_

**Continuum versus Algorithmic Tangent Comparison**
$$
\mathbf{D}^{\mathrm{ep}} = \lim_{\Delta \gamma \to 0} \mathbf{D}^{\mathrm{alg}} = \mathbf{D}^e - \frac{4\mu^2}{2\mu + \frac{2}{3}H} \mathbf{N} \otimes \mathbf{N}
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 189, 202; Simo_Hughes_1998_Computational inelasticity.pdf p. 124_

**Notation:**
\mathbf{D}^{\mathrm{alg}}: fourth-order consistent algorithmic tangent tensor; \mathbf{D}^{\mathrm{ep}}: fourth-order continuum elastoplastic tangent tensor; \mathbf{D}^e: elastic stiffness tensor; K: elastic bulk modulus; \mu: elastic shear modulus; \theta_{n+1}, \bar{\theta}_{n+1}: algorithmic shear scaling coefficients; \mathbf{n}_{n+1}, \mathbf{N}: unit yield surface normal tensor; \mathbf{I}_{\mathrm{dev}}: fourth-order deviatoric identity tensor; \Delta \gamma: discrete plastic consistency parameter increment; \|\bm{\xi}^{\mathrm{tr}}\|, \|\bm{\eta}^{\mathrm{tr}}\|: trial shifted deviatoric stress norm; H, K^{\prime}: kinematic and isotropic hardening moduli.


## 3. Algorithmic Implementation

**J2 Algorithmic Consistent Tangent Evaluation Algorithm**
$$
\begin{algorithmic}
\State $\text{Given trial stress } \bm{s}^{\mathrm{tr}}, \text{ plastic strain increment } \Delta \gamma, \text{ elastic shear modulus } \mu, \text{ bulk modulus } K, \text{ and hardening moduli } H, K^{\prime}$
\If{$\text{State is elastic } (\Delta \gamma = 0)$}
\State $\mathbf{D}^{\mathrm{alg}} = \mathbf{D}^e = K \mathbf{I} \otimes \mathbf{I} + 2\mu \mathbf{I}_{\mathrm{dev}}$
\Return $\text{Return elastic tangent tensor } \mathbf{D}^e$
\Else
\State $\bar{\theta}_{n+1} = \frac{1}{1 + \frac{H + K^{\prime}}{3\mu}} - (1 - \theta_{n+1})$
\State $c_1 = \frac{4\mu^2}{2\mu + \frac{2}{3}(H + K^{\prime})}, \quad c_2 = \frac{4\mu^2 \Delta \gamma}{\|\bm{s}^{\mathrm{tr}}\|}$
\State $\mathbf{D}^{\mathrm{alg}} = \mathbf{D}^e - (c_1 - c_2) \mathbf{n} \otimes \mathbf{n} - c_2 \mathbf{I}_{\mathrm{dev}}$
\EndIf
\Return $\text{Return exact J2 consistent algorithmic tangent tensor } \mathbf{D}^{\mathrm{alg}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 124-125; Kim_FEA for Elastoplastic Problems.pdf p. 202-205, 209_


## 4. Known Pitfalls

- **Loss of Quadratic Newton-Raphson Convergence with Continuum Tangent**: Using the continuum elastoplastic tangent operator D^{ep} instead of the exact algorithmic consistent tangent operator D^{alg} in implicit FE solvers destroys quadratic Newton-Raphson convergence, resulting in linear convergence and excessive iteration counts. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 122; Kim_FEA for Elastoplastic Problems.pdf p. 189, 202; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 38)_
- **Division by Zero at Zero Trial Deviatoric Stress Norm**: Evaluating the unit normal vector n = s^{tr} / \|s^{tr}\| or shear scale factor c_2 = 4\mu^2 \Delta \gamma / \|s^{tr}\| when the trial deviatoric stress vanishes (\|s^{tr}\| \to 0) causes floating-point division by zero; elastic handling must be enforced. _(Source: Kim_FEA for Elastoplastic Problems.pdf p. 202-204; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 34-35)_
- **Spurious Non-Symmetry from Non-Linear Hardening Terms**: Omitting hardening derivatives in \bar{\theta}_{n+1} or incorrectly linearizing non-linear isotropic/kinematic hardening functions leads to inconsistent global Jacobians and loss of quadratic convergence. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 122-124; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 251-252)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf
