---
id: kinematics-corotational-update
title: Corotational Stress Update Algorithms
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- corotational
- hughes-winget
status: established
confidence: 0.9
source: hybrid
edges:
- to: kinematics-objective-rates
  type: requires
  weight: 1.0
- to: kinematics-velocity-gradient
  type: requires
  weight: 0.9
- to: kinematics-polar-decomposition
  type: requires
  weight: 0.8
- to: plasticity-general-return-mapping
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Corotational Stress Update Algorithms

## Summary

Corotational stress update algorithms integrate rate-type constitutive equations under large finite rotations by transforming stress and internal state variables into a corotating reference frame. By applying an incrementally objective proper orthogonal rotation operator (such as the Hughes-Winget midpoint formula), these algorithms isolate rigid-body rotation from material stretching, preventing spurious stress generation during pure rotational motion.

## 1. Core Concept

In finite-strain solid mechanics, rate-type constitutive equations require integration schemes that maintain incremental objectivity under large rigid-body rotations. Standard forward Euler integration fails under finite rotations, producing unphysical stress oscillations. Corotational update algorithms overcome this by factorizing incremental motion into a rigid rotation followed or preceded by material stretching. First, the stress and internal state variables from the previous step are rotated into a corotating frame via a proper orthogonal rotation matrix Q. Second, a standard small-strain constitutive update or return-mapping algorithm computes stress increments from the midpoint rate-of-stretching tensor. Finally, updated stresses are back-rotated or stored in the current spatial configuration.

## 2. Mathematical Formulation

**Hughes-Winget Midpoint Incremental Rotation Operator**
$$
Q = \left(I - \frac{1}{2} \omega\right)^{-1} \left(I + \frac{1}{2} \omega\right)
$$
_Source: Hughes and Winget - 1980 - Finite rotation effects in numerical integration of rate constitutive equations arising in large‐def.pdf, Eqs. 10 & 13, p. 1864; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Prop. 5.4, p. 24_

**Rotated Stress Predictor Transformation**
$$
\bar{\sigma}_{n+1} = Q \sigma_n Q^T, \quad \bar{\alpha}_{n+1} = Q \alpha_n Q^T
$$
_Source: Hughes and Winget - 1980 - Finite rotation effects in numerical integration of rate constitutive equations arising in large‐def.pdf, Eqs. 11–12, p. 1864; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Def. 5.10, p. 24_

**Midpoint Strain Increment and Stress Update**
$$
\gamma = \frac{1}{2}\left(G + G^T\right), \quad \Delta \sigma = c : \gamma, \quad \sigma_{n+1} = \bar{\sigma}_{n+1} + \Delta \sigma
$$
_Source: Hughes and Winget - 1980 - Finite rotation effects in numerical integration of rate constitutive equations arising in large‐def.pdf, Eqs. 9 & 11–14, p. 1864; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Alg. 1, p. 25_

**Explicit Closed-Form Vector Rotation Expression**
$$
Q = I + \frac{\omega_m}{1 + \frac{1}{4} \theta_m \cdot \theta_m} \left(I + \frac{1}{2} \omega_m\right)
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.4, Eq. 12.86, p. 417; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 9.5.18, Eq. 9.5.56, p. 556_

**Notation:**
{'G': 'Spatial gradient of the displacement increment evaluated at midpoint configuration.', '\\gamma': 'Symmetric midpoint strain increment tensor.', '\\omega': 'Skew-symmetric midpoint spin increment tensor.', 'Q': 'Proper orthogonal rotation tensor (Q^T Q = I).', '\\sigma_n, \\sigma_{n+1}': 'Cauchy stress tensor at step n and step n+1.', '\\bar{\\sigma}_{n+1}': 'Stress tensor rotated by Q prior to constitutive integration.', '\\alpha_n, \\bar{\\alpha}_{n+1}': 'Vector/tensor of material internal state variables before and after rotation.'}


## 3. Algorithmic Implementation

**Hughes-Winget Corotational Stress Update Algorithm**
$$
\begin{algorithmic}
\State $Given current configuration x_n, displacement increment \Delta u, Cauchy stress \sigma_n, and state variables \alpha_n$
\State $Compute midpoint displacement gradient G \gets \frac{\partial \Delta u}{\partial x_{n+1/2}}$
\State $Compute midpoint strain increment \gamma \gets \frac{1}{2}(G + G^T) \text{ and spin increment } \omega \gets \frac{1}{2}(G - G^T)$
\State $Compute orthogonal incremental rotation Q \gets \left(I - \frac{1}{2}\omega\right)^{-1}\left(I + \frac{1}{2}\omega\right)$
\State $Rotate stress and state variables: \bar{\sigma} \gets Q \sigma_n Q^T \text{ and } \bar{\alpha} \gets Q \alpha_n Q^T$
\State $Evaluate small-strain constitutive update using \gamma, \bar{\sigma}, \bar{\alpha} \text{ to obtain stress increment } \Delta \sigma$
\State $Update Cauchy stress \sigma_{n+1} \gets \bar{\sigma} + \Delta \sigma$
\Return $\sigma_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Hughes and Winget - 1980 - Finite rotation effects in numerical integration of rate constitutive equations arising in large‐def.pdf, Eqs. 11–14, p. 1864; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Alg. 1, p. 25_


## 4. Known Pitfalls

- **Spurious Straining Under Finite Rigid-Body Rotations**: Integrating rate constitutive equations without proper incremental rotation neutrality causes false stress generation under pure rigid-body rotation. Mitigation: Use incrementally objective rotation operators, such as the Hughes-Winget midpoint rotation Q = (I - 1/2 \omega)^{-1}(I + 1/2 \omega), which guarantees exact energy conservation and zero stress updates during rigid motions. _(Source: Hughes and Winget - 1980 - Finite rotation effects in numerical integration of rate constitutive equations arising in large‐def.pdf, pp. 1864–1865; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.4, pp. 415–417)_
- **Kinematic Coupling Errors Under Combined Large Stretch and Rotation**: Assuming constant velocity gradients over a finite time step induces kinematic coupling between stretching and rotation in midpoint corotational updates when rotation increments are large (\theta > 30^\circ). Mitigation: Sub-increment large time steps or use strongly objective rate-of-stretching expansions. _(Source: Rashid - 1993 - Incremental kinematics for finite element applications.pdf, Sec. 4, pp. 3947–3948; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.4, p. 417)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Hughes and Winget - 1980 - Finite rotation effects in numerical integration of rate constitutive equations arising in large‐def.pdf
- Rashid - 1993 - Incremental kinematics for finite element applications.pdf
