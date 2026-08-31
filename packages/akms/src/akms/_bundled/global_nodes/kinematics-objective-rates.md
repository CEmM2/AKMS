---
id: kinematics-objective-rates
title: Objective Stress Rates
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- objectivity
- stress-rates
status: established
confidence: 0.9
source: hybrid
edges:
- to: kinematics-velocity-gradient
  type: requires
  weight: 1.0
- to: stress-cauchy-kirchhoff
  type: requires
  weight: 1.0
- to: kinematics-lie-derivative
  type: feeds-into
  weight: 1.0
- to: kinematics-corotational-update
  type: feeds-into
  weight: 1.0
- to: stress-tangent-push-forward
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Objective Stress Rates

## Summary

Objective stress rates modify the material time derivative of Eulerian stress tensors to guarantee frame indifference under rigid-body rotations. Common formulations include the Jaumann rate, Green-Naghdi rate, Truesdell rate, and convected (Oldroyd) rates, which frame rate-type hypoelastic and elastoplastic constitutive laws in finite-deformation continuum mechanics.

## 1. Core Concept

In finite-strain continuum mechanics, rate-type constitutive laws relate stress rate measures to the rate of deformation tensor D. Simply taking the ordinary material time derivative of Cauchy stress \dot{\sigma} violates principle of material frame indifference because rigid-body rotations induce fictitious stress changes. Objective stress rates eliminate rotational contributions by subtracting spin-induced corotational terms or Lie derivative frame transformations. The Jaumann rate utilizes the continuum spin tensor W, but suffers from artificial stress oscillations in monotonic simple shear. The Green-Naghdi rate uses the rigid rotation tensor R from polar decomposition F = R U, eliminating shear oscillations. The Truesdell and Lie rates incorporate velocity gradient or metric transformation terms to maintain geometric invariance during finite stretching.

## 2. Mathematical Formulation

**Jaumann Objective Stress Rate**
$$
\sigma^{\nabla J} = \dot{\sigma} - W \sigma + \sigma W
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 3.5, p. 137; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.2, p. 372; Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, Eq. A.2–A.3, pp. 47–48_

**Green-Naghdi Objective Stress Rate**
$$
\sigma^{\nabla \mathrm{GN}} = \dot{\sigma} - \Omega_{\mathrm{GN}} \sigma + \sigma \Omega_{\mathrm{GN}}, \quad \Omega_{\mathrm{GN}} = \dot{R} R^T
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 3.5, p. 137; Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, Eq. A.3, p. 48; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.2, p. 372_

**Truesdell Objective Stress Rate**
$$
\sigma^{\nabla T} = \dot{\sigma} - L \sigma - \sigma L^T + \sigma \mathrm{tr}(D)
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 3.5, p. 137; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 12.1, Eq. 12.19, p. 403_

**Convected (Oldroyd) Kirchhoff Stress Rate**
$$
\tau^{\nabla c} = \dot{\tau}_{ij} g^i \otimes g^j
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, p. 779; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Sec. 4.3, p. 23_

**Notation:**
{'\\sigma': 'Cauchy stress tensor.', '\\dot{\\sigma}': 'Material time derivative of Cauchy stress tensor.', '\\sigma^{\\nabla J}': 'Jaumann objective rate of Cauchy stress.', '\\sigma^{\\nabla \\mathrm{GN}}': 'Green-Naghdi objective rate of Cauchy stress.', '\\sigma^{\\nabla T}': 'Truesdell objective rate of Cauchy stress.', 'L': 'Spatial velocity gradient tensor L = \\nabla v.', 'W': 'Spin tensor W = \\mathrm{skw}(L).', 'D': 'Rate of deformation tensor D = \\mathrm{sym}(L).', 'R': 'Proper orthogonal rotation tensor from polar decomposition F = R U.'}


## 3. Algorithmic Implementation

**Explicit Hypoelastic Objective Stress Rate Integration Step**
$$
\begin{algorithmic}
\State $Given current spatial velocity gradient L = \nabla v and Cauchy stress \sigma_n$
\State $Extract rate of deformation D \gets \frac{1}{2}(L + L^T) \text{ and spin tensor } W \gets \frac{1}{2}(L - L^T)$
\If{$Objective rate is Jaumann rate$}
\State $Compute spin tensor \Omega \gets W$
\Else
\EndIf
\State $Evaluate elastic stress rate \dot{\sigma}^{\circ} \gets C^{\mathrm{e}} : D$
\State $Compute Cauchy stress time derivative \dot{\sigma} \gets \dot{\sigma}^{\circ} + \Omega \sigma_n - \sigma_n \Omega$
\State $Update Cauchy stress \sigma_{n+1} \gets \sigma_n + \Delta t \, \dot{\sigma}$
\Return $\sigma_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 12.1, p. 415; Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, p. 47_


## 4. Known Pitfalls

- **Spurious Stress Oscillations in Monotonic Simple Shear under Jaumann Rate**: Integrating hypoelastic constitutive models using the Jaumann stress rate during large monotonic simple shear produces non-physical sinusoidal oscillations in shear and normal stresses. Mitigation: Substitute the Green-Naghdi stress rate based on polar rotation R or adopt hyperelastic-plastic multiplicative stress formulations. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.2, p. 372 & Sec. 12.4, Fig. 12.2, p. 414; Rashid - 1993 - Incremental kinematics for finite element applications.pdf, Sec. 2, p. 3941)_
- **Loss of Frame Indifference from Material Time Derivatives**: Directly integrating the material time derivative of Cauchy stress \dot{\sigma} in finite deformation analysis violates material frame indifference (objectivity), generating unphysical stresses during rigid-body rotation. Mitigation: Express rate constitutive equations using objective stress rates (such as Jaumann, Green-Naghdi, or Truesdell rates) or corotational frame updates. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 3.5, p. 137; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Sec. 4.1–4.3, pp. 21–23)_

## References

- Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf
- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Rashid - 1993 - Incremental kinematics for finite element applications.pdf
