---
id: damage-cockcroft-latham
title: Cockcroft-Latham Fracture Criterion
domain: computational-mechanics
subdomain: damage
tags:
- damage
- cockcroft-latham
- principal-stress
- ductile-fracture
- simple-criterion
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-continuum-framework
  type: refines
  weight: 0.7
- to: damage-johnson-cook-failure
  type: contradicts
  weight: 0.6
- to: tensor-spectral-decomposition
  type: requires
  weight: 0.7
context_size: small
reading_priority: full
content_ref: null
akms_schema: v2
---

# Cockcroft-Latham Fracture Criterion

## Summary

Principal stress-based ductile fracture models evaluate material degradation and failure initiation driven by the maximum tensile principal stress and plastic strain accumulation.

## 1. Core Concept

Principal stress-based ductile failure criteria postulate that tensile failure and scalar damage growth are primarily driven by the maximum principal tensile stress. In continuum damage mechanics and computational plasticity, tensor spectral decomposition extracts the maximum principal stress component, where a Heaviside step function or Macaulay bracket isolates tensile stress states from compressive states. Damage accumulation evolves as a function of the ratio of maximum principal stress to equivalent stress scaled by effective plastic strain rates, or via Rankine-type limit surfaces where the maximum principal stress reaches the material tensile strength.

## 2. Mathematical Formulation

**Maximum Principal Stress Scalar Damage Evolution Rate**
$$
\dot{\omega} = \left(\frac{\sigma_1}{\sigma_e}\right)^\chi H(\sigma_1) \dot{\bar{\varepsilon}}^p
$$
_Source: Dunne_Petrinic_2005_Introduction to computational plasticity.pdf p. 211_

**Rankine Maximum Principal Stress Failure Criterion**
$$
f(\bm{\sigma}) = \sigma_1 - f_t = 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 201, 226, 254_

**Spectral Decomposition of Cauchy Stress Tensor**
$$
\bm{\sigma} = \sum_{i=1}^3 \sigma_i \bm{n}_i \otimes \bm{n}_i
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 368; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 266_

**Plane-Stress Principal Stress Ratio and Triaxiality**
$$
\rho = \frac{\sigma_2}{\sigma_1}, \quad T = \frac{\operatorname{sgn}(\sigma_1)(\rho + 1)}{3 \sqrt{\rho^2 - \rho + 1}}
$$
_Source: Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 612; Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 536_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; \sigma_1: maximum principal Cauchy stress; \sigma_e: von Mises equivalent stress; \bm{s}: deviatoric stress tensor; H(\cdot): Heaviside step function; \omega: scalar damage variable; \chi: stress-state sensitivity parameter; \bar{\varepsilon}^p: equivalent plastic strain; f_t: uniaxial tensile strength; \bm{n}_i: principal stress eigenvectors; \rho: principal stress ratio; T: stress triaxiality.


## 3. Algorithmic Implementation

**Maximum Principal Stress Damage State Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given stress tensor } \bm{\sigma}_{n+1}, \text{ equivalent plastic strain increment } \Delta \bar{\varepsilon}^p, \text{ and previous damage } \omega_n$
\State $\text{Compute principal stress eigenvalues } \sigma_1 \ge \sigma_2 \ge \sigma_3 \text{ via spectral decomposition of } \bm{\sigma}_{n+1}$
\State $\sigma_e = \sqrt{\frac{3}{2} \bm{s}:\bm{s}}, \quad \text{where } \bm{s} = \bm{\sigma}_{n+1} - \frac{1}{3}\mathrm{tr}(\bm{\sigma}_{n+1})\mathbf{I}$
\If{$\sigma_1 > 0$}
\State $\Delta \omega = \left(\frac{\sigma_1}{\sigma_e}\right)^\chi \Delta \bar{\varepsilon}^p$
\Else
\EndIf
\State $\omega_{n+1} = \omega_n + \Delta \omega$
\If{$\omega_{n+1} \ge 1.0 \text{ or } \sigma_1 \ge f_t$}
\State $\text{Material point reaches tensile fracture initiation threshold}$
\Return $\text{Set failure state } \omega_{n+1} = 1.0 \text{ and degrade stress}$
\Else
\EndIf
\Return $\text{Return updated damage state } \omega_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Dunne_Petrinic_2005_Introduction to computational plasticity.pdf p. 211; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 201, 266_


## 4. Known Pitfalls

- **Spurious Damage Growth Under Compressive Principal Stresses**: Failing to apply a Heaviside step function H(\sigma_1) or spectral positive stress projection to isolate the maximum principal tensile stress leads to unphysical damage accumulation during purely compressive stress states. _(Source: Dunne_Petrinic_2005_Introduction to computational plasticity.pdf p. 211; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 444)_
- **Neglecting Triaxiality and Lode Effects in Shear Loading**: Relying solely on maximum principal stress or Rankine failure criteria without accounting for stress triaxiality T or Lode parameter L underpredicts shear localization and fails to capture ductility minima in plane stress. _(Source: Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf p. 536, 552; Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf p. 585, 622)_
- **Indeterminacy in Eigenvector Derivatives for Coincident Principal Stresses**: Evaluating derivatives of principal stress functions when two principal stresses coincide (\sigma_1 = \sigma_2) causes numerical indeterminacy during return-mapping or tangent operator evaluation, requiring specialized eigenprojection formulas. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 261-266; Kim_FEA for Elastoplastic Problems.pdf p. 374-375)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Dunne_Petrinic_2005_Introduction to computational plasticity.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Torki and Benzerga - 2021 - Ductile Fracture in Plane Stress.pdf
- Torki et al. - 2021 - An analysis of Lode effects in ductile failure.pdf
