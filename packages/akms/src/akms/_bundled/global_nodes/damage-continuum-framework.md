---
id: damage-continuum-framework
title: Continuum Damage Mechanics Framework
domain: computational-mechanics
subdomain: damage
tags:
- damage
- cdm
- lemaitre
- kachanov
- effective-stress
status: established
confidence: 0.9
source: hybrid
edges:
- to: constit-thermodynamic-framework
  type: requires
  weight: 1.0
- to: plasticity-von-mises
  type: feeds-into
  weight: 0.9
- to: damage-johnson-cook-failure
  type: feeds-into
  weight: 0.8
- to: damage-bai-wierzbicki
  type: feeds-into
  weight: 0.8
- to: damage-gtn-yield-function
  type: feeds-into
  weight: 0.8
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Continuum Damage Mechanics Framework

## Summary

Continuum damage mechanics models material degradation through internal variables that reduce the effective load-carrying area and degrade secant elastic stiffness.

## 1. Core Concept

The Continuum Damage Mechanics (CDM) framework describes the progressive degradation of material stiffness and strength caused by microstructural micro-cracks and void growth. A scalar or tensor-valued damage variable \omega \in [1] quantifies the reduction in load-carrying area, establishing the effective stress concept \hat{\bm{\sigma}} = \bm{\sigma} / (1 - \omega). Under isotropic elasticity-based damage, the secant stiffness degrades as \mathbf{D}^s = (1 - \omega) \mathbf{D}^e, relating Cauchy stress to total or elastic strain. Damage evolution is driven by an equivalent strain measure \tilde{\varepsilon} and enforced via Karush-Kuhn-Tucker loading/unloading conditions against a history threshold \kappa. When combined with computational plasticity, effective stresses enter the yield criterion and flow rule, while damage accumulation induces material strain softening.

## 2. Mathematical Formulation

**Effective Stress and Isotropic Secant Stiffness Relation**
$$
\bm{\sigma} = (1 - \omega) \hat{\bm{\sigma}}, \quad \hat{\bm{\sigma}} = \mathbf{D}^e : \bm{\varepsilon}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 171-172_

**Damage Loading Function and KKT Conditions**
$$
f(\tilde{\varepsilon}, \kappa) = \tilde{\varepsilon} - \kappa \le 0, \quad \dot{\kappa} \ge 0, \quad f \dot{\kappa} = 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 172_

**Energy-Based Equivalent Strain Definition**
$$
\tilde{\varepsilon} = \frac{1}{2} \bm{\varepsilon} : \mathbf{D}^e : \bm{\varepsilon}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 172_

**Coupled Elasticity-Damage-Plasticity Constitutive Relation**
$$
\bm{\sigma} = (1 - \omega) \mathbf{D}^e : \bm{\varepsilon}^e, \quad f^p(\hat{\bm{\sigma}}, \kappa^p) \le 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 270; Simo_Hughes_1998_Computational inelasticity.pdf p. 140_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; \hat{\bm{\sigma}}: effective stress tensor; \omega: scalar damage parameter (0 \le \omega \le 1); \mathbf{D}^e: fourth-order elastic stiffness tensor; \mathbf{D}^s: degraded secant stiffness tensor; \bm{\varepsilon}: total strain tensor; \bm{\varepsilon}^e: elastic strain tensor; \bm{\varepsilon}^p: plastic strain tensor; \tilde{\varepsilon}: equivalent strain measure; \kappa: internal damage history parameter; f: damage loading function; f^p: plastic yield function.


## 3. Algorithmic Implementation

**Isotropic Elasticity-Based Damage Update Algorithm**
$$
\begin{algorithmic}
\State $\text{Given strain increment } \Delta \bm{\varepsilon}_{j+1}, \text{ previous total strain } \bm{\varepsilon}_0, \text{ and previous damage history } \kappa_0$
\State $\bm{\varepsilon}_{j+1} = \bm{\varepsilon}_0 + \Delta \bm{\varepsilon}_{j+1}$
\State $\tilde{\varepsilon}_{j+1} = \tilde{\varepsilon}(\bm{\varepsilon}_{j+1})$
\State $f = \tilde{\varepsilon}_{j+1} - \kappa_0$
\If{$f \ge 0$}
\State $\kappa_{j+1} = \tilde{\varepsilon}_{j+1}$
\Else
\EndIf
\State $\omega_{j+1} = \omega(\kappa_{j+1})$
\State $\hat{\bm{\sigma}}_{j+1} = \mathbf{D}^e : \bm{\varepsilon}_{j+1}$
\State $\bm{\sigma}_{j+1} = (1 - \omega_{j+1}) \hat{\bm{\sigma}}_{j+1}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{j+1} \text{ and history } \kappa_{j+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf Box 6.1, p. 174_


## 4. Known Pitfalls

- **Mesh Sensitivity and Loss of Ellipticity Under Local Strain Softening**: Incorporating strain-softening damage into local rate-independent continuum models causes the governing partial differential equations to lose ellipticity, leading to pathological mesh sensitivity where energy dissipation vanishes as the finite element size approaches zero. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 179-184; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 477-478)_
- **Spurious Energy Dissipation Near Complete Damage Singularity**: Evaluating plastic strain rates or stress updates without proper numerical bounds as damage approaches complete failure (\omega \to 1) creates severe numerical ill-conditioning or unphysical stress growth if damage is uncoupled from plastic hardening. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 470-471; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 182-184)_
- **Ignoring Asymmetric Damage in Tension versus Compression**: Applying isotropic damage degradation equally to compressive and tensile stress states causes unphysical degradation under hydrostatic compression, failing to reflect crack closure effects (unilateral contact). _(Source: Meng and Tabiei - 2024 - Phase field modeling of ductile fracture with isotropic hardening and radius return method.pdf p. 417-418; Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 470-471)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Dunne_Petrinic_2005_Introduction to computational plasticity.pdf
- Meng and Tabiei - 2024 - Phase field modeling of ductile fracture with isotropic hardening and radius return method.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
