---
id: kinematics-logarithmic-strain
title: Logarithmic (Hencky) Strain
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- hencky-strain
- log-strain
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: kinematics-polar-decomposition
  type: requires
  weight: 1.0
  note: $\mathbf{E}_{\log}=\ln\mathbf{U}$ depends on the right stretch from polar decomposition
- to: tensor-isotropic-functions
  type: requires
  weight: 1.0
  note: Spectral evaluation of $\ln\mathbf{C}$ via $\sum_a\ln\lambda_a\,\mathbf{P}_a$
- to: kinematics-strain-tensors
  type: refines
  weight: 0.9
  note: Hencky strain is the $m=0$ member of the Seth-Hill family
- to: kinematics-velocity-gradient
  type: feeds-into
  weight: 0.6
  note: Rate $\dot{\mathbf{E}}_{\log}$ equals $\mathbf{D}$ only for coaxial flows
context_size: medium
reading_priority: full
load_with:
- kinematics-polar-decomposition
- tensor-isotropic-functions
content_ref: null
akms_schema: v2
---

# Logarithmic (Hencky) Strain

## Summary
The logarithmic (Hencky) strain $\mathbf{E}_{\log}=\ln\mathbf{U}=\tfrac12\ln\mathbf{C}$ is the natural finite-strain extension of the small-strain tensor: it has additive structure on the principal axes and reduces exactly to $\boldsymbol{\varepsilon}=\tfrac12(\nabla\mathbf{u}+\nabla\mathbf{u}^T)$ in the small-strain limit. Spectrally $\mathbf{E}_{\log}=\sum_a\ln\lambda_a\,\mathbf{N}_a\otimes\mathbf{N}_a$ where $\lambda_a$ are principal stretches. Its rate equals the rate-of-deformation $\mathbf{D}$ ONLY for coaxial flows (no rotation of principal axes); under non-coaxial loading $\dot{\mathbf{E}}_{\log}\ne\mathbf{D}$ and the integral of $\mathbf{D}$ is path-dependent while $\mathbf{E}_{\log}$ is path-independent. The Miehe-Apel-Lambrecht (2002) framework wraps a small-strain plasticity model with geometric pre/post-processors $\mathbb{P}_L=2\,\partial\mathbf{E}_{\log}/\partial\mathbf{C}$ and $\mathbb{L}_L=4\,\partial^2\mathbf{E}_{\log}/\partial\mathbf{C}\partial\mathbf{C}$, evaluated by Carlson-Hoger divided differences with explicit L'Hopital limits at coincident eigenvalues.


## 1. Core Concept
Hencky strain has two virtues that make it the strain measure of choice for finite-strain plasticity. (1) Additive structure: principal Hencky strains add under composition of coaxial stretches, $\ln(\lambda_1\lambda_2)=\ln\lambda_1+\ln\lambda_2$, mirroring the additive small-strain calculus that constitutive theories were originally built on. (2) Volume-deviatoric decoupling: $\mathrm{tr}\,\mathbf{E}_{\log}=\ln J$ is exactly the logarithmic volume change, so the deviatoric Hencky strain $\mathbf{E}_{\log}^{\mathrm{dev}}=\mathbf{E}_{\log}-\tfrac13(\ln J)\mathbf{I}$ is a clean shape-change measure orthogonal to volume change. The price is that the decomposition through the eigenvalues of $\mathbf{C}$ (or $\mathbf{U}$) is required, with all the robustness machinery of `tensor-spectral-decomposition` and `tensor-isotropic-functions`. The Miehe et al. modular wrapper makes the price worthwhile: any small-strain plasticity model can be promoted to finite strain by sandwiching it between $\mathbb{P}_L$ and $\mathbb{L}_L$.


## 2. Mathematical Formulation
Throughout, $\mathbf{C}=\mathbf{F}^T\mathbf{F}$ is symmetric positive-definite (so $\det\mathbf{F}>0$). $\mathbf{U}=\sqrt{\mathbf{C}}$ is the right stretch from the polar decomposition. $\lambda_a$ are principal stretches (eigenvalues of $\mathbf{U}$); $\mathbf{N}_a$ material principal directions; $\mathbf{P}_a=\mathbf{N}_a\otimes\mathbf{N}_a$ eigenprojections.


**Definition (material / spatial):**

$$
\mathbf{E}_{\log} = \ln\mathbf{U} = \tfrac{1}{2}\ln\mathbf{C},\qquad
\mathbf{e}_{\log} = \ln\mathbf{V} = \tfrac{1}{2}\ln\mathbf{b}
$$

where Material (Lagrangian) and spatial (Eulerian) versions related by $\mathbf{e}_{\log}=\mathbf{R}\mathbf{E}_{\log}\mathbf{R}^T$

