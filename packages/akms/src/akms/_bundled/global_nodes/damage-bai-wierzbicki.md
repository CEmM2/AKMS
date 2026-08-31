---
id: damage-bai-wierzbicki
title: Bai-Wierzbicki / MMC Fracture Model
domain: computational-mechanics
subdomain: damage
tags:
- damage
- bai-wierzbicki
- mmc
- lode-angle
- ductile-fracture
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-lode-triaxiality
  type: requires
  weight: 1.0
- to: damage-johnson-cook-failure
  type: refines
  weight: 0.9
- to: damage-continuum-framework
  type: refines
  weight: 0.8
- to: damage-element-erosion
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Bai-Wierzbicki / MMC Fracture Model

## Summary

Bai-Wierzbicki / MMC fracture model formulates a stress-state-dependent ductile failure locus using stress triaxiality and the Lode parameter.

## 1. Core Concept

The Bai-Wierzbicki / Modified Mohr-Coulomb (MMC) ductile fracture model extends classical failure criteria by explicitly incorporating both stress triaxiality and the Lode parameter. Ductile fracture strain is expressed as a multi-variable surface in stress-state space, capturing asymmetric material ductility under tension, shear, and compression loading paths. Phenomenological damage accumulation integrates incremental plastic strain normalized by the instantaneous fracture strain threshold. This formulation accounts for localized shear band failure and the characteristic cusp observed in plane-stress fracture loci.

## 2. Mathematical Formulation

**Stress Triaxiality and Lode Parameter Definitions**
$$
T = \frac{\sigma_m}{\sigma_{eq}}, \quad L = \frac{27 J_3}{2 \sigma_{eq}^3} = \frac{2 \sigma_2 - \sigma_1 - \sigma_3}{\sigma_1 - \sigma_3}
$$
_Source: Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 609; Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 536_

**Plane-Stress Triaxiality-Lode Interdependence**
$$
T(\rho) = \frac{\operatorname{sgn}(\sigma_1)(\rho + 1)}{3 \sqrt{\rho^2 - \rho + 1}}, \quad L(\rho) = \frac{(1 + \rho)(2 - \rho)(2\rho - 1)}{2 (\rho^2 - \rho + 1)^{3/2}}
$$
_Source: Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 612; Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 536, 552_

**Stress-State-Dependent Fracture Strain Surface**
$$
\bar{\varepsilon}_f = \bar{\varepsilon}_f(T, L)
$$
_Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 444; Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 585, 622_

**Phenomenological Damage Accumulation Rule**
$$
D = \int_0^{\bar{\varepsilon}^p} \frac{d\bar{\varepsilon}^p}{\bar{\varepsilon}_f(T, L)} \ge 1
$$
_Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 444; Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 536, 558_

**Notation:**
T: stress triaxiality ratio; L: normalized Lode parameter; \sigma_m: hydrostatic stress; \sigma_{eq}: von Mises equivalent stress; \bm{s}: deviatoric stress tensor; J_3: third invariant of deviatoric stress; \sigma_1, \sigma_2, \sigma_3: principal stress values; \rho: principal stress ratio under plane stress; \bar{\varepsilon}^p: equivalent plastic strain; \bar{\varepsilon}_f: fracture strain threshold; D: scalar damage accumulation parameter.


## 3. Algorithmic Implementation

**Bai-Wierzbicki / MMC Fracture State Update Algorithm**
$$
\begin{algorithmic}
\State $\text{Given stress tensor } \bm{\sigma}_{n+1}, \text{ equivalent plastic strain increment } \Delta \bar{\varepsilon}^p, \text{ and previous damage } D_n$
\State $\sigma_m = \frac{1}{3} \mathrm{tr}(\bm{\sigma}_{n+1}), \quad \bm{s} = \bm{\sigma}_{n+1} - \sigma_m \mathbf{I}, \quad \sigma_{eq} = \sqrt{\frac{3}{2} \bm{s}:\bm{s}}$
\State $T = \frac{\sigma_m}{\sigma_{eq}}, \quad J_3 = \det(\bm{s}), \quad L = \frac{27 J_3}{2 \sigma_{eq}^3}$
\State $\bar{\varepsilon}_f = \bar{\varepsilon}_f(T, L)$
\State $\Delta D = \frac{\Delta \bar{\varepsilon}^p}{\bar{\varepsilon}_f(T, L)}, \quad D_{n+1} = D_n + \Delta D$
\If{$D_{n+1} \ge 1.0$}
\State $\text{Material point reaches fracture initiation threshold}$
\Return $\text{Initiate element erosion or stress degradation } (D_{n+1} = 1.0)$
\Else
\EndIf
\Return $\text{Return updated damage state } D_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 444; Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 536, 558_


## 4. Known Pitfalls

- **Neglecting Lode Parameter Dependence in Low-Triaxiality Shear Loading**: Relying exclusively on stress triaxiality T without Lode parameter L dependence overpredicts ductility under shear-dominated loadings (L \approx 0), failing to capture the characteristic ductility drop and cusp observed in plane-stress fracture loci. _(Source: Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 585, 621-622; Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 536, 552-553)_
- **Unphysical Stress Extrapolation in Uncoupled Damage Accumulation**: Integrating phenomenological damage uncoupled from elastoplastic constitutive equations without stress degradation allows stress to increase due to plastic hardening even as damage approaches unity, predicting unphysical energy dissipation during final material failure. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 470-471; Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 564-565)_
- **Non-Proportional Loading Path Miscalibration**: Applying fracture loci calibrated strictly under proportional loading paths (constant T and L) to complex non-proportional histories introduces errors, as strain path changes alter void distortion and localized band formation. _(Source: Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 558, 567)_

## References

- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
- Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf
- Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf
