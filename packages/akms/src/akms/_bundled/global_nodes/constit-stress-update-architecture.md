---
id: constit-stress-update-architecture
title: Stress Update Architecture (Operator Split)
domain: computational-mechanics
subdomain: constitutive
tags:
- constitutive
- stress-update
- return-mapping
- operator-split
- plasticity
status: established
confidence: 0.9
source: hybrid
edges:
- to: constit-thermodynamic-framework
  type: requires
  weight: 1.0
- to: constit-elastic-predictor
  type: feeds-into
  weight: 1.0
- to: plasticity-general-return-mapping
  type: feeds-into
  weight: 1.0
- to: plasticity-consistent-tangent-general
  type: feeds-into
  weight: 1.0
- to: fem-tl-weak-form
  type: feeds-into
  weight: 0.9
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Stress Update Architecture (Operator Split)

## Summary

Stress update architecture uses an operator split to decouple strain-driven elastic prediction from plastic or viscoplastic return-mapping correction.

## 1. Core Concept

The stress update architecture in computational inelasticity relies on an operator-split methodology to integrate rate constitutive equations over a discrete time step. The additive operator split decomposes the continuous initial-value problem into two sequential sub-problems: an elastic predictor problem and a plastic or viscoplastic corrector problem. In the elastic predictor phase, plastic deformation and internal variables are frozen, allowing the incremental strain to be processed purely elastically. If the resulting trial stress violates the yield criterion, the corrector phase freezes total strain and executes an implicit return mapping or overstress integration. This projects the stress state back onto the yield surface or relaxes the overstress, updating internal state variables and enabling the exact calculation of an algorithmic consistent tangent operator for global Newton equilibrium iterations.

## 2. Mathematical Formulation

**Additive Operator Split of Inelastic Governing Equations**
$$
\begin{bmatrix} \dot{\bm{\varepsilon}} \\ \dot{\bm{\varepsilon}}^p \\ \dot{\bm{q}} \end{bmatrix} = \begin{bmatrix} \nabla^s \bm{v} \\ \bm{0} \\ \bm{0} \end{bmatrix} + \begin{bmatrix} \bm{0} \\ \dot{\gamma} \frac{\partial f}{\partial \bm{\sigma}} \\ -\dot{\gamma} \bm{h}(\bm{\sigma}, \bm{q}) \end{bmatrix}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 140_

**Elastic Predictor Stress and Yield Trial Evaluation**
$$
\bm{\sigma}^{tr} = \bm{\sigma}^n + \mathbf{D}^e : \Delta \bm{\varepsilon}, \quad \bm{q}^{tr} = \bm{q}_n, \quad f^{tr} = f(\bm{\sigma}^{tr}, \bm{q}_n)
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.5, p. 146; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 240_

**Implicit Backward Euler Plastic Corrector Return Mapping**
$$
\bm{\sigma}_{n+1} = \bm{\sigma}^{tr} - \Delta \gamma \mathbf{D}^e : \left.\frac{\partial f}{\partial \bm{\sigma}}\right|_{n+1}, \quad \bm{q}_{n+1} = \bm{q}_n - \Delta \gamma \bm{h}_{n+1}, \quad f(\bm{\sigma}_{n+1}, \bm{q}_{n+1}) = 0
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 116, 120; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 242_

**Viscoplastic Overstress Evolution Formulations**
$$
\dot{\bar{\varepsilon}}^{vp} = \frac{1}{\eta} \left\langle \frac{f(\bm{\sigma}, \bm{q})}{\sigma_0} \right\rangle^n \quad \text{or} \quad \dot{\bar{\varepsilon}}^{vp} = \alpha \sinh\left[ \beta (\sigma_e - r - \sigma_y) \right]
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 293, 295; Dunne_Petrinic_2005_Introduction to computational plasticity.pdf p. 41, 180_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; \bm{\sigma}^{tr}: elastic trial Cauchy stress tensor; \mathbf{D}^e: fourth-order elastic stiffness tensor; \bm{\varepsilon}: total strain tensor; \bm{\varepsilon}^p: plastic strain tensor; \bm{\varepsilon}^{vp}: viscoplastic strain tensor; \bm{q}: internal hardening variables vector; f: yield function or flow potential; \gamma, \Delta \gamma: continuous and discrete plastic consistency parameters; \eta: fluidity or viscosity parameter; \sigma_e: equivalent von Mises stress; \sigma_y: static yield stress; r: isotropic hardening stress; \mathbf{D}^{alg}: algorithmic consistent tangent stiffness tensor.


