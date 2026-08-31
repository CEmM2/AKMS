---
id: pf-ductile-plasticity-coupling
title: Coupled Plasticity–Phase-Field Fracture (Borden, Miehe)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- plasticity
- ductile
- borden-2016
- plastic-work-driving
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-variational-griffith
  type: refines
  weight: 0.7
- to: pf-spectral-split
  type: requires
  weight: 1.0
- to: plasticity-isotropic-hardening
  type: requires
  weight: 1.0
- to: pf-ductile-mixed-mode
  type: feeds-into
  weight: 0.5
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Coupled Plasticity–Phase-Field Fracture (Borden, Miehe)

## Summary

Formulation, energy splitting, and return-mapping algorithms for coupled elastoplasticity and diffusive phase-field fracture in ductile materials. Based on foundational continuum mechanics frameworks by Borden et al. (2016) and Miehe et al. (2015), the node details the energetic and microforce balance governing coupled plastic dissipation and damage evolution. Key aspects include: (1) free-energy potential decomposition incorporating degraded hyperelastic/elastic strain energy and plastic work, (2) yield surface degradation functions g_p(c) that induce plastic softening and eliminate non-physical elastic deformation after crack initiation, (3) plastic work thresholds \langle W_p - W_0 \rangle or accumulated plastic strain driving fields \mathcal{H}_p that prevent premature damage nucleation prior to macroscopic yielding, and (4) J2 flow theory return-mapping algorithms integrating plastic yield surface degradation with objective configuration updates.

## 1. Core Concept

Coupling continuum plasticity with phase-field fracture requires unifying two dissipative mechanisms: irreversible dislocation slip (plastic flow) and diffusive crack surface evolution (damage). In classical brittle phase-field formulations, crack propagation is driven purely by elastic strain energy release rate. In ductile metals, however, plastic deformation absorbs significant energy, producing localized plastic work and strain-rate-dependent thermal softening before macroscopic crack initiation occurs. To capture this physics without predicting artificial damage prior to yielding, the free energy functional is split into elastic and plastic contributions. The elastic strain energy (often partitioned via volumetric-deviatoric or principal stretch splits rather than strict spectral splits) drives damage evolution alongside an accumulated plastic work density W_p or plastic threshold field \mathcal{H}_p. Crucially, to model post-initiation softening and maintain thermodynamic consistency, the plastic yield function f(\boldsymbol{\tau}, \alpha) = \|\mathbf{s}\| - g_p(c)\sqrt{2/3}k(\alpha) incorporates a yield surface degradation function g_p(c). This degrades material flow strength as damage c \to 1, eliminating spurious residual stresses in fully broken material zones.

## 2. Mathematical Formulation

**free_energy_density_ductile_pf**
$$
\rho_0 \psi(\mathbf{C}, \mathbf{C}^p, \alpha, c, \nabla_X c) = g(c) W^+(\mathbf{C}, \mathbf{C}^p) + W^-(\mathbf{C}, \mathbf{C}^p) + g_p(c) W_p(\alpha) + \frac{G_c}{2 \ell_0} \left[ \frac{(1-c)^2}{2} + \ell_0^2 |\nabla_X c|^2 \right]
$$
_Source: Borden et al. (2016), A phase-field formulation for fracture in ductile materials; Borden et al. (2017), Corrigendum_

**microforce_phase_field_governing_equation**
$$
2 \ell_0 \frac{G_c}{c_0} \left[ \beta_e \frac{dg}{dc} \mathcal{H}_e + \beta_p \frac{dg_p}{dc} \langle W_p - W_0 \rangle \right] + c - 4 \ell_0^2 \Delta_X c = 1
$$
_Source: Borden et al. (2016), A phase-field formulation for fracture in ductile materials; Borden et al. (2017), Corrigendum_

**degraded_j2_yield_function**
$$
f(\boldsymbol{\tau}, \alpha, c) = \|\mathbf{s}\| - g_p(c) \sqrt{\frac{2}{3}} k(\alpha) \le 0
$$
_Source: Borden et al. (2016), A phase-field formulation for fracture in ductile materials; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method_

