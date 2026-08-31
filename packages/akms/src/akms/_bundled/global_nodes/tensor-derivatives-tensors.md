---
id: tensor-derivatives-tensors
title: Derivatives of Tensors w.r.t. Tensors
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- tensor-derivatives
- fourth-order
- carlson-hoger
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-derivatives-scalars
  type: requires
  weight: 1.0
- to: tensor-products-contractions
  type: requires
  weight: 1.0
- to: tensor-spectral-decomposition
  type: feeds-into
  weight: 1.0
- to: tensor-isotropic-functions
  type: feeds-into
  weight: 1.0
- to: plasticity-consistent-tangent-general
  type: feeds-into
  weight: 0.9
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Derivatives of Tensors w.r.t. Tensors

## Summary

Derivatives of second-order tensors with respect to second-order tensors yield fourth-order linear transformation tensors. These fourth-order derivatives form the foundation for algorithmic consistent tangent operators, elastic-plastic tangent moduli, kinematic strain-gradient transformations, and inverse tensor differentials in non-linear finite element formulations.

## 1. Core Concept

In finite-strain solid mechanics, linearizing non-linear constitutive relations or kinematic transformations requires differentiating second-order tensor fields (such as stress, logarithmic strain, or stretch) with respect to state tensors (such as deformation gradients, Cauchy-Green tensors, or left stretch tensors). The resulting derivative is a fourth-order tensor mapping second-order tensor increments to second-order tensor variations. Key analytical identities include the derivative of inverse tensor fields \mathrm{d}\mathbf{C}^{-1} = -\mathbf{C}^{-1} \mathrm{d}\mathbf{C} \mathbf{C}^{-1}, the derivative of elastic Green-Lagrange strain \frac{\partial \mathbf{E}^e}{\partial \mathbf{F}^e} = \frac{1}{2}(\mathbf{I} \bar{\otimes} \mathbf{F}^{eT} + \mathbf{F}^{eT} \otimes \mathbf{I}), and the fourth-order derivative of squared symmetric tensors. These tensor-by-tensor derivative operators enable implicit return mapping linearizations and exact Newton-Raphson global convergence.

## 2. Mathematical Formulation

**Inverse Tensor Differential Identity**
$$
\mathrm{d}\mathbf{C}^{-1} = -\mathbf{C}^{-1} \mathrm{d}\mathbf{C} \mathbf{C}^{-1}
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Sec. III-E, p. 6_

**Elastic Strain Derivative with Respect to Deformation Gradient**
$$
\frac{\partial \mathbf{E}^e}{\partial \mathbf{F}^e} = \frac{1}{2} \left( \mathbf{I} \bar{\otimes} \mathbf{F}^{eT} + \mathbf{F}^{eT} \otimes \mathbf{I} \right)
$$
_Source: Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, Eq. A.21, p. 50_

**Fourth-Order Derivative of Squared Symmetric Tensor**
$$
\left( \frac{\mathrm{d}\tilde{\mathbf{C}}^2}{\mathrm{d}\tilde{\mathbf{C}}} \right)_{ijkl} = \frac{1}{2} \left( \delta_{ik}\tilde{\mathbf{C}}_{lj} + \delta_{il}\tilde{\mathbf{C}}_{kj} + \delta_{jl}\tilde{\mathbf{C}}_{ik} + \delta_{kj}\tilde{\mathbf{C}}_{il} \right)
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.3, p. 387_

**Left Stretch Tensor Derivative in Updated Kinematics**
$$
\left[ \frac{\partial \mathbf{B}_e^e}{\partial \mathbf{F}_{j+1}} \right]_{ijkl} = \delta_{ik}(\mathbf{B}_e^e)_{jl} + \delta_{jk}(\mathbf{B}_e^e)_{il}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.5, Eq. 12.114, p. 422_

