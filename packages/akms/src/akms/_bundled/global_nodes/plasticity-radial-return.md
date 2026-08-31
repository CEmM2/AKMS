---
id: plasticity-radial-return
title: Radial Return for J2 Plasticity
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- radial-return
- j2
- return-mapping
- implicit
status: established
confidence: 0.9
source: hybrid
edges:
- to: plasticity-von-mises
  type: requires
  weight: 1.0
- to: constit-stress-update-architecture
  type: requires
  weight: 1.0
- to: plasticity-isotropic-hardening
  type: requires
  weight: 0.9
- to: plasticity-kinematic-hardening
  type: feeds-into
  weight: 0.7
- to: plasticity-consistent-tangent-j2
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Radial Return for J2 Plasticity

## Summary

The radial return algorithm is an implicit backward Euler integration scheme for J2 von Mises plasticity that projects trial elastic stress radially onto the yield surface in deviatoric stress space.

## 1. Core Concept

The radial return algorithm integrates rate-independent J2 von Mises plastic constitutive equations over discrete finite time increments using an operator split into an elastic predictor and a plastic corrector. Under isotropic elastic response, the yield surface normal in deviatoric stress space is collinear with the trial deviatoric stress tensor \bm{s}^{\mathrm{tr}}. As established by Wilkins (1964), Simo and Hughes (1998), and Čermák et al. (2019), the plastic correction reduces to a scalar return mapping along the radial direction \bm{n}^{\mathrm{tr}} = \bm{s}^{\mathrm{tr}} / \|\bm{s}^{\mathrm{tr}}\|. For linear isotropic and kinematic hardening, the radial return projection yields a closed-form update for the discrete plastic consistency multiplier \Delta \gamma without requiring iterative local equation solving.

## 2. Mathematical Formulation

**Deviatoric Elastic Trial Stress and Shifted Stress**
$$
\bm{s}^{\mathrm{tr}} = \bm{s}_n + 2G \operatorname{dev}(\Delta \bm{\varepsilon}), \quad \bm{\xi}^{\mathrm{tr}} = \bm{s}^{\mathrm{tr}} - \bm{\alpha}_n
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 120, 124; Kim_FEA for Elastoplastic Problems.pdf p. 202, 222; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598_

**J2 Yield Criterion Admissibility Test**
$$
f^{\mathrm{tr}} = \|\bm{\xi}^{\mathrm{tr}}\| - \sqrt{\frac{2}{3}} \sigma_y(\bar{\varepsilon}^p_n)
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 120, 124; Kim_FEA for Elastoplastic Problems.pdf p. 202, 222_

**Closed-Form Plastic Multiplier Formula (Linear Hardening)**
$$
\Delta \gamma = \frac{f^{\mathrm{tr}}}{2G + \frac{2}{3}(K^{\prime} + H^{\prime})} = \frac{\|\bm{s}^{\mathrm{tr}}\| - Y}{2G + a}
$$
_Source: Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598; Simo_Hughes_1998_Computational inelasticity.pdf p. 124; Kim_FEA for Elastoplastic Problems.pdf p. 203, 222_

**Radial Return Stress and Internal State Updates**
$$
\bm{s}_{n+1} = \bm{s}^{\mathrm{tr}} - 2G \Delta \gamma \bm{n}^{\mathrm{tr}}, \quad \bm{\alpha}_{n+1} = \bm{\alpha}_n + \frac{2}{3} H^{\prime} \Delta \gamma \bm{n}^{\mathrm{tr}}, \quad \bar{\varepsilon}^p_{n+1} = \bar{\varepsilon}^p_n + \sqrt{\frac{2}{3}} \Delta \gamma
$$
_Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 120, 124; Kim_FEA for Elastoplastic Problems.pdf p. 202-204, 222; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598_

**Notation:**
\bm{s}: deviatoric Cauchy stress tensor; \bm{s}^{\mathrm{tr}}: trial elastic deviatoric stress tensor; \bm{\alpha}: back stress tensor; \bm{\xi}^{\mathrm{tr}}: trial shifted stress tensor (\bm{s}^{\mathrm{tr}} - \bm{\alpha}_n); G, \mu: elastic shear modulus; \mathbf{I}_{\mathrm{dev}}: fourth-order deviatoric projection tensor; \Delta \gamma: discrete plastic multiplier; \bm{n}^{\mathrm{tr}}: unit normal vector to yield surface (\bm{\xi}^{\mathrm{tr}} / \|\bm{\xi}^{\mathrm{tr}}\|); \sigma_y, Y: flow yield stress radius; K^{\prime}, H^{\prime}, a: plastic hardening moduli parameters.


