---
id: pf-porous-ductile
title: Porous-Ductile Phase-Field (GTN + PF Coupling)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- GTN
- porous
- two-scale
- aldakheel
- ductile-fracture
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-ductile-plasticity-coupling
  type: refines
  weight: 0.7
- to: damage-gtn-yield-function
  type: requires
  weight: 1.0
- to: damage-gtn-void-evolution
  type: requires
  weight: 1.0
- to: damage-nonlocal-gradient
  type: requires
  weight: 1.0
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Porous-Ductile Phase-Field (GTN + PF Coupling)

## Summary

Multi-scale formulation and implementation of coupled Gurson-Tvergaard-Needleman (GTN) porous plasticity and diffusive phase-field fracture mechanics. The framework bridges microvoid nucleation, growth, and coalescence at the microscopic scale with regularized crack initiation and macroscopic fracture propagation. Microvoid evolution degrades matrix yield strength via the GTN yield surface \Upsilon_G(\boldsymbol{\tau}, \bar{\sigma}) = 0, where void volume fraction \\(f = 1 - (1-f_0)/J^p\\) evolves with plastic volume expansion. Phase-field damage \\(s \in [1]\\) or \\(d \in [1]\\) is driven by plastic work dissipation \\(\psi^{pl}\\) alongside elastic strain energy \\(\psi^+\\), regularized by internal length scale \\(l_f\\) to eliminate pathological mesh sensitivity during softening. Modern extensions incorporate shear damage \\(D_s\\) into shear-modified GTN phase-field models (Tao et al., 2022) and multi-field finite element implementations (Dittmann et al., 2020).

## 1. Core Concept

Classical GTN continuum porous plasticity models effectively describe microvoid nucleation and growth under high stress triaxialities. However, upon reaching critical void coalescence, local loss of ellipticity causes extreme mesh dependency and non-physical localized energy dissipation. Coupling the GTN porous plasticity framework with a gradient-extended phase-field fracture model regularizes the failure process by introducing an internal length scale parameter \\(l_f\\). Microvoid growth governs early ductile softening and void volume fraction \\(f = 1 - (1-f_0)/J^p\\), while the phase-field variable \\(s\\) (or \\(d\\)) captures sharp macroscopic crack localization. The thermodynamic driving force \\(\mathcal{H}\\) incorporates accumulated plastic dissipation \\(\psi^{pl} = \int \boldsymbol{\sigma} : d\boldsymbol{\epsilon}^p\\) and tensile elastic strain energy \\(\psi^+\\). This two-scale mechanism prevents mesh alignment bias and accurately predicts failure transitions across low, medium, and high stress triaxialities in complex 2D and 3D structural components.

## 2. Mathematical Formulation

**gtn_yield_surface_phase_field**
$$
\Upsilon_G(\boldsymbol{\tau}, \bar{\sigma}) = \frac{\sigma_{eq}^2}{\bar{\sigma}^2} + 2 q_1 f \cosh\left(\frac{3}{2} \frac{q_2 p}{\bar{\sigma}}\right) - \left(1 + (q_1 f)^2\right) = 0
$$
_Source: Dittmann et al. (2020), Phase-field modeling of porous-ductile fracture in non-linear thermo-elasto-plastic solids; Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids_

**void_volume_fraction_kinematics**
$$
f = \max\left\{f_0, 1 - \frac{1-f_0}{J^p}\right\}, \quad J^p = \det(\mathbf{F}^p) = \sqrt{\det(\mathbf{C}^p)}
$$
_Source: Dittmann et al. (2020), Phase-field modeling of porous-ductile fracture; Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids_

**porous_ductile_phase_field_driving_force**
$$
\mathcal{H}_{n+1} = \max\left(\mathcal{H}_n, \psi_0^+ + \psi_0^{pl} - \psi_c\right), \quad \frac{g_c}{l_f}(s - l_f^2 \Delta s) = 2(1-s)\mathcal{H}_{n+1}
$$
_Source: Dittmann et al. (2020), Phase-field modeling of porous-ductile fracture; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method_

**shear_modified_gtn_coupled_degradation**
$$
D = q_1 f^* + D_s, \quad g(d, D_s, f) = (1-d)^{(a_1 + a_2 D_s + a_3 f)}
$$
_Source: Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids based on the shear-modified GTN model_

**Notation:**
s, d: scalar phase-field damage variables (s, d \in); \boldsymbol{\tau}: Kirchhoff stress tensor; \mathbf{s}: deviatoric stress tensor; p: hydrostatic pressure; \sigma_{eq}: equivalent von Mises stress; \bar{\sigma}: matrix flow stress; f, f_0: current and initial void volume fractions; J^p: plastic volumetric determinant; \mathbf{F}, \mathbf{F}^e, \mathbf{F}^p: total, elastic, and plastic deformation gradients; \mathcal{H}: historical maximum energy release rate driving field; l_f, l_p: fracture and plastic internal length scales; g_c: critical fracture energy; D_s: shear damage variable.


## 3. Algorithmic Implementation

**gtn-phase-field-staggered-return-mapping**
$$
\begin{algorithmic}
\State $Initialize deformation mapping \boldsymbol{\phi}_0, plastic metric \mathbf{C}^p_0, void fraction f_0, hardening variable \alpha_0, damage s_0 = 0, and history field \mathcal{H}_0 = 0.$
\For{$Loop over load/time increments n = 0, 1, 2, \dots, N_{steps}.$}
\State $Compute trial elastic state \mathbf{b}^{e, tr} = \mathbf{F}_{n+1} (\mathbf{C}^p_n)^{-1} \mathbf{F}_{n+1}^T and trial GTN yield function \Upsilon_G(\boldsymbol{\tau}^{tr}, \bar{\sigma}^{tr}).$
\If{$\Upsilon_G \le 0 (Elastic step).$}
\State $Accept trial state, setting plastic multiplier \Delta \lambda^p = 0 and keeping f_{n+1} = f_n.$
\Else
\State $Solve non-linear return-mapping equations for plastic multiplier \Delta \lambda^p, update plastic metric \mathbf{C}^p_{n+1}, and update void fraction f_{n+1} = \max\left\{f_0, 1 - (1-f_0)/J^p_{n+1}\right\}.$
\EndIf
\State $Evaluate plastic dissipation work \psi_n^{pl} and elastic strain energy \psi_n^+, then update driving force history field \mathcal{H}_{n+1} = \max(\mathcal{H}_n, \psi_n^+ + \psi_n^{pl} - \psi_c).$
\State $Solve phase-field sub-problem for s_{n+1}: \frac{g_c}{l_f}(s_{n+1} - l_f^2 \Delta s_{n+1}) = 2(1-s_{n+1})\mathcal{H}_{n+1}.$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Dittmann et al. (2020), Phase-field modeling of porous-ductile fracture; Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids_


## 4. Known Pitfalls

- **gtn-mesh-sensitivity-without-phase-field-regularization**: Classical GTN porous-plasticity models suffer from pathological mesh dependency and artificial strain localization when void growth causes plastic softening. Coupling GTN with a gradient phase-field fracture model introduces internal length scale l_f, regularizing void coalescence and maintaining well-posed governing equations. _(Source: Dittmann et al. (2020), Phase-field modeling of porous-ductile fracture; Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids)_
- **misattributing-gtn-phase-field-to-hydraulic-fracture-literature**: Confusing porous-ductile fracture (GTN void growth coupled with phase-field damage in metals) with hydraulic fracturing models in saturated porous media (e.g., Heider & Markert 2017/2018 for fluid-driven rock cracking) leads to incorrect kinematic assumptions and inappropriate fluid pressure coupling. _(Source: Dittmann et al. (2020), Phase-field modeling of porous-ductile fracture in non-linear thermo-elasto-plastic solids; Zhang et al. (2022), Assessment of four strain energy decomposition methods)_

## References

- Dittmann, M., Aldakheel, F., Schulte, J., Schmidt, F., Krüger, M., Wriggers, P., and Hesch, C. (2020). Phase-field modeling of porous-ductile fracture in non-linear thermo-elasto-plastic solids. Computer Methods in Applied Mechanics and Engineering, 361, 112730.
- Tao, Z., Li, X., Tao, S., and Chen, Z. (2022). Phase-field modeling of 3D fracture in elasto-plastic solids based on the shear-modified GTN model and Abaqus subroutines UEL/UMAT. Engineering Fracture Mechanics, 260, 108196.
- Aldakheel, F., Wriggers, P., and Miehe, C. (2018). A modified Gurson-type plasticity model at finite strains: formulation, numerical analysis and phase-field coupling. Computational Mechanics, 62(4), 815-833.
- Miehe, C., Kienle, D., Aldakheel, F., and Teichtmeister, S. (2016). Phase field modeling of fracture in porous plasticity: A variational gradient-extended Eulerian framework for the macroscopic analysis of ductile failure. Computer Methods in Applied Mechanics and Engineering, 312, 3-50.
- Borden, M. J., Hughes, T. J. R., Landis, C. M., Anvari, A., and Lee, I. J. (2016). A phase-field formulation for fracture in ductile materials: Finite deformation balance law derivation, plastic degradation, and stress triaxiality effects. Computer Methods in Applied Mechanics and Engineering, 312, 130-166.
- Molnar, G., Gravouil, A., Seghir, R., and Réthoré, J. (2020). An open-source Abaqus implementation of the phase-field method to study the effect of plasticity on the instantaneous fracture toughness in dynamic crack propagation. Computer Methods in Applied Mechanics and Engineering, 365, 113004.
