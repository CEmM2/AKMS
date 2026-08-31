---
id: fem-locking-remedies
title: Volumetric & Shear Locking Remedies
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- locking
- b-bar
- f-bar
- eas
status: established
confidence: 0.9
source: hybrid
edges:
- to: fem-isoparametric-mapping
  type: requires
  weight: 0.9
- to: kinematics-motion-deformation-gradient
  type: requires
  weight: 0.9
- to: fem-mixed-methods
  type: refines
  weight: 0.9
- to: fem-hourglass-control
  type: feeds-into
  weight: 0.8
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Volumetric & Shear Locking Remedies

## Summary

Volumetric and shear locking occur in fully-integrated lower-order finite elements subjected to incompressibility constraints or bending-dominated states. Remedies include the B-bar and F-bar methods, which modify volumetric strain and deformation gradient fields, and Enhanced Assumed Strain (EAS) methods, which introduce discontinuous incompatible strain modes that are statically condensed at the element level.

## 1. Core Concept

Finite element locking arises when kinematically constrained displacement fields (such as incompressibility \det\mathbf{F}=1 or pure bending shear constraints) cause artificial stiffening and overly constraint-dominated responses in lower-order isoparametric elements. The B-bar method replaces the volumetric strain-displacement operator with a modified or averaged volumetric B-matrix \bar{\mathbf{B}}. In finite deformation analysis, the F-bar method replaces the deformation gradient with a modified deformation gradient \bar{\mathbf{F}} combining volumetric centroid evaluations with local isochoric deformations. Enhanced Assumed Strain (EAS) methods supplement the displacement-derived strain tensor with additional incompatible strain fields \mathbf{G}\boldsymbol{\alpha} that are discontinuous across element boundaries, allowing element-level static condensation of parameters \boldsymbol{\alpha}.

## 2. Mathematical Formulation

**B-Bar Strain-Displacement Operator**
$$
\bar{\mathbf{B}} = \mathbf{B}^{\mathrm{dev}} + \bar{\mathbf{B}}^{\mathrm{vol}}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 7.6, p. 275; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.5.8, Eq. 8.5.38, p. 510_

**F-Bar Modified Deformation Gradient**
$$
\bar{\mathbf{F}} = \left( \frac{\det \mathbf{F}_0}{\det \mathbf{F}} \right)^{1/3} \mathbf{F}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.9, Eq. 11.146, p. 396_

**Enhanced Assumed Strain Field**
$$
\boldsymbol{\varepsilon} = \mathbf{B}\mathbf{a} + \mathbf{G}\boldsymbol{\alpha}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 6.5, Eq. 6.72 & 6.73, p. 192_

**Hu-Washizu Orthogonality Condition for EAS**
$$
\int_{V_e} \boldsymbol{\sigma} : \mathbf{G} \, \mathrm{d}V = 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 6.5, Eq. 6.63 & 6.64, p. 192_

**Notation:**
{'\\bar{\\mathbf{B}}': 'Modified strain-displacement matrix in B-bar formulation.', '\\mathbf{B}^{\\mathrm{dev}}': 'Deviatoric strain-displacement matrix.', '\\bar{\\mathbf{B}}^{\\mathrm{vol}}': 'Averaged or modified volumetric strain-displacement matrix.', '\\mathbf{F}': 'Deformation gradient tensor.', '\\bar{\\mathbf{F}}': 'Modified deformation gradient in F-bar method.', '\\mathbf{F}_0': 'Deformation gradient evaluated at element centroid \\boldsymbol{\\xi}_0.', '\\mathbf{G}': 'Interpolation matrix for enhanced assumed strain modes.', '\\boldsymbol{\\alpha}': 'Vector of internal enhanced strain parameters condensed at element level.'}


## 3. Algorithmic Implementation

**Element-Level Static Condensation for EAS Formulations**
$$
\begin{algorithmic}
\State $Given element displacement vector a and internal enhanced parameters \boldsymbol{\alpha}$
\State $Evaluate element submatrices K_{aa} \gets \int_{V_e} \mathbf{B}^T \mathbf{D}^e \mathbf{B} \, \mathrm{d}V, \quad K_{a\alpha} \gets \int_{V_e} \mathbf{B}^T \mathbf{D}^e \mathbf{G} \, \mathrm{d}V, \quad K_{\alpha\alpha} \gets \int_{V_e} \mathbf{G}^T \mathbf{D}^e \mathbf{G} \, \mathrm{d}V$
\State $Solve internal parameters \Delta \boldsymbol{\alpha} \gets -K_{\alpha\alpha}^{-1} (f_{\alpha}^{\mathrm{int}} + K_{\alpha a} \Delta \mathbf{a})$
\State $Compute condensed element stiffness matrix K_e^c \gets K_{aa} - K_{a\alpha} K_{\alpha\alpha}^{-1} K_{\alpha a}$
\State $Compute condensed internal force vector f_{e,\mathrm{int}}^c \gets f_{a,\mathrm{int}} - K_{a\alpha} K_{\alpha\alpha}^{-1} f_{\alpha,\mathrm{int}}$
\Return $K_e^c, f_{e,\mathrm{int}}^c$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 6.2, p. 194 & Sec. 6.5, p. 197_


## 4. Known Pitfalls

- **Spurious Kinematic Modes in Reduced Integration**: Applying uniform under-integration (reduced Gaussian quadrature) to eliminate locking introduces rank deficiency and unconstrained zero-energy modes (hourglassing). Mitigation: Use selective reduced integration (under-integrating only volumetric/shear terms), B-bar/F-bar methods, or add hourglass stabilization. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 7.6, pp. 273–275; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.4.3, p. 499)_
- **Loss of Frame Invariance in Naive F-Bar Formulations**: Evaluating volumetric deformation scaling improperly in large-strain problems can violate objective frame indifference or distort large shear deformations. Mitigation: Decompose the deformation gradient multiplicatively into isochoric and volumetric parts before modifying the volumetric Jacobian det(F). _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.9, pp. 395–396)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
