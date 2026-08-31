---
id: plasticity-general-return-mapping
title: General Return Mapping (Backward Euler)
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- return-mapping
- backward-euler
- implicit-integration
- newton
status: established
confidence: 0.9
source: hybrid
edges:
- to: constit-stress-update-architecture
  type: requires
  weight: 1.0
- to: plasticity-radial-return
  type: refines
  weight: 0.9
- to: plasticity-cpp-nonassociative
  type: feeds-into
  weight: 0.9
- to: plasticity-consistent-tangent-general
  type: feeds-into
  weight: 1.0
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# General Return Mapping (Backward Euler)

## Summary

General return mapping integrates elastoplastic constitutive equations over finite strain increments using a backward Euler implicit integration scheme that enforces yield surface consistency at the end of the step.

## 1. Core Concept

The general backward Euler return-mapping algorithm integrates elastoplastic constitutive rate equations over discrete time increments [t_n, t_{n+1}]. Operating under an operator-split paradigm, the algorithm first computes an elastic predictor state with frozen internal plastic variables. If the trial elastic stress violates plastic admissibility (f^{tr} > 0), an implicit plastic corrector step projects the stress state back onto the yield surface. Local Newton-Raphson iterations solve the coupled discrete system enforcing plastic flow direction and yield consistency f(\bm{\sigma}_{n+1}, \bm{q}_{n+1}) = 0 at the step endpoint, ensuring unconditional algorithmic stability and path-independent state updates.

## 2. Mathematical Formulation

**Discrete Backward Euler Stress Update Relation**
$$
\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}} - \Delta \gamma \mathbf{D}^e : \mathbf{m}_{n+1}, \quad \mathbf{m}_{n+1} = \left. \frac{\partial g}{\partial \bm{\sigma}} \right|_{n+1}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 143-144; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 242_

**Internal Hardening Variable Evolution Update**
$$
\bm{q}_{n+1} = \bm{q}_n - \Delta \gamma \bm{h}(\bm{\sigma}_{n+1}, \bm{q}_{n+1})
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 143; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 242_

**Step-End Plastic Yield Consistency Condition**
$$
f(\bm{\sigma}_{n+1}, \bm{q}_{n+1}) = 0, \quad \Delta \gamma \ge 0, \quad f(\bm{\sigma}_{n+1}, \bm{q}_{n+1}) \Delta \gamma = 0
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 143; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 242_

**Plastic Flow Residual Vector System**
$$
\bm{R}_{\bm{\varepsilon}}(\bm{\sigma}_{n+1}, \bm{q}_{n+1}, \Delta \gamma) = -\bm{\varepsilon}^p_{n+1} + \bm{\varepsilon}^p_n + \Delta \gamma \mathbf{m}_{n+1} = \bm{0}
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.5, p. 146_

**Notation:**
\bm{\sigma}_{n+1}: updated Cauchy stress tensor; \bm{\sigma}^{\mathrm{tr}}: elastic trial stress tensor; \mathbf{D}^e: fourth-order elastic stiffness tensor; \Delta \gamma: discrete plastic consistency parameter; f: yield function; g: plastic potential function; \mathbf{m}: plastic flow direction tensor (\partial g / \partial \bm{\sigma}); \mathbf{n}: yield surface normal tensor (\partial f / \partial \bm{\sigma}); \bm{q}: internal hardening state variable vector; \bm{h}: hardening evolution function; \bm{R}_{\bm{\varepsilon}}: local plastic flow residual tensor.


## 3. Algorithmic Implementation

**General Backward Euler Return-Mapping Integration Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: stress } \bm{\sigma}_n, \text{ plastic strain } \bm{\varepsilon}^p_n, \text{ internal variables } \bm{q}_n, \text{ and strain increment } \Delta \bm{\varepsilon}$
\State $\bm{\sigma}^{\mathrm{tr}} = \bm{\sigma}_n + \mathbf{D}^e : \Delta \bm{\varepsilon}, \quad \bm{q}^{\mathrm{tr}} = \bm{q}_n, \quad f^{\mathrm{tr}} = f(\bm{\sigma}^{\mathrm{tr}}, \bm{q}^{\mathrm{tr}})$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{\mathrm{tr}}, \quad \bm{\varepsilon}^p_{n+1} = \bm{\varepsilon}^p_n, \quad \bm{q}_{n+1} = \bm{q}_n$
\Return $\text{Step is elastic; return trial state}$
\Else
\EndIf
\While{$\|\bm{R}_{\bm{\sigma}}^{(k)}\| > \text{TOL}_1 \quad \text{or} \quad |f^{(k)}| > \text{TOL}_2$}
\State $\mathbf{n}^{(k)} = \left.\frac{\partial f}{\partial \bm{\sigma}}\right|_{n+1}^{(k)}, \quad \mathbf{m}^{(k)} = \left.\frac{\partial g}{\partial \bm{\sigma}}\right|_{n+1}^{(k)}, \quad \mathbf{\Xi}^{(k)} = \left[ \mathbf{D}^{e-1} + \Delta \gamma^{(k)} \frac{\partial^2 g}{\partial \bm{\sigma}^2} \right]^{-1}$
\State $d\Delta \gamma = \frac{f^{(k)} - \mathbf{n}^{(k)} : \mathbf{\Xi}^{(k)} : \bm{R}_{\bm{\sigma}}^{(k)}}{\mathbf{n}^{(k)} : \mathbf{\Xi}^{(k)} : \mathbf{m}^{(k)} + H_{\mathrm{alg}}^{(k)}}$
\State $d\bm{\sigma} = -\mathbf{\Xi}^{(k)} : \left[ \bm{R}_{\bm{\sigma}}^{(k)} + d\Delta \gamma \mathbf{m}^{(k)} \right]$
\State $\bm{\sigma}_{n+1}^{(k+1)} = \bm{\sigma}_{n+1}^{(k)} + d\bm{\sigma}, \quad \Delta \gamma^{(k+1)} = \Delta \gamma^{(k)} + d\Delta \gamma, \quad k = k + 1$
\EndWhile
\Return $\text{Return updated stress } \bm{\sigma}_{n+1}, \text{ plastic strain } \bm{\varepsilon}^p_{n+1}, \text{ and internal variables } \bm{q}_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Simo_Hughes_1998_Computational inelasticity.pdf Box 3.5, p. 146; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 242-246_


## 4. Known Pitfalls

- **Overtaking Trial Yield Boundary and Missing Unloading Transitions**: Evaluating trial elastic stress without verifying yield function admissibility f^{\mathrm{tr}} \le 0 can execute plastic corrector updates during elastic unloading, causing unphysical plastic dissipation and spurious stress drift. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 241-242; Kim_FEA for Elastoplastic Problems.pdf p. 203)_
- **Loss of Quadratic Solver Convergence Using Non-Consistent Tangents**: Substituting the continuum elastoplastic tangent operator D^{ep} for the exact consistent algorithmic tangent operator in global Newton-Raphson iterations destroys asymptotic quadratic convergence, requiring excess global equilibrium iterations. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 145-147; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 38-39)_
- **Ill-Conditioning near Non-Smooth Yield Surface Vertices**: Applying smooth backward Euler return mapping equations at non-differentiable yield surface corners or apices introduces singular Hessians \partial^2 g / \partial \bm{\sigma}^2 and division by zero, requiring multi-surface Koiter return algorithms or subdifferential formulations. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 212-215; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 252-253; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf
