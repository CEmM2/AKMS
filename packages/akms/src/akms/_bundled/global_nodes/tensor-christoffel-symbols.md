---
id: tensor-christoffel-symbols
title: Christoffel Symbols (1st and 2nd Kind)
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- curvilinear
- christoffel
- covariant-derivative
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-metric
  type: requires
  weight: 1.0
- to: tensor-curvilinear-bases
  type: requires
  weight: 0.9
- to: tensor-covariant-derivative
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Christoffel Symbols (1st and 2nd Kind)

## Summary

Christoffel symbols of the second kind (connection coefficients) characterize the metric-compatible, torsion-free Levi-Civita connection on a Riemannian manifold. Expressed in terms of metric tensor components and their spatial derivatives, they define covariant differentiation in curvilinear coordinates and transform non-tensorially under coordinate chart changes.

## 1. Core Concept

In tensor analysis on Riemannian manifolds, Christoffel symbols of the second kind \gamma^k_{ij} represent connection coefficients for the unique Levi-Civita connection \nabla. They express spatial derivatives of metric tensor components g_{ij} and quantify the geometric influence of curvilinear coordinate charts. Christoffel symbols are symmetric in their lower indices for torsion-free connections (\gamma^k_{ij} = \gamma^k_{ji}). Because their transformation law under coordinate chart changes contains an inhomogeneous second-derivative term, connection coefficients are not tensors.

## 2. Mathematical Formulation

**Christoffel Symbols of the Second Kind from Metric Tensor**
$$
\gamma^k_{ij} = \frac{1}{2} g^{kl} \left( \frac{\partial g_{jl}}{\partial x^i} + \frac{\partial g_{il}}{\partial x^j} - \frac{\partial g_{ij}}{\partial x^l} \right)
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Theorem A.1, p. 39_

**Symmetry and Torsion-Free Property**
$$
\gamma^k_{ij} = \gamma^k_{ji}
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Def. A.31, p. 39_

**Non-Tensorial Transformation Law Under Chart Transitions**
$$
\gamma^j_{ki} = \frac{\partial x^{k'}}{\partial x^k} \frac{\partial x^j}{\partial x^{j'}} \frac{\partial x^{i'}}{\partial x^i} \gamma^{j'}_{k' i'} + \frac{\partial x^j}{\partial x^{m'}} \frac{\partial^2 x^{m'}}{\partial x^k \partial x^i}
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Def. A.30, p. 39_

**Notation:**
{'g_{ij}': 'Components of the Riemannian metric tensor.', 'g^{kl}': 'Components of the inverse metric tensor satisfying g^{ik} g_{kj} = \\delta^i_j.', '\\gamma^k_{ij}': 'Christoffel symbols of the second kind (connection coefficients).', '\\nabla': 'Covariant derivative / Levi-Civita connection operator.'}


## 3. Algorithmic Implementation

**Computation of Christoffel Symbols from Metric Tensor**
$$
\begin{algorithmic}
\State $Given metric tensor components g_{ij}(x) and coordinate partial derivatives \frac{\partial g_{ij}}{\partial x^k}$
\State $Compute inverse metric tensor g^{kl} such that \sum_{k} g^{ik} g_{kj} = \delta^i_j$
\For{$i \gets 1 \text{ to } n_{\mathrm{SD}}$}
\For{$j \gets 1 \text{ to } n_{\mathrm{SD}}$}
\For{$k \gets 1 \text{ to } n_{\mathrm{SD}}$}
\State $Evaluate \gamma^k_{ij} \gets \frac{1}{2} \sum_{l=1}^{n_{\mathrm{SD}}} g^{kl} \left( \frac{\partial g_{jl}}{\partial x^i} + \frac{\partial g_{il}}{\partial x^j} - \frac{\partial g_{ij}}{\partial x^l} \right)$
\EndFor
\EndFor
\EndFor
\Return $\gamma^k_{ij}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Theorem A.1, p. 39_


## 4. Known Pitfalls

- **Treating Connection Coefficients as Tensor Components**: Attempting to transform Christoffel symbols \gamma^k_{ij} using standard multilinear tensor transformation laws. Connection coefficients pick up an inhomogeneous second-derivative term \frac{\partial x^j}{\partial x^{m'}} \frac{\partial^2 x^{m'}}{\partial x^k \partial x^i} under chart changes, reflecting coordinate frame curvature rather than intrinsic physical tensor transformation. _(Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Def. A.30 & Def. A.31, p. 39)_
- **Assuming Lower-Index Symmetry in Torsion-Free Connections**: Applying lower-index symmetry \gamma^k_{ij} = \gamma^k_{ji} in non-holonomic frames or non-Riemannian connections with non-zero torsion. On Riemannian manifolds in coordinate charts, lower-index symmetry is uniquely guaranteed by the torsion-free Levi-Civita connection property. _(Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.4, Def. A.31 & Theorem A.1, p. 39)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
