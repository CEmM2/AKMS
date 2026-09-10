# Constitutive modeling: rate-dependent plasticity + temperature

## Defaults
- Finite strain: multiplicative split $\mathbf{F}=\mathbf{F}^e\mathbf{F}^p$.
- Rate dependence: Perzyna overstress with **implicit backward Euler**.
- Thermal coupling: adiabatic heating via Taylor-Quinney.

## Perzyna viscoplasticity (J2 template)
Yield function (deviatoric):
\[
\Phi = q(\boldsymbol\sigma - \boldsymbol\alpha) - \sigma_y(\kappa,T)
\]
Overstress flow:
\[
\dot{\gamma} = \frac{1}{\eta_v}\langle \frac{\Phi}{\sigma_0} \rangle^m
\]
with viscosity params $(\eta_v, m, \sigma_0)$.
Plastic flow (associative):
\[
\mathbf{D}^p = \dot{\gamma}\,\mathbf{n},\quad \mathbf{n}=\partial q / \partial \boldsymbol\sigma.
\]

### Implicit BE update skeleton
Given $\Delta t$:
1. Trial elastic predictor (hold plastic state fixed).
2. Solve scalar nonlinear equation for $\Delta\gamma$:
   - Consistency-like equation derived from flow + hardening.
3. Update stress, internal variables (hardening, backstress).
4. Provide algorithmic tangent if Newton is used (or supply JVP in matrix-free form).

## Duvaut-Lions regularization (alt)
Interpret as viscoplastic relaxation toward rate-independent solution over time scale $\tau$.
Good when you already have a robust rate-independent return mapping.

## Temperature coupling
Adiabatic heating:
\[
\rho C_p \dot{T} = \eta\,\boldsymbol\sigma : \mathbf{D}^p
\]
Discrete BE:
\[
T_{n+1}=T_n + \Delta t\,\frac{\eta}{\rho C_p}\,\boldsymbol\sigma_{n+1}:\mathbf{D}^p_{n+1}.
\]

### Thermal softening
Make $\sigma_y$ temperature dependent (e.g., Johnson-Cook style softening):
\[
\sigma_y(\kappa,T) = (A + B\kappa^n)\bigl(1 - T^*\bigr)^s
\]
with $T^*=(T-T_{ref})/(T_{melt}-T_{ref})$.

## Brittle vs ductile transition guidance
- Brittle dominance: low triaxiality sensitivity, cleavage criterion, low plastic dissipation.
- Ductile dominance: void growth/coalescence (GTN), triaxiality + Lode effects.
- Coupling strategy: use plastic dissipation / porosity evolution to drive phase-field (see ductile fracture reference).

## Unit sanity (always check)
- $\boldsymbol\sigma:\mathbf{D}^p$ has units of power density (W/m$^3$).
- $\eta$ is dimensionless (fraction of plastic work to heat).
- $\rho C_p$ is J/(m$^3$ K).
