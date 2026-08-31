---
id: fem-weak-form-derivation
title: Weak Form & Variational Principles
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- variational
- weak-form
- galerkin
- boundary-conditions
status: established
confidence: 0.9
source: hybrid
edges:
- to: fem-shape-functions
  type: feeds-into
  weight: 1.0
- to: fem-isoparametric-mapping
  type: feeds-into
  weight: 1.0
- to: fem-assembly-algorithm
  type: feeds-into
  weight: 0.9
- to: fem-tl-weak-form
  type: refines
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Weak Form & Variational Principles

## Summary

The weak form converts local differential momentum balance equations into an equivalent integral scalar statement over a continuum domain by testing against arbitrary kinematically admissible virtual displacement fields. Through integration by parts and the Gauss divergence theorem, the weak form relaxes continuity requirements on stress fields, incorporates Neumann natural boundary conditions directly into boundary integrals, and serves as the foundation for Ritz-Galerkin finite element spatial discretizations.

## 1. Core Concept

The principle of virtual work provides the fundamental weak form for continuum mechanics problems. Starting from local strong-form momentum balance \nabla \cdot \boldsymbol{\sigma} + \rho \mathbf{b} = \rho \ddot{\mathbf{u}}, the governing differential equation is multiplied by an arbitrary test function (virtual displacement \delta \mathbf{u}) and integrated over the continuum volume. Applying tensor divergence identities reduces second-order spatial derivatives to first-order derivatives. Essential (Dirichlet) boundary conditions are enforced strongly on the trial displacement space, requiring test functions to vanish on essential boundary surfaces. Natural (Neumann) surface tractions enter the weak formulation directly as boundary integrals. The Galerkin method selects finite-dimensional trial and test spaces from the same polynomial shape function basis.

## 2. Mathematical Formulation

**Strong Form Differential Balance**
$$
\nabla \cdot \boldsymbol{\sigma} + \rho \mathbf{b} = \rho \ddot{\mathbf{u}} \quad \text{in } V
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.1, Eq. 2.4, p. 32; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 2.2.4, p. 23_

**Principle of Virtual Work (Weak Form)**
$$
\int_V \boldsymbol{\sigma} : \nabla(\delta \mathbf{u}) \, \mathrm{d}V + \int_V \rho \ddot{\mathbf{u}} \cdot \delta \mathbf{u} \, \mathrm{d}V = \int_V \rho \mathbf{b} \cdot \delta \mathbf{u} \, \mathrm{d}V + \int_{S_t} \bar{\mathbf{t}} \cdot \delta \mathbf{u} \, \mathrm{d}S
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 2.3.1, Eq. 2.3.8 & Sec. 2.3.4, p. 33; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.1, Eq. 2.8, p. 32_

**Virtual Work Integral Balance**
$$
\delta W^{\mathrm{int}} + \delta W^{\mathrm{kin}} = \delta W^{\mathrm{ext}}
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 2.3.3, pp. 32–33; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.1, Eq. 2.7, p. 32_

**Galerkin Discretized Weak Form**
$$
\int_V \nabla(w^h) : \boldsymbol{\sigma}(u^h) \, \mathrm{d}V + \int_V \rho \ddot{u}^h \cdot w^h \, \mathrm{d}V - \int_V \rho \mathbf{b} \cdot w^h \, \mathrm{d}V - \int_{S_t} \bar{\mathbf{t}} \cdot w^h \, \mathrm{d}S = 0
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 2.4.1, pp. 34–35; ME280A.pdf, Sec. 7, p. 136_

**Notation:**
{'\\boldsymbol{\\sigma}': 'Cauchy stress tensor.', '\\mathbf{u}': 'Displacement vector field.', '\\delta \\mathbf{u}': 'Virtual displacement test function.', '\\rho': 'Mass density.', '\\mathbf{b}': 'Body force vector.', '\\bar{\\mathbf{t}}': 'Prescribed surface traction vector.', 'S_u': 'Boundary surface with prescribed essential (Dirichlet) displacement.', 'S_t': 'Boundary surface with prescribed natural (Neumann) surface traction.'}


## 3. Algorithmic Implementation

**Galerkin Weak Form Variational Derivation Procedure**
$$
\begin{algorithmic}
\State $Start with strong form momentum balance \nabla \cdot \boldsymbol{\sigma} + \rho \mathbf{b} = \rho \ddot{\mathbf{u}} \text{ in } V$
\State $Define trial space \mathcal{U} = \{ \mathbf{u} \in H^1(V) \mid \mathbf{u} = \bar{\mathbf{u}} \text{ on } S_u \} \text{ and test space } \mathcal{V}_0 = \{ \delta \mathbf{u} \in H^1(V) \mid \delta \mathbf{u} = \mathbf{0} \text{ on } S_u \}$
\State $Multiply by test function \delta \mathbf{u} \in \mathcal{V}_0 \text{ and integrate over volume } V: \int_V \delta \mathbf{u} \cdot (\nabla \cdot \boldsymbol{\sigma} + \rho \mathbf{b} - \rho \ddot{\mathbf{u}}) \, \mathrm{d}V = 0$
\State $Apply tensor identity \delta \mathbf{u} \cdot (\nabla \cdot \boldsymbol{\sigma}) = \nabla \cdot (\boldsymbol{\sigma} \cdot \delta \mathbf{u}) - \nabla(\delta \mathbf{u}) : \boldsymbol{\sigma}$
\State $Apply Gauss divergence theorem: \int_V \nabla \cdot (\boldsymbol{\sigma} \cdot \delta \mathbf{u}) \, \mathrm{d}V = \int_{\partial V} \delta \mathbf{u} \cdot (\boldsymbol{\sigma} \cdot \mathbf{n}) \, \mathrm{d}S$
\State $Substitute traction condition \boldsymbol{\sigma} \cdot \mathbf{n} = \bar{\mathbf{t}} \text{ on } S_t \text{ and } \delta \mathbf{u} = \mathbf{0} \text{ on } S_u$
\Return $\int_V \nabla(\delta \mathbf{u}) : \boldsymbol{\sigma} \, \mathrm{d}V + \int_V \rho \ddot{\mathbf{u}} \cdot \delta \mathbf{u} \, \mathrm{d}V = \int_V \rho \mathbf{b} \cdot \delta \mathbf{u} \, \mathrm{d}V + \int_{S_t} \bar{\mathbf{t}} \cdot \delta \mathbf{u} \, \mathrm{d}S$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 2.3.1, pp. 28–30; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.1, pp. 31–33_


## 4. Known Pitfalls

- **Non-Zero Test Functions on Essential Boundaries**: Failing to enforce that virtual displacements or test functions \delta \mathbf{u} vanish on Dirichlet essential boundary surfaces S_u introduces uncancelled boundary integrals \int_{S_u} \delta \mathbf{u} \cdot \mathbf{t} \, \mathrm{d}S, invalidating the weak form derivation. Mitigation: Restrict test functions \delta \mathbf{u} strictly to the homogeneous space \mathcal{V}_0 with \delta \mathbf{u} = \mathbf{0} on S_u. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 2.3.1, p. 29; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.1, p. 32)_
- **Inconsistent Field Smoothness in Strong vs Weak Forms**: Requiring C^1 derivative continuity in strong form equations leads to overly restrictive function spaces. The weak form reduces order-of-differentiation requirements to C^0 piecewise polynomials across element interfaces, provided inter-element derivative discontinuities are square-integrable (H^1 space). Mitigation: Select C^0 continuous finite element shape functions satisfying H^1 completeness. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 2.2.6 & 2.3.1, pp. 27–30)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- ME280A.pdf