## 3. Algorithmic Implementation

**Operator-Split Stress Update and Return-Mapping Algorithm**
$$
\begin{algorithmic}
\State $\text{Given converged state at } t_n\text{: } \bm{\sigma}^n, \bm{\varepsilon}^p_n, \bm{q}_n \text{ and strain increment } \Delta \bm{\varepsilon}$
\State $\bm{\sigma}^{tr} = \bm{\sigma}^n + \mathbf{D}^e : \Delta \bm{\varepsilon}$
\State $f^{tr} = f(\bm{\sigma}^{tr}, \bm{q}_n)$
\If{$f^{tr} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{tr}, \quad \bm{\varepsilon}^p_{n+1} = \bm{\varepsilon}^p_n, \quad \bm{q}_{n+1} = \bm{q}_n$
\Return $\text{Step is purely elastic; return trial state}$
\Else
\If{$\text{Material model is rate-independent plasticity}$}
\While{$|f(\bm{\sigma}_{n+1}^{(k)}, \bm{q}_{n+1}^{(k)})| > \text{TOL}$}
\State $\text{Solve local Newton-Raphson system for } \Delta \gamma \text{ and return-mapping corrections } \bm{\sigma}_{n+1}, \bm{q}_{n+1}$
\EndWhile
\ElsIf{$\text{Material model is rate-dependent viscoplasticity}$}
\State $\text{Integrate overstress rate } \dot{\bar{\varepsilon}}^{vp} = \Phi(f) \text{ via backward Euler to solve for } \bm{\sigma}_{n+1}, \bm{\varepsilon}^{vp}_{n+1}, \bm{q}_{n+1}$
\EndIf
\EndIf
\State $\text{Compute algorithmic consistent tangent tensor } \mathbf{D}^{alg} = \frac{\partial \bm{\sigma}_{n+1}}{\partial \bm{\varepsilon}_{n+1}}$
\Return $\text{Return updated stress } \bm{\sigma}_{n+1}, \text{ internal variables } \bm{q}_{n+1}, \text{ and consistent tangent tensor } \mathbf{D}^{alg}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.2, p. 124, Box 3.5, p. 146; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 8.1, p. 294_


## 4. Known Pitfalls

- **Using Continuum Tangent Modulus in Implicit Newton FE Iterations**: Substituting the continuous elastoplastic tangent operator D^{ep} for the algorithmic consistent tangent operator D^{alg} = \partial \bm{\sigma}_{n+1} / \partial \bm{\varepsilon}_{n+1} in implicit finite element solvers destroys the asymptotic quadratic convergence rate of global Newton-Raphson iterations. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 122-124; Kim_FEA for Elastoplastic Problems.pdf p. 236, 248)_
- **Yield Surface Drift in Explicit Stress Updates**: Integrating constitutive rate equations explicitly without a plastic return-mapping corrector leads to accumulated stress drift off the yield surface and potential numerical divergence, particularly for large load increments. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 240-241; Dunne_Petrinic_2005_Introduction to computational plasticity.pdf p. 146)_
- **Unphysical Dissipation in Predictor Phase**: Updating internal hardening variables or plastic strains during the elastic predictor phase violates the operator split decomposition, causing spurious energy dissipation before yield admissibility is evaluated. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 140-141)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Dunne_Petrinic_2005_Introduction to computational plasticity.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
