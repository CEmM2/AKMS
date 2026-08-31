---
id: plasticity-consistent-tangent-general
title: Consistent Tangent for General Models
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- consistent-tangent
- jacobian
- algorithmic-tangent
- verification
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-general-return-mapping
  type: requires
  weight: 1.0
- to: plasticity-cpp-nonassociative
  type: requires
  weight: 0.9
- to: plasticity-consistent-tangent-j2
  type: refines
  weight: 1.0
- to: fem-newton-raphson
  type: feeds-into
  weight: 1.0
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Consistent Tangent for General Models

## Summary

The consistent algorithmic tangent operator for general elastoplastic constitutive models is derived by exact linearization of the discrete implicit return-mapping algorithm, ensuring asymptotic quadratic convergence in global Newton-Raphson solvers.

## 1. Core Concept

The consistent algorithmic tangent operator provides the exact derivative of the updated stress tensor with respect to the strain increment at the end of a time step, \mathbf{D}^{\mathrm{alg}} = d\bm{\sigma}_{n+1} / d\bm{\varepsilon}_{n+1}. Unlike the continuum elastoplastic tangent tensor \mathbf{D}^{\mathrm{ep}}, which is derived from rate equations assuming instantaneous yield surface consistency, the consistent tangent operator accounts for the discrete algorithmic step size \Delta \gamma and local iteration history. As established by Simo and Hughes (1998) and Borst and Crisfield (2012), exact linearization of backward Euler closest-point projection algorithms yields an algorithmic flexibility tensor \mathbf{\Xi}_{n+1} = [\mathbf{C}^{-1} + \Delta \gamma \partial^2 f / \partial \bm{\sigma}^2]^{-1}. Using the algorithmic tangent tensor in implicit finite element formulations restores the asymptotic quadratic convergence rate of the global Newton-Raphson iteration.

## 2. Mathematical Formulation

**Algorithmic Stress Linearization**
$$
d\bm{\sigma}_{n+1} = \mathbf{\Xi}_{n+1} : \left( d\bm{\varepsilon}_{n+1} - d\gamma_{n+1} \frac{\partial g}{\partial \bm{\sigma}_{n+1}} \right)
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 147, 213; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 252_

**General Algorithmic Consistent Tangent Tensor**
$$
\mathbf{D}^{\mathrm{alg}} = \mathbf{\Xi}_{n+1} - \frac{\left( \mathbf{\Xi}_{n+1} : \frac{\partial g}{\partial \bm{\sigma}_{n+1}} \right) \otimes \left( \frac{\partial f}{\partial \bm{\sigma}_{n+1}} : \mathbf{\Xi}_{n+1} \right)}{\frac{\partial f}{\partial \bm{\sigma}_{n+1}} : \mathbf{\Xi}_{n+1} : \frac{\partial g}{\partial \bm{\sigma}_{n+1}} + H_{\mathrm{alg}}}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 147, 213; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 252_

**Discrete Plastic Multiplier Increment Linearization**
$$
d\gamma_{n+1} = \frac{\frac{\partial f}{\partial \bm{\sigma}_{n+1}} : \mathbf{\Xi}_{n+1} : d\bm{\varepsilon}_{n+1}}{\frac{\partial f}{\partial \bm{\sigma}_{n+1}} : \mathbf{\Xi}_{n+1} : \frac{\partial g}{\partial \bm{\sigma}_{n+1}} + H_{\mathrm{alg}}}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 147, 213_

**Asymmetric Algorithmic Tangent Operator Structure**
$$
\mathbf{D}^{\mathrm{alg}} = \mathbf{A}^{-1} : \mathbf{D}^e - \frac{\left( \mathbf{A}^{-1} : \mathbf{D}^e : \mathbf{n} \right) \otimes \left( \mathbf{n}^T : \mathbf{A}^{-1} : \mathbf{D}^e \right)}{\mathbf{n}^T : \mathbf{A}^{-1} : \mathbf{D}^e : \mathbf{n} + H}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.7, p. 252_

**Notation:**
\mathbf{D}^{\mathrm{alg}}: fourth-order consistent algorithmic tangent tensor; \mathbf{D}^e: fourth-order elastic stiffness tensor; \mathbf{C}: elasticity tensor (\mathbf{D}^e); \mathbf{\Xi}_{n+1}: modified algorithmic elasticity tensor; f: yield function; g: plastic potential function; \mathbf{n}: yield surface normal vector (\partial f / \partial \bm{\sigma}); \mathbf{m}: plastic flow direction vector (\partial g / \partial \bm{\sigma}); \Delta \gamma: discrete plastic multiplier; H, H_{\mathrm{alg}}: plastic hardening parameter.


## 3. Algorithmic Implementation

**General Consistent Algorithmic Tangent Construction Algorithm**
$$
\begin{algorithmic}
\State $\text{Given converged local state at } t_{n+1}\text{: Cauchy stress } \bm{\sigma}_{n+1}, \text{ plastic multiplier } \Delta \gamma, \text{ internal hardening } \bm{q}_{n+1}, \text{ and elasticity tensor } \mathbf{C}$
\State $\text{Compute yield surface gradient } \mathbf{n}_{n+1} = \frac{\partial f}{\partial \bm{\sigma}_{n+1}} \text{ and plastic potential gradient } \mathbf{m}_{n+1} = \frac{\partial g}{\partial \bm{\sigma}_{n+1}}$
\State $\text{Compute second derivatives } \mathbf{H}_g = \frac{\partial^2 g}{\partial \bm{\sigma}_{n+1}^2} \text{ and hardening derivatives } \frac{\partial f}{\partial \bm{q}_{n+1}}, \frac{\partial \bm{q}_{n+1}}{\partial \Delta \gamma}$
\State $\text{Form matrix } \mathbf{A} = \mathbf{I} + \Delta \gamma \mathbf{C} : \mathbf{H}_g$
\State $\text{Invert } \mathbf{A} \text{ to evaluate modified algorithmic elasticity tensor } \mathbf{\Xi}_{n+1} = \mathbf{A}^{-1} : \mathbf{C}$
\State $\text{Compute scalar denominator } d_{denom} = \mathbf{n}_{n+1} : \mathbf{\Xi}_{n+1} : \mathbf{m}_{n+1} + H_{\mathrm{alg}}$
\State $\mathbf{D}^{\mathrm{alg}} = \mathbf{\Xi}_{n+1} - \frac{(\mathbf{\Xi}_{n+1} : \mathbf{m}_{n+1}) \otimes (\mathbf{n}_{n+1} : \mathbf{\Xi}_{n+1})}{d_{denom}}$
\Return $\text{Return explicit fourth-order consistent algorithmic tangent tensor } \mathbf{D}^{\mathrm{alg}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 147, 213; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.7, p. 252_


## 4. Known Pitfalls

- **Loss of Quadratic Global Newton Convergence using Continuum Tangent**: Substituting the continuum elastoplastic tangent D^{ep} for the algorithmic consistent tangent D^{alg} in implicit global Newton-Raphson solvers degrades the quadratic convergence rate to linear, significantly increasing iteration counts per load step. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 122, 145; Kim_FEA for Elastoplastic Problems.pdf p. 195, 207; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 600)_
- **Spurious Non-Symmetry Enforcement in Symmetric Global Solvers**: Enforcing major symmetry on D^{alg} when using non-associated flow rules (g \neq f) or non-linear kinematic hardening destroys exact linearization, preventing quadratic convergence in symmetric linear system solvers. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.7, p. 252; Simo_Hughes_1998_Computational inelasticity.pdf p. 147)_
- **Singularity in Algorithmic Elasticity Tensor Inversion at Yield Vertices**: Attempting to evaluate smooth second-order derivatives \partial^2 g / \partial \bm{\sigma}^2 at non-smooth yield surface corners (e.g. Tresca, Mohr-Coulomb apices) causes matrix singular ill-conditioning unless multi-surface Koiter return mapping or subdifferential operators are applied. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 212-214; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 252; Simplify_radial_return_Part_1.pdf p. 1-2)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- Simplify_radial_return_Part_1.pdf
- Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf
