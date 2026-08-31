# Kinematics: Total Lagrangian with convected coordinates

This is the **strict workflow** for TL convected-coordinate implementations.

## TL baseline (no convected basis)
- Unknown: displacement $\mathbf{u}(\mathbf{X})$.
- Motion: $\mathbf{x}=\mathbf{X}+\mathbf{u}$.
- $\mathbf{F}=\mathbf{I}+\nabla_X\mathbf{u}$.
- Strain: $\mathbf{E}=\tfrac12(\mathbf{F}^T\mathbf{F}-\mathbf{I})$.
- Stress measure for equilibrium: 2nd PK $\mathbf{S}$.

Weak form:
\[
\int_{\Omega_0} \mathbf{S}:\delta\mathbf{E}\,dV_0 = \delta W_{ext}.
\]

## Convected coordinates (basis deforms with the body)
Let $\xi^i$ be convected coordinates on the element/patch.

### 1) Metric tensor
- Covariant bases:
  - Reference: $\mathbf{G}_i=\partial\mathbf{X}/\partial\xi^i$.
  - Current: $\mathbf{g}_i=\partial\mathbf{x}/\partial\xi^i$.
- Metrics:
  - $G_{ij}=\mathbf{G}_i\cdot\mathbf{G}_j$.
  - $g_{ij}=\mathbf{g}_i\cdot\mathbf{g}_j$.

### 2) Green strain in convected basis
\[
E_{ij}=\tfrac12(g_{ij}-G_{ij}).
\]
This is the cleanest way to capture **large rotations** without spurious stress.

### 3) Stress update strategy
Two common routes:

**Route A (material law in reference):**
- Evaluate constitutive response directly in $(\mathbf{E},\mathbf{S})$.
- Good for hyperelasticity or small-strain plasticity embedded in TL.

**Route B (material law in spatial):**
- Push-forward the kinematics to spatial frame, evaluate law in terms of $\boldsymbol\sigma$ and $\mathbf{D}$, then pull back to $\mathbf{S}$ for TL equilibrium.
- Required for many industrial plasticity models expressed in Cauchy stress.

A minimal, explicit mapping if you have $\boldsymbol\sigma$:
1. Compute $\boldsymbol\tau = J\boldsymbol\sigma$.
2. Pull back to $\mathbf{S}$:
\[
\mathbf{S} = \mathbf{F}^{-1}\,\boldsymbol\tau\,\mathbf{F}^{-T}.
\]

### 4) Internal force (matrix-free friendly)
Use power functional form:
\[
\mathbf{f}_{int} = \int_{\Omega_0} \mathbf{B}^T\,\mathbf{S}\,dV_0
\]
where $\mathbf{B}$ is the TL strain-displacement operator (in whatever basis you store it).

### 5) Large rotations vs large strains
- **Finite rotations, small strains:** treat strain measure carefully (convected metric or corotational). Plasticity may still be small-strain.
- **Finite strains:** multiplicative plasticity, update $\mathbf{F}^p$ (see viscoplastic reference).

## Implementation gotchas
- Always recompute metrics from current nodal positions each nonlinear iteration.
- Guard against inversion: $J=\det\mathbf{F} \le 0$.
- If using Route B, ensure the rate update is objective (see objective rates reference).
