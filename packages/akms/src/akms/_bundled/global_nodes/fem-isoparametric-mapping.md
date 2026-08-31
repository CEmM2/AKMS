---
id: fem-isoparametric-mapping
title: Isoparametric Mapping & Numerical Integration
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- isoparametric
- quadrature
- gauss-legendre
- elements
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fem-shape-functions
  type: requires
  weight: 1.0
  note: Same shape functions used for geometry mapping and field interpolation
- to: fem-weak-form-derivation
  type: feeds-into
  weight: 1.0
  note: Weak-form integrals are evaluated by Gauss quadrature on the parent element
- to: fem-tl-b-matrix
  type: feeds-into
  weight: 1.0
  note: B-matrix uses the chain-rule Jacobian to map parent gradients to physical gradients
- to: fem-locking-remedies
  type: feeds-into
  weight: 0.8
  note: Reduced integration is one source of locking remedies but introduces hourglass modes
context_size: medium
reading_priority: full
load_with:
- fem-shape-functions
content_ref: null
akms_schema: v2
---

# Isoparametric Mapping & Numerical Integration

## Summary
The isoparametric concept uses identical shape functions for geometric mapping and field interpolation, allowing curved / distorted physical elements to be parameterised by a single fixed parent element $[-1,1]^d$. Physical coordinates are interpolated as $\mathbf{x}(\boldsymbol{\xi})=\sum_a N_a(\boldsymbol{\xi})\mathbf{x}_a$ and field values as $u(\boldsymbol{\xi})=\sum_a N_a(\boldsymbol{\xi})u_a$. The parametric Jacobian $\mathbf{J}=\partial\mathbf{x}/\partial\boldsymbol{\xi}$ controls the chain rule $\partial N_a/\partial\mathbf{x}=\mathbf{J}^{-1}\,\partial N_a/\partial\boldsymbol{\xi}$ and the volume element $dV=\det\mathbf{J}\,d\xi^1 d\xi^2 d\xi^3$. Numerical integration uses tensor-product Gauss-Legendre quadrature: an $n$-point rule integrates polynomials up to degree $2n-1$ exactly. Full integration ($n_g=$ poly order) ensures correct stiffness; reduced integration saves cost but introduces zero-energy hourglass modes that need stabilisation. Distorted elements with $\det\mathbf{J}\le 0$ render the mapping invalid.


## 1. Core Concept
Mapping curved physical elements onto a regular parent element is the workhorse of practical FEM. The isoparametric concept makes the mapping use the SAME shape functions as the field interpolation, which guarantees that a constant field is reproduced exactly (the patch test) and that geometric continuity matches displacement continuity at element boundaries. The cost is a Jacobian $\mathbf{J}=\partial\mathbf{x}/\partial\boldsymbol{\xi}$ that varies in space and must be inverted at every Gauss point: physical gradients of shape functions are obtained via the chain rule $\partial N_a/\partial\mathbf{x}=\mathbf{J}^{-1}\partial N_a/\partial\boldsymbol{\xi}$, and the volume element picks up a $\det\mathbf{J}$ factor. Numerical integration on the parent uses Gauss-Legendre quadrature, which is exact for polynomials up to degree $2n-1$ with $n$ points per dimension — sufficient for the stiffness integrand $\mathbb{C}_{ikjl}(\partial N_a/\partial x_k)(\partial N_b/\partial x_l)$ when $n_g\ge p$ (polynomial degree of shape functions). Reduced integration ($n_g<p$) saves up to $30\%$ of compute and softens the volumetric response (helps locking) but introduces spurious zero-energy modes (hourglass) that need explicit stabilisation. Element distortion drives $\det\mathbf{J}\to 0$ and the mapping becomes singular; mesh-quality control is essential.


## 2. Mathematical Formulation
The parent element is $\hat\Omega=[-1,1]^d$ in $d$ dimensions; $\boldsymbol{\xi}\in\hat\Omega$ are parametric coordinates; $\mathbf{x}\in\Omega_e\subset\mathbb{R}^d$ are physical coordinates. Indices: lower-case $i,j,k,l\in\{1,\ldots,d\}$. Shape function $N_a(\boldsymbol{\xi})$ for node $a$ satisfies $N_a(\boldsymbol{\xi}_b)=\delta_{ab}$.


**Isoparametric mapping (geometry = field):**

$$
\mathbf{x}(\boldsymbol{\xi}) = \sum_{a=1}^{n_n} N_a(\boldsymbol{\xi})\,\mathbf{x}_a,\qquad
u(\boldsymbol{\xi}) = \sum_{a=1}^{n_n} N_a(\boldsymbol{\xi})\,u_a
$$

where Same $N_a$ for both — distinguishes isoparametric from sub- / super-parametric

**Parametric Jacobian:**

$$
\mathbf{J} = \frac{\partial \mathbf{x}}{\partial \boldsymbol{\xi}},\qquad
J_{ij} = \frac{\partial x_i}{\partial \xi_j} = \sum_{a=1}^{n_n}(\partial N_a/\partial \xi_j)\,x_{a,i}
$$

where $\det\mathbf{J}>0$ required for valid mapping

**Chain rule for physical gradients:**

$$
\frac{\partial N_a}{\partial \mathbf{x}} = \mathbf{J}^{-1}\,\frac{\partial N_a}{\partial \boldsymbol{\xi}},\qquad
\frac{\partial N_a}{\partial x_i} = \sum_{j=1}^{d}(\mathbf{J}^{-1})_{ij}\,(\partial N_a/\partial \xi_j)
$$

where Standard chain rule on a smooth invertible map

**Volume element and integration:**

$$
dV = \det\mathbf{J}\,d\xi^1\,d\xi^2\,d\xi^3,\qquad
\int_{\Omega_e} f(\mathbf{x})\,dV = \int_{\hat\Omega} f(\mathbf{x}(\boldsymbol{\xi}))\,\det\mathbf{J}\,d\boldsymbol{\xi}
$$

where Pull-back of the integral onto the parent element

**Gauss-Legendre tensor-product quadrature:**

$$
\int_{\hat\Omega} g(\boldsymbol{\xi})\,d\boldsymbol{\xi}
\approx \sum_{g_1=1}^{n_g}\sum_{g_2=1}^{n_g}\sum_{g_3=1}^{n_g}
        w_{g_1}w_{g_2}w_{g_3}\,g(\xi_{g_1},\xi_{g_2},\xi_{g_3})
$$

where Exact for polynomials up to degree $2n_g-1$ per dimension

**Standard Gauss points and weights (1D, $n_g=2$):**

$$
\xi_1 = -1/\sqrt{3},\;\xi_2 = +1/\sqrt{3},\qquad
w_1 = w_2 = 1
$$

where Two-point rule integrates cubics exactly; standard for hex8 elements

**Full vs reduced integration:**

$$
\text{Full} \colon n_g = p + 1 \;\text{(}p\text{ poly degree)} \;\Rightarrow\; \text{stiffness exact},\\
\text{Reduced} \colon n_g = p \;\Rightarrow\; \text{cheaper, may produce hourglass modes}
$$

where Full integration removes spurious zero-energy modes; reduced integration trades cost for locking relief

**Element internal force / stiffness via quadrature:**

$$
K_{ab,ij}^e = \sum_{g}\,(\partial N_a/\partial x_k)\,\mathbb{C}_{ikjl}\,(\partial N_b/\partial x_l)\,
                      \det\mathbf{J}(\boldsymbol{\xi}_g)\,w_g
$$

where Element-level assembly via Gauss quadrature

**Distorted-element criterion:**

$$
\det\mathbf{J}(\boldsymbol{\xi}_g) > J_{\min}\,(\sim 10^{-3}\,\max\det\mathbf{J})
$$

where Validate at every Gauss point; very small $\det\mathbf{J}$ indicates a distorted / inverted element

**Notation:**

- $\boldsymbol{\xi}$ — Parametric (parent) coordinates
- $\mathbf{x}$ — Physical coordinates
- $\hat\Omega = [-1,1]^d$ — Parent (master) element
- $\Omega_e$ — Physical element
- $\mathbf{J}$ — Parametric Jacobian, $\partial\mathbf{x}/\partial\boldsymbol{\xi}$
- $N_a(\boldsymbol{\xi})$ — Shape function for local node $a$
- $n_n$ — Nodes per element
- $n_g$ — Gauss points per dimension
- $w_g$ — Gauss quadrature weight
- $p$ — Polynomial degree of shape functions


## 3. Algorithmic Implementation
**Algorithm: Compute Element Quadrature Data (one-time setup)**

$$
\begin{algorithmic}
\State $\text{input} \colon \text{element nodes } \{\mathbf{x}_a\},\,\text{Gauss data } \{(\boldsymbol{\xi}_g, w_g)\}$
\For{$\text{each Gauss point } g$}
\For{$a = 1,\ldots,n_n,\,k = 1,\ldots,d$}
\State $(\partial N_a/\partial \xi_k)|_g \gets \text{evaluate at } \boldsymbol{\xi}_g$
\EndFor
\State $\mathbf{J}_g \gets \sum_a \mathbf{x}_a \otimes (\partial N_a/\partial \boldsymbol{\xi})|_g$
\State $\det\mathbf{J}_g \gets \det(\mathbf{J}_g)$
\If{$\det\mathbf{J}_g \le J_{\min}$}
\State $\text{abort: distorted / inverted element}$
\EndIf
\State $\mathbf{J}_g^{-1} \gets \mathrm{cofactor\;inverse}(\mathbf{J}_g)$
\For{$a = 1,\ldots,n_n$}
\State $(\partial N_a/\partial \mathbf{x})|_g \gets \mathbf{J}_g^{-1}\,(\partial N_a/\partial \boldsymbol{\xi})|_g$
\EndFor
\EndFor
\Return $\{(\partial N_a/\partial \mathbf{x})|_g,\,\det\mathbf{J}_g\,w_g\}$
\end{algorithmic}
$$

**Taichi Mapping:**
Pre-compute once per element at the START of the simulation (TL-FEM uses reference geometry, never changes). Store $(\partial N_a/\partial \mathbf{x})|_g$ in a `ti.field(dtype=ti.f64, shape=(n_elem, n_GP, n_n, d))` and $\det\mathbf{J}_g\,w_g$ in `ti.field(shape=(n_elem, n_GP))`. Per-element cost: one $3\times 3$ inverse + chain-rule per Gauss point = ~$30 n_g$ FMAs. Validate $\det\mathbf{J}>J_{\min}$ on every element at startup; any failure indicates mesh-quality issue.


**Algorithm: Gauss-Legendre Quadrature on a Parent Cube**

$$
\begin{algorithmic}
\State $\text{input} \colon n_g \;\text{(points per dim)},\,\text{integrand handle } f(\boldsymbol{\xi})$
\State $(\xi^{1D}_g, w^{1D}_g)_{g=1}^{n_g} \gets \text{Gauss-Legendre tabulated values}$
\State $I \gets 0$
\For{$g_1, g_2, g_3 = 1,\ldots,n_g$}
\State $w_g \gets w^{1D}_{g_1}\,w^{1D}_{g_2}\,w^{1D}_{g_3}$
\State $\boldsymbol{\xi}_g \gets (\xi^{1D}_{g_1},\xi^{1D}_{g_2},\xi^{1D}_{g_3})$
\State $I \mathrel{+}= w_g\,f(\boldsymbol{\xi}_g)$
\EndFor
\Return $I$
\end{algorithmic}
$$

**Taichi Mapping:**
Hard-code Gauss-Legendre points / weights for the most common rules ($n_g=1,2,3$). For hex8 use $2\times 2\times 2=8$ Gauss points (full integration); reduced is $1\times 1\times 1=1$. Tensor-product structure means the inner loops can be unrolled with `ti.static`; the integrand call is the dominant cost.


**Algorithm: Patch-Test Verification**

