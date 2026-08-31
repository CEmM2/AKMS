---
id: damage-gtn-yield-function
title: GTN Yield Function
domain: computational-mechanics
subdomain: damage
tags:
- damage
- gtn
- porous-plasticity
- yield-function
- tvergaard
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-continuum-framework
  type: refines
  weight: 0.9
- to: plasticity-von-mises
  type: refines
  weight: 0.9
- to: damage-gtn-void-evolution
  type: feeds-into
  weight: 1.0
- to: damage-gtn-return-mapping
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# GTN Yield Function

## Summary

GTN yield function models pressure-dependent porous plasticity by coupling equivalent von Mises stress, hydrostatic pressure, and void volume fraction.

## 1. Core Concept

The Gurson-Tvergaard-Needleman (GTN) yield function extends classical J_2 von Mises plasticity to porous ductile metals by introducing hydrostatic pressure dependence and void volume fraction (porosity) as an isotropic damage parameter. Originally derived by Gurson (1977) via micromechanical analysis of a unit cell containing a spherical void, the yield condition was subsequently modified by Tvergaard and Needleman through parameters q_1, q_2, q_3 to account for inter-void interaction effects. Hydrostatic tension accelerates plastic yield and void expansion, whereas hydrostatic compression suppresses void growth. In the limit of zero porosity, the GTN yield surface reduces identically to the standard von Mises yield criterion.

## 2. Mathematical Formulation

**Gurson-Tvergaard-Needleman Yield Function**
$$
\Phi(\bm{\sigma}, \sigma_0, f) = \frac{q^2}{\sigma_0^2} + 2 q_1 f \cosh\left( \frac{3 q_2 p}{2 \sigma_0} \right) - 1 - q_3 f^2 = 0
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 36; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 229_

**Original Gurson Yield Condition**
$$
\Phi(\bm{\sigma}, \bar{\sigma}, f) = \frac{\sigma_e^2}{\bar{\sigma}^2} + 2 f \cosh\left( \frac{\sigma_k^k}{2 \bar{\sigma}} \right) - 1 - f^2 = 0
$$
_Source: Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf p. 249_

**Normal to the GTN Yield Surface (Flow Direction)**
$$
\bm{N} = \frac{\partial \Phi}{\partial \bm{\sigma}} = \frac{3}{\sigma_0^2} \bm{s} - \frac{q_1 q_2 f}{\sigma_0} \sinh\left( \frac{3 q_2 p}{2 \sigma_0} \right) \mathbf{I}
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 33, 43; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 295-296_

**Pure Matrix von Mises Limit**
$$
\lim_{f \to 0} \Phi(\bm{\sigma}, \sigma_0, f) = \frac{q^2}{\sigma_0^2} - 1 = 0 \implies q = \sigma_0
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 36; Kim_FEA for Elastoplastic Problems.pdf p. 255_

**Notation:**
q: equivalent von Mises stress; p: hydrostatic pressure (-1/3 tr(\bm{\sigma})); \bm{\sigma}: macroscopic Cauchy stress tensor; \bm{s}: deviatoric Cauchy stress tensor; \sigma_0, \bar{\sigma}: matrix yield/flow stress; f: void volume fraction (porosity); q_1, q_2, q_3: Tvergaard GTN constitutive fitting parameters; \bm{N}: plastic flow direction tensor.


## 3. Algorithmic Implementation

**GTN Yield Admissibility Check Algorithm**
$$
\begin{algorithmic}
\State $\text{Given trial stress tensor } \bm{\sigma}^{tr}, \text{ matrix flow stress } \sigma_0, \text{ current porosity } f_n, \text{ and GTN parameters } q_1, q_2, q_3$
\State $p^{tr} = -\frac{1}{3}\mathrm{tr}(\bm{\sigma}^{tr}), \quad \bm{s}^{tr} = \bm{\sigma}^{tr} + p^{tr}\mathbf{I}, \quad q^{tr} = \sqrt{\frac{3}{2}\bm{s}^{tr}:\bm{s}^{tr}}$
\State $\Phi^{tr} = \frac{(q^{tr})^2}{\sigma_0^2} + 2 q_1 f_n \cosh\left( \frac{3 q_2 p^{tr}}{2 \sigma_0} \right) - 1 - q_3 f_n^2$
\If{$\Phi^{tr} \le 0$}
\State $\text{Accept step as purely elastic; set } \bm{\sigma}_{n+1} = \bm{\sigma}^{tr}$
\Return $\text{Return elastic trial state}$
\Else
\EndIf
\Return $\text{Return yield violation state } \Phi^{tr} > 0$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 33, 36; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 234_


## 4. Known Pitfalls

- **Floating-Point Overflow from Rapid Cosh Term Growth**: Evaluating the GTN yield condition \Phi at high hydrostatic tensile pressures without bounding the argument of \cosh(\frac{3 q_2 p}{2 \sigma_0}) causes exponential growth and floating-point overflow during local Newton-Raphson iterations. _(Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 295-296; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 43)_
- **Inappropriate Tvergaard Parameter Calibration Across Material Classes**: Assuming fixed universal values for Tvergaard parameters (q_1, q_2, q_3) across all metals leads to inaccurate yield surface predictions; parameters must be calibrated for specific matrix materials (e.g., q_1 = 1.5, q_2 = 1.15 for steel versus q_1 = 1.25, q_2 = 0.95 for aluminum or copper alloys). _(Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 229; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 297)_
- **Ocurrence of Zero Stress Carrying Capacity at High Porosity Limits**: When void volume fraction reaches f = 1/q_1, all stress components must vanish to satisfy the GTN yield condition (\Phi = 0), causing severe matrix ill-conditioning and singular stiffness matrices unless regulated by phase-field or capping thresholds. _(Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 36; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 294-297)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf
