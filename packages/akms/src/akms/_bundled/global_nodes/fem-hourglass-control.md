---
id: fem-hourglass-control
title: Hourglass Stabilization
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- hourglass
- reduced-integration
- stabilization
- flanagan-belytschko
status: established
confidence: 0.9
source: hybrid
edges:
- to: fem-isoparametric-mapping
  type: requires
  weight: 0.9
- to: fem-locking-remedies
  type: requires
  weight: 0.9
- to: kinematics-velocity-gradient
  type: feeds-into
  weight: 0.6
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Hourglass Stabilization

## Summary

Hourglass stabilization suppresses spurious zero-energy deformation modes (hourglass modes) that arise when under-integrated (one-point quadrature) continuum elements are used in finite element analyses. Stabilization methods add artificial stiffness or viscosity orthogonal to physical rigid-body and linear strain fields using hourglass vectors, scaling parameters, and dilatational wave speeds.

## 1. Core Concept

Under-integrated isoparametric elements, such as 4-node quadrilaterals or 8-node hexahedra with one-point quadrature, eliminate volumetric locking and significantly reduce computational effort. However, reduced integration creates rank-deficient stiffness matrices with spurious non-zero kinematic modes that produce zero strain at the quadrature center. Hourglass control eliminates these spurious modes by projecting nodal velocity/displacement vectors onto specialized hourglass vectors orthogonal to linear fields, adding a stabilization force scaled by a perturbation stiffness modulus C^Q or maximum element stiffness K_{\mathrm{max}}.

## 2. Mathematical Formulation

**Hourglass Vector Orthogonality**
$$
\gamma = h - \frac{1}{A} (h^T x) b_1 - \frac{1}{A} (h^T y) b_2
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.7.2, Eq. 8.7.4, p. 519_

**Generalized Hourglass Strain Rate**
$$
q_i = \gamma^T v_i
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.7.3, Eq. 8.7.9b, p. 521_

**Perturbation Hourglass Stiffness Modulus**
$$
C^Q = \frac{1}{2} \alpha_s c^2 \rho A b_i^T b_i
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.7.3, Eq. 8.7.14, p. 522_

**Hourglass Stabilization Nodal Force**
$$
f_i^{\mathrm{stab}} = Q_i \gamma
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.7.3, Eq. 8.7.11 & 8.7.18, pp. 521–523_

**Hexahedron Hourglass Resistance Force**
$$
f_{Ii}^{\mathrm{Hg}} = k u_{Ji} \gamma_J \gamma_I, \quad k = \frac{\epsilon K_{\mathrm{max}}}{8}
$$
_Source: TL_hourglass.pdf, Eqs. 4, 12, 13, pp. 1315–1316_

**Notation:**
{'\\gamma': 'Hourglass projection vector orthogonal to linear displacement fields.', 'h': 'Base hourglass vector [1, -1, 1, -1]^T.', 'q_i': 'Generalized hourglass strain rate.', 'Q_i': 'Generalized hourglass stress.', 'C^Q': 'Perturbation hourglass stabilization modulus.', 'c': 'Dilatational wave speed c = \\sqrt{(\\lambda + 2\\mu)/\\rho}.', '\\alpha_s': 'Non-dimensional hourglass scaling parameter (\\alpha_s \\approx 0.1).', 'f_i^{\\mathrm{stab}}': 'Vector of stabilization nodal forces.'}


## 3. Algorithmic Implementation

**Perturbation Hourglass Stabilization Force Computation**
$$
\begin{algorithmic}
\State $Given nodal coordinates x, y, nodal velocities v_x, v_y, and material properties \rho, c, \alpha_s$
\State $Compute element area A and shape function derivatives b_1, b_2 at element centroid \xi = (0,0)$
\State $Compute hourglass vector \gamma \gets h - \frac{1}{A}(h^T x) b_1 - \frac{1}{A}(h^T y) b_2$
\State $Compute generalized strain rates q_x \gets \gamma^T v_x \text{ and } q_y \gets \gamma^T v_y$
\State $Compute stabilization modulus C^Q \gets \frac{1}{2} \alpha_s c^2 \rho A (b_1^T b_1 + b_2^T b_2)$
\State $Compute generalized stress rates \dot{Q}_x \gets C^Q q_x \text{ and } \dot{Q}_y \gets C^Q q_y$
\State $Update generalized stresses Q_x \gets Q_x + \Delta t \dot{Q}_x \text{ and } Q_y \gets Q_y + \Delta t \dot{Q}_y$
\State $Compute stabilization nodal forces f_x^{\mathrm{stab}} \gets Q_x \gamma \text{ and } f_y^{\mathrm{stab}} \gets Q_y \gamma$
\Return $f_x^{\mathrm{stab}}, f_y^{\mathrm{stab}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.7.3 & Box 8.2, pp. 521–524_


## 4. Known Pitfalls

- **Over-Stabilization and Artificial Stiffening**: Setting the hourglass scaling parameter \alpha_s or \epsilon too large introduces excessive artificial stiffness into the model, locking the element in bending or shear and corrupting the physical response. Mitigation: Keep scaling parameters in recommended ranges (\alpha_s \approx 0.1, or \epsilon between 0.01 and 0.05). _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.7.5, p. 522 & Sec. 9.9, p. 593)_
- **Non-Orthogonality Under Finite Rigid-Body Rotations**: Evaluating hourglass vectors in the unrotated global coordinate frame causes rigid-body rotations to generate non-zero fake hourglass strain rates q_i, producing spurious internal stabilization forces. Mitigation: Evaluate hourglass vectors and nodal velocities in a corotational or objective local element coordinate frame. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 8.2, p. 524; TL_hourglass.pdf, Sec. 1, p. 1315)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- TL_hourglass.pdf
