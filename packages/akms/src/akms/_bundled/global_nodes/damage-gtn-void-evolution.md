---
id: damage-gtn-void-evolution
title: GTN Void Nucleation, Growth & Coalescence
domain: computational-mechanics
subdomain: damage
tags:
- damage
- gtn
- porosity
- chu-needleman
- coalescence
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-gtn-yield-function
  type: requires
  weight: 1.0
- to: damage-gtn-shear-extension
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

# GTN Void Nucleation, Growth & Coalescence

## Summary

GTN void evolution governs ductile material damage through volumetric void growth, strain- or stress-controlled void nucleation, and Tvergaard-Needleman void coalescence acceleration.

## 1. Core Concept

In the Gurson-Tvergaard-Needleman (GTN) porous plasticity model, void volume fraction evolution drives isotropic material damage and strain softening. Total void growth comprises volumetric plastic expansion of existing voids and the nucleation of new micro-voids from second-phase inclusions, typically governed by Chu and Needleman's normal distribution law. As plastic deformation progresses, inter-void matrix tearing triggers void coalescence at a critical porosity threshold f_c, modeled either through Tvergaard and Needleman's bilinear effective porosity function f^*(f) or gradient-enhanced phase-field driving forces, rapidly degrading stress-carrying capacity until complete material failure.

## 2. Mathematical Formulation

**Total Void Volume Fraction Evolution Rate**
$$
\dot{f} = \dot{f}_{growth} + \dot{f}_{nucleation}
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 36; Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf p. 251_

**Chu-Needleman Strain-Controlled Void Nucleation Rule**
$$
\dot{f}_{nucleation} = A \dot{\bar{\varepsilon}}^p, \quad A = \frac{f_N}{S_N \sqrt{2\pi}} \exp\left[ -\frac{1}{2} \left( \frac{\bar{\varepsilon}^p - \varepsilon_N}{S_N} \right)^2 \right]
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 36; Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf p. 251_

**Matrix Plastic Work Equivalence Relation**
$$
\bm{\sigma} : \dot{\bm{\varepsilon}}^p = (1 - f) \sigma_0 \dot{\bar{\varepsilon}}^p
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 36; Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf p. 251_

**Tvergaard-Needleman Bilinear Void Coalescence Function**
$$
f^*(f) = \begin{cases} f & \text{for } f \le f_c \\ f_c + K_f (f - f_c) & \text{for } f > f_c \end{cases}, \quad K_f = \frac{f_u^* - f_c}{f_F - f_c}
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 37_

**Notation:**
\dot{f}: total void volume fraction rate; \dot{f}_{growth}: volumetric void growth rate; \dot{f}_{nucleation}: void nucleation rate; f: void volume fraction (porosity); f^*: effective void volume fraction; f_c: critical void volume fraction for coalescence onset; f_F: final failure void volume fraction; f_u^*: ultimate effective void volume fraction (1/q_1); K_f: void coalescence acceleration factor; f_N: volume fraction of void-nucleating particles; \varepsilon_N: mean void nucleation strain; S_N: standard deviation of nucleation strain; A: strain-controlled nucleation scaling coefficient; \bm{\sigma}: macroscopic Cauchy stress tensor; \dot{\bm{\varepsilon}}^p: macroscopic plastic strain rate tensor; \sigma_0: matrix flow stress; \dot{\bar{\varepsilon}}^p: matrix equivalent plastic strain rate.


## 3. Algorithmic Implementation

**GTN Void Evolution and Coalescence Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given matrix plastic strain increment } \Delta \bar{\varepsilon}^p, \text{ macroscopic hydrostatic plastic strain increment } \Delta \varepsilon_p, \text{ and previous void volume fraction } f_n$
\State $\Delta f_{growth} = (1 - f_n) \Delta \varepsilon_p$
\State $A = \frac{f_N}{S_N \sqrt{2\pi}} \exp\left[ -\frac{1}{2} \left( \frac{\bar{\varepsilon}^p_n - \varepsilon_N}{S_N} \right)^2 \right]$
\State $\Delta f_{nuc} = A \Delta \bar{\varepsilon}^p$
\State $f_{n+1} = f_n + \Delta f_{growth} + \Delta f_{nuc}$
\If{$f_{n+1} \le f_c$}
\State $f^*_{n+1} = f_{n+1}$
\Else
\State $f^*_{n+1} = f_c + K_f (f_{n+1} - f_c)$
\EndIf
\If{$f^*_{n+1} \ge q_1^{-1}$}
\State $f^*_{n+1} = q_1^{-1}$
\State $\text{Material point reaches complete failure threshold; set stress to zero}$
\EndIf
\Return $\text{Return updated void volume fraction } f_{n+1} \text{ and effective porosity } f^*_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 36-37; Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf p. 251_


## 4. Known Pitfalls

- **Division by Zero in Matrix Work Equivalence Near Complete Void Failure**: Evaluating matrix equivalent plastic strain increments using macro-micro plastic work equivalence \dot{\bar{\varepsilon}}^p = (\bm{\sigma} : \dot{\bm{\varepsilon}}^p) / [(1-f)\sigma_0] as porosity approaches complete loss of material (f \to 1) causes division by zero and numerical instability, requiring porosity capping or effective porosity regularization f^*. _(Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 36-37; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 6)_
- **Pathological Mesh Sensitivity in Local Void Growth Without Regularization**: Modeling local void growth and coalescence in rate-independent continuum plasticity without gradient enhancements or phase-field regularization causes severe mesh dependency, where localized void failure concentrates within a single element layer. _(Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 291-292; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 225, 229)_
- **Unphysical Zero Nucleation in Clean Alloys Without Initial Porosity**: Assuming zero initial void volume fraction (f_0 = 0) while omitting strain-controlled or stress-controlled void nucleation suppresses void evolution entirely under volumetric plastic strain, failing to predict ductile fracture in inclusion-sparse alloys. _(Source: Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf p. 249, 251; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 36)_

## References

- Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf
