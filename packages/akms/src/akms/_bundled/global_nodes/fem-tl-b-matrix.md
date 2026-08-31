---
id: fem-tl-b-matrix
title: TL B-Matrix (Strain-Displacement Operator)
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- finite-strain
- total-lagrangian
- b-matrix
- elements
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fem-tl-weak-form
  type: requires
  weight: 1.0
  note: B-matrix is the operator linking nodal $\delta\mathbf{u}$ to $\delta\mathbf{E}$ in the weak form
- to: kinematics-motion-deformation-gradient
  type: requires
  weight: 1.0
  note: $\mathbf{B}_1$ depends on $\mathbf{F}$ — nonlinear in displacement
- to: tensor-voigt-notation
  type: requires
  weight: 0.8
  note: Voigt form of B-matrix uses the kinematic rule (factor 2 on shears)
- to: fem-tl-linearization
  type: feeds-into
  weight: 1.0
  note: Material tangent $\mathbf{K}_m=\int\mathbf{B}^T\mathbb{C}^{SE}\mathbf{B}\,dV_0$
- to: kinematics-convected-coordinates
  type: refines
  weight: 0.5
  note: Convected-basis B-matrix is an alternative formulation in curvilinear coordinates
context_size: large
reading_priority: full
load_with:
- fem-tl-weak-form
- tensor-voigt-notation
content_ref: null
akms_schema: v2
---

# TL B-Matrix (Strain-Displacement Operator)

## Summary
The TL B-matrix maps nodal displacement variations to the variation of Green-Lagrange strain: $\delta\mathbf{E}=\sum_a\mathbf{B}_a\,\delta\mathbf{u}_a$. It splits into a constant linear part $\mathbf{B}_0$ (the small-strain B-matrix) and a displacement-dependent nonlinear part $\mathbf{B}_1(\mathbf{u})=\mathbf{B}_1(\mathbf{F})$. In Voigt / kinematic form (with factor 2 on shears), the indicial pieces are $(\mathbf{B}_0)_{aIJk}=\tfrac12(\delta_{kI}\partial N_a/\partial X_J+\delta_{kJ}\partial N_a/\partial X_I)$ and $(\mathbf{B}_1)_{aIJk}=\tfrac12(F_{kI}\partial N_a/\partial X_J+F_{kJ}\partial N_a/\partial X_I)-(\mathbf{B}_0)_{aIJk}$, so the full B-matrix is $\mathbf{B}_a=\mathbf{B}_0(\mathbf{F}=\mathbf{I})+\mathbf{B}_1(\mathbf{F})=\tfrac12(F_{kI}\partial N_a/\partial X_J+F_{kJ}\partial N_a/\partial X_I)$ in compact form. Reference shape function gradients $\partial N_a/\partial\mathbf{X}$ are constant in time (TL); only $\mathbf{F}$ updates each step. The internal-force computation $\int_{\Omega_0}\mathbf{B}^T\mathbf{S}\,dV_0$ contracts the B-matrix with the PK2 stress at every Gauss point.


## 1. Core Concept
The TL B-matrix is the algebraic backbone of finite-strain FEM assembly: it converts the geometric question "how does the strain change when nodal displacements change?" into a linear operator on the nodal displacement increments. The split $\mathbf{B}=\mathbf{B}_0+\mathbf{B}_1(\mathbf{u})$ separates the (cheap, constant) small-strain contribution from the (expensive, $\mathbf{F}$-dependent) finite-strain contribution. $\mathbf{B}_0$ alone gives the linear elasticity B-matrix and is recovered when $\mathbf{F}\to\mathbf{I}$; $\mathbf{B}_1$ adds the cubic / quadratic terms in displacement that make the residual nonlinear. Reference shape function gradients $\partial N_a/\partial\mathbf{X}$ — the data that enters both $\mathbf{B}_0$ and $\mathbf{B}_1$ — are computed once at the start of the simulation from the reference parent-physical mapping and stored: a major efficiency advantage over UL-FEM, where current shape function gradients $\partial N_a/\partial\mathbf{x}=(\partial N_a/\partial\mathbf{X})\mathbf{F}^{-1}$ must be recomputed every step. The Voigt convention introduces the most common bug: the kinematic rule (factor 2 on shears) on the strain side is what makes $\mathbf{B}^T\{\mathbf{S}\}$ produce the correct internal force.


## 2. Mathematical Formulation
Indices $a$ runs over element nodes ($n_n$ total), $i,j,k\in\{1,2,3\}$ spatial, $I,J,K\in\{1,2,3\}$ material. $\nabla_0 N_a=\partial N_a/\partial\mathbf{X}$. $\mathbf{F}=\mathbf{I}+\sum_a\mathbf{u}_a\otimes\nabla_0 N_a$.


**Nodal strain-displacement relation:**

$$
\delta\mathbf{E}(\mathbf{X}) = \sum_{a=1}^{n_n}\mathbf{B}_a(\mathbf{X};\mathbf{F})\,\delta\mathbf{u}_a
$$

where Linear in $\delta\mathbf{u}_a$, nonlinear in $\mathbf{u}_a$ through $\mathbf{F}$

**Tensor (indicial) form of TL B-matrix:**

$$
(\mathbf{B}_a)_{IJk} = \tfrac{1}{2}\!\left(F_{kI}\,\frac{\partial N_a}{\partial X_J} + F_{kJ}\,\frac{\partial N_a}{\partial X_I}\right)
$$

where Symmetric in $(I,J)$; the $k$-leg is spatial / displacement-component

**Linear / nonlinear split:**

$$
\mathbf{B}_a = \mathbf{B}_0^a + \mathbf{B}_1^a(\mathbf{F}),\qquad
(\mathbf{B}_0^a)_{IJk} = \tfrac{1}{2}(\delta_{kI}\,\partial N_a/\partial X_J + \delta_{kJ}\,\partial N_a/\partial X_I),\quad
(\mathbf{B}_1^a)_{IJk} = (\mathbf{B}_a)_{IJk} - (\mathbf{B}_0^a)_{IJk}
$$

where $\mathbf{B}_0$ is the small-strain B-matrix; $\mathbf{B}_1$ vanishes when $\mathbf{F}=\mathbf{I}$

**Voigt form (3D, kinematic rule):**

$$
[\mathbf{B}_a]_{6\times 3}
= \begin{bmatrix}
F_{1I}\,\partial N_a/\partial X_1 \\[2pt]
F_{2I}\,\partial N_a/\partial X_2 \\[2pt]
F_{3I}\,\partial N_a/\partial X_3 \\[2pt]
F_{2I}\,\partial N_a/\partial X_3 + F_{3I}\,\partial N_a/\partial X_2 \\[2pt]
F_{1I}\,\partial N_a/\partial X_3 + F_{3I}\,\partial N_a/\partial X_1 \\[2pt]
F_{1I}\,\partial N_a/\partial X_2 + F_{2I}\,\partial N_a/\partial X_1
\end{bmatrix}_{I=1,2,3}
$$

where Six rows = $\{E_{11},E_{22},E_{33},2E_{23},2E_{13},2E_{12}\}$ Voigt strain; factor 2 on shears already absorbed

**Internal force at node $a$:**

$$
\mathbf{f}^{\mathrm{int}}_a = \int_{\Omega_0}\mathbf{B}_a^T\,\mathbf{S}\,dV_0
                        = \int_{\Omega_0}\nabla_0 N_a\cdot(\mathbf{F}\,\mathbf{S})\,dV_0
$$

where Both forms produce the same nodal force; second avoids explicit B construction

**Convected (curvilinear) form:**

$$
(\mathbf{B}_a)_{IJk}^{\mathrm{conv}}
= \tfrac{1}{2}\!\left(g_{ki}\,(\mathbf{N}_a)_I\,(\mathbf{N}_a)_J\,\delta_J{}^I + \cdots\right)
$$

where Schematic — full convected derivation in `kinematics-convected-coordinates`; reduces to the Cartesian form when $\mathbf{G}_i=\mathbf{e}_i$

**Hex8 isoparametric construction:**

$$
N_a(\boldsymbol{\xi}) = \tfrac{1}{8}(1+\xi_1\xi_1^a)(1+\xi_2\xi_2^a)(1+\xi_3\xi_3^a),\;
\frac{\partial N_a}{\partial \mathbf{X}} = (\mathbf{J}^{\mathrm{ref}})^{-1}\cdot\frac{\partial N_a}{\partial \boldsymbol{\xi}}
$$

where $\boldsymbol{\xi}^a$ corner coordinates; $\mathbf{J}^{\mathrm{ref}}=\partial\mathbf{X}/\partial\boldsymbol{\xi}$ parent-reference Jacobian

**Reduction to small strain ($\mathbf{F}\to\mathbf{I}$):**

$$
\lim_{\mathbf{F}\to\mathbf{I}}\mathbf{B}_a = \mathbf{B}_0^a,\qquad
\delta\mathbf{E} \to \delta\boldsymbol{\varepsilon} = \tfrac{1}{2}(\nabla_0\delta\mathbf{u}+\nabla_0\delta\mathbf{u}^T)
$$

where TL recovers linear elasticity exactly in the small-strain limit

**Notation:**