$$
\begin{algorithmic}
\State $\text{input} \colon \text{distorted element mesh},\,\text{linear constant-strain trial field}$
\State $\text{prescribe } \mathbf{u}|_{\partial\Omega} = \boldsymbol{\varepsilon}_0\,\mathbf{x}$
\State $\text{solve and recover } \boldsymbol{\sigma}_h\,\text{at all Gauss points}$
\State $\text{check } \|\boldsymbol{\sigma}_h - \mathbb{C}\colon\boldsymbol{\varepsilon}_0\| < \tau\,(\sim 10^{-12})$
\Return $\text{pass / fail}$
\end{algorithmic}
$$

**Taichi Mapping:**
Standard verification benchmark every isoparametric implementation must pass. Failure indicates incorrect Jacobian inversion, missing $\det\mathbf{J}$ in the volume element, or wrong Gauss point locations. Run on a 2x2x2 mesh with one warped interior element; uniform extension must produce uniform stress to round-off.



## 4. Known Pitfalls
**Distorted elements with $\det\mathbf{J}\le 0$:** A distorted physical element with re-entrant corners or extreme aspect ratio can yield $\det\mathbf{J}_g\to 0$ or even $<0$ at some Gauss points — the mapping is then non-invertible. Detect $\det\mathbf{J}<J_{\min}$ at every Gauss point and reject the element / refine the mesh. Standard mesh-quality metrics (Jacobian ratio, aspect ratio, scaled Jacobian) catch this before solver stage.


**Reduced integration causing hourglass modes:** Hex8 with 1-point integration ($n_g=1$) has 12 zero-energy modes (hourglass) because the single Gauss point cannot detect the $1{,}\xi{,}\xi^2$ patterns. Without explicit hourglass control (Flanagan-Belytschko stabilisation), the mesh can deform along these modes for free and produce wild oscillations. Either use full integration ($n_g=2$) or add hourglass stabilisation — see `fem-hourglass-control`.


**Stress at non-Gauss points requires extrapolation:** Gauss-Legendre quadrature is most accurate at the Gauss points; stresses recovered there are super-convergent. Extrapolating to nodes for visualisation introduces additional error of order $h^p$. For accurate nodal stress fields use Zienkiewicz-Zhu superconvergent recovery or L2 projection from Gauss values; never average raw element-Gauss stresses at nodes.


**Wrong integration order for thin elements:** Thin shell-like elements with very high aspect ratio require integration orders that resolve through-thickness variation. Using a single Gauss point through thickness collapses bending into membrane response (transverse-shear locking). Use selective reduced integration (full in-plane, full through-thickness) or layered integration for shells.


**Integration error degrading below interpolation accuracy:** For polynomial shape functions of degree $p$, the interpolation error is $\mathcal{O}(h^{p+1})$. Quadrature error must be at least $\mathcal{O}(h^{p+1})$ (i.e., $n_g\ge p+1$) to preserve convergence rate. Reduced integration ($n_g=p$) sacrifices accuracy for cost; verify on a mesh-refinement study.


**Mixing parent and physical coordinates:** $\partial N_a/\partial \boldsymbol{\xi}$ and $\partial N_a/\partial \mathbf{x}$ are different objects; the chain rule $\partial N_a/\partial\mathbf{x}=\mathbf{J}^{-1}\partial N_a/\partial\boldsymbol{\xi}$ is the bridge. Substituting one for the other in a B-matrix construction silently produces wrong gradients — pass the Cartesian-physical gradients to constitutive routines and the parent gradients to Jacobian computation.


**Forgetting the $\det\mathbf{J}$ factor in element integrals:** The pull-back of the integral to the parent element MUST include $\det\mathbf{J}$. Dropping it (a common bug when copying integrand templates from linear-elasticity textbooks) produces results scaled by the parent volume rather than the physical volume — total mass, total stiffness all wrong.


**Higher-order elements with poor conditioning:** Equispaced Lagrange shape functions of high order ($p\ge 6$) suffer from Runge phenomenon and poor conditioning. For high-order FEM use Gauss-Lobatto-Legendre nodes (or Chebyshev) which match the integration points and produce well-conditioned mass / stiffness matrices.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed. (isoparametric mapping, Gauss quadrature, full vs reduced integration)
- Hughes (1987) — The Finite Element Method: Linear Static and Dynamic Finite Element Analysis (isoparametric concept, parent element, Jacobian)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (numerical integration, hourglass modes, patch test)

