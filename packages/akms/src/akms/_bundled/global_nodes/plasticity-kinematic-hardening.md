---
id: plasticity-kinematic-hardening
title: Kinematic Hardening (Armstrong-Frederick, Chaboche)
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- hardening
- kinematic-hardening
- bauschinger
- chaboche
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-von-mises
  type: refines
  weight: 1.0
- to: plasticity-isotropic-hardening
  type: feeds-into
  weight: 0.9
- to: constit-stress-update-architecture
  type: requires
  weight: 1.0
- to: constit-thermodynamic-framework
  type: requires
  weight: 0.8
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Kinematic Hardening (Armstrong-Frederick, Chaboche)

## Summary

Kinematic hardening models translate the center of the elastic yield surface in stress space via a back stress tensor, capturing the Bauschinger effect under reverse cyclic plastic loading.

## 1. Core Concept

Kinematic hardening accounts for anisotropy induced by plastic deformation history by shifting the origin of the elastic yield surface in stress space through a internal tensor variable known as back stress \bm{\alpha}. Unlike isotropic hardening, which expands the yield surface radius uniformly, kinematic hardening preserves the size and shape of the elastic domain, capturing the Bauschinger effect wherein a material yielding in tension exhibits a reduced yield threshold upon load reversal in compression. In classical J2 plasticity, yield is governed by the shifted stress tensor \bm{\eta} = \bm{s} - \bm{\alpha}, where \bm{s} is deviatoric Cauchy stress. Prager and Ziegler linear kinematic hardening rules specify rate evolution \dot{\bm{\alpha}} = \frac{2}{3} H_{\mathrm{kin}} \dot{\bm{\varepsilon}}^p. In combined isotropic/kinematic models, a scalar weighting parameter \beta \in [1] partitions total hardening modulus H into isotropic and kinematic back stress contributions.

## 2. Mathematical Formulation

**Shifted Deviatoric Stress Tensor**
$$
\bm{\eta} = \bm{s} - \bm{\alpha}
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 218, 222; Simo_Hughes_1998_Computational inelasticity.pdf p. 120, 124_

**Von Mises Yield Function with Kinematic Hardening**
$$
f(\bm{s}, \bm{\alpha}, \sigma_y) = \|\bm{s} - \bm{\alpha}\| - \sqrt{\frac{2}{3}} \sigma_y = 0
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 222, 228; Simo_Hughes_1998_Computational inelasticity.pdf p. 120_

**Linear Kinematic Hardening Back Stress Evolution**
$$
\dot{\bm{\alpha}} = \frac{2}{3} H_{\mathrm{kin}} \dot{\bm{\varepsilon}}^p = \frac{2}{3} H_{\mathrm{kin}} \dot{\gamma} \mathbf{N}, \quad \mathbf{N} = \frac{\bm{\eta}}{\|\bm{\eta}\|}
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 228; Simo_Hughes_1998_Computational inelasticity.pdf p. 120, 124_

**Combined Isotropic-Kinematic Hardening Evolution**
$$
\dot{\bm{\alpha}} = \frac{2}{3} \beta H \dot{\gamma} \mathbf{N}, \quad \dot{\sigma}_y = \sqrt{\frac{2}{3}} (1 - \beta) H \dot{\gamma}
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 222, 228; Simo_Hughes_1998_Computational inelasticity.pdf p. 120, 184_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; \bm{s}: deviatoric Cauchy stress tensor; \bm{\alpha}: back stress tensor; \bm{\eta}: shifted stress tensor (\bm{s} - \bm{\alpha}); f: yield function; \sigma_y: yield stress radius; H_{\mathrm{kin}}, H: kinematic and total plastic hardening moduli; \beta: combined hardening parameter (0 \le \beta \le 1); \mathbf{N}: unit yield surface normal vector; \dot{\gamma}, \Delta \gamma: plastic consistency parameter rate and increment; \bm{\varepsilon}^p: plastic strain tensor.


## 3. Algorithmic Implementation

**J2 Kinematic and Combined Hardening Return-Mapping Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: stress } \bm{s}_n, \text{ back stress } \bm{\alpha}_n, \text{ equivalent plastic strain } \bar{\varepsilon}^p_n, \text{ strain increment } \Delta \bm{\varepsilon}, \text{ and material parameters } \mu, H, \beta, \sigma_y^0$
\State $\bm{s}^{\mathrm{tr}} = \bm{s}_n + 2\mu \operatorname{dev}(\Delta \bm{\varepsilon}), \quad \bm{\alpha}^{\mathrm{tr}} = \bm{\alpha}_n, \quad \bm{\eta}^{\mathrm{tr}} = \bm{s}^{\mathrm{tr}} - \bm{\alpha}^{\mathrm{tr}}$
\State $\sigma_y^{\mathrm{tr}} = \sigma_y^0 + (1 - \beta) H \bar{\varepsilon}^p_n, \quad f^{\mathrm{tr}} = \|\bm{\eta}^{\mathrm{tr}}\| - \sqrt{\frac{2}{3}} \sigma_y^{\mathrm{tr}}$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\bm{s}_{n+1} = \bm{s}^{\mathrm{tr}}, \quad \bm{\alpha}_{n+1} = \bm{\alpha}^{\mathrm{tr}}, \quad \bar{\varepsilon}^p_{n+1} = \bar{\varepsilon}^p_n$
\Return $\text{Step is elastic; accept trial state}$
\Else
\EndIf
\State $\bm{s}_{n+1} = \bm{s}^{\mathrm{tr}} - 2\mu \Delta \gamma \mathbf{N}, \quad \bm{\alpha}_{n+1} = \bm{\alpha}_n + \frac{2}{3} \beta H \Delta \gamma \mathbf{N}$
\State $\bar{\varepsilon}^p_{n+1} = \bar{\varepsilon}^p_n + \sqrt{\frac{2}{3}} \Delta \gamma, \quad \bm{\sigma}_{n+1} = \bm{s}_{n+1} + \frac{1}{3} \mathrm{tr}(\bm{\sigma}^{\mathrm{tr}}) \mathbf{I}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ back stress } \bm{\alpha}_{n+1}, \text{ and plastic strain } \bar{\varepsilon}^p_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 218-222, 228-230; Simo_Hughes_1998_Computational inelasticity.pdf p. 120-125_


## 4. Known Pitfalls

- **Inability to Model Yield Surface Expansion in Pure Kinematic Hardening**: Using pure kinematic hardening (\beta = 1) translates the yield surface center without allowing the elastic domain size to expand, underpredicting flow stress growth during monotonic hardening regimes. _(Source: Kim_FEA for Elastoplastic Problems.pdf p. 217, 222; Simo_Hughes_1998_Computational inelasticity.pdf p. 120-121)_
- **Spurious Stress Oscillations in Finite Rotation Without Objective Back Stress Integration**: Evaluating back stress rate equations \dot{\bm{\alpha}} in large-deformation analysis without co-rotational rate objective integration (e.g. Jaumann or Green-Naghdi rates) introduces artificial stress oscillations during rigid body rotation. _(Source: Kim_FEA for Elastoplastic Problems.pdf p. 244-245; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 412-414; Simo_Hughes_1998_Computational inelasticity.pdf p. 316)_
- **Division by Zero at Zero Shifted Stress Norm**: Evaluating unit normal vector \mathbf{N} = \bm{\eta}^{\mathrm{tr}} / \|\bm{\eta}^{\mathrm{tr}}\| when trial shifted stress vanishes (\bm{s}^{\mathrm{tr}} = \bm{\alpha}_n) leads to floating-point division by zero; elastic step logic must be checked prior to normal calculation. _(Source: Kim_FEA for Elastoplastic Problems.pdf p. 222, 228; Simo_Hughes_1998_Computational inelasticity.pdf p. 124)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
