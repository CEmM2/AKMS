---
id: stress-tangent-push-forward
title: Push-Forward of 4th-Order Tangent
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- tangent-moduli
- fourth-order
status: established
confidence: 0.9
source: hybrid
edges:
- to: stress-push-forward-pull-back
  type: requires
  weight: 1.0
- to: tensor-derivatives-tensors
  type: requires
  weight: 1.0
- to: tensor-voigt-notation
  type: requires
  weight: 0.7
- to: kinematics-objective-rates
  type: feeds-into
  weight: 1.0
- to: plasticity-consistent-tangent-general
  type: feeds-into
  weight: 1.0
- to: fem-tl-linearization
  type: feeds-into
  weight: 0.9
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Push-Forward of 4th-Order Tangent

## Summary

The push-forward of a fourth-order material tangent modulus tensor maps Second Piola-Kirchhoff constitutive relations from reference material space to spatial Eulerian coordinate frames. This transformation contracts four legs of the deformation gradient tensor with the material tangent tensor, scaling by the Jacobian determinant to yield consistent spatial Kirchhoff or Cauchy stress tangent tensors for non-linear finite element linearizations.

## 1. Core Concept

In finite-strain solid mechanics, rate-type constitutive updates and Newton-Raphson tangent stiffness matrices require converting material constitutive tensors defined in the reference domain (such as \(C^{SE}_{mnpq} = \partial S_{mn} / \partial E_{pq}\)) into spatial tangent tensors defined in the current configuration. The push-forward transformation \(\phi_*\) maps each index of the fourth-order material tensor through the deformation gradient tensor \(F\). Pushing forward \(C^{SE}\) yields the fourth-order spatial Kirchhoff tangent tensor \(C^{\tau}_{ijkl} = F_{im} F_{jn} F_{kp} F_{lq} C^{SE}_{mnpq}\). Dividing by the volume Jacobian \(J = \det F\) delivers the Truesdell Cauchy stress tangent tensor \(C^{\sigma T}_{ijkl}\), which can be adjusted via stress-dependent terms to yield spatial tangent tensors corresponding to Jaumann or Green-Naghdi objective stress rates.

## 2. Mathematical Formulation

**Push-Forward of Fourth-Order Material Tangent to Kirchhoff Tangent**
$$
C^{\tau}_{ijkl} = F_{im} F_{jn} F_{kp} F_{lq} C^{SE}_{mnpq}
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 5.16 & Eq. 5.10.44, pp. 315–316; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Sec. 4.5 & Box 3, pp. 5389–5390_

**Cauchy Stress Truesdell Spatial Tangent Modulus**
$$
C^{\sigma T}_{ijkl} = \frac{1}{J} C^{\tau}_{ijkl} = \frac{1}{J} F_{im} F_{jn} F_{kp} F_{lq} C^{SE}_{mnpq}
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 5.1, p. 245 & Box 6.5, p. 364; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.1, Eq. 12.19, pp. 403–404_

**Geometric Push-Forward Operator Duality**
$$
\mathcal{H} = \phi_* C^{SE}, \quad \mathcal{H}_{ijkl} = F_{im} F_{jn} F_{kp} F_{lq} C^{SE}_{mnpq}
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 5.10.2, Eqs. 5.10.43–5.10.44, p. 316; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.3, p. 37_

**Conversion Between Truesdell and Jaumann Spatial Tangents**
$$
C^{\sigma J}_{ijkl} = C^{\sigma T}_{ijkl} + \frac{1}{2}(\sigma_{ik} \delta_{jl} + \sigma_{il} \delta_{jk} + \delta_{ik} \sigma_{jl} + \delta_{il} \sigma_{jk})
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 5.1, p. 245; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.1, Eq. 12.22 & Sec. 12.3, p. 412_

**Notation:**
{'C^{SE}_{mnpq}': 'Fourth-order material tangent constitutive tensor in reference domain.', 'C^{\\tau}_{ijkl}': 'Fourth-order Kirchhoff spatial tangent modulus tensor.', 'C^{\\sigma T}_{ijkl}': 'Fourth-order spatial tangent tensor for Truesdell rate of Cauchy stress.', 'C^{\\sigma J}_{ijkl}': 'Fourth-order spatial tangent tensor for Jaumann rate of Cauchy stress.', 'F_{im}': 'Deformation gradient tensor component mapping reference to spatial coordinates.', 'J': 'Jacobian determinant J = det F.', '\\sigma_{ij}': 'Cauchy stress tensor component.', '\\delta_{ij}': 'Kronecker delta identity tensor.'}


## 3. Algorithmic Implementation

**Fourth-Order Tangent Modulus Push-Forward Computation Algorithm**
$$
\begin{algorithmic}
\State $Given 4th-order material tangent C^{SE}_{mnpq}, deformation gradient F_{ij}, and Jacobian J = \det F$
\For{$i \gets 1 \text{ to } 3$}
\For{$j \gets 1 \text{ to } 3$}
\For{$k \gets 1 \text{ to } 3$}
\For{$l \gets 1 \text{ to } 3$}
\State $Evaluate Kirchhoff tangent component C^{\tau}_{ijkl} \gets \sum_{m=1}^3 \sum_{n=1}^3 \sum_{p=1}^3 \sum_{q=1}^3 F_{im} F_{jn} F_{kp} F_{lq} C^{SE}_{mnpq}$
\State $Evaluate Truesdell Cauchy tangent component C^{\sigma T}_{ijkl} \gets \frac{1}{J} C^{\tau}_{ijkl}$
\EndFor
\EndFor
\EndFor
\EndFor
\Return $C^{\tau}, C^{\sigma T}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 5.1, p. 245 & Box 6.5, p. 364; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.1, pp. 403–404_


## 4. Known Pitfalls

- **Confusing Spatial Tangent Moduli across Different Objective Rates**: Applying a material tangent C^{SE} or Truesdell spatial tangent C^{\sigma T} directly in a finite element formulation that uses the Jaumann rate causes inconsistent linearization and loss of quadratic Newton convergence. Mitigation: Transform tangent moduli using exact rate-conversion relations, such as C^{\sigma J}_{ijkl} = C^{\sigma T}_{ijkl} + \frac{1}{2}(\sigma_{ik}\delta_{jl} + \sigma_{il}\delta_{jk} + \delta_{ik}\sigma_{jl} + \delta_{il}\sigma_{jk}). _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 5.1, p. 245 & Box 6.6, p. 375; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.1, Eq. 12.22, p. 406)_
- **Omitting Geometric Stiffness Terms During Linearization**: Using only the pushed-forward material tangent K^{\mathrm{mat}} in Updated or Total Lagrangian Newton-Raphson solvers while ignoring initial-stress geometric stiffness terms K^{\mathrm{geo}} = \mathbf{I} \int_{\Omega} \mathbf{B}_I^T \boldsymbol{\sigma} \mathbf{B}_J \, \mathrm{d}\Omega destroys quadratic convergence in finite strain analyses. Mitigation: Include both material stiffness K^{\mathrm{mat}} and geometric stiffness K^{\mathrm{geo}} when forming the global Jacobian matrix. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 6.5, p. 364; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.4.1, Eqs. 3.99–3.102, pp. 94–96)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf
