---
id: pf-at1-regularization
title: AT1 Regularization (Linear Crack Density)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- AT1
- regularization
- elastic-limit
- bound-constraint
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-variational-griffith
  type: refines
  weight: 0.7
- to: pf-at2-regularization
  type: contradicts
  weight: 0.0
- to: pf-cohesive-zone
  type: feeds-into
  weight: 0.5
- to: pf-staggered-scheme
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# AT1 Regularization (Linear Crack Density)

## Summary

The AT1 phase-field damage formulation (Pham et al., 2011) employs a linear geometric crack function \alpha(d) = d and quadratic energetic degradation function \omega(d) = (1-d)^2 to model brittle fracture with a distinct finite elastic regime. Unlike the standard AT2 model—which initiates damage immediately upon non-zero strain—AT1 incorporates a strictly positive elastic limit threshold stress \sigma_c = \sqrt{3 E_0 G_f / (8 b)}, below which the material remains purely elastic. The geometric crack density surface functional incorporates a geometric scaling constant c_{\alpha} = 8/3 and a regularization length scale b. Numerical implementation of AT1 requires bound-constrained variational inequality solvers or history-field updates to rigorously enforce damage irreversibility \dot{d} \ge 0 and phase-field boundedness 0 \le d \le 1.

## 1. Core Concept

The AT1 model is a regularized gradient-damage approximation of Griffith brittle fracture that introduces a purely linear geometric crack density function \alpha(d) = d. In contrast to AT2 regularization where \alpha(d) = d^2 causes immediate damage nucleation at infinitesimal stress levels, the linear density in AT1 creates a finite dissipation gradient at d=0. This establishes a well-defined elastic domain bounded by a critical threshold stress \sigma_c = \sqrt{3 E_0 G_f / (8 b)}. During loading below \sigma_c, the thermodynamic damage driving force Q(d) remains strictly negative or zero, preventing spurious damage accumulation. Upon reaching \sigma_c, damage initiates and localizes within a finite crack band of width proportional to length scale b. Because the linear crack function yields a non-zero threshold at d=0, numerical algorithms must enforce bound constraints (0 \le d \le 1) and irreversibility (\dot{d} \ge 0) using active-set methods, augmented Lagrangian formulations, or historical maximum driving force fields \mathcal{H}. Within unified phase-field damage theory, AT1 represents the linear geometric limit precursor to cohesive zone formulations.

## 2. Mathematical Formulation

**at1_crack_density_functional**
$$
\Gamma_b(d) = \int_{B} \gamma(d, \nabla d) dV = \int_{B} \frac{1}{c_{\alpha}} \left[ \frac{\alpha(d)}{b} + b |\nabla d|^2 \right] dV = \int_{B} \frac{3}{8} \left[ \frac{d}{b} + b |\nabla d|^2 \right] dV
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**at1_elastic_limit_threshold**
$$
\sigma_c = \sqrt{\frac{3 E_0 G_f}{8 b}}, \quad \epsilon_c = \frac{\sigma_c}{E_0} = \sqrt{\frac{3 G_f}{8 E_0 b}}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**at1_governing_microforce_equation**
$$
\nabla \cdot \mathbf{q} + Q(d) \le 0, \quad \mathbf{q} = \frac{2b}{c_{\alpha}} G_f \nabla d = \frac{3}{4} b G_f \nabla d, \quad Q(d) = -\omega'(d) \mathcal{H} - \frac{G_f}{c_{\alpha} b} \alpha'(d) = 2(1-d) \mathcal{H} - \frac{3 G_f}{8 b}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**at1_irreversibility_history_field**
$$
\mathcal{H}(x, t) = \max_{\tau \in [0, t]} \bar{Y}(x, \tau), \quad \bar{Y} = \frac{\bar{\sigma}_{eq}^2}{2 E_0}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture_

**Notation:**
d: scalar damage variable (d \in [1]); \alpha(d): linear crack geometric function (\alpha(d)=d); \omega(d): energetic degradation function (\omega(d)=(1-d)^2); b: regularization length scale parameter; c_{\alpha}: geometric scaling constant (c_{\alpha}=8/3 for AT1); G_f: critical energy release rate (fracture toughness); E_0: Young's modulus; \sigma_c: finite elastic threshold stress; \mathcal{H}: historical strain energy release rate driving field; \mathbf{q}: microforce damage flux; Q(d): damage source driving force.


## 3. Algorithmic Implementation

**at1-staggered-bound-constrained-solver**
$$
\begin{algorithmic}
\State $Initialize nodal displacement vector \mathbf{a}_0, nodal damage vector \bar{\mathbf{a}}_0 = \mathbf{0}, and history field \mathcal{H}_0 = 0.$
\For{$Loop over time increments n = 1, 2, \dots, N_{steps}.$}
\State $Set iteration counter k = 0, initial trial displacement \mathbf{a}_{n+1}^{(0)} = \mathbf{a}_n, and initial trial damage \bar{\mathbf{a}}_{n+1}^{(0)} = \bar{\mathbf{a}}_n.$
\While{$Residual norm \|\mathbf{g}^{(k)}\| > \text{tol}.$}
\State $Solve mechanical displacement sub-problem for \mathbf{a}_{n+1}^{(k+1)} with fixed damage \bar{\mathbf{a}}_{n+1}^{(k)}: \mathbf{K}_{uu}(\bar{\mathbf{a}}_{n+1}^{(k)}) \delta \mathbf{a} = \mathbf{r}_u.$
\State $Evaluate effective equivalent stress \bar{\sigma}_{eq} at element integration points and update history field: \mathcal{H}_{n+1} = \max\left(\mathcal{H}_n, \frac{\bar{\sigma}_{eq}^2}{2 E_0}\right).$
\State $Assemble damage stiffness matrix \mathbf{K}_{dd} = \int_B \left[ 2 \mathcal{H}_{n+1} \bar{\mathbf{N}}^T \bar{\mathbf{N}} + \frac{3}{4} b G_f \bar{\mathbf{B}}^T \bar{\mathbf{B}} \right] dV and damage residual \mathbf{r}_d.$
\State $Solve damage sub-problem for trial increment: \mathbf{K}_{dd} \delta \bar{\mathbf{a}} = \mathbf{r}_d \implies \bar{\mathbf{a}}_{trial} = \bar{\mathbf{a}}_{n+1}^{(k)} + \delta \bar{\mathbf{a}}.$
\If{$Bound constraints or damage irreversibility are violated (\bar{\mathbf{a}}_{trial} < \bar{\mathbf{a}}_n or \bar{\mathbf{a}}_{trial} > \mathbf{1}).$}
\State $Enforce nodal bound projections: \bar{\mathbf{a}}_{n+1}^{(k+1)} = \max\left(\bar{\mathbf{a}}_n, \min\left(\mathbf{1}, \bar{\mathbf{a}}_{trial}\right)\right).$
\EndIf
\State $Increment iteration counter k \leftarrow k + 1.$
\EndWhile
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Amor et al. (2009), Regularized formulation of the variational brittle fracture with unilateral contact_


## 4. Known Pitfalls

- **at1-spurious-damage-triggering-below-elastic-limit**: In contrast to the AT2 model where damage initiates at zero stress, AT1 relies on a threshold stress \sigma_c = \sqrt{3 E_0 G_f / (8 b)}. If history field \mathcal{H} is computed without subtracting or accounting for the linear dissipation threshold \frac{3 G_f}{8 b}, numerical errors can trigger premature, unphysical damage evolution below the elastic limit. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_
- **at1-mesh-resolution-and-length-scale-sensitivity**: Because the linear geometric crack function \alpha(d)=d produces a sharp damage profile cusp at d=1, the finite element mesh size h inside the localized crack band must be significantly smaller than length scale b (typically h \le b/5). Coarse meshes fail to resolve the crack surface density \Gamma_b(d), leading to severe mesh-bias and overestimation of peak load capacity. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture)_

## References

- Pham, K., Amor, H., Marigo, J.-J., and Maurini, C. (2011). Gradient damage models and their use to approximate brittle fracture. International Journal of Damage Mechanics, 20(4), 618-652.
- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Miehe, C., Welschinger, F., and Hofacker, M. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Amor, H., Marigo, J.-J., and Maurini, C. (2009). Regularized formulation of the variational brittle fracture with unilateral contact: Numerical experiments. Journal of the Mechanics and Physics of Solids, 57(8), 1209-1229.
