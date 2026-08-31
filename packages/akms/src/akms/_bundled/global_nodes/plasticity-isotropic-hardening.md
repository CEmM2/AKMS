---
id: plasticity-isotropic-hardening
title: Isotropic Hardening Laws
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- hardening
- voce
- swift
- calibration
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-von-mises
  type: feeds-into
  weight: 1.0
- to: constit-stress-update-architecture
  type: feeds-into
  weight: 0.9
- to: plasticity-kinematic-hardening
  type: feeds-into
  weight: 0.7
- to: plasticity-johnson-cook
  type: refines
  weight: 0.6
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Isotropic Hardening Laws

## Summary

Isotropic hardening laws quantify the uniform expansion of the yield surface in stress space as equivalent plastic strain accumulates during inelastic deformation.

## 1. Core Concept

Isotropic hardening models describe the evolution of material yield strength as a function of plastic deformation history, expanding the elastic domain uniformly in all stress directions without shifting the yield surface center. In rate-independent and rate-dependent J2 plasticity, isotropic hardening is driven either by the strain-hardening hypothesis, where the internal state variable is equivalent plastic strain \bar{\varepsilon}^p = \int \sqrt{\frac{2}{3} \dot{\bm{\varepsilon}}^p : \dot{\bm{\varepsilon}}^p} dt, or by the work-hardening hypothesis, where plastic work \kappa = \int \bm{\sigma} : \dot{\bm{\varepsilon}}^p dt acts as the history parameter. Canonical mathematical formulations include linear isotropic hardening, nonlinear Voce exponential saturation, and power-law hardening rules.

## 2. Mathematical Formulation

**Strain-Hardening Hypothesis Rate Equation**
$$
\dot{\kappa} = \dot{\bar{\varepsilon}}^p = \sqrt{\frac{2}{3} \dot{\bm{\varepsilon}}^p : \dot{\bm{\varepsilon}}^p}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 233; Simo_Hughes_1998_Computational inelasticity.pdf p. 120_

**Work-Hardening Hypothesis Rate Equation**
$$
\dot{\kappa} = \bm{\sigma} : \dot{\bm{\varepsilon}}^p = (1 - f) \sigma_y \dot{\bar{\varepsilon}}^p
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 232-233; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 267_

**Voce Exponential Saturation Isotropic Hardening Law**
$$
\sigma_y(\bar{\varepsilon}^p) = \sigma_y^0 + (\sigma_y^{\infty} - \sigma_y^0) \left[ 1 - \exp\left( -\frac{\bar{\varepsilon}^p}{e_p^{\infty}} \right) \right]
$$
_Source: Kim_FEA for Elastoplastic Problems.pdf p. 219_

**Combined Voce-Linear Isotropic Hardening Law**
$$
h(\alpha) = \bar{K}_{\infty} - [\bar{K}_{\infty} - \bar{K}_0] \exp(-\delta \alpha) + \bar{H}^{\prime} \alpha
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 184_

**Notation:**
\sigma_y, \bar{\sigma}: updated yield stress (flow stress); \sigma_y^0, \bar{K}_0: initial yield stress; \sigma_y^{\infty}, \bar{K}_{\infty}: saturated flow stress; \bar{\varepsilon}^p, \alpha, e_p: equivalent plastic strain; e_p^{\infty}, \delta: saturation strain parameters; H, \bar{H}^{\prime}: linear plastic hardening modulus; \dot{\kappa}: rate of internal isotropic hardening variable; \dot{\bm{\varepsilon}}^p: plastic strain rate tensor.


## 3. Algorithmic Implementation

**Isotropic Hardening Local Newton Return Mapping Algorithm**
$$
\begin{algorithmic}
\State $\text{Given trial deviatoric stress norm } \|\bm{s}^{\mathrm{tr}}\|, \text{ previous equivalent plastic strain } \bar{\varepsilon}^p_n, \text{ elastic shear modulus } \mu, \text{ and hardening function } \sigma_y(\bar{\varepsilon}^p)$
\State $\text{Evaluate trial yield function: } f^{\mathrm{tr}} = \|\bm{s}^{\mathrm{tr}}\| - \sqrt{\frac{2}{3}} \sigma_y(\bar{\varepsilon}^p_n)$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\bar{\varepsilon}^p_{n+1} = \bar{\varepsilon}^p_n, \quad \sigma_{y,n+1} = \sigma_y(\bar{\varepsilon}^p_n)$
\Return $\text{Step is elastic; return trial yield stress}$
\Else
\EndIf
\While{$|f^{(k)}| > \text{TOL}$}
\State $\bar{\varepsilon}^{p,(k)} = \bar{\varepsilon}^p_n + \sqrt{\frac{2}{3}} \Delta \gamma^{(k)}$
\State $f^{(k)} = \|\bm{s}^{\mathrm{tr}}\| - 2\mu \Delta \gamma^{(k)} - \sqrt{\frac{2}{3}} \sigma_y\left( \bar{\varepsilon}^{p,(k)} \right)$
\State $H^{(k)} = \left. \frac{d \sigma_y}{d \bar{\varepsilon}^p} \right|_{\bar{\varepsilon}^{p,(k)}}$
\State $d\Delta \gamma = \frac{f^{(k)}}{2\mu + \frac{2}{3} H^{(k)}}$
\State $\Delta \gamma^{(k+1)} = \Delta \gamma^{(k)} + d\Delta \gamma, \quad k = k + 1$
\EndWhile
\State $\bar{\varepsilon}^p_{n+1} = \bar{\varepsilon}^p_n + \sqrt{\frac{2}{3}} \Delta \gamma, \quad \sigma_{y,n+1} = \sigma_y(\bar{\varepsilon}^p_{n+1})$
\Return $\text{Return updated equivalent plastic strain } \bar{\varepsilon}^p_{n+1} \text{ and yield stress } \sigma_{y,n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 120-124; Kim_FEA for Elastoplastic Problems.pdf p. 219, 225_


## 4. Known Pitfalls

- **Unphysical Re-Yielding Under Reverse Cyclic Loading**: Relying exclusively on isotropic hardening for cyclic or reversed loading overpredicts the elastic range upon load reversal by assuming equal yield stress expansion in tension and compression, failing to account for the Bauschinger effect. _(Source: Kim_FEA for Elastoplastic Problems.pdf p. 202, 212; Simo_Hughes_1998_Computational inelasticity.pdf p. 120-121)_
- **Derivative Discontinuities in Non-Smooth Hardening Functions**: Using piecewise linear or multi-stage empirical curves for \sigma_y(\bar{\varepsilon}^p) without continuous derivatives d\sigma_y/d\bar{\varepsilon}^p causes local Newton-Raphson return-mapping oscillation and degrades global solver convergence. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 122, 184; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 238)_
- **Confusing Strain-Hardening and Work-Hardening Hypotheses under Softening or Damage**: Assuming equivalence between plastic strain history \bar{\varepsilon}^p and plastic work history \kappa in porous or damaged media introduces errors, because plastic work dissipation is degraded by void volume fraction (1-f). _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 232-233; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 267)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
