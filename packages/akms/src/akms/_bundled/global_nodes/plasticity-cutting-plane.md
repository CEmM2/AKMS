---
id: plasticity-cutting-plane
title: Cutting Plane Algorithm
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- cutting-plane
- return-mapping
- semi-implicit
- continuum-tangent
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-general-return-mapping
  type: contradicts
  weight: 0.7
- to: plasticity-cpp-nonassociative
  type: contradicts
  weight: 0.7
- to: constit-stress-update-architecture
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Cutting Plane Algorithm

## Summary

The cutting plane algorithm is an iterative return-mapping scheme that linearizes the yield function locally at each iteration step to compute plastic multiplier increments without requiring second derivatives or matrix inversions.

## 1. Core Concept

The cutting plane algorithm provides a simplified, computationally efficient alternative to the closest point projection (CPP) method for elastoplastic constitutive return mapping. First formulated by Simo and Ortiz (1987) and presented in Simo and Hughes (1998), the algorithm linearizes the yield criterion f(\bm{\sigma}, q) = 0 via a first-order Taylor series expansion about the current iterative state. By re-evaluating the flow direction \partial f / \partial \bm{\sigma} and hardening vector h at each iterate, the scalar plastic multiplier increment \Delta \gamma^{(k)} is calculated explicitly without computing second-order derivatives \partial^2 f / \partial \bm{\sigma}^2 or inverting local Hessian matrices \mathbf{\Xi}.

## 2. Mathematical Formulation

**Cutting Plane Linearized Yield Function Expansion**
$$
f\left(\bm{\sigma}_{n+1}^{(k+1)}, q_{n+1}^{(k+1)}\right) \approx f_{n+1}^{(k)} + \left. \frac{\partial f}{\partial \bm{\sigma}} \right|_{n+1}^{(k)} : \Delta \bm{\sigma}_{n+1}^{(k)} + \left. \frac{\partial f}{\partial q} \right|_{n+1}^{(k)} \Delta q_{n+1}^{(k)} = 0
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 148_

**Explicit Plastic Multiplier Increment Formula**
$$
\Delta \gamma_{n+1}^{(k)} = \frac{f_{n+1}^{(k)}}{\left. \frac{\partial f}{\partial \bm{\sigma}} \right|_{n+1}^{(k)} : \mathbf{C} : \left. \frac{\partial f}{\partial \bm{\sigma}} \right|_{n+1}^{(k)} + \left. \frac{\partial f}{\partial q} \right|_{n+1}^{(k)} \cdot h_{n+1}^{(k)}}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.6, p. 148_

**Iterative Plastic Strain and Hardening Updates**
$$
\bm{\varepsilon}^p_{(k+1)} = \bm{\varepsilon}^p_{(k)} + \Delta \gamma_{n+1}^{(k)} \left. \frac{\partial f}{\partial \bm{\sigma}} \right|_{n+1}^{(k)}, \quad q_{n+1}^{(k+1)} = q_{n+1}^{(k)} - \Delta \gamma_{n+1}^{(k)} h_{n+1}^{(k)}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.6, p. 148_

**Iterative Cauchy Stress Update**
$$
\bm{\sigma}_{n+1}^{(k+1)} = \mathbf{C} : \left( \bm{\varepsilon}_{n+1} - \bm{\varepsilon}^p_{(k+1)} \right)
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.6, p. 148_

**Notation:**
\bm{\sigma}_{n+1}^{(k)}: Cauchy stress tensor at iteration k; q_{n+1}^{(k)}: internal hardening variable at iteration k; f: yield function; \mathbf{C}: fourth-order elastic stiffness tensor; \Delta \gamma_{n+1}^{(k)}: scalar plastic multiplier increment; \bm{\varepsilon}^p: plastic strain tensor; h: plastic hardening function; \mathrm{TOL}: yield tolerance threshold.


## 3. Algorithmic Implementation

**Cutting Plane Return-Mapping Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: plastic strain } \bm{\varepsilon}^p_n, \text{ hardening variable } q_n, \text{ total strain } \bm{\varepsilon}_{n+1}, \text{ and elasticity tensor } \mathbf{C}$
\State $\text{Initialize iteration counter } k = 0, \bm{\varepsilon}^p_{(0)} = \bm{\varepsilon}^p_n, q_{n+1}^{(0)} = q_n, \gamma_{n+1}^{(0)} = 0$
\State $\bm{\sigma}_{n+1}^{(0)} = \mathbf{C} : (\bm{\varepsilon}_{n+1} - \bm{\varepsilon}^p_{(0)})$
\State $f_{n+1}^{(0)} = f(\bm{\sigma}_{n+1}^{(0)}, q_{n+1}^{(0)})$
\If{$f_{n+1}^{(0)} \le \text{TOL}$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}_{n+1}^{(0)}, \quad \bm{\varepsilon}^p_{n+1} = \bm{\varepsilon}^p_n, \quad q_{n+1} = q_n$
\Return $\text{Step is elastic; return trial state}$
\Else
\EndIf
\While{$f_{n+1}^{(k)} > \text{TOL}$}
\State $\mathbf{n}^{(k)} = \left.\frac{\partial f}{\partial \bm{\sigma}}\right|_{n+1}^{(k)}, \quad h^{(k)} = h(\bm{\sigma}_{n+1}^{(k)}, q_{n+1}^{(k)})$
\State $\Delta \gamma_{n+1}^{(k)} = \frac{f_{n+1}^{(k)}}{\mathbf{n}^{(k)} : \mathbf{C} : \mathbf{n}^{(k)} + \left.\frac{\partial f}{\partial q}\right|_{n+1}^{(k)} \cdot h^{(k)}}$
\State $\bm{\varepsilon}^p_{(k+1)} = \bm{\varepsilon}^p_{(k)} + \Delta \gamma_{n+1}^{(k)} \mathbf{n}^{(k)}$
\State $q_{n+1}^{(k+1)} = q_{n+1}^{(k)} - \Delta \gamma_{n+1}^{(k)} h^{(k)}$
\State $\gamma_{n+1}^{(k+1)} = \gamma_{n+1}^{(k)} + \Delta \gamma_{n+1}^{(k)}$
\State $\bm{\sigma}_{n+1}^{(k+1)} = \mathbf{C} : (\bm{\varepsilon}_{n+1} - \bm{\varepsilon}^p_{(k+1)})$
\State $f_{n+1}^{(k+1)} = f(\bm{\sigma}_{n+1}^{(k+1)}, q_{n+1}^{(k+1)})$
\State $k = k + 1$
\EndWhile
\Return $\text{Return updated stress } \bm{\sigma}_{n+1}, \text{ plastic strain } \bm{\varepsilon}^p_{n+1}, \text{ and hardening variable } q_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.6, p. 148_


## 4. Known Pitfalls

- **Loss of Quadratic Convergence in Global Implicit Finite Element Solvers**: Because the cutting plane algorithm evaluates gradients at intermediate iterates without forming exact second-order Hessian matrices, exact algorithmic consistent tangent operators cannot be derived, causing global Newton-Raphson iterations to revert to linear convergence. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 145, 148)_
- **Spurious Iterative Drift for Highly Curved Yield Surfaces**: For non-linear yield surfaces with high localized curvature (such as GTN or cap models), first-order Taylor expansion approximations in the cutting plane method can cause iterative drift or slow convergence compared to fully implicit closest point projection schemes. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 143, 148)_

## References

- Simo_Hughes_1998_Computational inelasticity.pdf