## 3. Algorithmic Implementation

**J2 Plasticity Radial Return Mapping Algorithm**
$$
\begin{algorithmic}
\State $\text{Given state at } t_n\text{: Cauchy stress } \bm{\sigma}_n, \text{ back stress } \bm{\alpha}_n, \text{ plastic strain } \bar{\varepsilon}^p_n, \text{ strain increment } \Delta \bm{\varepsilon}, \text{ shear modulus } G, \text{ bulk modulus } K, \text{ and yield stress } Y$
\State $\bm{s}_n = \bm{\sigma}_n - \frac{1}{3} \mathrm{tr}(\bm{\sigma}_n) \mathbf{I}, \quad \bm{s}^{\mathrm{tr}} = \bm{s}_n + 2G \operatorname{dev}(\Delta \bm{\varepsilon}), \quad \bm{\xi}^{\mathrm{tr}} = \bm{s}^{\mathrm{tr}} - \bm{\alpha}_n$
\State $f^{\mathrm{tr}} = \|\bm{\xi}^{\mathrm{tr}}\| - Y, \quad \bm{n}^{\mathrm{tr}} = \frac{\bm{\xi}^{\mathrm{tr}}}{\|\bm{\xi}^{\mathrm{tr}}\|}$
\If{$f^{\mathrm{tr}} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{s}^{\mathrm{tr}} + \left[ \frac{1}{3} \mathrm{tr}(\bm{\sigma}_n) + K \mathrm{tr}(\Delta \bm{\varepsilon}) \right] \mathbf{I}, \quad \bm{\alpha}_{n+1} = \bm{\alpha}_n, \quad \bar{\varepsilon}^p_{n+1} = \bar{\varepsilon}^p_n$
\Return $\text{Step is elastic; return trial elastic state}$
\Else
\EndIf
\State $\bm{s}_{n+1} = \bm{s}^{\mathrm{tr}} - 2G \Delta \gamma \bm{n}^{\mathrm{tr}}, \quad \bm{\alpha}_{n+1} = \bm{\alpha}_n + \frac{2}{3} H^{\prime} \Delta \gamma \bm{n}^{\mathrm{tr}}, \quad \bar{\varepsilon}^p_{n+1} = \bar{\varepsilon}^p_n + \sqrt{\frac{2}{3}} \Delta \gamma$
\State $\bm{\sigma}_{n+1} = \bm{s}_{n+1} + \left[ \frac{1}{3} \mathrm{tr}(\bm{\sigma}_n) + K \mathrm{tr}(\Delta \bm{\varepsilon}) \right] \mathbf{I}$
\Return $\text{Return updated Cauchy stress } \bm{\sigma}_{n+1}, \text{ back stress } \bm{\alpha}_{n+1}, \text{ and plastic strain } \bar{\varepsilon}^p_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598; Simo_Hughes_1998_Computational inelasticity.pdf p. 120-125; Kim_FEA for Elastoplastic Problems.pdf p. 202-205, 222-224_


## 4. Known Pitfalls

- **Division by Zero at Zero Trial Deviatoric Stress Norm**: Evaluating unit normal vector \bm{n}^{\mathrm{tr}} = \bm{\xi}^{\mathrm{tr}} / \|\bm{\xi}^{\mathrm{tr}}\| when the trial shifted stress vanishes (\|\bm{\xi}^{\mathrm{tr}}\| \to 0) causes floating-point division by zero; trial yield function check (f^{\mathrm{tr}} \le 0) must bypass normal evaluation. _(Source: Kim_FEA for Elastoplastic Problems.pdf p. 202-204; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 34-35; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 598)_
- **Inappropriately Applying Radial Return to Plane Stress Formulations**: Applying standard 3D radial return return-mapping directly to plane stress J2 plasticity violates the zero out-of-plane normal stress condition (\sigma_{33} = 0), requiring specialized constrained plane-stress return algorithms. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 125-128; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf p. 248-250)_
- **Using Continuum Tangent Moduli Instead of Algorithmic Consistent Tangents**: Substituting continuum elastoplastic tangent moduli for algorithmic consistent tangents in implicit global Newton-Raphson solvers destroys asymptotic quadratic convergence, leading to excessive global iteration counts. _(Source: Simo_Hughes_1998_Computational inelasticity.pdf p. 122; Kim_FEA for Elastoplastic Problems.pdf p. 205-207; Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf p. 600)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Čermák et al_2019_Efficient and flexible MATLAB implementation of 2D and 3D elastoplastic problems.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
