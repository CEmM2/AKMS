---
id: plasticity-drucker-prager
title: Drucker-Prager Yield & Non-Associative Flow
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- yield-criterion
- drucker-prager
- non-associative
- friction
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-invariants
  type: requires
  weight: 1.0
- to: plasticity-von-mises
  type: refines
  weight: 0.9
- to: constit-stress-update-architecture
  type: requires
  weight: 0.9
- to: constit-thermodynamic-framework
  type: requires
  weight: 0.8
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Drucker-Prager Yield & Non-Associative Flow

## Summary

Drucker-Prager yield criterion models pressure-dependent shear strength in frictional materials using a conical yield surface with non-associative dilatancy and specialized apex return mapping.

## 1. Core Concept

The Drucker-Prager yield criterion extends von Mises plasticity to pressure-dependent materials (such as soil, concrete, and rock) by introducing a hydrostatic stress term into the yield condition, forming a smooth cone in principal stress space with an apex on the hydrostatic axis. To prevent unphysical volumetric dilation under shear, a non-associative plastic potential g(\bm{\sigma}) is employed with an independent dilatancy angle \psi, which renders the elastoplastic tangent operator non-symmetric. When trial elastic stresses project beyond the conical yield surface above the apex transition boundary, a dedicated apex return mapping algorithm projects stress directly to the singularity point, zeroing deviatoric stress.

## 2. Mathematical Formulation

**Drucker-Prager Yield Function**
$$
f(\bm{\sigma}) = \sqrt{J_2} + \alpha I_1 - k = 0, \quad \alpha = \frac{2 \sin\phi}{\sqrt{3}(3 - \sin\phi)}, \quad k = \frac{6 c_{coh} \cos\phi}{\sqrt{3}(3 - \sin\phi)}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 228, 244; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598_

**Non-Associative Plastic Potential Function**
$$
g(\bm{\sigma}) = \sqrt{J_2} + \alpha_g I_1 - k_g, \quad \alpha_g = \frac{2 \sin\psi}{\sqrt{3}(3 - \sin\psi)}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 231-232_

**Non-Symmetric Algorithmic Tangent Operator**
$$
\mathbf{D}^{\mathrm{alg}} = \mathbf{A}^{-1} : \mathbf{D}^e - \frac{\left( \mathbf{A}^{-1} : \mathbf{D}^e : \mathbf{n} \right) \otimes \left( \mathbf{m}^T : \mathbf{A}^{-1} : \mathbf{D}^e \right)}{\mathbf{n}^T : \mathbf{A}^{-1} : \mathbf{D}^e : \mathbf{m} + h}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.7, p. 251-252_

**Apex Singularity Return Condition**
$$
\bm{\sigma}_{apex} = \frac{k}{3 \alpha} \mathbf{I}, \quad \text{for } I_1^{\mathrm{tr}} \ge \frac{k}{\alpha} + \frac{G \sqrt{2}}{K \alpha} \sqrt{J_2^{\mathrm{tr}}}
$$
_Source: Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 600; Simplify_radial_return_Part_1.pdf p. 307_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; \bm{s}: deviatoric stress tensor; J_2: second invariant of deviatoric stress; I_1: first invariant of stress tensor; \phi: internal friction angle; \psi: dilatancy angle; c_{coh}: cohesion coefficient; \alpha, k: Drucker-Prager yield parameters; \alpha_g, k_g: plastic potential parameters; \mathbf{n}: yield surface gradient vector (\partial f / \partial \bm{\sigma}); \mathbf{m}: flow direction vector (\partial g / \partial \bm{\sigma}); \mathbf{D}^{\mathrm{alg}}: consistent elastoplastic tangent tensor; \bm{\sigma}_{apex}: hydrostatic apex stress tensor.


## 3. Algorithmic Implementation

**Drucker-Prager Return Mapping and Apex Singularity Algorithm**
$$
\begin{algorithmic}
\State $\text{Given trial elastic stress } \bm{\sigma}^{\mathrm{tr}}, \text{ bulk modulus } K, \text{ shear modulus } G, \text{ and material parameters } \alpha, k, \alpha_g$
\State $I_1^{\mathrm{tr}} = \mathrm{tr}(\bm{\sigma}^{\mathrm{tr}}), \quad \bm{s}^{\mathrm{tr}} = \bm{\sigma}^{\mathrm{tr}} - \frac{1}{3} I_1^{\mathrm{tr}} \mathbf{I}, \quad J_2^{\mathrm{tr}} = \frac{1}{2} \bm{s}^{\mathrm{tr}} : \bm{s}^{\mathrm{tr}}$
\State $f^{\mathrm{tr}} = \sqrt{J_2^{\mathrm{tr}}} + \alpha I_1^{\mathrm{tr}} - k$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}}, \quad \mathbf{D}^{\mathrm{alg}} = \mathbf{D}^e$
\Return $\text{Step is elastic; accept trial state}$
\ElsIf{$\alpha I_1^{\mathrm{tr}} - k + \frac{9 K \alpha \alpha_g}{G} \sqrt{J_2^{\mathrm{tr}}} \ge 0 \quad \text{(Apex Region)}$}
\State $\bm{\sigma}_{n+1} = \frac{k}{3 \alpha} \mathbf{I}, \quad \mathbf{D}^{\mathrm{alg}} = \mathbf{O}$
\Return $\text{Return apex hydrostatic stress state}$
\Else
\State $\Delta \gamma = \frac{f^{\mathrm{tr}}}{G + 9 K \alpha \alpha_g}$
\State $\bm{s}_{n+1} = \left( 1 - \frac{G \Delta \gamma}{\sqrt{J_2^{\mathrm{tr}}}} \right) \bm{s}^{\mathrm{tr}}, \quad I_{1,n+1} = I_1^{\mathrm{tr}} - 9 K \alpha_g \Delta \gamma$
\State $\bm{\sigma}_{n+1} = \bm{s}_{n+1} + \frac{1}{3} I_{1,n+1} \mathbf{I}$
\State $\mathbf{D}^{\mathrm{alg}} = \text{Form non-symmetric consistent tangent from } \mathbf{m} \neq \mathbf{n}$
\EndIf
\Return $\text{Return updated stress } \bm{\sigma}_{n+1} \text{ and algorithmic tangent } \mathbf{D}^{\mathrm{alg}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 244, 251-252; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 600; Simplify_radial_return_Part_1.pdf p. 307_


## 4. Known Pitfalls

- **Spurious Volumetric Expansion from Associative Flow Assumptions**: Enforcing an associative flow rule (\psi = \phi) in Drucker-Prager plasticity severely overpredicts plastic volume growth (dilatancy) under shear, causing unrealistic uplift in geotechnical and soil-structure simulations. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 231-232; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598)_
- **Division by Zero and Convergence Failure at the Apex Singularity**: Applying smooth return mapping derivative formulas \bm{s} / \sqrt{J_2} when trial stress projects near or above the hydrostatic apex (\sqrt{J_2^{\mathrm{tr}}} \to 0) causes division by zero; explicit apex projection logic must be enforced. _(Source: Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 600; Simplify_radial_return_Part_1.pdf p. 307)_
- **Loss of Quadratic Solver Convergence from Symmetrizing Non-Associative Moduli**: Forcing major symmetry on the algorithmic tangent tensor \mathbf{D}^{\mathrm{alg}} when \psi \neq \phi discards off-diagonal flow terms, degrading global Newton-Raphson convergence rates. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.7, p. 251-252)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- Simplify_radial_return_Part_1.pdf
- Simplify_radial_return_Part_2.pdf
