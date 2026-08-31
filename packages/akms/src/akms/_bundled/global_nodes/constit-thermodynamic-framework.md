---
id: constit-thermodynamic-framework
title: Thermodynamic Framework (Helmholtz, Dissipation)
domain: computational-mechanics
subdomain: constitutive
tags:
- constitutive
- thermodynamics
- internal-variables
- dissipation
- clausius-duhem
status: established
confidence: 0.9
source: hybrid
edges:
- to: constit-stress-update-architecture
  type: feeds-into
  weight: 1.0
- to: plasticity-von-mises
  type: feeds-into
  weight: 0.9
- to: damage-continuum-framework
  type: feeds-into
  weight: 0.8
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Thermodynamic Framework (Helmholtz, Dissipation)

## Summary

Thermodynamic framework provides the physical foundation for constitutive modeling, leveraging Helmholtz free energy potentials and the Clausius-Duhem dissipation inequality to enforce thermodynamic consistency.

## 1. Core Concept

The thermodynamic framework of constitutive modeling formulates continuum state laws and evolution equations using thermodynamic principles. The internal material state is defined by observable kinematic variables (e.g., elastic strain tensor) and internal state variables representing microstructural evolution, dislocation storage, or damage. The Helmholtz free energy potential determines stress tensors and conjugate thermodynamic forces via the Coleman-Noll procedure. Enforcing the Clausius-Duhem entropy inequality guarantees non-negative mechanical dissipation during inelastic flow. Thermodynamic consistency is established either through the Principle of Maximum Dissipation, which yields associative flow rules and Kuhn-Tucker loading/unloading conditions, or through Onsagerian linear relations coupling thermodynamic forces to flux evolution rates.

## 2. Mathematical Formulation

**Helmholtz Free Energy Decomposition and Stress Relation**
$$
\Psi(\bm{\varepsilon}^e, \bm{\alpha}, a) = \Psi^e(\bm{\varepsilon}^e) + \Psi^k(\bm{\alpha}) + \Psi^i(a), \quad \bm{\sigma} = \frac{\partial \Psi}{\partial \bm{\varepsilon}^e}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 27, 104; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf p. 5390_

**Clausius-Duhem Dissipation Inequality**
$$
\mathcal{D}_{mech} = \bm{\sigma} : \dot{\bm{\varepsilon}}^p + \bm{A} : \dot{\bm{\alpha}} + A_a \dot{a} \ge 0, \quad \bm{A} = -\frac{\partial \Psi}{\partial \bm{\alpha}}, \quad A_a = -\frac{\partial \Psi}{\partial a}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 27, 101; entropy-25-00721-v2.pdf p. 9, 10_

**Principle of Maximum Plastic Dissipation**
$$
(\bm{\sigma} - \bm{\tau}^*) : \dot{\bm{\varepsilon}}^p + (\bm{A} - \bm{A}^*) : \dot{\bm{\alpha}} \ge 0 \quad \forall (\bm{\tau}^*, \bm{A}^*) \in \mathbb{E}_{\sigma}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 98-102; Kim_FEA for Elastoplastic Problems.pdf p. 296-298_

**Onsagerian Thermodynamic Linear Flux-Force Relations**
$$
\begin{bmatrix} \dot{\bm{\alpha}} \\ \bm{q} \end{bmatrix} = \mathbf{M} \begin{bmatrix} -\frac{\partial \Psi}{\partial \bm{\alpha}} \\ -\nabla \theta \end{bmatrix}
$$
_Source: entropy-25-00721-v2.pdf p. 8, 10, 12_

**Notation:**
\Psi: Helmholtz free energy density per unit reference volume; \bm{\varepsilon}^e: elastic strain tensor; \bm{\varepsilon}^p: plastic strain tensor; \bm{\sigma}: Cauchy stress tensor; \bm{\alpha}: kinematic hardening back-stress tensor internal variable; a: isotropic hardening scalar internal variable; \bm{A}: thermodynamic force conjugate to \bm{\alpha}; A_a: thermodynamic force conjugate to a; \mathcal{D}_{mech}: mechanical rate of energy dissipation per unit volume; \mathbb{E}_{\sigma}: closed convex elastic domain in stress/force space; f: yield function; \mathbf{M}: positive semi-definite Onsagerian response matrix; \theta: absolute temperature; \bm{q}: heat flux vector.


## 3. Algorithmic Implementation

**Thermodynamic State Determination and Dissipation Verification**
$$
\begin{algorithmic}
\State $\text{Given total strain } \bm{\varepsilon}_{n+1}, \text{ internal state } \bm{\alpha}_n, a_n, \text{ and free energy function } \Psi(\bm{\varepsilon}^e, \bm{\alpha}, a)$
\State $\text{Compute trial elastic strain } \bm{\varepsilon}^{e,tr} = \bm{\varepsilon}_{n+1} - \bm{\varepsilon}^p_n \text{ and trial stress } \bm{\sigma}^{tr} = \left.\frac{\partial \Psi}{\partial \bm{\varepsilon}^e}\right|^{tr}$
\State $\text{Compute thermodynamic conjugate forces } \bm{A}_n = -\frac{\partial \Psi}{\partial \bm{\alpha}_n}, \quad A_{a,n} = -\frac{\partial \Psi}{\partial a_n}$
\State $f^{tr} = f(\bm{\sigma}^{tr}, \bm{A}_n, A_{a,n})$
\If{$f^{tr} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{tr}, \quad \bm{\alpha}_{n+1} = \bm{\alpha}_n, \quad a_{n+1} = a_n, \quad \mathcal{D}_{mech} = 0$
\Return $\text{Process is purely elastic; dissipation is zero and state is accepted}$
\Else
\EndIf
\State $\dot{\bm{\varepsilon}}^p = \dot{\gamma} \frac{\partial f}{\partial \bm{\sigma}}, \quad \dot{\bm{\alpha}} = \dot{\gamma} \frac{\partial f}{\partial \bm{A}}, \quad \dot{a} = \dot{\gamma} \frac{\partial f}{\partial A_a}$
\State $\mathcal{D}_{mech} = \bm{\sigma}_{n+1} : \dot{\bm{\varepsilon}}^p + \bm{A}_{n+1} : \dot{\bm{\alpha}} + A_{a,n+1} \dot{a} = \dot{\gamma} \left(\bm{\sigma}_{n+1} : \frac{\partial f}{\partial \bm{\sigma}} + \bm{A}_{n+1} : \frac{\partial f}{\partial \bm{A}} + A_{a,n+1} \frac{\partial f}{\partial A_a}\right)$
\If{$\mathcal{D}_{mech} \ge 0$}
\State $\text{Update state variables } \bm{\sigma}_{n+1}, \bm{\varepsilon}^p_{n+1}, \bm{\alpha}_{n+1}, a_{n+1}$
\Return $\text{Thermodynamic consistency verified; accept state}$
\Else
\EndIf
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 27-28, 98-102; Kim_FEA for Elastoplastic Problems.pdf p. 296-298; entropy-25-00721-v2.pdf p. 8-10_


## 4. Known Pitfalls

- **Assuming Unconstrained State Variable Independence in Internal Variable Theories**: Applying Coleman-Noll procedures directly to internal variables assumes their time rates can be controlled independently on boundaries; however, internal variables are observable but not controllable, requiring Onsagerian linear flux-force relations or thermodynamic variational principles (Principle of Maximum Dissipation) to establish evolution equations. _(Source: entropy-25-00721-v2.pdf p. 2, 8; Simo_Hughes_1998_Computational inelasticity.pdf p. 98-102)_
- **Ignoring Stored Energy of Hardening in Heat Generation Calculations**: Assuming all plastic work is converted into thermal dissipation ignores the thermodynamic energy storage in dislocation microstructures (\Psi^k, \Psi^i), overestimating the Taylor-Quinney coefficient and thermal softening in coupled thermomechanical problems. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 27-28; Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf p. 4, 10)_
- **Spurious Dissipation in Elastic Predictor Step**: Evolving internal state variables or plastic strains during the elastic trial evaluation violates the Coleman-Noll thermoelastic constitutive relation, generating unphysical mechanical dissipation before yield admissibility is determined. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 27, 103-104; Kim_FEA for Elastoplastic Problems.pdf p. 296-298)_

## References

- Clayton - 2025 - Analysis of adiabatic shear coupled to ductile fracture and melting in viscoplastic metals.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- entropy-25-00721-v2.pdf
