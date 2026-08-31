---
id: damage-johnson-cook-failure
title: Johnson-Cook Fracture Model
domain: computational-mechanics
subdomain: damage
tags:
- damage
- johnson-cook
- ductile-fracture
- element-erosion
- rate-dependent
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-continuum-framework
  type: refines
  weight: 0.9
- to: plasticity-johnson-cook
  type: feeds-into
  weight: 1.0
- to: plasticity-lode-triaxiality
  type: requires
  weight: 0.9
- to: damage-element-erosion
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Johnson-Cook Fracture Model

## Summary

Johnson-Cook fracture model formulates rate- and temperature-dependent ductile damage evolution where a scalar damage variable tracks plastic strain accumulation normalized by a stress-state and temperature-dependent failure strain.

## 1. Core Concept

The Johnson-Cook damage model extends finite-strain viscoplasticity by incorporating a scalar damage history variable D in [1] to represent dynamic material degradation and loss of load-carrying capacity. Undamaged material corresponds to D = 0, whereas D = 1 indicates complete failure where Cauchy stress vanishes. Damage evolution is governed by the rate equation \dot{D} = \dot{\bar{\varepsilon}} / \varepsilon_f, where \bar{\varepsilon} is equivalent plastic strain and \varepsilon_f is the failure strain threshold depending on hydrostatic pressure, strain rate, and temperature. In computational physics codes and inelastic equations of state (IEOS), Johnson-Cook damage couples with Helmholtz free energy potentials to model high-strain-rate impact and shock wave propagation.

## 2. Mathematical Formulation

**Johnson-Cook Scalar Damage Evolution Rate**
$$
\dot{D} = \frac{\dot{\bar{\varepsilon}}}{\varepsilon_f}
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 311, 312_

**Johnson-Cook Plastic Flow Strain Energy Function**
$$
Y(\bar{\varepsilon}, T) = \left[ A + B \bar{\varepsilon}^N \right] \left[ 1 - \left( \theta(T) \right)^M \right], \quad \theta(T) = \frac{T - T_r}{T_M - T_r}
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 309, 310; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 245_

**Inelastic Equation of State (IEOS) Damage Potential Relation**
$$
\bm{\sigma} = J^{-1} \frac{\partial \tilde{\Psi}}{\partial \bm{\varepsilon}^e}, \quad \tilde{\Psi} = \tilde{\Psi}(\bm{\varepsilon}^e, D, T)
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 310, 312-314_

**Consistency Condition for Damaged Inelastic Response**
$$
\tilde{F}(\bm{\tau}, \bar{\varepsilon}, D, T) = \bar{\tau} - (1 - D) Y(\bar{\varepsilon}, T) = 0
$$
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 310-314_

**Notation:**
D: scalar damage parameter (0 \le D \le 1); \dot{\bar{\varepsilon}}: equivalent plastic strain rate; \varepsilon_f: failure strain threshold; Y: flow stress function; A, B, N, M: Johnson-Cook material strength parameters; T: absolute temperature; T_r: reference room temperature; T_M: melting temperature; \theta(T): homologous temperature; \bm{\sigma}: Cauchy stress tensor; \bm{\tau}: Kirchhoff stress tensor; \bar{\tau}: equivalent von Mises Kirchhoff stress; \tilde{\Psi}: damage-degraded Helmholtz free energy density; J: elastic volumetric Jacobian ratio.


## 3. Algorithmic Implementation

**Johnson-Cook Plasticity and Damage Time Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: elastic strain } \bm{\varepsilon}^e_n, \text{ equivalent plastic strain } \bar{\varepsilon}_n, \text{ damage } D_n, \text{ temperature } T_n, \text{ and deformation gradient increment } \mathbf{F}$
\State $\text{Compute trial elastic strain } \bm{\varepsilon}^{e,tr} = \bm{\varepsilon}^e_n + \operatorname{sym}(\nabla \Delta \bm{u}) \text{ and trial Kirchhoff stress } \bm{\tau}^{tr} = \frac{\partial \tilde{\Psi}}{\partial \bm{\varepsilon}^{e,tr}}$
\State $\theta = \frac{T_n - T_r}{T_M - T_r}, \quad Y_n = [A + B (\bar{\varepsilon}_n)^N][1 - \theta^M]$
\State $\tilde{F}^{tr} = \bar{\tau}^{tr} - (1 - D_n) Y_n$
\If{$\tilde{F}^{tr} \le 0$}
\State $\bm{\sigma}_{n+1} = J^{-1} \bm{\tau}^{tr}, \quad \bar{\varepsilon}_{n+1} = \bar{\varepsilon}_n, \quad D_{n+1} = D_n$
\Return $\text{Step is elastic; accept trial state}$
\Else
\EndIf
\State $\Delta \bar{\varepsilon} = \Delta \lambda, \quad \bar{\varepsilon}_{n+1} = \bar{\varepsilon}_n + \Delta \bar{\varepsilon}$
\State $\Delta D = \frac{\Delta \bar{\varepsilon}}{\varepsilon_f(p, \dot{\bar{\varepsilon}}, T)}, \quad D_{n+1} = \min(D_n + \Delta D, 1.0)$
\State $\bm{\sigma}_{n+1} = (1 - D_{n+1}) J^{-1} \bm{\tau}_{n+1}$
\Return $\text{Return updated stress } \bm{\sigma}_{n+1}, \text{ equivalent plastic strain } \bar{\varepsilon}_{n+1}, \text{ and damage } D_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 310-316_


## 4. Known Pitfalls

- **Uncoupled Damage Integration and Unphysical Stress Growth**: Updating Johnson-Cook damage D independently from plastic yield consistency allows equivalent stress to increase due to strain hardening even as damage approaches unity, predicting unphysical energy dissipation and numerical instability. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 470-471; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 182-184)_
- **Singularity in Energy Potential Derivatives as Damage Approaches Unity**: Evaluating elastic stress or tangent operators as damage approaches complete material failure (D \to 1) without proper lower bounds causes division by zero and matrix ill-conditioning in finite element solvers. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 312-314; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 183-184)_
- **Omission of Pressure and Strain-Rate Sensitivity in Constant Failure Strain Approximations**: Assuming a constant failure strain \varepsilon_f independent of pressure, strain rate, and temperature oversimplifies material response, failing to capture spallation or shear band localization under dynamic impact loading. _(Source: Sanchez - 2021 - Inelastic equation of state for solids.pdf p. 311; Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 4, 8)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Sanchez - 2021 - Inelastic equation of state for solids.pdf
