---
id: damage-spall
title: Spall Fracture Models
domain: computational-mechanics
subdomain: damage
tags:
- damage
- spall
- dynamic-fracture
- nag
- tuler-butcher
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-continuum-framework
  type: refines
  weight: 0.8
- to: damage-element-erosion
  type: feeds-into
  weight: 0.9
- to: damage-gtn-yield-function
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Spall Fracture Models

## Summary

Spall fracture models describe dynamic material failure and crack formation under high-velocity impact loading driven by rarefaction wave-induced dynamic tensile stresses.

## 1. Core Concept

Spallation is a dynamic failure mechanism occurring in ductile metals subjected to high-velocity impact or shock wave loading. When compressive shock waves reflect off free surfaces, intersecting rarefaction waves generate severe dynamic hydrostatic tensile stresses. Under these intense tensile stress states, material failure progresses through the rapid nucleation, volumetric growth, and coalescence of micro-voids in a localized spall zone. Modern computational formulations model dynamic spalling by coupling Gurson-type porous plasticity with phase-field or gradient-enhanced continuum damage mechanics, incorporating pressure-dependent bulk moduli to accurately represent material response under multi-gigapascal impact pressures.

## 2. Mathematical Formulation

**Pressure-Dependent Bulk Modulus (Murnaghan Approximation)**
$$
\kappa(p) = \kappa_0 + n_0 p
$$
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231_

**Phase-Field Degraded Tensile Elastic Stress Relation**
$$
\bm{\sigma} = g(d) \bm{\sigma}^+ + \bm{\sigma}^-, \quad g(d) = (1 - d)^2
$$
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231_

**Gurson-Type Phase-Field Spall Driving Force**
$$
\dot{d} = \frac{1}{\eta_d} \left\langle \mathcal{H} - \frac{G_c}{2 \ell_c} d + G_c \ell_c \nabla^2 d \right\rangle
$$
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 230, 238_

**Phase-Field Degraded Yield Stress**
$$
\sigma_y = g(d) \sigma_{0y}
$$
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; p: hydrostatic pressure; \kappa(p): pressure-dependent bulk modulus; \kappa_0: initial bulk modulus; n_0: Murnaghan parameter; d: phase-field spall damage variable (0 \le d \le 1); g(d): continuous quadratic degradation function; \bm{\sigma}^+, \bm{\sigma}^-: tensile and compressive spectral stress components; \mathcal{H}: history-dependent energy driving force; G_c: fracture energy release rate; \ell_c: characteristic phase-field length scale; \eta_d: phase-field mobility/viscosity parameter; f: void volume fraction; f_c: critical void coalescence threshold; \sigma_y: degraded yield strength; \sigma_{0y}: initial yield strength.


## 3. Algorithmic Implementation

**Explicit Gurson-Type Phase-Field Dynamic Spall Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_k\text{: displacement } \mathbf{u}_k, \text{ phase-field } d_k, \text{ porosity } f_k, \text{ plastic strain } \bm{\varepsilon}_k, \text{ and explicit time step } \Delta t$
\State $\text{Compute strain increment } \Delta \bm{\varepsilon} = \operatorname{sym}(\nabla \Delta \mathbf{u}) \text{ and updated pressure } p_{k+1}$
\State $\text{Update bulk modulus: } \kappa(p_{k+1}) = \kappa_0 + n_0 p_{k+1}$
\State $\text{Predict trial stress } \bm{\sigma}^{pre} \text{ and evaluate GTN yield function } \Phi(p, q, f_k)$
\If{$\Phi > 0$}
\State $\text{Solve GTN return mapping for updated plastic strain } \bm{\varepsilon}_{k+1} \text{ and porosity } f_{k+1}$
\Else
\EndIf
\If{$f_{k+1} \ge f_c$}
\State $\text{Compute phase-field driving force } \mathcal{H}_{k+1} \text{ from plastic work and void expansion}$
\State $\text{Solve phase-field evolution PDE for } d_{k+1} = d_k + \dot{d} \Delta t$
\Else
\EndIf
\State $\text{Update degraded Cauchy stress: } \bm{\sigma}_{k+1} = g(d_{k+1}) \bm{\sigma}^+ + \bm{\sigma}^-$
\Return $\text{Return updated stress } \bm{\sigma}_{k+1}, \text{ porosity } f_{k+1}, \text{ and phase-field damage } d_{k+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231, 238_


## 4. Known Pitfalls

- **Ignoring Pressure Dependence of Bulk Modulus under High Shock Pressures**: Using a constant linear elastic bulk modulus \kappa_0 under multi-gigapascal dynamic impact pressures overpredicts volumetric expansion and miscalculates shock wave velocity, distorting the location and magnitude of peak tensile rarefaction stresses in spallation zones. _(Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231)_
- **Unsplit Elastic Energy Degradation Causing Spurious Compressive Failure**: Degrading total elastic energy uniformly without splitting tensile \bm{\sigma}^+ and compressive \bm{\sigma}^- stress components causes unphysical stiffness loss under shock compression, preventing correct wave reflection and spall zone formation. _(Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 231; Meng and Tabiei - 2024 - Phase field modeling of ductile fracture with isotropic hardening and radius return method.pdf p. 281-282)_
- **Premature Spall Crack Activation Before Void Coalescence**: Triggering macroscopic spall damage or phase-field evolution prior to reaching the critical void volume fraction threshold (f < f_c) artificially accelerates material failure during early wave propagation. _(Source: Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 230, 238)_

## References

- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Meng and Tabiei - 2024 - Phase field modeling of ductile fracture with isotropic hardening and radius return method.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