**plastic_work_driving_history_field**
$$
\mathcal{H}_{n+1} = \max\left( \mathcal{H}_n, \psi_0^+ + \psi_0^{pl} - \psi_c \right), \quad \psi_0^{pl} = \int_0^t \boldsymbol{\sigma} : d\boldsymbol{\epsilon}^p
$$
_Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Dittmann et al. (2020), Phase-field modeling of porous-ductile fracture_

**alessi_coupled_1d_yield_surface**
$$
f_p(\sigma, c) = |\sigma| - \sigma_P(c) \le 0, \quad \sigma_P(c) = (1-c)^s \sigma_p
$$
_Source: Alessi et al. (2018), Coupling damage and plasticity for a phase-field regularisation of brittle, cohesive and ductile fracture_

**Notation:**
c: scalar phase-field damage variable (c \in [1]); \mathbf{C}, \mathbf{C}^p: total and plastic right Cauchy-Green deformation tensors; \boldsymbol{\tau}: Kirchhoff stress tensor; \mathbf{s}: deviatoric Kirchhoff stress tensor; \boldsymbol{\sigma}: Cauchy stress tensor; \boldsymbol{\epsilon}^p: plastic strain tensor; \alpha: equivalent plastic strain / isotropic hardening variable; k(\alpha): isotropic yield stress function; g(c), g_p(c): elastic and plastic yield surface degradation functions; W^+, W^-: positive (tensile) and negative (compressive) strain energy density components; W_p: plastic work density; W_0, \psi_c: threshold plastic/elastic energy density; G_c: fracture toughness; \ell_0: regularization length scale parameter; \mathcal{H}_e, \mathcal{H}: energy history fields.


## 3. Algorithmic Implementation

**j2-plasticity-return-mapping-with-phase-field-degradation**
$$
\begin{algorithmic}
\State $Given state at time t_n: deformation gradient \mathbf{F}_n, plastic intermediate metric \bar{\mathbf{b}}_n^e, isotropic hardening variable \alpha_n, damage c_n, and incremental displacement \Delta \mathbf{u}_n.$
\State $Update deformation gradient \mathbf{F}_{n+1} = \mathbf{f}_{n+1} \mathbf{F}_n with relative deformation gradient \mathbf{f}_{n+1} = \mathbf{I} + \nabla \mathbf{u}_n.$
\State $Compute trial elastic predictor configuration: \bar{\mathbf{b}}_{n+1}^{e, trial} = \bar{\mathbf{f}}_{n+1} \bar{\mathbf{b}}_n^e \bar{\mathbf{f}}_{n+1}^T where \bar{\mathbf{f}}_{n+1} = \det(\mathbf{f}_{n+1})^{-1/3} \mathbf{f}_{n+1}.$
\State $Evaluate trial deviatoric Kirchhoff stress: \mathbf{s}_{n+1}^{trial} = g(c_n) \mu \text{dev}[\bar{\mathbf{b}}_{n+1}^{e, trial}].$
\State $Evaluate trial yield function: f_{n+1}^{trial} = \|\mathbf{s}_{n+1}^{trial}\| - g_p(c_n) \sqrt{\frac{2}{3}} k(\alpha_n).$
\If{$f_{n+1}^{trial} \le 0 (Elastic step).$}
\State $Accept trial state: \mathbf{s}_{n+1} = \mathbf{s}_{n+1}^{trial}, \alpha_{n+1} = \alpha_n, \bar{\mathbf{b}}_{n+1}^e = \bar{\mathbf{b}}_{n+1}^{e, trial}, and \Delta \gamma = 0.$
\Else
\State $Solve non-linear scalar plastic consistency equation for algorithmic plastic multiplier \Delta \gamma: \hat{f}(\Delta \gamma) = \|\mathbf{s}_{n+1}^{trial}\| - g_p(c_n) \sqrt{\frac{2}{3}} k\left(\alpha_n + \sqrt{\frac{2}{3}} \Delta \gamma\right) - 2 \bar{\mu} \Delta \gamma = 0 where \bar{\mu} = g(c_n) \mu \frac{1}{3} \text{tr}[\bar{\mathbf{b}}_{n+1}^{e, trial}].$
\State $Update deviatoric stress and hardening parameter: \mathbf{s}_{n+1} = \mathbf{s}_{n+1}^{trial} - 2 \bar{\mu} \Delta \gamma \frac{\mathbf{s}_{n+1}^{trial}}{\|\mathbf{s}_{n+1}^{trial}\|}, \alpha_{n+1} = \alpha_n + \sqrt{\frac{2}{3}} \Delta \gamma.$
\State $Update intermediate elastic metric maintaining unit determinant: \text{dev}[\bar{\mathbf{b}}_{n+1}^e] = \frac{\mathbf{s}_{n+1}}{g(c_n) \mu}, solve \det\left(\text{dev}[\bar{\mathbf{b}}_{n+1}^e] + \bar{I}_{n+1}^e \mathbf{I}\right) = 1 for \bar{I}_{n+1}^e, set \bar{\mathbf{b}}_{n+1}^e = \text{dev}[\bar{\mathbf{b}}_{n+1}^e] + \bar{I}_{n+1}^e \mathbf{I}.$
\EndIf
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borden et al. (2016), A phase-field formulation for fracture in ductile materials; Borden et al. (2017), Corrigendum_