**Spectral form:**

$$
\mathbf{E}_{\log}
= \sum_{a=1}^{3}\ln\lambda_a\,\mathbf{P}_a
= \tfrac{1}{2}\sum_{a=1}^{3}\ln(\lambda_a^2(\mathbf{C}))\,\mathbf{P}_a(\mathbf{C})
$$

where $\lambda_a(\mathbf{C})=\lambda_a^2(\mathbf{U})$

**Volumetric / deviatoric decoupling:**

$$
\mathrm{tr}\,\mathbf{E}_{\log} = \ln J,\qquad
\mathbf{E}_{\log}^{\mathrm{dev}} = \mathbf{E}_{\log} - \tfrac{1}{3}\,(\ln J)\,\mathbf{I}
$$

where Deviatoric Hencky strain measures pure shape change; trace gives logarithmic volume strain

**Small-strain limit:**

$$
\mathbf{E}_{\log} = \boldsymbol{\varepsilon} + \mathcal{O}(\|\mathbf{H}\|^2),\qquad
\boldsymbol{\varepsilon} = \tfrac{1}{2}(\nabla\mathbf{u} + \nabla\mathbf{u}^T)
$$

where All Seth-Hill measures coincide in $\mathbf{H}\to 0$; Hencky uniquely preserves the additive structure

**Inverse: recovery of $\mathbf{C}$:**

$$
\mathbf{C} = \exp(2\,\mathbf{E}_{\log}) = \sum_{a=1}^{3}\exp(2\,e_a)\,\mathbf{P}_a,\qquad
e_a = \ln\lambda_a
$$

where Exponential map: takes Hencky strain back to deformation tensor

**Rate vs $\mathbf{D}$ — coaxial only:**

$$
\dot{\mathbf{E}}_{\log} = \mathbf{D} \;\Leftrightarrow\;
\dot{\mathbf{N}}_a = \mathbf{0}\;\text{(coaxial flow)}
$$

where For non-coaxial flow $\dot{\mathbf{E}}_{\log}\ne\mathbf{D}$ and the equality fails by spin-coupling terms

**Path independence:**

$$
\int_0^t \dot{\mathbf{E}}_{\log}\,d\tau = \mathbf{E}_{\log}(t)\;\;\text{(path-independent)},\qquad
\int_0^t \mathbf{D}\,d\tau \ne \mathbf{E}_{\log}(t)\;\;\text{(path-dependent)}
$$

where Logarithmic strain integrates to a state function; rate-of-deformation does not

**Miehe et al. transformation tensors:**

$$
\mathbb{P}_L = 2\,\frac{\partial \mathbf{E}_{\log}}{\partial \mathbf{C}},\qquad
\mathbb{L}_L = 4\,\frac{\partial^2 \mathbf{E}_{\log}}{\partial \mathbf{C}\partial\mathbf{C}}
$$

where Pre/post-processor 4th- / 6th-order tensors of the modular log-strain framework (`tensor-isotropic-functions`)

**Carlson-Hoger derivative:**

$$
\mathbb{P}_L = \sum_{i=1}^{3} d_i\,\mathbf{P}_i\bar\otimes\mathbf{P}_i
           + 2\sum_{i\ne j}\,\upsilon_{ij}\,\mathbf{P}_i\bar\otimes\mathbf{P}_j,
\qquad
d_i = \lambda_i^{-2},\;
\upsilon_{ij} = \frac{e_i - e_j}{\lambda_i^2 - \lambda_j^2}
$$

where Eigenvalues of $\mathbf{C}$ are $\lambda_i^2$; divided differences become $\tfrac{1}{2}d_i$ at coincident eigenvalues (`tensor-derivatives-tensors`)

**Notation:**

- $\mathbf{E}_{\log}$ — Lagrangian Hencky strain, $\ln\mathbf{U}=\tfrac12\ln\mathbf{C}$
- $\mathbf{e}_{\log}$ — Eulerian Hencky strain, $\ln\mathbf{V}=\tfrac12\ln\mathbf{b}$
- $\mathbf{U}$ — Right stretch (`kinematics-polar-decomposition`)
- $\mathbf{C}$ — Right Cauchy-Green tensor, $\mathbf{C}=\mathbf{F}^T\mathbf{F}=\mathbf{U}^2$
- $\lambda_a$ — Principal stretches
- $e_a$ — Logarithmic eigenstrains, $e_a=\ln\lambda_a$
- $\mathbf{P}_a$ — Eigenprojections, $\mathbf{P}_a=\mathbf{N}_a\otimes\mathbf{N}_a$
- $\mathbf{D}$ — Rate-of-deformation (`kinematics-velocity-gradient`)
- $\mathbb{P}_L,\mathbb{L}_L$ — Lagrangian transformation tensors of Miehe et al. 2002
- $J$ — Jacobian, $J=\det\mathbf{F}$


## 3. Algorithmic Implementation
**Algorithm: Hencky Strain via Spectral Decomposition of $\mathbf{C}$**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{C}\in\mathbb{R}^{3\times 3}_{\mathrm{sym},\mathrm{pd}},\,\text{tol }\tau$
\State $\{\lambda_i^2, \mathbf{N}_i\}_{i=1,2,3} \gets \mathrm{eig}(\mathbf{C}) \;\text{(closed-form Lode-angle)}$
\For{$i = 1,2,3$}
\If{$\lambda_i^2 < \lambda_{\min}^2$}
\State $\text{abort: log strain undefined for non-positive eigenvalues}$
\EndIf
\State $e_i \gets \tfrac{1}{2}\ln(\lambda_i^2)$
\EndFor
\State $\mathbf{E}_{\log} \gets \sum_{i=1}^{3} e_i\,\mathbf{N}_i\otimes\mathbf{N}_i$
\Return $\mathbf{E}_{\log}$
\end{algorithmic}
$$

**Taichi Mapping:**
Reuse the closed-form Lode-angle eigensolver. Use $\lambda_{\min}=10^{-3}$ in double precision; below that the log saturates and the constitutive model is outside its calibration range anyway. For mass production, fuse with the constitutive update in one kernel so the eigendecomposition is computed once and reused for both $\mathbf{E}_{\log}$ and $\mathbb{P}_L$.


**Algorithm: Tangent $\mathbb{P}_L$ via Carlson-Hoger Divided Differences**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{C},\,\{\lambda_i^2,\mathbf{N}_i\},\,e_i,\,\text{tol }\tau$
\For{$i = 1,2,3$}
\State $d_i \gets (\lambda_i^2)^{-1}$
\State $\mathbf{P}_i \gets \mathbf{N}_i\otimes\mathbf{N}_i$
\EndFor
\For{$i,j = 1,2,3,\;i\ne j$}
\If{$|\lambda_i^2 - \lambda_j^2| > \tau\,(\lambda_i^2 + \lambda_j^2)$}
\State $\upsilon_{ij} \gets (e_i - e_j)/(\lambda_i^2 - \lambda_j^2)$
\Else
\State $\upsilon_{ij} \gets \tfrac{1}{2}\,d_i \;\text{(L'Hopital limit)}$
\EndIf
\EndFor
\State $\mathbb{P}_L \gets \sum_i d_i\,\mathbf{P}_i\bar\otimes\mathbf{P}_i + 2\sum_{i\ne j}\upsilon_{ij}\,\mathbf{P}_i\bar\otimes\mathbf{P}_j$
\Return $\mathbb{P}_L$
\end{algorithmic}
$$

**Taichi Mapping:**
Store $\mathbb{P}_L$ in Mandel form ($6\times 6$) so the downstream stress map $\mathbf{S}=\mathbf{T}\colon\mathbb{P}_L$ is a $6$-vector / $6\times 6$ matrix dot product. Use $\tau=10^{-12}$ in double precision; the L'Hopital branch is rare except at exactly biaxial / hydrostatic loading, which are precisely the cases used in verification benchmarks.


**Algorithm: Modular Finite-Strain Plasticity Wrapper (Miehe et al. 2002)**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{C}_{n+1},\,(\mathbf{E}^p_n,q_n)$
\State $\mathbf{E}_{\log,n+1} \gets \tfrac{1}{2}\ln\mathbf{C}_{n+1}$
\State $\mathbb{P}_L \gets 2\,\partial\mathbf{E}_{\log}/\partial\mathbf{C}$
\State $\mathbf{T}_{n+1},\mathbf{E}^p_{n+1},q_{n+1},\mathbb{E}_{ep} \gets \mathrm{SmallStrainPlasticity}(\mathbf{E}_{\log,n+1},\mathbf{E}^p_n,q_n)$
\State $\mathbf{S}_{n+1} \gets \mathbf{T}_{n+1}\colon\mathbb{P}_L$
\State $\mathbb{L}_L \gets 4\,\partial^2 \mathbf{E}_{\log}/\partial\mathbf{C}\partial\mathbf{C}$
\State $\mathbb{C}^L_{ep} \gets \mathbb{P}_L^T\colon\mathbb{E}_{ep}\colon\mathbb{P}_L + \mathbf{T}_{n+1}\colon\mathbb{L}_L$
\Return $\mathbf{S}_{n+1},\mathbb{C}^L_{ep},\mathbf{E}^p_{n+1},q_{n+1}$
\end{algorithmic}
$$

**Taichi Mapping:**
The wrapper makes any verified small-strain return-mapping (`plasticity-return-mapping`, `plasticity-yield-surfaces`) usable at finite strain with no changes to the constitutive box. Cache the eigendecomposition of $\mathbf{C}_{n+1}$ once; reuse for $\mathbf{E}_{\log}$, $\mathbb{P}_L$, $\mathbb{L}_L$. The geometric correction $\mathbf{T}\colon\mathbb{L}_L$ is essential for quadratic Newton convergence at finite strain — do NOT drop it.



## 4. Known Pitfalls
**Branch-cut at non-positive principal stretches:** $\ln\lambda_a$ is real-valued only for $\lambda_a>0$. Numerical instability (element inversion, severe distortion) can briefly drive $\lambda_a\to 0$ and the spectral $\ln\mathbf{C}$ returns NaN. Detect $\lambda_{\min}<\lambda_{\mathrm{tol}}$ before invoking $\ln$; abort the increment / activate locking remedies / reduce the time step.


**$\dot{\mathbf{E}}_{\log}\ne\mathbf{D}$ for non-coaxial flows:** The naive identification $\dot{\mathbf{E}}_{\log}=\mathbf{D}$ is exact only when principal axes do not rotate (coaxial flow). Under simple shear with rotation the two differ by spin-coupling terms and the integral of $\mathbf{D}$ is path-dependent while $\mathbf{E}_{\log}$ is not. Constitutive integrators that use $\mathbf{D}$ as if it were $\dot{\mathbf{E}}_{\log}$ accumulate spurious strain along closed paths — most visible on cyclic shear benchmarks.


**Series vs spectral evaluation mismatch:** The Taylor series $\ln\mathbf{C}=\sum_{n\ge 1}(-1)^{n-1}(\mathbf{C}-\mathbf{I})^n/n$ converges only for $\|\mathbf{C}-\mathbf{I}\|<1$ (small / moderate strain). At large strain a truncated series gives a different $\mathbf{E}_{\log}$ than the spectral form, and mixing series for the strain with spectral for the tangent breaks the energy mapping. Use the spectral form everywhere.


**Factor of 1/2 confusion between $\ln\mathbf{U}$ and $\tfrac12\ln\mathbf{C}$:** $\mathbf{E}_{\log}=\ln\mathbf{U}=\tfrac12\ln\mathbf{C}$ — equivalent because $\mathbf{C}=\mathbf{U}^2$. Mixing the two conventions in the same code path inserts a factor 2 into the conjugate stress. State the convention explicitly at every wrapper boundary and validate on a uniaxial benchmark where the closed-form analytical answer is known.


**Singular Carlson-Hoger divided differences at degenerate eigenvalues:** The divided difference $\upsilon_{ij}=(e_i-e_j)/(\lambda_i^2-\lambda_j^2)$ blows up as $\lambda_i^2\to\lambda_j^2$, even though $\mathbf{E}_{\log}$ remains smooth. Without the L'Hopital substitution $\upsilon_{ii}\gets\tfrac{1}{2}d_i$ the constitutive tangent NaN's at hydrostatic / biaxial states. Trigger the branch with a relative tolerance $|\lambda_i^2-\lambda_j^2|<\tau(\lambda_i^2+\lambda_j^2)$.


**Dropping $\mathbf{T}\colon\mathbb{L}_L$ in the Lagrangian tangent:** The tangent $\mathbb{C}^L_{ep}$ has TWO terms: the "constitutive" $\mathbb{P}_L^T\colon\mathbb{E}_{ep}\colon\mathbb{P}_L$ and the "geometric" $\mathbf{T}\colon\mathbb{L}_L$. Dropping the geometric correction (a common simplification in implementation) degrades Newton convergence from quadratic to linear at finite strain and makes path-following solvers stall near limit points. The geometric term vanishes only in the small-strain limit.


**Confusing material $\mathbf{E}_{\log}$ with spatial $\mathbf{e}_{\log}$:** $\mathbf{E}_{\log}=\ln\mathbf{U}$ lives on the reference frame; $\mathbf{e}_{\log}=\ln\mathbf{V}$ lives on the current frame; they are related by $\mathbf{e}_{\log}=\mathbf{R}\mathbf{E}_{\log}\mathbf{R}^T$. Plotting the material strain on the deformed mesh (a common output mistake) yields visually plausible but quantitatively wrong distributions — the principal directions are off by the polar rotation $\mathbf{R}$.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed. (Hencky strain definition, additive structure, conjugacy)
- Miehe, Apel, Lambrecht (2002) — Anisotropic additive plasticity in the logarithmic strain space (modular framework, four key transformation equations $\mathbb{P}_L$ and $\mathbb{L}_L$, divided-difference branches)
- Holzapfel (2000) — Nonlinear Solid Mechanics (Hencky strain, principal-stretch decomposition)

