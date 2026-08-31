# Objective stress integration (finite rotations)

Use this when you are integrating **rate constitutive equations** in the spatial frame.

## Problem
If you integrate
\[
\dot{\boldsymbol\sigma} = \mathcal{F}(\boldsymbol\sigma, \mathbf{D}, \ldots)
\]
with a plain time derivative, a rigid body rotation can create spurious stresses.

## Recommended pattern: corotational update
1. Compute incremental rotation $\mathbf{R}$ from the deformation increment.
   - Common: polar decomposition of $\Delta\mathbf{F} = \Delta\mathbf{R}\Delta\mathbf{U}$.
2. Rotate stress and any backstresses into corotational frame:
   - $\tilde{\boldsymbol\tau}_n = \Delta\mathbf{R}^T\boldsymbol\tau_n\Delta\mathbf{R}$.
3. Integrate the constitutive update in the corotational frame (no spin term required).
4. Rotate back:
   - $\boldsymbol\tau_{n+1} = \Delta\mathbf{R}\tilde{\boldsymbol\tau}_{n+1}\Delta\mathbf{R}^T$.
5. Convert to desired stress measure (Cauchy, PK2, etc.).

## Jaumann rate (if you insist)
Kirchhoff stress Jaumann rate:
\[
\overset{\triangle}{\boldsymbol\tau} = \dot{\boldsymbol\tau} - \mathbf{W}\boldsymbol\tau + \boldsymbol\tau\mathbf{W}.
\]
Use with care: Jaumann + nonlinear elastic response can produce shear oscillations.
Corotational updates are usually more robust.

## Minimal verification
- **Rigid rotation test:** apply $\mathbf{F}=\mathbf{R}(t)$, $\mathbf{D}=\mathbf{0}$.
  Expect constant stress (often zero for elastic) and constant internal energy.
- **Simple shear with rotation:** compare against an implementation known to be objective.