**Notation:**
{'\\mathbf{F}^e': 'Elastic deformation gradient tensor.', '\\mathbf{E}^e': 'Elastic Green-Lagrange strain tensor.', '\\mathbf{C}': 'Right Cauchy-Green deformation tensor.', '\\mathbf{B}_e^e': 'Elastic left Cauchy-Green deformation tensor.', '\\boldsymbol{\\varepsilon}_e^e': 'Logarithmic strain tensor \\boldsymbol{\\varepsilon}_e^e = \\frac{1}{2}\\ln \\mathbf{B}_e^e.', '\\delta_{ij}': 'Kronecker delta identity component.'}


## 3. Algorithmic Implementation

**Fourth-Order Logarithmic Strain-Tensor Derivative Algorithm**
$$
\begin{algorithmic}
\State $Given elastic left Cauchy-Green tensor \mathbf{B}_e^e and updated deformation gradient \mathbf{F}_{j+1}$
\State $Compute spectral decomposition of \mathbf{B}_e^e to find principal stretches \lambda_i^2 and spatial eigenprojections \mathbf{E}_i$
\State $Evaluate logarithmic strain tensor \boldsymbol{\varepsilon}_e^e \gets \frac{1}{2} \ln \mathbf{B}_e^e = \sum_{i=1}^3 (\ln \lambda_i) \mathbf{E}_i$
\State $Evaluate fourth-order tensor derivative \frac{\partial \boldsymbol{\varepsilon}_e^e}{\partial \mathbf{B}_e^e} \gets \frac{1}{2} \frac{\partial \ln[\mathbf{B}_e^e]}{\partial \mathbf{B}_e^e}$
\State $Evaluate kinematic gradient derivative \left[\frac{\partial \mathbf{B}_e^e}{\partial \mathbf{F}_{j+1}}\right]_{ijkl} \gets \delta_{ik}(\mathbf{B}_e^e)_{jl} + \delta_{jk}(\mathbf{B}_e^e)_{il}$
\State $Compose total fourth-order chain rule tangent \frac{\partial \boldsymbol{\varepsilon}_e^e}{\partial \mathbf{F}_{j+1}} \gets \frac{\partial \boldsymbol{\varepsilon}_e^e}{\partial \mathbf{B}_e^e} : \frac{\partial \mathbf{B}_e^e}{\partial \mathbf{F}_{j+1}}$
\Return $\frac{\partial \boldsymbol{\varepsilon}_e^e}{\partial \mathbf{F}_{j+1}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.5, Eqs. 12.111–12.114, pp. 421–422_


## 4. Known Pitfalls

- **Ignoring Major and Minor Symmetries in Fourth-Order Derivatives**: Assuming arbitrary fourth-order tensor derivatives possess major symmetry (\mathbb{C}_{ijkl} = \mathbb{C}_{klij}) or minor symmetries (\mathbb{C}_{ijkl} = \mathbb{C}_{jikl} = \mathbb{C}_{ijlk}). Differentiating non-symmetric second-order tensors or non-associated potential functions breaks major symmetry, resulting in non-symmetric global tangent stiffness matrices. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 7.7, p. 252 & Sec. 12.1, p. 406)_
- **Failure to Apply Chain Rule Across Non-Coaxial Intermediate Configurations**: Differentiating composite stress functions without accounting for rotations between intermediate elastic-plastic configurations or principal axis rotations introduces kinematic inconsistency and destroys quadratic Newton convergence. Mitigation: Apply exact multi-stage fourth-order tensor chain rule contractions \frac{\partial \mathbf{M}}{\partial \mathbf{F}^e} = \frac{\partial \mathbf{M}}{\partial \mathbf{\Pi}^e} : \frac{\partial \mathbf{\Pi}^e}{\partial \mathbf{E}^e} : \frac{\partial \mathbf{E}^e}{\partial \mathbf{F}^e}. _(Source: Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, Eq. A.21, p. 50; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Sec. 2.6 & Box 3, pp. 5389, 5406)_

## References

- Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf
- Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf
- Rashid - 1993 - Incremental kinematics for finite element applications.pdf
