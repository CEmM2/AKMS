---
id: plasticity-perzyna
title: Perzyna Viscoplasticity
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- viscoplasticity
- perzyna
- rate-dependent
- regularisation
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-von-mises
  type: refines
  weight: 0.9
- to: constit-stress-update-architecture
  type: requires
  weight: 1.0
- to: plasticity-duvaut-lions
  type: contradicts
  weight: 0.5
- to: pf-ductile-plasticity-coupling
  type: feeds-into
  weight: 0.6
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Perzyna Viscoplasticity

## Summary

Perzyna viscoplasticity formulates rate-dependent inelastic deformation using an overstress function that allows stress states to exceed the yield surface.

## 1. Core Concept

Perzyna viscoplasticity extends classical rate-independent plasticity to rate-dependent regimes by replacing discrete Kuhn-Tucker yield consistency with a continuous overstress rate law. In the Perzyna formulation, plastic flow occurs whenever the yield function f(\bm{\sigma}, \bm{q}) > 0, with the viscoplastic strain rate \dot{\bm{\varepsilon}}^{vp} governed by a monotonic function of the overstress \Phi(f) scaled by a fluid viscosity parameter \eta. Under dynamic strain softening, viscoplasticity regularizes ill-posed boundary value problems, restoring hyperbolicity in transient initial-value problems and preventing mesh sensitivity.

## 2. Mathematical Formulation

**Perzyna Viscoplastic Flow Rule**
$$
\dot{\bm{\varepsilon}}^{vp} = \frac{\langle \Phi(f(\bm{\sigma}, \bm{q})) \rangle}{\eta} \frac{\partial f}{\partial \bm{\sigma}}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 109; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 293_

**Macaulay Bracket Overstress Function Definition**
$$
\langle \Phi(f) \rangle = \frac{\Phi(f) + |\Phi(f)|}{2}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 109_

**Implicit Discrete Viscoplastic Return Residual Equation**
$$
r_f = \Phi(f(\bm{\sigma}_{n+1}, \kappa_{n+1})) - \frac{\Delta \gamma \eta}{\Delta t} = 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 293_

**Viscoplastic Regularized Stress Solution**
$$
\bm{\sigma}_{n+1} = \frac{\bm{\sigma}^{\mathrm{tr}} + \frac{\Delta t}{\tau} \bm{\sigma}_{\infty}}{1 + \frac{\Delta t}{\tau}}, \quad \tau = \frac{\eta}{E + K}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 1.7, p. 68_

**Notation:**
\dot{\bm{\varepsilon}}^{vp}: viscoplastic strain rate tensor; f: yield function; \Phi(f): scalar overstress function; \eta: fluid viscosity parameter; \langle \cdot \rangle: Macaulay bracket operator; \bm{\sigma}: Cauchy stress tensor; \bm{\sigma}^{\mathrm{tr}}: elastic trial stress; \bm{\sigma}_{\infty}: rate-independent yield stress; \Delta \gamma: discrete plastic consistency parameter; \Delta t: time step size; \tau: characteristic relaxation time.


## 3. Algorithmic Implementation

**Perzyna Viscoplasticity Implicit Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: stress } \bm{\sigma}_n, \text{ viscoplastic strain } \bm{\varepsilon}^{vp}_n, \text{ hardening variable } \kappa_n, \text{ time step } \Delta t, \text{ and viscosity } \eta$
\State $\bm{\sigma}^{\mathrm{tr}} = \bm{\sigma}_n + \mathbf{D}^e : \Delta \bm{\varepsilon}, \quad f^{\mathrm{tr}} = f(\bm{\sigma}^{\mathrm{tr}}, \kappa_n)$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}}, \quad \bm{\varepsilon}^{vp}_{n+1} = \bm{\varepsilon}^{vp}_n, \quad \kappa_{n+1} = \kappa_n$
\Return $\text{Step is elastic; accept trial state}$
\Else
\EndIf
\State $\bm{\varepsilon}^{vp}_{n+1} = \bm{\varepsilon}^{vp}_n + \Delta \gamma \frac{\partial f}{\partial \bm{\sigma}_{n+1}}, \quad \kappa_{n+1} = \kappa_n + \Delta \gamma$
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}} - \Delta \gamma \mathbf{D}^e : \frac{\partial f}{\partial \bm{\sigma}_{n+1}}$
\Return $\text{Return updated stress } \bm{\sigma}_{n+1}, \text{ viscoplastic strain } \bm{\varepsilon}^{vp}_{n+1}, \text{ and hardening variable } \kappa_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 1.7, p. 68, p. 150; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 293_


## 4. Known Pitfalls

- **Assuming Zero Yield Function Excess Under Dynamic Viscoplastic Loading**: Applying rate-independent Karush-Kuhn-Tucker consistency conditions (f = 0) to Perzyna viscoplasticity prevents the stress state from exceeding the yield surface (f > 0), failing to model rate-dependent overstress behavior. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 293; Simo_Hughes_1998_Computational inelasticity.pdf p. 109)_
- **Ill-Conditioned Explicit Integration for Small Viscosity Values**: Integrating Perzyna rate equations explicitly using forward Euler schemes when fluid viscosity parameter \eta is very small causes numerical stiffness and severe time-step restrictions (\Delta t < \tau); implicit backward Euler integration is required for stability. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 68, 150; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 293)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- Zabaras and Arif - 1992 - A family of integration algorithms for constitutive equations in finite deformation elasto‐viscoplas.pdf
