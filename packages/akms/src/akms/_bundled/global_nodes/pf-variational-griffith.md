---
id: pf-variational-griffith
title: Griffith Energy & Variational Fracture (Francfort-Marigo)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- fracture
- griffith
- variational
- gamma-convergence
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: damage-continuum-framework
  type: refines
  weight: 0.7
- to: pf-at2-regularization
  type: feeds-into
  weight: 0.5
- to: pf-at1-regularization
  type: feeds-into
  weight: 0.5
- to: pf-cohesive-zone
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Griffith Energy & Variational Fracture (Francfort-Marigo)

## Summary
The variational formulation of fracture due to Francfort and Marigo (1998)
recasts Griffith's criterion as a global energy minimization: the elastic
strain energy plus the surface energy of the crack set is minimized over
admissible displacement fields and crack geometries. Unlike classical
Griffith, no pre-existing crack is required and crack nucleation,
branching, and arrest emerge naturally from the minimization. The
Ambrosio-Tortorelli regularization makes this tractable in FE codes by
smearing the crack into a phase field that Gamma-converges to the sharp
crack as the regularization length ell -> 0.


## 1. Core Concept
Griffith's classical theory states that a crack advances when the energy
release rate G equals the critical fracture energy Gc. This is a local
criterion that requires a pre-existing crack and knowledge of crack-tip
fields, and cannot predict crack nucleation, kinking, or branching from
first principles.

Francfort and Marigo (1998) reformulated fracture as a global variational
principle: minimize the total energy
    E(u, K) = elastic_energy(u) + Gc * H^{n-1}(K)
over admissible displacements u and crack sets K, subject to the
irreversibility constraint K(t1) subset K(t2) for t1 < t2. This admits
arbitrary crack topology evolution from minimization alone.

Direct numerical solution is intractable because K is a lower-dimensional
set. The Ambrosio-Tortorelli (1990) regularization replaces the sharp
crack K with a continuous phase field d (or phi) in [0,1] (d=0 intact,
d=1 fully cracked) and approximates the surface energy by a volume
integral
    Gc * H^{n-1}(K) approx Gc * integral_Omega gamma_l(d, grad d) dV
where gamma_l is a regularized crack surface density per unit volume.
As ell -> 0, the regularized functional Gamma-converges to the sharp-crack
Francfort-Marigo functional, guaranteeing the discrete approximation
recovers the variational fracture solution.


## 2. Mathematical Formulation
The phase-field formulation introduces a continuous order parameter
representing material damage and a crack surface density that approximates
the codimension-1 crack set in the limit ell -> 0.


**griffith-criterion:**

$$
G \;=\; -\frac{\partial \Pi}{\partial A} \;=\; G_c \quad \text{(crack advance condition)}
$$

where Pi = total potential energy; A = crack area; Gc = critical energy release rate

**francfort-marigo-energy:**

$$
\mathcal{E}(\mathbf{u}, K) \;=\; \int_{\Omega \setminus K} \psi(\boldsymbol{\varepsilon}(\mathbf{u})) \, dV \;+\; G_c \, \mathcal{H}^{n-1}(K)
$$

where psi = elastic strain energy density; H^{n-1} = (n-1)-dimensional Hausdorff measure of crack set K

**minimization-principle:**

$$
(\mathbf{u}_t, K_t) \;=\; \arg\min_{(\mathbf{u}, K)} \mathcal{E}(\mathbf{u}, K) \quad \text{s.t.} \quad K_s \subset K_t \;\forall s \le t
$$

where irreversibility: crack set monotonically grows in time

**regularized-crack-density:**

$$
\gamma_\ell(d, \nabla d) \;=\; \frac{1}{2\ell} \, d^2 \;+\; \frac{\ell}{2} |\nabla d|^2 \quad \text{(AT2 form)}
$$

where ell = regularization length scale; gamma_l integrates to approx H^{n-1}(K) as ell -> 0

**regularized-energy:**

$$
\mathcal{E}_\ell(\mathbf{u}, d) \;=\; \int_\Omega g(d) \, \psi(\boldsymbol{\varepsilon}) \, dV \;+\; G_c \int_\Omega \gamma_\ell(d, \nabla d) \, dV
$$

where g(d) = degradation function (typically (1-d)^2); recovers Francfort-Marigo as ell -> 0

**gamma-convergence:**

$$
\mathcal{E}_\ell \;\xrightarrow{\Gamma}\; \mathcal{E} \quad \text{as} \quad \ell \to 0
$$

where Gamma-convergence guarantees minimizers of the regularized functional approximate minimizers of the sharp-crack functional

**Notation:**

- $u$ — displacement field
- $d, phi$ — phase field / damage variable in [0,1]
- $K$ — sharp crack set (lower-dimensional)
- $Gc$ — critical fracture energy (Griffith)
- $ell$ — regularization length scale
- $gamma_l$ — regularized crack surface density per volume
- $g(d)$ — degradation function


## 3. Algorithmic Implementation
**Algorithm: variational-fracture-flow**

$$
\begin{algorithmic}
\State $$
\State $$
\State $$
\State $$
\end{algorithmic}
$$

**Taichi Mapping:**
Two ti.field arrays: u (vector) and d (scalar). At each time step,
assemble two residuals (momentum + phase-field balance) and solve
either alternately (staggered) or together (monolithic). History
variable kappa stored at Gauss points.



## 4. Known Pitfalls
**ell-as-physical-length:** AT2 has no elastic limit (sigma_c -> 0 as ell -> 0), so ell is a
physical material length, not a vanishing numerical parameter. Choosing
ell affects the response, not just resolution. AT1 and PF-CZM
partially decouple ell from sigma_c.


**mesh-resolution:** Gamma-convergence requires h << ell; rule of thumb h <= ell/2 to
resolve the diffuse crack profile. Coarse meshes overestimate Gc by
a factor (1 + h/(c_w*ell)).


**irreversibility-enforcement:** Without explicit irreversibility, d can decrease on unloading,
producing unphysical "crack healing". Enforce via kappa-history
(Miehe 2010), penalty term, or active-set bound enforcement.


**nonconvex-energy:** The coupled (u, d) energy is non-convex in (u, d) jointly though
convex in each separately. Monolithic Newton can stall at local
minima; staggered alternate minimization is more robust but slower
to converge.


**branch-prediction-cost:** Variational fracture predicts branching automatically — but the
mesh must be fine enough to resolve all branches. Use AMR (h-adaptive
refinement) where d > threshold to keep cost tractable.


## 5. References
- Francfort, G. A., Marigo, J.-J. (1998). Revisiting brittle fracture as an energy minimization problem. JMPS 46:1319-1342.
- Bourdin, B., Francfort, G. A., Marigo, J.-J. (2000). Numerical experiments in revisited brittle fracture. JMPS 48:797-826.
- Ambrosio, L., Tortorelli, V. M. (1990). Approximation of functionals depending on jumps by elliptic functionals via Gamma-convergence. CPAM 43:999-1036.
- Miehe, C., Welschinger, F., Hofacker, M. (2010). Thermodynamically consistent phase-field models of fracture: variational principles and multi-field FE implementations. IJNME 83:1273-1311.
- Griffith, A. A. (1921). The phenomena of rupture and flow in solids. Philosophical Transactions A 221:163-198.
