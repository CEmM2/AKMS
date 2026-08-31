---
id: damage-gtn-consistent-tangent
title: GTN Consistent Algorithmic Tangent
domain: computational-mechanics
subdomain: damage
tags:
- damage
- gtn
- consistent-tangent
- aravas
- newton
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-gtn-return-mapping
  type: requires
  weight: 1.0
- to: damage-gtn-yield-function
  type: requires
  weight: 0.9
- to: plasticity-consistent-tangent-general
  type: refines
  weight: 0.9
- to: fem-newton-raphson
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# GTN Consistent Algorithmic Tangent

## Summary

GTN consistent algorithmic tangent derives from the exact linearization of the implicit return-mapping algorithm, providing closed-form algorithmic moduli for Newton-Raphson iterations.

## 1. Core Concept

The consistent algorithmic tangent tensor for the Gurson-Tvergaard-Needleman (GTN) porous plasticity model is obtained by exact linearization of the discrete implicit backward Euler return-mapping state update. Unlike the continuum elastoplastic tangent operator, which is derived from continuous rate equations, the algorithmic tangent accounts for the discrete step size and non-linear void evolution. As shown by Zhang (1995) following Aravas (1987), the GTN consistent tangent tensor can be expressed in an explicit, closed-form 4th-order structure involving five scalar coefficients without requiring 4th-order matrix inversions. Utilizing the consistent tangent operator in global implicit finite element solvers preserves the asymptotic quadratic convergence rate of Newton-Raphson iterations.

## 2. Mathematical Formulation

**Explicit 4th-Order Consistent Algorithmic Tangent Structure**
$$
\mathbf{D}^{consis} = d_0 \mathbf{J} + d_1 \mathbf{I} \otimes \mathbf{I} + d_2 \mathbf{n} \otimes \mathbf{n} + d_3 \mathbf{n} \otimes \mathbf{I} + d_4 \mathbf{I} \otimes \mathbf{n}
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 35_

**Closed-Form GTN Tangent Coefficients**
$$
d_0 = 2G \frac{q}{q^{tr}}, \quad d_1 = K - \frac{2G}{3}\frac{q}{q^{tr}} - 3K^2 C_{11}, \quad d_2 = \frac{4G^2}{q^{tr}} \Delta \varepsilon_q - 4G^2 C_{22}, \quad d_3 = -2GK C_{12}, \quad d_4 = -6GK C_{21}
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 35_

**Linearized Flow and Yield Condition Matrix System**
$$
\begin{bmatrix} A_{11} & A_{12} \\ A_{21} & A_{22} \end{bmatrix} \begin{bmatrix} \partial \Delta \varepsilon_p \\ \partial \Delta \varepsilon_q \end{bmatrix} = \begin{bmatrix} B_{11} \mathbf{I} + B_{12} \mathbf{n} \\ B_{21} \mathbf{I} + B_{22} \mathbf{n} \end{bmatrix} : \partial \bm{\sigma}
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 34-35, 41-43_

**GTN Tangent Major Symmetry Condition**
$$
d_3 = d_4 \iff C_{12} = 3 C_{21}
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 35_

**Notation:**
\mathbf{D}^{consis}: fourth-order consistent algorithmic tangent stiffness tensor; \mathbf{J}: fourth-order symmetric identity tensor; \mathbf{I}: second-order identity tensor; \mathbf{n}: unit deviatoric normal tensor; d_0, d_1, d_2, d_3, d_4: scalar GTN tangent coefficients; G: elastic shear modulus; K: elastic bulk modulus; q: updated equivalent von Mises stress; q^{tr}: trial equivalent von Mises stress; \Delta \varepsilon_p: hydrostatic plastic strain increment; \Delta \varepsilon_q: equivalent plastic strain increment; A_{ij}, B_{ij}, C_{ij}: scalar linearization coefficients.


## 3. Algorithmic Implementation

**GTN Algorithmic Consistent Tangent Evaluation Algorithm**
$$
\begin{algorithmic}
\State $\text{Given converged state at } t_{n+1}\text{: stress } \bm{\sigma}_{n+1}, \text{ trial stress } q^{tr}, \text{ plastic strain increments } \Delta \varepsilon_p, \Delta \varepsilon_q, \text{ and unit normal } \mathbf{n} = \frac{3}{2q}\bm{s}_{n+1}$
\State $\text{Compute partial derivatives of GTN yield function } \Phi(\sigma_m, q, f) \text{ and matrix hardening } H(\bar{\varepsilon}^p)$
\State $\text{Evaluate Aravas system matrices } A_{ij} \text{ and } B_{ij}$
\State $\text{Invert } 2 \times 2 \text{ matrix } \mathbf{A}\text{: } \mathbf{C} = \mathbf{A}^{-1} \mathbf{B}$
\State $d_0 = 2G \frac{q}{q^{tr}}$
\State $d_1 = K - \frac{2G}{3}\frac{q}{q^{tr}} - 3K^2 C_{11}$
\State $d_2 = \frac{4G^2}{q^{tr}} \Delta \varepsilon_q - 4G^2 C_{22}$
\State $d_3 = -2GK C_{12}, \quad d_4 = -6GK C_{21}$
\State $\mathbf{D}^{consis} = d_0 \mathbf{J} + d_1 \mathbf{I} \otimes \mathbf{I} + d_2 \mathbf{n} \otimes \mathbf{n} + d_3 \mathbf{n} \otimes \mathbf{I} + d_4 \mathbf{I} \otimes \mathbf{n}$
\Return $\text{Return explicit 4th-order consistent tangent tensor } \mathbf{D}^{consis}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 34-35_


## 4. Known Pitfalls

- **Loss of Quadratic Convergence with Continuum Tangent Operator**: Using the continuum elastoplastic tangent operator D^{ep} in implicit global Newton-Raphson solvers instead of the algorithmic consistent tangent operator D^{consis} degrades convergence from quadratic to linear, requiring significantly more iterations per load step. _(Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 31, 38; Kim_FEA for Elastoplastic Problems.pdf p. 243, 252)_
- **Spurious Non-Symmetry from Index Misalignment**: Assuming minor or major symmetry of D^{consis} when C_12 \neq 3 C_21 introduces errors in symmetric global FE solvers; major symmetry holds if and only if C_12 = 3 C_21, which requires careful coefficient calculation. _(Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 35)_
- **Division by Zero at Zero Trial Deviatoric Stress**: Evaluating d_0, d_2, or n = 3s / (2q) as trial deviatoric stress approaches zero (q^{tr} \to 0) causes floating-point division by zero; hydrostatic or purely elastic states must revert to the isotropic elastic tangent tensor D^e. _(Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 34-35; Kim_FEA for Elastoplastic Problems.pdf p. 252-254)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf
