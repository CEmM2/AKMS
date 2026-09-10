# Solver architecture: matrix-free Newton-Krylov (FEM and FFT)

## Default nonlinear loop
Given unknown x (displacements u, or strain field eps, etc.) solve R(x)=0.

1) Predictor: x0 (previous step, extrapolation, etc.)
2) For k=0..max:
   a) Evaluate residual r = R(x)
   b) If ||r|| < tol: converged
   c) Solve (J(x) * dx = -r) with Krylov (CG/GMRES)
   d) Line search / trust region (optional)
   e) Update x <- x + alpha*dx

## Matrix-free Jacobian action (JVP)
Instead of assembling J, implement a function:
   y = JVP(x, v) ≈ (R(x + eps*v) - R(x)) / eps
or derive an analytic directional derivative.

## FEM specifics
- Internal force f_int(u) = Int B^T S dV0 (TL) or Int B^T sigma dV (spatial)
- Residual r = f_ext - f_int
- JVP maps a displacement increment (size 3N) to a force increment (size 3N)

## FFT specifics
- Unknown often the strain field eps(x) (each voxel 6 comps).
- Residual uses LS projection: R(eps) = eps - E + Gamma0 * tau(eps)
- JVP uses tangent at voxels + FFT projection (no global matrix).

## Preconditioning hints
- FEM: Jacobi/diagonal of element tangents, p-multigrid, physics-based blocks.
- FFT: use C0-based preconditioner, or block-diagonal per voxel.

## Stop criteria
Use at least two checks:
- ||r|| / ||r0|| < tol_r
- ||dx|| / ||x|| < tol_x

## Debug checklist
- Residual is consistent with weak form (sign conventions!)
- JVP uses same BC treatment as residual
- Converges quadratically near solution (Newton) if tangent/JVP is consistent
