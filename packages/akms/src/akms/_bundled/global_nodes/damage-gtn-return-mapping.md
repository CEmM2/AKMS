---
id: damage-gtn-return-mapping
title: Return Mapping for GTN
domain: computational-mechanics
subdomain: damage
tags:
- damage
- gtn
- return-mapping
- aravas
- implicit-integration
status: established
confidence: 0.9
source: hybrid
edges:
- to: damage-gtn-yield-function
  type: requires
  weight: 1.0
- to: damage-gtn-void-evolution
  type: requires
  weight: 1.0
- to: plasticity-general-return-mapping
  type: refines
  weight: 0.9
- to: damage-gtn-consistent-tangent
  type: feeds-into
  weight: 1.0
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Return Mapping for GTN

## Summary

Implicit return mapping for the GTN porous plasticity model decouples stress updates into hydrostatic and deviatoric scalar equations solved via a two-variable Newton-Raphson scheme.

## 1. Core Concept

The return-mapping algorithm for the Gurson-Tvergaard-Needleman (GTN) model integrates pressure-dependent porous plastic constitutive equations over discrete time steps. Following the operator split, the elastic trial stress is computed with frozen internal state variables. If the trial state violates yield admissibility, an implicit backward Euler corrector is executed. As formulated by Aravas (1987) and detailed by Zhang (1995), decoupling the return mapping into hydrostatic and deviatoric directions reduces the multi-dimensional tensor return mapping to two coupled scalar equations governing incremental hydrostatic plastic strain \Delta \varepsilon_p and equivalent plastic strain \Delta \varepsilon_q. Solving this 2x2 nonlinear system updates the Cauchy stress tensor, void volume fraction, and matrix equivalent plastic strain.

## 2. Mathematical Formulation

**GTN Hydrostatic and Deviatoric Stress Return Relations**
$$
p = p^{tr} + K \Delta \varepsilon_p, \quad q = q^{tr} - 3G \Delta \varepsilon_q
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 33_

**GTN Plastic Flow Potential Derivatives**
$$
\Delta \varepsilon_p = -\Delta \lambda \frac{\partial \Phi}{\partial p}, \quad \Delta \varepsilon_q = \Delta \lambda \frac{\partial \Phi}{\partial q}
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 33; Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 3_

**Matrix Plastic Work Equivalence Relation**
$$
(1 - f) \sigma_0 \Delta \bar{\varepsilon}^p = \bm{\sigma} : \Delta \bm{\varepsilon}^p = -p \Delta \varepsilon_p + q \Delta \varepsilon_q
$$
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 33; Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf p. 249_

**Void Volume Fraction Incremental Growth**
$$
\Delta f = (1 - f) \Delta \varepsilon_p + A_{nuc} \Delta \bar{\varepsilon}^p
$$
_Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 3; Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf p. 249_

**Notation:**
p: hydrostatic pressure (-1/3 tr(\bm{\sigma})); q: equivalent von Mises stress; p^{tr}, q^{tr}: elastic trial pressure and equivalent stress; K: bulk modulus; G: shear modulus; \Delta \varepsilon_p: hydrostatic plastic strain increment; \Delta \varepsilon_q: equivalent plastic strain increment; \Delta \lambda: discrete plastic multiplier; \Phi: GTN yield function; f: void volume fraction; \sigma_0: matrix flow stress; \bar{\varepsilon}^p: matrix equivalent plastic strain.


## 3. Algorithmic Implementation

**Aravas Two-Variable GTN Implicit Return-Mapping Algorithm**
$$
\begin{algorithmic}
\State $\text{Given converged state at } t_n\text{: } \bm{\sigma}^n, \bar{\varepsilon}^p_n, f_n \text{ and strain increment } \Delta \bm{\varepsilon}$
\State $\bm{\sigma}^{tr} = \bm{\sigma}^n + \mathbf{D}^e : \Delta \bm{\varepsilon}, \quad p^{tr} = -\frac{1}{3}\mathrm{tr}(\bm{\sigma}^{tr}), \quad \bm{s}^{tr} = \bm{\sigma}^{tr} + p^{tr}\mathbf{I}, \quad q^{tr} = \sqrt{\frac{3}{2}\bm{s}^{tr}:\bm{s}^{tr}}$
\State $\text{Evaluate trial yield function } \Phi^{tr} = \Phi(p^{tr}, q^{tr}, f_n, \bar{\varepsilon}^p_n)$
\If{$\Phi^{tr} \le 0$}
\State $\bm{\sigma}_{n+1} = \bm{\sigma}^{tr}, \quad f_{n+1} = f_n, \quad \bar{\varepsilon}^p_{n+1} = \bar{\varepsilon}^p_n$
\Return $\text{Step is elastic; return trial state}$
\Else
\EndIf
\While{$\|\bm{R}(\Delta \varepsilon_p^{(k)}, \Delta \varepsilon_q^{(k)})\| > \text{TOL}$}
\State $p^{(k)} = p^{tr} + K \Delta \varepsilon_p^{(k)}, \quad q^{(k)} = q^{tr} - 3G \Delta \varepsilon_q^{(k)}$
\State $\Delta \bar{\varepsilon}^{p(k)} = \frac{-p^{(k)} \Delta \varepsilon_p^{(k)} + q^{(k)} \Delta \varepsilon_q^{(k)}}{(1 - f^{(k)}) \sigma_0}$
\State $f^{(k+1)} = f_n + (1 - f^{(k)}) \Delta \varepsilon_p^{(k)} + A_{nuc} \Delta \bar{\varepsilon}^{p(k)}$
\State $R_1 = \Delta \varepsilon_p^{(k)} \frac{\partial \Phi}{\partial q} + \Delta \varepsilon_q^{(k)} \frac{\partial \Phi}{\partial p}, \quad R_2 = \Phi(p^{(k)}, q^{(k)}, f^{(k+1)}, \bar{\varepsilon}_n^p + \Delta \bar{\varepsilon}^{p(k)})$
\State $\text{Solve } 2 \times 2 \text{ linear system } \mathbf{J} \begin{bmatrix} \delta \Delta \varepsilon_p \\ \delta \Delta \varepsilon_q \end{bmatrix} = -\begin{bmatrix} R_1 \\ R_2 \end{bmatrix} \text{ and update unknowns}$
\EndWhile
\State $\bm{n} = \frac{3}{2 q^{tr}} \bm{s}^{tr}, \quad \bm{s}_{n+1} = q_{n+1} \frac{2}{3} \bm{n}, \quad \bm{\sigma}_{n+1} = \bm{s}_{n+1} - p_{n+1} \mathbf{I}$
\Return $\text{Return updated stress } \bm{\sigma}_{n+1}, \text{ porosity } f_{n+1}, \text{ and plastic strain } \bar{\varepsilon}^p_{n+1}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 33-34; Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf p. 10_


## 4. Known Pitfalls

- **Overflow from Rapid Cosh Growth at High Hydrostatic Triaxiality**: Evaluating the GTN yield function \Phi at high hydrostatic pressures without numerical safeguards causes exponential growth in the \cosh(\frac{3 q_2 p}{2 \sigma_0}) term, leading to floating-point overflow or divergence in Newton-Raphson iterations for poor initial guesses. _(Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 3, 6; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 43)_
- **Unphysical Singularity as Porosity Approaches Void Coalescence**: Allowing void volume fraction f to approach complete matrix material loss (f \to 1) in the matrix work-equivalence denominator (1-f)\sigma_0 produces division by zero and matrix ill-conditioning; capping porosity at an upper threshold preserves numerical robustness. _(Source: Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf p. 6; Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 33)_
- **Spurious Stress Direction Evolution in Deviatoric Projection**: Assuming the deviatoric stress direction \bm{n} changes during return mapping introduces tensor integration errors; in isotropic pressure-dependent return mapping, \bm{n}_{n+1} is strictly parallel to the trial deviatoric direction \bm{n}^{tr} = \frac{3}{2 q^{tr}} \bm{s}^{tr}. _(Source: Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf p. 33; Kim_FEA for Elastoplastic Problems.pdf p. 252)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Chu and Needleman - 1980 - Void Nucleation Effects in Biaxially Stretched Sheets.pdf
- Han et al. - 2024 - Study of the dynamic impact spalling of ductile materials based on Gurson-type phase-field model.pdf
- Kim_FEA for Elastoplastic Problems.pdf
- Pascon and Waisman - 2022 - A gradient-enhanced formulation for thermoviscoplastic metals accounting for ductile damage.pdf
- Simo_Hughes_1998_Computational inelasticity.pdf
- Zhang_1995_Explicit consistent tangent moduli with a return mapping algorithm for.pdf
