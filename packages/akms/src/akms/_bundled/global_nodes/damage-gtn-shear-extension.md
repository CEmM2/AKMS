---
id: damage-gtn-shear-extension
title: GTN Shear Modifications (Nahshon-Hutchinson)
domain: computational-mechanics
subdomain: damage
tags:
- damage
- gtn
- nahshon-hutchinson
- shear-damage
- lode-angle
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-gtn-void-evolution
  type: refines
  weight: 1.0
- to: damage-gtn-yield-function
  type: requires
  weight: 0.9
- to: plasticity-lode-triaxiality
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# GTN Shear Modifications (Nahshon-Hutchinson)

## Summary

GTN shear modifications extend the classical Gurson-Tvergaard-Needleman model to account for shear-dominated void growth using a Lode parameter-dependent evolution rule.

## 1. Core Concept

Classical Gurson-Tvergaard-Needleman (GTN) porous plasticity models void growth solely driven by volumetric hydrostatic plastic dilation, predicting zero void growth under pure shear stress states (zero triaxiality). The Nahshon-Hutchinson extension modifies the void volume fraction rate equation by introducing a Lode-angle-dependent shear void growth term. Governed by a dimensionless shear coefficient k_w and a stress-state parameter \omega(\bm{\sigma}) = 1 - L^2, this modification enables void growth under low-triaxiality shear loading paths while preserving classical GTN behavior under axisymmetric tension and compression.

## 2. Mathematical Formulation

**Augmented GTN Void Volume Fraction Evolution Rate**
$$
\dot{f} = \dot{f}_{growth} + \dot{f}_{nucleation} + \dot{f}_{shear}
$$
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 234; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 297-298_

**Nahshon-Hutchinson Shear Void Growth Evolution Rule**
$$
\dot{f}_{shear} = k_w f \omega(\bm{\sigma}) \dot{\bar{\varepsilon}}^p, \quad \omega(\bm{\sigma}) = 1 - \left(\frac{27 J_3}{2 \sigma_{eq}^3}\right)^2 = 1 - L^2
$$
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 234; Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 609_

**Normalized Lode Parameter Definition**
$$
L = \frac{27 J_3}{2 \sigma_{eq}^3} = \frac{2 \sigma_2 - \sigma_1 - \sigma_3}{\sigma_1 - \sigma_3}
$$
_Source: Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 609; Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 536_

**Lode Stress-State Parameter Bounds**
$$
\omega(\bm{\sigma}) = 1 - L^2 \in [1]
$$
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 234; Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 609_

**Notation:**
\dot{f}: total void volume fraction rate; \dot{f}_{growth}: volumetric void growth rate; \dot{f}_{nucleation}: void nucleation rate; \dot{f}_{shear}: shear void growth rate; k_w: shear void growth parameter; f: void volume fraction; \omega(\bm{\sigma}): Lode stress-state function; L: normalized Lode parameter; J_3: third invariant of deviatoric stress tensor \bm{s}; \sigma_{eq}: equivalent von Mises stress; \sigma_1, \sigma_2, \sigma_3: principal Cauchy stresses; \dot{\bar{\varepsilon}}^p: equivalent matrix plastic strain rate.


## 3. Algorithmic Implementation

**GTN Shear Extension Void Evolution Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given stress tensor } \bm{\sigma}_{n+1}, \text{ current porosity } f_n, \text{ matrix plastic strain increment } \Delta \bar{\varepsilon}^p, \text{ and shear growth parameter } k_w$
\State $\bm{s} = \bm{\sigma}_{n+1} - \frac{1}{3}\mathrm{tr}(\bm{\sigma}_{n+1})\mathbf{I}, \quad \sigma_{eq} = \sqrt{\frac{3}{2}\bm{s}:\bm{s}}, \quad J_3 = \det(\bm{s})$
\If{$\sigma_{eq} > 0$}
\State $L = \frac{27 J_3}{2 \sigma_{eq}^3}, \quad \omega(\bm{\sigma}) = 1 - L^2$
\Else
\EndIf
\State $\Delta f_{growth} = (1 - f_n) \Delta \varepsilon_p$
\State $\Delta f_{shear} = k_w f_n \omega(\bm{\sigma}) \Delta \bar{\varepsilon}^p$
\State $\Delta f_{nuc} = A_{nuc} \Delta \bar{\varepsilon}^p$
\State $f_{n+1} = f_n + \Delta f_{growth} + \Delta f_{shear} + \Delta f_{nuc}$
\Return $\text{Return updated void volume fraction } f_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 234, 238; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 297-298_


## 4. Known Pitfalls

- **Indeterminacy of Lode Parameter at Purely Hydrostatic States**: Evaluating the Lode parameter L = 27 J_3 / (2 \sigma_{eq}^3) as equivalent stress approaches zero (\sigma_{eq} \to 0) causes division by zero; implementations must set \omega(\bm{\sigma}) = 0 when \sigma_{eq} falls below a numerical tolerance. _(Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 234; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 34)_
- **Overpredicting Softening in Complex Low-Triaxiality Stress Paths**: Calibrating the shear growth parameter k_w solely on simple shear experiments can overestimate void growth and premature material softening during combined shear-compression or non-proportional loading paths. _(Source: Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 558, 567; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 297)_
- **Spurious Void Creation in Void-Free Matrix Material**: Because the shear void growth rate \dot{f}_{shear} is proportional to the current porosity f, setting an initial porosity of zero (f_0 = 0) without void nucleation suppresses shear void growth entirely. _(Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 234; Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf p. 249)_

## References

- Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf
- Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf
- Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf
