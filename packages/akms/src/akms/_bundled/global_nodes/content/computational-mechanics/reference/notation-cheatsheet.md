# Notation cheatsheet

## Configurations
- Reference: $\Omega_0$, material point $\mathbf{X}$, gradient $\nabla_X(\cdot)$.
- Current: $\Omega_t$, spatial point $\mathbf{x}$, gradient $\nabla_x(\cdot)$.

## Kinematics
- Motion: $\mathbf{x}=\boldsymbol\varphi(\mathbf{X},t)$.
- Deformation gradient: $\mathbf{F}=\nabla_X\boldsymbol\varphi$.
- Jacobian: $J=\det\mathbf{F}$ (must stay positive).
- Right Cauchy-Green: $\mathbf{C}=\mathbf{F}^T\mathbf{F}$.
- Left Cauchy-Green: $\mathbf{b}=\mathbf{F}\mathbf{F}^T$.
- Green-Lagrange strain: $\mathbf{E}=\tfrac12(\mathbf{C}-\mathbf{I})$.
- Spatial velocity gradient: $\mathbf{L}=\nabla_x\mathbf{v}$, $\mathbf{D}=\tfrac12(\mathbf{L}+\mathbf{L}^T)$, $\mathbf{W}=\tfrac12(\mathbf{L}-\mathbf{L}^T)$.

## Stress measures
- Cauchy: $\boldsymbol\sigma$.
- 1st PK: $\mathbf{P}=J\,\boldsymbol\sigma\,\mathbf{F}^{-T}$.
- 2nd PK: $\mathbf{S}=\mathbf{F}^{-1}\mathbf{P}$.
- Kirchhoff: $\boldsymbol\tau=J\boldsymbol\sigma$.

## Push-forward / pull-back
- Push-forward (material $\to$ spatial): $\boldsymbol\tau=\mathbf{F}\,\mathbf{S}\,\mathbf{F}^T$.
- Pull-back (spatial $\to$ material): $\mathbf{S}=\mathbf{F}^{-1}\,\boldsymbol\tau\,\mathbf{F}^{-T}$.

## Finite strain plasticity
- Multiplicative split: $\mathbf{F}=\mathbf{F}^e\mathbf{F}^p$.
- Plastic velocity gradient: $\mathbf{L}^p=\dot{\mathbf{F}}^p\mathbf{F}^{p-1}$.

## Phase-field fracture
- Phase-field: $\phi\in[0,1]$ (0 intact, 1 fully broken).
- Degradation: $g(\phi)=(1-\phi)^2+k$ with small $k\ll1$.
- History field (irreversibility): $\mathcal{H}(t)=\max_{s\le t}\psi^+(s)$.

## FFT-Galerkin
- Macroscopic strain: $\langle\boldsymbol\varepsilon\rangle=\mathbf{E}$.
- Polarization: $\boldsymbol\tau(\mathbf{x}) = \boldsymbol\sigma(\mathbf{x})-\mathbb{C}^0:\boldsymbol\varepsilon(\mathbf{x})$.
- Lippmann-Schwinger: $\boldsymbol\varepsilon=\mathbf{E}-\boldsymbol\Gamma^0 * \boldsymbol\tau$.