- $\mathbf{B}_a$ — Full TL B-matrix block for node $a$
- $\mathbf{B}_0^a$ — Linear (small-strain) part; constant in time
- $\mathbf{B}_1^a(\mathbf{F})$ — Nonlinear part; depends on current $\mathbf{F}$
- $\mathbf{F}$ — Deformation gradient at the Gauss point
- $N_a$ — Shape function for node $a$
- $\partial N_a/\partial \mathbf{X}$ — Reference shape function gradient
- $\mathbf{J}^{\mathrm{ref}}$ — Reference parent-physical Jacobian, $\mathbf{J}^{\mathrm{ref}}=\partial \mathbf{X}/\partial \boldsymbol{\xi}$
- $\delta\mathbf{u}_a,\delta\mathbf{E}$ — Variation of nodal displacement and Green-Lagrange strain
- $E_{IJ}$ — Green-Lagrange strain components


## 3. Algorithmic Implementation
**Algorithm: Construct TL B-Matrix at a Gauss Point**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{F},\,\{\partial N_a/\partial \mathbf{X}\}_{a=1}^{n_n}$
\For{$a = 1,\ldots,n_n$}
\For{$I,J = 1,2,3 \;\text{(symmetric pair)},\,k = 1,2,3$}
\State $(\mathbf{B}_a)_{IJk} \gets \tfrac{1}{2}(F_{kI}\,\partial N_a/\partial X_J + F_{kJ}\,\partial N_a/\partial X_I)$
\EndFor
\EndFor
\State $\text{convert to Voigt 6x3 form via the symmetric-pair index map (kinematic rule absorbs factor 2 on shears)}$
\Return $[\mathbf{B}_a]\,\text{for}\,a=1,\ldots,n_n$
\end{algorithmic}
$$

**Taichi Mapping:**
Pre-compute $\partial N_a/\partial \mathbf{X}$ once per element at startup (reference data, constant in time). Build the Voigt 6x3 form per node directly from the indicial expression to avoid the explicit symmetric-pair conversion. For hex8 / tet4 with $n_n=8/4$ nodes, fully unroll the node loop with `ti.static(range(n_n))`. Storage: $6\times 3 n_n$ floats per Gauss point — for hex8 = 144 floats. Total memory across all Gauss points may be too large; recompute per Newton iteration if memory is tight.


**Algorithm: Internal Force via $\mathbf{B}^T\mathbf{S}$ vs $\nabla_0 N_a\cdot\mathbf{P}$**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{S}\,\text{(Voigt 6-vector)},\,\mathbf{F},\,\partial N_a/\partial \mathbf{X}$
\State $\text{Option 1: } \mathbf{f}^{\mathrm{int}}_a \mathrel{+}= \mathbf{B}_a^T\,\{\mathbf{S}\}\,w_g\,\det J_g$
\State $\text{Option 2: } \mathbf{P} \gets \mathbf{F}\,\mathbf{S},\;\mathbf{f}^{\mathrm{int}}_{a,i} \mathrel{+}= P_{iJ}\,(\partial N_a/\partial X_J)\,w_g\,\det J_g$
\Return $\mathbf{f}^{\mathrm{int}}_a$
\end{algorithmic}
$$

**Taichi Mapping:**
Option 2 (PK1 / nominal product) avoids storing the full B-matrix and is faster on GPU when $n_n$ is large (high-order elements). Option 1 is convenient when the same B-matrix is reused for $\mathbf{B}^T\mathbb{C}^{SE}\mathbf{B}$ in the material tangent (`fem-tl-linearization`). Choose based on whether implicit / explicit dynamics is being run.


**Algorithm: Convert from Indicial to Voigt B-Matrix**

$$
\begin{algorithmic}
\State $\text{input} \colon (\mathbf{B}_a)_{IJk}\,\text{indicial}$
\For{$\alpha = 1,\ldots,6 \;\text{Voigt index}$}
\State $(I,J) \gets \mathrm{voigt\_pair}(\alpha) \in \{(1,1),(2,2),(3,3),(2,3),(1,3),(1,2)\}$
\For{$k = 1,2,3$}
\If{$I = J$}
\State $[\mathbf{B}_a]_{\alpha k} \gets (\mathbf{B}_a)_{IIk}$
\Else
\State $[\mathbf{B}_a]_{\alpha k} \gets 2\,(\mathbf{B}_a)_{IJk} \;\text{(kinematic Voigt: factor 2 on shears)}$
\EndIf
\EndFor
\EndFor
\Return $[\mathbf{B}_a]_{6\times 3}$
\end{algorithmic}
$$

**Taichi Mapping:**
Inline the conversion inside the assembly kernel — never as a separate routine. The factor 2 on shears is absorbed into the off-diagonal Voigt rows; failing to apply it produces shear stresses half their correct values. Tag every B-matrix array with `_voigt_kin` to make the convention explicit at API boundaries.



