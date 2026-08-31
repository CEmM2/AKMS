---
id: damage-element-erosion
title: Element Erosion & Deletion Techniques
domain: computational-mechanics
subdomain: damage
tags:
- damage
- element-erosion
- explicit-dynamics
- mass-conservation
- particle-conversion
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-continuum-framework
  type: requires
  weight: 0.9
- to: damage-johnson-cook-failure
  type: requires
  weight: 0.9
- to: damage-bai-wierzbicki
  type: requires
  weight: 0.9
- to: damage-spall
  type: feeds-into
  weight: 0.9
- to: fem-assembly-algorithm
  type: feeds-into
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Element Erosion & Deletion Techniques

## Summary

Element erosion and failure modeling in explicit dynamic finite element analysis represent material failure through smeared continuum damage degradation or discrete element disconnection.

## 1. Core Concept

In explicit dynamic finite element modeling, material failure and element degradation are represented either through discrete crack disconnections that modify mesh topology or smeared continuum damage formulations that scale stress and stiffness tensors by degradation functions. In explicit solvers such as LS-DYNA and Abaqus/Explicit, multi-point solid elements require integration-point damage averaging across Gauss points to prevent stress equilibrium instabilities. Furthermore, to avoid numerical singularities as damage approaches unity or porosity reaches coalescence limits, damage or void volume fraction variables are numerically capped at a threshold (e.g., 90% of the failure limit) to maintain solver stability during dynamic impact and spallation simulations.

## 2. Mathematical Formulation

**Smeared Damage Stress Degradation Relation**
$$
\bm{\sigma} = g(d) \bm{\sigma}^+ + \bm{\sigma}^-, \quad g(d) = (1 - d)^2
$$
_Source: Meng and Tabiei - 2024 - Phase field modeling of ductile fracture with isotropic hardening and radius return method.pdf p. 10; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 10_

**Integration-Point Averaged Damage Variable for Element Stiffness**
$$
\bar{d}_e = \frac{1}{n_{gp}} \sum_{i=1}^{n_{gp}} d_i
$$
_Source: Meng and Tabiei - 2024 - Phase field modeling of ductile fracture with isotropic hardening and radius return method.pdf p. 15_

**Numerical Porosity Threshold Capping for Solver Stability**
$$
f_{nodal} = \min\left(f, 0.9 f_r\right)
$$
_Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 6_

**Discrete Interface Traction Failure Threshold**
$$
t_n \ge f_t \implies \text{Create new nodal DOFs across } S_d
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 201_

**Notation:**
\bm{\sigma}: Cauchy stress tensor; d: scalar damage or phase-field variable (0 \le d \le 1); g(d): continuous material degradation function; \bm{\sigma}^+, \bm{\sigma}^-: positive (tensile) and negative (compressive) stress tensor components; \bar{d}_e: element-averaged damage variable; n_{gp}: number of element Gauss integration points; f: void volume fraction (porosity); f_r: critical porosity failure limit; t_n: normal interface traction vector; f_t: material tensile strength threshold; S_d: element boundary failure surface.


## 3. Algorithmic Implementation

**Explicit Dynamic Damage Degradation and Element Removal Algorithm**
$$
\begin{algorithmic}
\State $\text{Given element strain increment } \Delta \bm{\varepsilon}_{n+1}, \text{ previous state variables at } t_n, \text{ and explicit time step } \Delta t$
\For{$\text{Each Gauss integration point } i = 1, \dots, n_{gp} \text{ in element } e$}
\State $\text{Compute local strain } \bm{\varepsilon}_i^{n+1} = \bm{\varepsilon}_i^n + \Delta \bm{\varepsilon}_i \text{ and trial stress } \bm{\sigma}_i^{tr}$
\State $\text{Evaluate plastic yield and void/damage evolution } \dot{f}_i \text{ or } \dot{d}_i$
\State $d_i^{n+1} = d_i^n + \dot{d}_i \Delta t$
\EndFor
\State $\text{Compute element-averaged damage: } \bar{d}_e = \frac{1}{n_{gp}} \sum_{i=1}^{n_{gp}} d_i^{n+1}$
\If{$\bar{d}_e \ge d_{thresh} \quad (d_{thresh} \approx 0.90 \text{ or } 0.9 f_r)$}
\State $\text{Cap damage/porosity at threshold to prevent numerical ill-conditioning: } \bar{d}_e = d_{thresh}$
\State $\text{Degrade elastic moduli and yield stress: } E_{degraded} = g(\bar{d}_e) E_0, \quad \sigma_{y,degraded} = g(\bar{d}_e) \sigma_{y0}$
\Else
\EndIf
\State $\bm{\sigma}_e^{n+1} = g(\bar{d}_e) \bm{\sigma}_e^+ + \bm{\sigma}_e^-$
\State $\text{Assemble element internal force vector: } \bm{f}_{int}^e = \int_{V_e} \mathbf{B}^T \bm{\sigma}_e^{n+1} dV$
\Return $\text{Return degraded element stress } \bm{\sigma}_e^{n+1} \text{ and internal force vector } \bm{f}_{int}^e$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Meng and Tabiei - 2024 - Phase field modeling of ductile fracture with isotropic hardening and radius return method.pdf p. 10, 15; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 6; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 174_


## 4. Known Pitfalls

- **Unstable Stress Equilibrium from Independent Integration Point Degradation**: Degrading material stiffness independently at individual Gauss integration points in multi-point solid elements (e.g., 8-node 3D hexahedra) causes spatial stress oscillations and numerical instability in explicit time integration; averaging damage across all Gauss points stabilizes the element formulation. _(Source: Meng and Tabiei - 2024 - Phase field modeling of ductile fracture with isotropic hardening and radius return method.pdf p. 15)_
- **Numerical Singularity and Solver Failure Near Complete Failure**: Allowing damage or void volume fraction to reach complete material failure (\omega \to 1 or f \to f_r) causes division by zero and matrix ill-conditioning; capping porosity or damage at a threshold (e.g., 90% of the failure limit) preserves numerical robustness during explicit shock and impact simulations. _(Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 6; Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 470-471)_
- **Mesh Alignment Sensitivity in Discrete Element Disconnection**: Deleting elements or disconnecting nodes along pre-existing element boundaries forces crack propagation paths to follow the finite element mesh orientation, introducing severe mesh alignment bias unless enriched partition-of-unity or smeared gradient regularization techniques are applied. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 179-182, 201; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 404)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Meng and Tabiei - 2024 - Phase field modeling of ductile fracture with isotropic hardening and radius return method.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
