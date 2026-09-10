# Ductile fracture: porous plasticity (GTN) and phase-field coupling

## GTN (Gurson-Tvergaard-Needleman) summary
Typical yield function in terms of Kirchhoff/Cauchy stress invariants:

- q = sqrt(3/2 * s:s)  (von Mises equivalent)
- p = -tr(sigma)/3     (positive in compression by this sign convention)
- f = void volume fraction

Phi(q,p,f) = (q/sigma_y)^2 + 2*q1*f*cosh(3*q2*p/(2*sigma_y)) - (1 + q3*f^2) = 0

Key mechanisms:
- Void growth: f_dot ~ (1-f) * tr(D^p)
- Void nucleation: add a strain-controlled or stress-controlled nucleation law
- Coalescence: accelerate f after a critical f_c (piecewise law)

## Finite strain implementation notes
- Finite strain plasticity defaults to F = Fe Fp.
- Many GTN implementations are written in spatial form (sigma, D).
  If using TL equilibrium, push/pull stress measures consistently.

## Coupling to phase-field (ductile-to-macrocrack)
Common choices for a crack-driving field:
- Plastic dissipation: D_pl = sigma : D^p
- Porosity-weighted dissipation: f * D_pl
- Effective toughness reduction: Gc_eff = Gc0 * h(f) with decreasing h

Practical, stable pattern:
1) Solve mechanics with GTN, compute a history variable H_d (ductile driver)
2) Drive phase-field using H = max(H, H_d) (irreversibility)
3) Degrade only the tensile (active) part of the energy; keep compressive part intact

## Debug checks
- Uniaxial tension: f increases monotonically; q reaches and follows yield
- Hydrostatic compression: no spurious damage/crack growth
- Mesh/length-scale: localization should regularize with l (phase-field) or nonlocality