## 4. Known Pitfalls
**Factor of 2 on shear strains in Voigt-form B-matrix:** The kinematic Voigt rule requires multiplying off-diagonal (shear) rows of $[\mathbf{B}_a]$ by 2 so that $\{\mathbf{S}\}^T[\mathbf{B}_a]\delta\mathbf{u}_a$ reproduces the indicial $\mathbf{S}\colon\delta\mathbf{E}$. Forgetting it halves the shear contribution to the internal force; the bug is silent on uniaxial tests but obvious on shear-dominated benchmarks.


**Mismatch between $\mathbf{B}_0$ and $\mathbf{B}_1$ conventions:** Some references define $\mathbf{B}_1$ with $F_{kI}\partial N_a/\partial X_J$ (full $\mathbf{F}$) and others with $H_{kI}\partial N_a/\partial X_J$ (displacement gradient $\mathbf{H}=\mathbf{F}-\mathbf{I}$). The two differ by exactly $\mathbf{B}_0$, so $\mathbf{B}=\mathbf{B}_0+\mathbf{B}_1$ remains the same — but mixing the conventions in a code can produce a stiffness off by $\mathbf{B}_0$ in the linear part. Document and stick with one convention.


**Sign error in $\mathbf{F}$ dependence:** $\mathbf{F}=\mathbf{I}+\nabla_0\mathbf{u}$ — note the sign on $\nabla_0\mathbf{u}$ is positive. A common slip in code is $\mathbf{F}=\mathbf{I}-\nabla_0\mathbf{u}$ (confusion with $\mathbf{F}^{-1}\approx\mathbf{I}-\nabla_0\mathbf{u}$ at small strain). The wrong sign makes $\mathbf{B}_1$ negative-definite and Newton iteration diverges immediately under tension.


**Double-counting symmetric variations:** $\delta\mathbf{E}$ is symmetric ($\delta\mathbf{E}=\delta\mathbf{E}^T$); summing over all 9 components rather than the 6 unique ones double-counts off-diagonal entries and produces a residual wrong by a factor of 2 in shear blocks. Iterate over $I\le J$ when constructing $\delta\mathbf{E}$ in tensor form, OR use the Voigt 6-vector form with the kinematic rule's factor 2 already baked in.


**Performance issues with dense $\mathbf{B}_1$ storage for high-order elements:** For hex20 / hex27 / spectral-element discretisations $n_n$ grows quickly (20-125 nodes per element) and storing the full $6\times 3 n_n$ B-matrix per Gauss point exceeds GPU register / shared-memory budgets. Either compute B on the fly (recompute per kernel call) or use the matrix-free $\mathbf{B}^T\mathbf{S}$ pattern with $\mathbf{P}=\mathbf{F}\mathbf{S}$ (`fem-tl-matrix-free-action`).


**Mixing reference and current shape function gradients:** In TL the gradients are $\partial N_a/\partial\mathbf{X}$ (reference, constant in time). In UL they are $\partial N_a/\partial\mathbf{x}=(\partial N_a/\partial\mathbf{X})\mathbf{F}^{-1}$ (current, updated each step). Using the latter inside a TL kernel halves the cost of the conversion but corrupts the strain-displacement operator (the B-matrix would need additional terms to compensate). Pick TL or UL; never mix.


**Asymmetric stiffness from inconsistent index pairing:** The B-matrix construction $(\mathbf{B}_a)_{IJk}=\tfrac12(F_{kI}\partial N_a/\partial X_J + F_{kJ}\partial N_a/\partial X_I)$ has a specific index-pair symmetry. A common typo swaps $\partial N_a/\partial X_J$ to $\partial N_a/\partial X_I$ on one side and produces a non-symmetric $\delta\mathbf{E}$. The downstream $\mathbf{K}_m=\int\mathbf{B}^T\mathbb{C}^{SE}\mathbf{B}\,dV_0$ becomes asymmetric and breaks Cholesky / LDL solvers.


**Hex8 element with reduced integration:** Hex8 with full Gauss integration (8 GPs) gives the correct B-matrix per GP. Reduced integration (1 GP at the centroid) is cheaper but introduces zero-energy modes (hourglass) that the B-matrix alone cannot stabilise — additional hourglass control is needed. The B-matrix construction is unchanged; the issue is the chosen quadrature rule.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed., Ch. 4-6 (TL B-matrix construction, Voigt form, hex8 / tet4 specifics)
- Bathe (1975) — Finite element formulations for large deformation dynamic analysis ($\mathbf{B}_0+\mathbf{B}_1$ split, original notation)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (Green strain B-matrix, 2D / 3D Voigt forms with engineering shear)

