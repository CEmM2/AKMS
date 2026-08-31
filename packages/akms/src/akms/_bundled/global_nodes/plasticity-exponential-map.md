---
id: plasticity-exponential-map
title: Exponential Map for $\mathbf{F}^p$ Update
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- finite-strain
- exponential-map
- multiplicative-split
- plastic-incompressibility
status: established
confidence: 0.9
source: hybrid
edges:
- to: kinematics-multiplicative-decomp
  type: requires
  weight: 1.0
- to: tensor-isotropic-functions
  type: requires
  weight: 1.0
- to: kinematics-logarithmic-strain
  type: feeds-into
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Exponential Map for $\mathbf{F}^p$ Update

## Summary

The exponential map integrates plastic deformation gradient updates in finite-strain multiplicative plasticity, preserving exact plastic incompressibility det(F^p) = 1.

## 1. Core Concept

In finite-strain elastoplasticity based on the multiplicative decomposition F = F^e F^p, integrating the plastic velocity gradient rate equation F_dot^p = L_p F^p using standard forward or backward Euler difference schemes leads to numerical volume drift. The exponential map return-mapping algorithm integrates the plastic flow equation over a discrete time step via the matrix exponential F^p_{n+1} = exp(Delta t L_p) F^p_n. For trace-free deviatoric plastic flow (tr L_p = 0), this exponential formulation preserves exact unimodular plastic incompressibility det F^p = 1. In principal elastic strain space, the tensor exponential map simplifies to a linear return mapping on logarithmic elastic strains, enabling exact algorithmic equivalence to infinitesimal return-mapping schemes.

## 2. Mathematical Formulation

**Multiplicative Plastic Deformation Gradient Exponential Update**
$$
\mathbf{F}^p_{n+1} = \exp\left[ \Delta t \dot{\lambda} \mathbf{R}_{e,n+1}^T \cdot \left( \frac{\partial F}{\partial \bm{\tau}} \right)_{n+1} \cdot \mathbf{R}_{e,n+1} \right] \cdot \mathbf{F}^p_n
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 252; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 418, 421_

**Plastic Incompressibility Determinant Preservation**
$$
\mathrm{tr}(\mathbf{L}_p) = 0 \implies \det\left(\mathbf{F}^p_{n+1}\right) = \det\left(\mathbf{F}^p_n\right) = 1
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 252; Simo_Hughes_1998_Computational inelasticity.pdf p. 297_

**Equivalence to Logarithmic Elastic Strain Return Mapping**
$$
\bm{\varepsilon}^e_{n+1} = \bm{\varepsilon}^{e,\mathrm{tr}} - \Delta \lambda \left. \frac{\partial F}{\partial \bm{\tau}} \right|_{n+1}, \quad \bm{\varepsilon}^e = \frac{1}{2}\ln\left(\mathbf{F}^e \cdot \mathbf{F}^{eT}\right)
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 252; Kim_FEA for Elastoplastic Problems.pdf p. 226_

**Left Cauchy-Green Elastic Tensor Spectral Exponential Recovery**
$$
\mathbf{b}^e_{n+1} = \sum_{i=1}^3 \exp\left(2 \varepsilon^e_{i,n+1}\right) \mathbf{m}^i, \quad \mathbf{m}^i = \hat{\mathbf{n}}^i \otimes \hat{\mathbf{n}}^i
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 226, 228; Simo_Hughes_1998_Computational inelasticity.pdf p. 299-300_

**Notation:**
\mathbf{F}^p: plastic deformation gradient tensor; \mathbf{F}^e: elastic deformation gradient tensor; \mathbf{L}_p: plastic velocity gradient tensor; \mathbf{R}_e: elastic rotation tensor; \bm{\tau}: Kirchhoff stress tensor; \Delta \lambda: discrete plastic consistency multiplier; \bm{\varepsilon}^e: logarithmic elastic strain tensor; \bm{\varepsilon}^{e,\mathrm{tr}}: trial logarithmic elastic strain tensor; \mathbf{b}^e: elastic left Cauchy-Green deformation tensor; \varepsilon^e_i: principal logarithmic elastic strain components; \mathbf{m}^i: spectral eigenprojection tensors.


## 3. Algorithmic Implementation

**Multiplicative Finite Strain Exponential Map Return-Mapping Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: total deformation gradient } \mathbf{F}_n, \text{ elastic deformation gradient } \mathbf{F}^e_n, \text{ plastic deformation gradient } \mathbf{F}^p_n, \text{ and displacement increment } \Delta \mathbf{u}$
\State $\mathbf{F}_{n+1} = (\mathbf{I} + \nabla \Delta \mathbf{u}) \mathbf{F}_n, \quad \mathbf{f} = \mathbf{I} + \nabla \Delta \mathbf{u}$
\State $\mathbf{F}^{e,\mathrm{tr}} = \mathbf{f} \mathbf{F}^e_n, \quad \bar{\mathbf{f}} = (\det \mathbf{f})^{-1/3} \mathbf{f}, \quad \mathbf{b}^{e,\mathrm{tr}} = \bar{\mathbf{f}} \mathbf{b}^e_n \bar{\mathbf{f}}^T$
\State $\text{Compute trial principal logarithmic strains } \varepsilon^{e,\mathrm{tr}}_i = \frac{1}{2} \ln(\lambda^{\mathrm{tr}}_i) \text{ from eigenvalues } \lambda^{\mathrm{tr}}_i \text{ of } \mathbf{b}^{e,\mathrm{tr}}$
\State $\bm{\tau}^{\mathrm{tr}} = \mathbf{D}^e : \bm{\varepsilon}^{e,\mathrm{tr}}, \quad f^{\mathrm{tr}} = f(\bm{\tau}^{\mathrm{tr}}, \mathbf{q}_n)$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\mathbf{b}^e_{n+1} = \mathbf{b}^{e,\mathrm{tr}}, \quad \mathbf{F}^p_{n+1} = \mathbf{F}^p_n, \quad \bm{\tau}_{n+1} = \bm{\tau}^{\mathrm{tr}}$
\Return $\text{Step is elastic; return trial state}$
\Else
\EndIf
\State $\varepsilon^e_{i,n+1} = \varepsilon^{e,\mathrm{tr}}_i - \Delta \lambda N_i, \quad \bm{\tau}_{n+1} = \sum_{i=1}^3 \tau^p_{i,n+1} \mathbf{m}^i$
\State $\mathbf{b}^e_{n+1} = \sum_{i=1}^3 \exp(2 \varepsilon^e_{i,n+1}) \mathbf{m}^i, \quad \mathbf{F}^p_{n+1} = \exp\left[ \Delta \lambda \mathbf{N} \right] \cdot \mathbf{F}^p_n$
\Return $\text{Return updated Kirchhoff stress } \bm{\tau}_{n+1}, \text{ elastic left Cauchy-Green tensor } \mathbf{b}^e_{n+1}, \text{ and plastic deformation gradient } \mathbf{F}^p_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 252; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 12.2, p. 421; Simo_Hughes_1998_Computational inelasticity.pdf Box 9.1, p. 299-300_


## 4. Known Pitfalls

- **Volumetric Drift from Standard Linear Difference Integration of Plastic Rate Equations**: Integrating plastic deformation gradient rate equations using standard forward or backward Euler linear updates (F^p_{n+1} = [I + Delta t L_p] F^p_n) fails to preserve det(F^p) = 1, accumulating unphysical volumetric plastic drift under finite strain. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 252; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 414, 418)_
- **Coaxiality Assumption Breakdown in Non-Isotropic Plastic Flow**: Assuming principal axes of elastic left Cauchy-Green tensor b^e and Kirchhoff stress tau remain strictly coaxial during plastic correction introduces kinematic orientation errors under anisotropic hardening or non-associated flow. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 418; Kim_FEA for Elastoplastic Problems.pdf p. 225, 235)_
- **Loss of Frame Invariance from Non-Objective Stress Integration**: Evaluating exponential maps without properly pulling back deformation gradients to rotation-neutralized intermediate frames violates principle of material frame indifference under large rigid body rotations. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 252; Simo_Hughes_1998_Computational inelasticity.pdf p. 295-297)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
