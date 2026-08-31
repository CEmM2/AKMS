---
id: tensor-mandel-notation
title: Mandel Notation & Its Advantages
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- mandel
- kelvin-mandel
- tensor-notation
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-voigt-notation
  type: refines
  weight: 1.0
- to: tensor-products-contractions
  type: requires
  weight: 0.8
- to: tensor-spectral-decomposition
  type: feeds-into
  weight: 1.0
context_size: small
reading_priority: full
content_ref: null
akms_schema: v2
---

# Mandel Notation & Its Advantages

## Summary

In finite-strain continuum mechanics and anisotropic plasticity, Mandel stress measures operate on Mandel's isoclinic intermediate configuration resulting from the multiplicative decomposition of the deformation gradient F = F^e F^p. Matrix-vector representations convert symmetric second-order stress and strain tensors and fourth-order tangent moduli into array forms for computational finite element assembly.

## 1. Core Concept

In non-linear continuum mechanics, constitutive formulations at finite deformations frequently employ Mandel's isoclinic intermediate configuration derived from the multiplicative decomposition F = F^e F^p. The Mandel stress tensor M = C^e S (or M_d) is defined on this intermediate configuration, driving inelastic flow rules and kinematic hardening. For computational implementation, second-order symmetric tensors and fourth-order tangent operators are mapped into matrix-vector formats to evaluate inner products, strain energy rates, and global element stiffness matrices.

## 2. Mathematical Formulation

**Mandel Stress Tensor in Intermediate Configuration**
$$
M_d = 2 \rho_e C_{ps} \frac{\partial \psi_{\mathrm{kin}}}{\partial C_{ps}}
$$
_Source: Generic_anisotropic_thermo-elastoviscoplasticity.pdf, Sec. 3, Eq. 35, p. 127; Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, p. 48_

**Multiplicative Plastic Velocity Gradient in Intermediate Frame**
$$
\dot{F}^p (F^p)^{-1} = \dot{\lambda} \frac{\partial f}{\partial M_d}
$$
_Source: Generic_anisotropic_thermo-elastoviscoplasticity.pdf, Sec. 3, Eq. 36, p. 127; Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, Eq. A.5, p. 48_

**Tensor Double Contraction and Matrix Vector Product**
$$
\boldsymbol{\sigma} : \mathbf{D} = \sigma_{ij} D_{ij} = \{\sigma\}^T \{\varepsilon\}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1, p. 22; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, pp. 777–778_

**Notation:**
{'M_d': 'Mandel stress tensor on the isoclinic intermediate configuration.', 'F^e, F^p': 'Elastic and plastic parts of the multiplicative deformation gradient F = F^e F^p.', '\\boldsymbol{\\sigma}': 'Cauchy stress tensor.', '\\mathbf{D}': 'Rate of deformation tensor.', '\\{\\sigma\\}': 'Vector array representation of stress components.'}


## 3. Algorithmic Implementation

**Evaluation of Mandel Stress and Inelastic Return Mapping in Intermediate Frame**
$$
\begin{algorithmic}
\State $Given trial elastic deformation gradient F^e_0 and plastic deformation gradient F^p$
\State $Compute intermediate configuration metric C_{ps} \gets F^{p-T}_d C^p F^{p-1}_d$
\State $Evaluate Mandel stress tensor M_d \gets 2 \rho_e C_{ps} \frac{\partial \psi_{\mathrm{kin}}}{\partial C_{ps}}$
\State $Evaluate yield function f(M_d, A_I, T) \text{ in intermediate frame}$
\If{$f(M_d, A_I, T) > 0$}
\State $Compute plastic flow direction \frac{\partial f}{\partial M_d} \text{ and update } \dot{F}^p (F^p)^{-1} \gets \dot{\lambda} \frac{\partial f}{\partial M_d}$
\EndIf
\Return $M_d, F^p$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Generic_anisotropic_thermo-elastoviscoplasticity.pdf, Sec. 3, Eqs. 34–36, p. 127; Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, Eqs. A.4–A.5, p. 48_


## 4. Known Pitfalls

- **Evaluating Plastic Flow Outside Mandel Isoclinic Intermediate Frame**: Computing plastic flow rules or yield functions using Cauchy stress in spatial coordinates without pulling back to Mandel's isoclinic intermediate configuration produces thermodynamically inconsistent plastic spin and artificial material anisotropy updates. Mitigation: Formulate inelastic evolution equations directly using Mandel stress M_d on the intermediate frame. _(Source: Generic_anisotropic_thermo-elastoviscoplasticity.pdf, Sec. 1 & Sec. 3, pp. 124, 127)_
- **Mismatched Shear Factor Scalings in Matrix-Vector Tensor Contractions**: Mixing tensor double contractions \sigma_{ij} \varepsilon_{ij} with vector inner products without accounting for off-diagonal engineering shear factors (such as factor 2 in shear strains \gamma_{xy} = 2 \varepsilon_{xy}) corrupts energy calculations and stiffness matrix symmetry. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.3, p. 21; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, pp. 777–778)_

## References

- Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Generic_anisotropic_thermo-elastoviscoplasticity.pdf