## 4. Known Pitfalls

- **spurious-elastic-energy-after-crack-initiation-without-yield-degradation**: If the plastic yield surface is not degraded simultaneously with elastic stiffness (i.e. omitting g_p(c)), material inside fully broken crack zones (c \to 1) continues to yield at high flow stress. This generates non-physical elastic strains, artificial residual stresses, and incorrect strain energy calculations across fully fractured elements. _(Source: Borden et al. (2016), A phase-field formulation for fracture in ductile materials; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method)_
- **premature-damage-nucleation-prior-to-plastic-yield**: Using a pure elastic driving force or standard quadratic degradation g(c) = (1-c)^2 without a plastic threshold W_0 or \psi_c causes phase field c to evolve during early elastic deformation. This prematurely degrades initial elastic stiffness and artificially depresses the macroscopic yield strength. _(Source: Borden et al. (2016), A phase-field formulation for fracture in ductile materials; Miehe et al. (2015), Phase field modeling of fracture in multi-physics problems. Part II)_
- **volumetric-compression-locking-under-plastic-shear**: Failing to split or treat compressive pressure independently during plastic shear deformation causes non-physical damage growth under hydrostatic compression. Models must employ volumetric-deviatoric or principal stretch splits to prevent compressive energy from driving crack phase-field evolution. _(Source: Borden et al. (2016), A phase-field formulation for fracture in ductile materials; McAuliffe and Waisman (2015), A unified model for metal failure capturing shear banding and fracture)_

## References

- Borden, M. J., Hughes, T. J. R., Landis, C. M., Anvari, A., and Lee, I. J. (2016). A phase-field formulation for fracture in ductile materials: Finite deformation balance law derivation, plastic degradation, and stress triaxiality effects. Computer Methods in Applied Mechanics and Engineering, 312, 130-166.
- Borden, M. J., Hughes, T. J. R., Landis, C. M., Anvari, A., and Lee, I. J. (2017). Corrigendum to "A phase-field formulation for fracture in ductile materials: Finite deformation balance law derivation, plastic degradation, and stress triaxiality effects". Computer Methods in Applied Mechanics and Engineering, 324, 712-713.
- Miehe, C., Hofacker, M., Schänzel, L.-M., and Aldakheel, F. (2015). Phase field modeling of fracture in multi-physics problems. Part II. Coupled brittle-to-ductile failure criteria and crack propagation in thermo-elastic-plastic solids. Computer Methods in Applied Mechanics and Engineering, 294, 486-522.
- Alessi, R., Marigo, J.-J., Maurini, C., and Vidoli, S. (2018). Coupling damage and plasticity for a phase-field regularisation of brittle, cohesive and ductile fracture: One-dimensional examples. International Journal of Mechanical Sciences, 149, 559-576.
- Molnar, G., Gravouil, A., Seghir, R., and Réthoré, J. (2020). An open-source Abaqus implementation of the phase-field method to study the effect of plasticity on the instantaneous fracture toughness in dynamic crack propagation. Computer Methods in Applied Mechanics and Engineering, 365, 113004.
- Dittmann, M., Aldakheel, F., Schulte, J., Schmidt, F., Krüger, M., Wriggers, P., and Hesch, C. (2020). Phase-field modeling of porous-ductile fracture in non-linear thermo-elasto-plastic solids. Computer Methods in Applied Mechanics and Engineering, 361, 112730.
