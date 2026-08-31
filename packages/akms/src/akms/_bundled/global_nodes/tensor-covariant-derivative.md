---
id: tensor-covariant-derivative
title: Covariant Derivatives of Vectors & Tensors
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- curvilinear
- covariant-derivative
- divergence
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-christoffel-symbols
  type: requires
  weight: 1.0
- to: tensor-metric
  type: requires
  weight: 0.9
- to: kinematics-velocity-gradient
  type: feeds-into
  weight: 0.9
- to: kinematics-objective-rates
  type: feeds-into
  weight: 0.8
- to: fem-tl-weak-form
  type: feeds-into
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Covariant Derivatives of Vectors & Tensors

## Summary

Covariant differentiation extends partial differentiation to curvilinear coordinate systems and Riemannian manifolds, accounting for spatially varying basis vectors through connection coefficients. Covariant derivatives transform as true tensors under coordinate chart changes, enabling frame-invariant formulations of continuum strain rates, velocity gradients, and field equations.

## 1. Core Concept

Standard partial derivatives of vector or tensor components fail to transform as tensors in non-Cartesian or curvilinear coordinate systems because base vectors vary from point to point. Covariant differentiation introduces connection coefficients \gamma^k_{ij} (Christoffel symbols of the second kind) to correct for base vector variations. For contravariant vector components v^i, the covariant derivative \nabla_j v^i combines partial derivatives with connection terms. For covariant 1-forms a_i, connection terms enter with a negative sign. The symmetric part of the spatial velocity covariant derivative \nabla v defines the rate of deformation tensor d_{ij} = \frac{1}{2}(\nabla_i v_j + \nabla_j v_i).

## 2. Mathematical Formulation

**Covariant Derivative of Contravariant Vector Components**
$$
\nabla_j v^i = \frac{\partial v^i}{\partial x^j} + v^k \gamma^i_{kj}
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Def. A.30, p. 38_

**Covariant Derivative of Covariant 1-Form Components**
$$
\nabla_j a_i = \frac{\partial a_i}{\partial x^j} - a_k \gamma^k_{ij}
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Def. A.30, p. 39_

**Covariant Derivative of Vector Along Vector Field**
$$
\nabla_w v = \left( \frac{\partial v^i}{\partial x^j} w^j + v^k w^j \gamma^i_{kj} \right) \frac{\partial}{\partial x^i}
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Def. A.30, p. 39_

**Rate of Deformation Tensor in Covariant Form**
$$
d_{ij} = \frac{1}{2} (\nabla_i v_j + \nabla_j v_i)
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Sec. 2.1, Prop. 2.8, p. 7_

**Notation:**
{'\\nabla': 'Covariant derivative operator.', 'v^i': 'Contravariant vector components.', 'a_i': 'Covariant 1-form components.', '\\gamma^k_{ij}': 'Connection coefficients (Christoffel symbols of the second kind).', 'd_{ij}': 'Components of the rate of deformation tensor d_\\flat.', 'w^j': 'Contravariant components of directional vector field w.'}


## 3. Algorithmic Implementation

**Covariant Derivative and Rate of Deformation Computation Algorithm**
$$
\begin{algorithmic}
\State $Given velocity vector components v^i(x), metric tensor g_{ij}(x), and connection coefficients \gamma^k_{ij}(x)$
\State $Lower velocity indices to obtain covariant components v_i \gets g_{ij} v^j$
\For{$i \gets 1 \text{ to } n_{\mathrm{SD}}$}
\For{$j \gets 1 \text{ to } n_{\mathrm{SD}}$}
\State $Compute contravariant vector covariant derivative \nabla_j v^i \gets \frac{\partial v^i}{\partial x^j} + \sum_{k=1}^{n_{\mathrm{SD}}} v^k \gamma^i_{kj}$
\State $Compute 1-form covariant derivative \nabla_j v_i \gets \frac{\partial v_i}{\partial x^j} - \sum_{k=1}^{n_{\mathrm{SD}}} v_k \gamma^k_{ij}$
\State $Evaluate rate of deformation tensor component d_{ij} \gets \frac{1}{2}(\nabla_i v_j + \nabla_j v_i)$
\EndFor
\EndFor
\Return $\nabla v, d_{ij}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Sec. 2.1, Prop. 2.8, p. 7 & App. A.4, Def. A.30, pp. 38–39_


## 4. Known Pitfalls

- **Using Partial Differentiation in Curvilinear Coordinates**: Replacing covariant derivatives \nabla_j v^i with ordinary partial derivatives \partial v^i / \partial x^j in curvilinear coordinate systems omits connection coefficient terms \gamma^i_{kj} v^k, producing non-tensorial quantities that depend spuriously on coordinate chart choices. _(Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Def. A.30, pp. 38–39)_
- **Applying Incorrect Sign on Connection Coefficients for Covariant vs Contravariant Indices**: Using a positive sign for connection terms when differentiating covariant 1-forms a_i (i.e., using +\gamma^k_{ij} a_k instead of -\gamma^k_{ij} a_k). Contravariant vector components use +\gamma^i_{kj} v^k, whereas covariant 1-form components require -\gamma^k_{ij} a_k. _(Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Def. A.30, pp. 38–39)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Kolev_Desmorat_2021_Objective rates as covariant derivatives on the manifold of Riemannian metrics.pdf
