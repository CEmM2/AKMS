---
id: composite-failure-criteria
title: Composite Failure Criteria (Tsai-Wu, Hashin, Puck, LaRC)
domain: computational-mechanics
subdomain: composites
tags:
- composites
- failure-criteria
- tsai-wu
- hashin
- puck
- larc
status: established
confidence: 0.9
source: hybrid
edges:
- to: composite-laminate-theory
  type: requires
  weight: 1.0
- to: composite-progressive-damage
  type: feeds-into
  weight: 0.5
- to: composite-delamination
  type: refines
  weight: 0.7
- to: damage-continuum-framework
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Composite Failure Criteria (Tsai-Wu, Hashin, Puck, LaRC)

## Summary

Composite failure criteria establish mathematical bounds and activation rules for predicting damage initiation and catastrophic breakdown in heterogeneous composite constituents under multi-axial stress states. Failure modeling spans interactive macro-scale criteria—such as the 2D Tsai-Hill quadratic stress criterion used for First Ply Failure (FPF) assessments—and mode-specific constituent criteria, such as the Hashin fiber failure criterion based on combined axial and shear stress components. In progressive damage and multiscale frameworks, failure criteria dictate local constituent stiffness reduction (e.g., zeroing fiber stiffness upon reaching critical thresholds) or drive continuum phase-field damage evolution using activation flag parameters that enforce threshold-triggered damage propagation.

## 1. Core Concept

Failure criteria define thresholds at which material points transition from linear elastic or elastic-degradable behavior to irreversible damage or total loss of load-carrying capacity. In macro-scale lamina modeling, interactive stress criteria like Tsai-Hill formulate a single scalar failure index by combining longitudinal, transverse, and shear stress components relative to allowable material strengths. While effective for FPF prediction, interactive quadratic criteria do not distinguish between distinct micro-mechanical failure modes.

In micromechanical and multiscale progressive failure frameworks, failure criteria are applied directly at constituent length scales. For fiber constituents (e.g., carbon fibers), the Hashin failure criterion evaluates a quadratic index combining longitudinal axial stress and out-of-plane/in-plane shear stresses. Upon reaching unity, brittle fiber failure is triggered and local stiffness is zeroed. For matrix constituents, hydrostatic stress thresholds govern thermoelastic progressive degradation driven by thermal residual cooling stresses. Furthermore, physically-based or empirical criteria (such as Puck's criterion) can be integrated into variational phase-field fracture formulations by introducing an activation flag parameter P that multiplies the driving strain energy, ensuring phase-field evolution commences only after the critical failure boundary is crossed.

## 2. Mathematical Formulation

**Hashin Fiber Brittle Failure Criterion**
$$
h = \left(\frac{\sigma_{11}}{\sigma_{\text{axial}}}\right)^2 + \frac{1}{s_{\text{axial}}^2} \left(\sigma_{13}^2 + \sigma_{12}^2\right) \ge 1
$$
_Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 2.2, Eq. 18_

**Tsai-Hill 2D First Ply Failure Criterion**
$$
\frac{\sigma_{11}^2}{X^2} - \frac{\sigma_{11} \sigma_{22}}{X^2} + \frac{\sigma_{22}^2}{Y^2} + \frac{\sigma_{12}^2}{S^2} \ge 1
$$
_Source: Cumbo et al_2022_Design allowables of composite laminates.pdf, Section Common damage/failure modelling embedded in software solutions, Eq. 5_

**Phase-Field Failure Criterion Activation Flag Coupling**
$$
F = -\omega'(d) P H - \frac{G_c}{c_0} \left( \frac{\alpha'(d)}{l_0} - 2 l_0 \Delta d \right) \le 0
$$
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.6, Eq. 130_

**Thermoelastic Matrix Microcrack Initiation Criterion**
$$
\sigma_{\text{eq}} \ge r_{\text{crit}}(\dot{\epsilon}, T), \quad \sigma = (1 - \phi) C (\epsilon - \alpha \Delta T)
$$
_Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 2.2, Eqs. 1-2_

**Notation:**
- h: Hashin fiber failure index
- \sigma_{11}, \sigma_{22}: Longitudinal and transverse normal stress components
- \sigma_{12}, \sigma_{13}: Shear stress components
- \sigma_{\text{axial}}, s_{\text{axial}}: Fiber axial normal and shear allowable strengths
- X, Y, S: Lamina longitudinal, transverse, and shear allowable strengths
- P: Failure criterion activation flag parameter (0 or 1)
- H: Historical driving strain energy density
- d: Phase-field damage variable
- G_c: Critical strain energy release rate
- l_0: Phase-field internal length scale parameter
- c_0: Phase-field geometric normalization constant
- \sigma_{\text{eq}}: Hydrostatic equivalent stress in matrix
- r_{\text{crit}}: Critical threshold stress for matrix damage initiation
- \phi: Scalar damage variable scaling matrix stiffness
- \alpha: Coefficient of thermal expansion
- \Delta T: Temperature change relative to reference state


## 3. Algorithmic Implementation

**EvaluateHashinFiberFailure**
$$
\begin{algorithmic}
\State $h = \left(\frac{\sigma_{11}}{\sigma_{\text{axial}}}\right)^2 + \frac{1}{s_{\text{axial}}^2} \left(\sigma_{13}^2 + \sigma_{12}^2\right)$
\If{$h \ge 1.0$}
\State $\text{failed} = \text{True}, \quad C_{\text{fiber}} = 0$
\Else
\State $\text{failed} = \text{False}$
\EndIf
\Return $h, \text{failed}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 2.2, Eq. 18_

**EvaluatePhaseFieldActivationFlag**
$$
\begin{algorithmic}
\If{$\text{criterion\_met} == \text{True}$}
\State $P = 1.0$
\Else
\State $P = 0.0$
\EndIf
\State $H_{\text{eff}} = P \cdot H$
\State $F = -\omega'(d) H_{\text{eff}} - \frac{G_c}{c_0} \left( \frac{\alpha'(d)}{l_0} - 2 l_0 \Delta d \right)$
\Return $F, P$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.6, Eq. 130_


## 4. Known Pitfalls

- **unrealistic-sudden-damage-jump-activation-flag**: Multiplying an activation flag parameter P to the historical driving energy H in phase-field formulations keeps the driving force zero until the failure criterion is met; upon activation, the unchanged driving force is suddenly applied, which can cause an unrealistic sudden increase in the phase field variable and yield inaccurate crack evolution mechanics. _(Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.6)_
- **ignoring-thermal-cool-down-damage-overestimates-stiffness**: Neglecting thermal residual stresses and matrix microcracking induced during cool-down from manufacturing temperatures (due to CTE mismatch between fiber and matrix) results in an overprediction of the initial tensile stiffness of the composite laminate by 25% or more. _(Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 3)_
- **first-ply-failure-indicator-lacks-mode-differentiation**: Quadratic failure criteria such as 2D Tsai-Hill combine multiple stress components into a single scalar failure index to predict damage onset, but fail to differentiate between specific failure modes (e.g., fiber breakage vs. matrix cracking), preventing accurate post-initiation progressive degradation modeling without secondary mode identification rules. _(Source: Cumbo et al_2022_Design allowables of composite laminates.pdf, Section Common damage/failure modelling embedded in software solutions)_

## References

- Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf
- Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf
- Cumbo et al_2022_Design allowables of composite laminates.pdf
