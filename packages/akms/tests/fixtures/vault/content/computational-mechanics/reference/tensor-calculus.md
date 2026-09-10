# Tensor calculus essentials (continuum mechanics)

This file is for **math-to-code** checks: what lives in which configuration, how to map it, and how to keep objectivity.

## Curvilinear / convected coordinates
Let $\xi^i$ be convected coordinates.

- Covariant base vectors: $\mathbf{g}_i = \partial\mathbf{x}/\partial\xi^i$.
- Contravariant base vectors: $\mathbf{g}^i$ with $\mathbf{g}^i\cdot\mathbf{g}_j=\delta^i{}_j$.
- Metric: $g_{ij}=\mathbf{g}_i\cdot\mathbf{g}_j$, inverse $g^{ij}$.

Reference configuration counterparts: $\mathbf{G}_i,\mathbf{G}^i,G_{ij}$.

### Common coding pattern
1. Compute $\mathbf{g}_i$ from current nodal positions (or mapping).
2. Build $g_{ij}$ and $g^{ij}$ (invert 3x3).
3. Use metric to raise/lower indices.

## Material vs spatial gradients
- Material gradient: $(\nabla_X \mathbf{u})_{iJ} = \partial u_i/\partial X_J$.
- Spatial gradient: $(\nabla_x \mathbf{v})_{ij} = \partial v_i/\partial x_j$.

**Rule:** never mix them without an explicit map (typically $\mathbf{F}$):
- $\nabla_x(\cdot)=\nabla_X(\cdot)\,\mathbf{F}^{-1}$.

## Push-forward / pull-back (quick recipes)
For a 2nd-order tensor:
- Pull-back (spatial $\to$ material): $\mathbf{A}_0 = \mathbf{F}^{-1}\mathbf{A}\mathbf{F}^{-T}$.
- Push-forward (material $\to$ spatial): $\mathbf{A} = \mathbf{F}\mathbf{A}_0\mathbf{F}^T$.

For a 4th-order tensor (stiffness):
- $\mathbb{C} = (\mathbf{F}\bar\otimes\mathbf{F}) : \mathbb{C}_0 : (\mathbf{F}^T\bar\otimes\mathbf{F}^T)$.
(Use index notation in code to avoid confusion.)

## Objectivity and Lie derivatives (what you actually need)
If integrating a **rate form in the spatial frame** you must use an **objective rate**.

- Material time derivative is not objective for tensors under superposed rigid body motion.
- Practical options:
  - Corotational update (rotate to a co-rotating frame, integrate, rotate back).
  - Jaumann rate for Kirchhoff stress: $\overset{\triangle}{\boldsymbol\tau}=\dot{\boldsymbol\tau}-\mathbf{W}\boldsymbol\tau+\boldsymbol\tau\mathbf{W}$.

**When you are Total Lagrangian in convected coordinates**, you can avoid most of this by working with $\mathbf{S}$ and $\mathbf{E}$ in the reference frame.

## Sanity checks
- Symmetry: $\mathbf{E}^T=\mathbf{E}$, $\boldsymbol\sigma^T=\boldsymbol\sigma$ (for standard materials).
- Positive Jacobian: $J>0$.
- Rigid rotation test: pure rotation should not create stress for elastic/elastic-plastic models with correct objectivity.
