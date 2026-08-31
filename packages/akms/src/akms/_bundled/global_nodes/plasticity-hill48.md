---
id: plasticity-hill48
title: Hill 1948 Anisotropic Yield
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- anisotropy
- hill48
- sheet-metal
- r-values
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-invariants
  type: requires
  weight: 0.7
- to: plasticity-von-mises
  type: refines
  weight: 1.0
- to: constit-stress-update-architecture
  type: requires
  weight: 0.9
- to: plasticity-lode-triaxiality
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Hill 1948 Anisotropic Yield

## Summary

Hill 1948 yield criterion extends von Mises plasticity to orthotropic anisotropic materials using a quadratic stress tensor formulation.

## 1. Core Concept

The Hill anisotropic yield criterion (Hill, 1948) generalizes classical isotropic J_2 von Mises plasticity to orthotropic materials such as rolled metals. Formulated as a quadratic function of stress components in principal anisotropy directions, the Hill yield function eliminates hydrostatic pressure dependence by enforcing \alpha_{11} = \alpha_{22} = \alpha_{33} = 0 from the broader Hoffman failure criterion. Under backward Euler implicit integration, the stress update is evaluated via an anisotropic projection matrix \mathbf{P}_{\alpha}, maintaining exact algorithmic return mapping.

## 2. Mathematical Formulation

**Hill Anisotropic Yield Function**
$$
f(\bm{\sigma}) = \frac{1}{2} \bm{\sigma}^T \mathbf{P}_{\alpha} \bm{\sigma} - \bar{\sigma}^2 = 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.5, p. 246_

**Anisotropic Projection Matrix P_\alpha**
$$
\mathbf{P}_{\alpha} = \begin{bmatrix} 2(\alpha_{31}+\alpha_{12}) & -2\alpha_{12} & -2\alpha_{31} & 0 & 0 & 0 \\ -2\alpha_{12} & 2(\alpha_{23}+\alpha_{12}) & -2\alpha_{23} & 0 & 0 & 0 \\ -2\alpha_{31} & -2\alpha_{23} & 2(\alpha_{31}+\alpha_{23}) & 0 & 0 & 0 \\ 0 & 0 & 0 & 6\alpha_{44} & 0 & 0 \\ 0 & 0 & 0 & 0 & 6\alpha_{55} & 0 \\ 0 & 0 & 0 & 0 & 0 & 6\alpha_{66} \end{bmatrix}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.5, p. 246_

**Backward Euler Anisotropic Stress Update**
$$
\bm{\sigma}_{j+1} = \left( \mathbf{I} + \Delta \lambda \mathbf{D}^e \mathbf{P}_{\alpha} \right)^{-1} \bm{\sigma}^{\mathrm{tr}}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.5, p. 246_

**Fourth-Order Hill Tensor Norm Formulation**
$$
f(\mathbf{T}) = \|\mathbf{T}\|_{\mathbf{H}} - \sqrt{\frac{2}{3}} y_0 = 0, \quad \|\mathbf{T}\|_{\mathbf{H}} = \sqrt{\mathbf{T} : \mathbf{H} : \mathbf{T}}
$$
_Source: Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf p. 287_

**Notation:**
\bm{\sigma}: Cauchy stress vector in Voigt notation; \mathbf{P}_{\alpha}: symmetric anisotropic projection matrix; \alpha_{ij}: anisotropic yield parameters; \bar{\sigma}, y_0: equivalent flow yield stress; \mathbf{D}^e: elastic stiffness matrix; \Delta \lambda: discrete plastic multiplier; \mathbf{H}: fourth-order Hill anisotropy tensor; \mathbf{T}: stress tensor in logarithmic strain space.


## 3. Algorithmic Implementation

**Hill Anisotropic Plasticity Return-Mapping Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given elastic trial stress } \bm{\sigma}^{\mathrm{tr}}, \text{ elastic stiffness matrix } \mathbf{D}^e, \text{ and anisotropic projection matrix } \mathbf{P}_{\alpha}$
\State $f^{\mathrm{tr}} = \frac{1}{2} (\bm{\sigma}^{\mathrm{tr}})^T \mathbf{P}_{\alpha} \bm{\sigma}^{\mathrm{tr}} - \bar{\sigma}_0^2$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}}$
\Return $\text{Step is elastic; accept trial stress}$
\Else
\EndIf
\State $\bm{\sigma}_{n+1} = (\mathbf{I} + \Delta \lambda \mathbf{D}^e \mathbf{P}_{\alpha})^{-1} \bm{\sigma}^{\mathrm{tr}}$
\Return $\text{Return updated anisotropic Cauchy stress } \bm{\sigma}_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.5, p. 246_


## 4. Known Pitfalls

- **Assuming Isotropic Flow in Anisotropic Rolled Sheet Metals**: Applying isotropic J2 von Mises yield criteria to rolled sheet metals miscalculates directional yield strengths and plastic flow, producing errors in localized necking and springback predictions. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.5, p. 246; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf p. 287)_
- **Ill-Conditioned Matrix Inversion in Anisotropic Return Mapping**: Inverting (\mathbf{I} + \Delta \lambda \mathbf{D}^e \mathbf{P}_{\alpha}) without validating positive definiteness of anisotropic matrix \mathbf{P}_{\alpha} causes matrix singular ill-conditioning during local return mapping iterations. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 7.5, p. 246)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf
