---
id: fem-mixed-methods
title: Mixed Variational Formulations
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- mixed-methods
- hu-washizu
- hellinger-reissner
- inf-sup
status: established
confidence: 0.9
source: hybrid
edges:
- to: fem-weak-form-derivation
  type: refines
  weight: 1.0
- to: fem-locking-remedies
  type: refines
  weight: 0.9
- to: fem-shape-functions
  type: requires
  weight: 0.8
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Mixed Variational Formulations

## Summary

Mixed variational formulations introduce independent approximations for multiple continuum fields—such as displacements, stresses, strains, or hydrostatic pressure—to circumvent volumetric locking and shear locking in near-incompressible or constrained solid mechanics problems.

## 1. Core Concept

Conventional single-field displacement finite element methods suffer from volumetric locking in incompressible or nearly incompressible states because kinematic volumetric constraints overly restrict displacement shape functions. Mixed variational methods overcome this by treating pressure, stress, or strain as independent fields alongside displacements within multi-field weak forms derived from Hu-Washizu or two-field u-p principles. Stationarity conditions generate coupled systems of equations. When pressure or strain approximations are discontinuous across element boundaries, internal variables are statically condensed at the element level prior to global assembly. Stable mixed discretizations require a suitable ratio between displacement and pressure degrees of freedom to avoid spurious pressure modes.

## 2. Mathematical Formulation

**Hu-Washizu Three-Field Weak Form**
$$
\int_V \delta \boldsymbol{\sigma} : (\nabla \mathbf{u} - \boldsymbol{\varepsilon}) \, \mathrm{d}V + \int_V \delta \boldsymbol{\varepsilon} : (\boldsymbol{\sigma} - \boldsymbol{\sigma}^e) \, \mathrm{d}V + \int_V \nabla(\delta \mathbf{u}) : \boldsymbol{\sigma} \, \mathrm{d}V = \int_V \delta \mathbf{u} \cdot \mathbf{b} \, \mathrm{d}V + \int_\Gamma \delta \mathbf{u} \cdot \bar{\mathbf{t}} \, \mathrm{d}\Gamma
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 6.6, Eqs. 6.56–6.58, p. 191; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.5.2, Eqs. 8.5.2–8.5.4, p. 501_

**Two-Field Displacement-Pressure Weak Form (u-p Formulation)**
$$
\int_{V_0} \delta \boldsymbol{\varepsilon}^{\mathrm{dev}} : \boldsymbol{\tau}^{\mathrm{dev}} \, \mathrm{d}V_0 + \int_{V_0} \delta(\mathrm{tr}\,\boldsymbol{\varepsilon}) p \, \mathrm{d}V_0 + \int_{V_0} \delta p \left( \frac{\partial W^*}{\partial p} - \mathrm{tr}\,\boldsymbol{\varepsilon} \right) \mathrm{d}V_0 = \delta W^{\mathrm{ext}}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.10, Eqs. 11.116–11.117, p. 391; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.5.5, p. 505_

**Discrete Degree-of-Freedom Ratio for u-p Stability**
$$
r = \frac{n_{\mathrm{dof}}}{n_p}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.4, p. 393_

**Notation:**
{'\\mathbf{u}': 'Displacement vector field.', '\\boldsymbol{\\varepsilon}': 'Independent or derived strain tensor.', '\\boldsymbol{\\sigma}': 'Independent or derived Cauchy/Piola stress tensor.', 'p': 'Independent hydrostatic pressure scalar field.', 'W^*': 'Complementary strain energy density function for volumetric response.', 'r': 'Ratio of displacement degrees of freedom to pressure degrees of freedom.'}


## 3. Algorithmic Implementation

**Element-Level Pressure Condensation for Mixed u-p Formulation**
$$
\begin{algorithmic}
\State $Given element displacement vector u_e and element pressure parameter vector p_e$
\State $Evaluate coupled element submatrices K_{uu} \gets \int_{V_e} B_{\mathrm{dev}}^T D^{\mathrm{dev}} B_{\mathrm{dev}} \, \mathrm{d}V, \quad L_{up} \gets \int_{V_e} B_{\mathrm{vol}}^T N_p \, \mathrm{d}V, \quad M_{pp} \gets \int_{V_e} N_p^T \left( \frac{1}{K} \right) N_p \, \mathrm{d}V$
\If{$Pressure field p_e is discontinuous across element boundaries (element-wise pressure)$}
\State $Solve local pressure increment \Delta p_e \gets M_{pp}^{-1} (-r_p - L_{up}^T \Delta u_e)$
\State $Construct condensed element stiffness matrix K_e^c \gets K_{uu} + L_{up} M_{pp}^{-1} L_{up}^T$
\State $Construct condensed element force vector f_e^c \gets f_u^{\mathrm{ext}} - f_u^{\mathrm{int}} + L_{up} M_{pp}^{-1} r_p$
\EndIf
\Return $K_e^c, f_e^c$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.5.6, pp. 507–508; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.4, p. 393_


## 4. Known Pitfalls

- **Spurious Pressure Oscillations and Mode Instability**: Selecting equal-order or improper interpolation orders for displacement and pressure fields (such as Q1-Q1 or Q2/1 with excessive pressure DOFs) leads to ill-conditioned or rank-deficient pressure submatrices, generating non-physical checkerboard pressure oscillations. Mitigation: Ensure the element displacement-to-pressure degree-of-freedom ratio r = n_dof / n_p is sufficiently large (e.g., using 8/1 or 20/4 elements, or 4-node quads with constant pressure). _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 7.6, p. 273 & Box 11.4, p. 393; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.4.3, p. 499)_
- **Inability to Condense Continuous Pressure Fields**: Choosing continuous inter-element pressure approximations prevents element-level static condensation of pressure degrees of freedom, significantly increasing global matrix bandwidth and solver size. Mitigation: Use element-wise discontinuous pressure interpolations (such as piecewise constant pressure), enabling element-level elimination prior to global assembly. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.5.6, p. 507; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.4, p. 393)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
