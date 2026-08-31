---
id: plasticity-duvaut-lions
title: Duvaut-Lions Viscoplastic Regularization
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- viscoplasticity
- duvaut-lions
- regularisation
- relaxation
status: tentative
confidence: 0.85
source: hybrid
confidence_floor: 0.7
edges:
- to: plasticity-radial-return
  type: requires
  weight: 1.0
  note: Duvaut-Lions calls the rate-independent return mapping inside its update
- to: plasticity-perzyna
  type: contradicts
  weight: 0.5
  note: Same regularisation goal; different algorithm — Duvaut-Lions has closed form, Perzyna requires inner Newton
- to: constit-stress-update-architecture
  type: requires
  weight: 1.0
  note: Same operator-split scaffolding; relaxation interpolates trial and rate-independent stress
- to: plasticity-peirce-rate-tangent
  type: requires
  weight: 0.6
  note: Borrows the Peirce-Shih-Needleman rate-tangent modulus relation for the Duvaut-Lions consistent tangent
load_with:
- plasticity-perzyna
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Duvaut-Lions Viscoplastic Regularization

## Summary

Duvaut-Lions viscoplastic regularisation expresses rate-dependent plasticity through a relaxation differential equation $\dot{\boldsymbol{\sigma}}=\mathbb{C}\colon\dot{\boldsymbol{\varepsilon}}-(1/\eta)(\boldsymbol{\sigma}-\bar{\boldsymbol{\sigma}})$ where $\bar{\boldsymbol{\sigma}}$ is the rate-independent (closest-point projected) stress. Backward Euler integration produces a CLOSED-FORM update: $\boldsymbol{\sigma}_{n+1}=(\eta/(\eta+\Delta t))\,\boldsymbol{\sigma}^{\mathrm{trial}}+(\Delta t/(\eta+\Delta t))\,\bar{\boldsymbol{\sigma}}_{n+1}$, where $\bar{\boldsymbol{\sigma}}_{n+1}$ is obtained from the standard rate-independent return mapping at the same trial state. The interpolation factor $\Delta t/(\eta+\Delta t)$ ranges from $0$ (purely elastic, $\eta\to\infty$) to $1$ (rate-independent, $\eta\to 0$). The algorithmic tangent inherits the same linear interpolation: $\mathbb{C}^{\mathrm{alg}}=(\eta/(\eta+\Delta t))\mathbb{C}^e+(\Delta t/(\eta+\Delta t))\mathbb{C}^{\mathrm{alg,RI}}$. Compared to Perzyna: same regularisation goal, but Duvaut-Lions has CLOSED-FORM update (no inner Newton), exact rate-independent limit at $\eta=0$, and uses the rate-independent return mapping as a black box. Best when the rate-independent solver is robust; cleaner algorithmic structure than Perzyna for production codes.

## 1. Core Concept

Duvaut-Lions takes a different approach to viscoplasticity than Perzyna: instead of replacing the yield consistency with rate-dependent overstress, it adds a relaxation term to the constitutive ODE that pulls the stress toward the rate-independent yield surface at finite rate $\eta$. The geometric picture: the trial elastic stress is projected onto the rate-independent yield surface to give $\bar{\boldsymbol{\sigma}}$; the actual stress $\boldsymbol{\sigma}_{n+1}$ is a weighted average of the trial (no relaxation) and $\bar{\boldsymbol{\sigma}}$ (full relaxation), with weights determined by the relaxation time $\eta$ relative to the time step $\Delta t$. The algorithmic structure is much cleaner than Perzyna: NO inner Newton, the rate-independent return mapping is called as a subroutine, and the result is a single linear interpolation. The drawback is that Duvaut-Lions requires the rate-independent return mapping to converge robustly — for very stiff yield surfaces near apex / vertex regions where rate-independent return mapping itself struggles, the Duvaut-Lions wrapper inherits those difficulties. The Peirce tangent modulus relation gives the consistent tangent in closed form: $\mathbb{C}^{\mathrm{alg}}=(\eta/(\eta+\Delta t))\mathbb{C}^e+(\Delta t/(\eta+\Delta t))\mathbb{C}^{\mathrm{alg,RI}}$, where $\mathbb{C}^{\mathrm{alg,RI}}$ is the rate-independent algorithmic tangent (e.g., Souza-Neto J2). Production-code-friendly for codes with mature rate-independent infrastructure.

## 2. Mathematical Formulation

**Duvaut-Lions rate equation**
$$
\dot{\boldsymbol{\sigma}} = \mathbb{C}^e\colon\dot{\boldsymbol{\varepsilon}} - \frac{1}{\eta}\,(\boldsymbol{\sigma} - \bar{\boldsymbol{\sigma}})
$$

**Backward-Euler integration**
$$
\boldsymbol{\sigma}_{n+1} - \boldsymbol{\sigma}_n = \mathbb{C}^e\colon\Delta\boldsymbol{\varepsilon} - \frac{\Delta t}{\eta}\,(\boldsymbol{\sigma}_{n+1} - \bar{\boldsymbol{\sigma}}_{n+1})
$$

**Closed-form update (linear interpolation)**
$$
\boldsymbol{\sigma}_{n+1} = \frac{\eta}{\eta + \Delta t}\,\boldsymbol{\sigma}^{\mathrm{trial}} + \frac{\Delta t}{\eta + \Delta t}\,\bar{\boldsymbol{\sigma}}_{n+1}
$$

**Limits**
$$
\eta\to 0\,\Rightarrow\,\boldsymbol{\sigma}_{n+1}\to\bar{\boldsymbol{\sigma}}_{n+1}\,\text{(rate-independent)},\\
\eta\to\infty\,\Rightarrow\,\boldsymbol{\sigma}_{n+1}\to\boldsymbol{\sigma}^{\mathrm{trial}}\,\text{(elastic)}
$$

**Internal-variable update**
$$
\boldsymbol{\varepsilon}^p_{n+1} = \boldsymbol{\varepsilon}^p_n + \frac{\Delta t}{\eta + \Delta t}\,(\bar{\boldsymbol{\varepsilon}}^p_{n+1} - \boldsymbol{\varepsilon}^p_n)
$$

**Algorithmic tangent (Peirce form)**
$$
\mathbb{C}^{\mathrm{alg}} = \frac{\eta}{\eta+\Delta t}\,\mathbb{C}^e + \frac{\Delta t}{\eta+\Delta t}\,\bar{\mathbb{C}}^{\mathrm{alg,RI}}
$$

**Comparison with Perzyna**
$$
\text{Perzyna: } \dot\gamma = (1/\eta)\langle f/\sigma_0\rangle^m,\,\text{requires inner Newton on}\,\Delta\gamma\\
\text{Duvaut-Lions: closed-form interpolation between}\,\boldsymbol{\sigma}^{\mathrm{trial}}\,\text{and}\,\bar{\boldsymbol{\sigma}}_{n+1}
$$

**Effective overstress exponent**
$$
\dot{\bar\varepsilon}^p = (\Delta t/(\eta+\Delta t))\,\dot{\bar\varepsilon}^{p,\mathrm{RI}}
$$

**Peirce regularisation in shear-band analysis**
$$
\ell_{\mathrm{band}} \sim c_s\,\eta\,\sqrt{\Delta t/\eta}\,\text{at intermediate rate}
$$

**Notation:**
{'\\bar{\\boldsymbol{\\sigma}}': 'Rate-independent return-mapped stress', '\\eta': 'Relaxation time / viscosity parameter', '\\Delta t': 'Time step', '\\eta/(\\eta+\\Delta t)': 'Trial weight in interpolation', '\\Delta t/(\\eta+\\Delta t)': 'Relaxation weight in interpolation (range $[0, 1]$)', '\\bar{\\mathbb{C}}^{\\mathrm{alg,RI}}': 'Rate-independent algorithmic tangent (e.g., Souza-Neto J2)', '\\mathbb{C}^e': 'Elastic tangent', '\\bar{\\boldsymbol{\\varepsilon}}^p_{n+1}': 'Rate-independent end-of-step plastic strain'}


## 3. Algorithmic Implementation

**Duvaut-Lions Closed-Form Update**
$$
\begin{algorithmic}
\State State \text{input} \colon \boldsymbol{\sigma}_n,\boldsymbol{\varepsilon}^p_n,\bar\varepsilon^p_n,\Delta\boldsymbol{\varepsilon},\eta,\Delta t,\,\text{rate-indep return mapping}\,\mathrm{ReturnMapRI}$
\State State \boldsymbol{\sigma}^{\mathrm{trial}} \gets \boldsymbol{\sigma}_n + \mathbb{C}^e\colon\Delta\boldsymbol{\varepsilon}
\State State \bar{\boldsymbol{\sigma}}_{n+1},\bar{\boldsymbol{\varepsilon}}^p_{n+1},\bar{\bar\varepsilon}^p_{n+1},\bar{\mathbb{C}}^{\mathrm{alg,RI}} \gets \mathrm{ReturnMapRI}(\boldsymbol{\sigma}^{\mathrm{trial}},\bar\varepsilon^p_n,\boldsymbol{\varepsilon}^p_n)
\State State w \gets \Delta t/(\eta + \Delta t)
\State State \boldsymbol{\sigma}_{n+1} \gets (1-w)\,\boldsymbol{\sigma}^{\mathrm{trial}} + w\,\bar{\boldsymbol{\sigma}}_{n+1}
\State State \boldsymbol{\varepsilon}^p_{n+1} \gets \boldsymbol{\varepsilon}^p_n + w\,(\bar{\boldsymbol{\varepsilon}}^p_{n+1} - \boldsymbol{\varepsilon}^p_n)
\State State \bar\varepsilon^p_{n+1} \gets \bar\varepsilon^p_n + w\,(\bar{\bar\varepsilon}^p_{n+1} - \bar\varepsilon^p_n)
\State State \mathbb{C}^{\mathrm{alg}} \gets (1-w)\,\mathbb{C}^e + w\,\bar{\mathbb{C}}^{\mathrm{alg,RI}}
\State Return \boldsymbol{\sigma}_{n+1},\boldsymbol{\varepsilon}^p_{n+1},\bar\varepsilon^p_{n+1},\mathbb{C}^{\mathrm{alg}}
\end{algorithmic}
$$
Taichi Mapping: Cleanest viscoplastic algorithm: ONE call to rate-independent return mapping, ONE linear interpolation, no inner Newton. Per-Gauss-point cost: same as rate-independent return mapping plus $\sim 50$ FMAs for the interpolation. The rate-independent return mapping subroutine is a black box — works for any yield surface (J2, Drucker-Prager, GTN, Hill48). The simplicity makes Duvaut-Lions production-code-friendly.

**Choose Between Perzyna and Duvaut-Lions**
$$
\begin{algorithmic}
\State State \text{decision factors:}
\State State \text{(a) need exact rate-independent at}\,\eta=0\,\to\,\text{Duvaut-Lions (closed-form recovery)}
\State State \text{(b) physical Perzyna calibration available}\,\to\,\text{Perzyna (overstress exponent}\,m)
\State State \text{(c) production-code simplicity}\,\to\,\text{Duvaut-Lions (no inner Newton)}
\State State \text{(d) very stiff overstress (m > 10)}\,\to\,\text{Duvaut-Lions (Perzyna fails)}
\State State \text{(e) need power-law strain-rate sensitivity}\,\to\,\text{Perzyna (m parameter)}
\State Return \text{recommended choice}
\end{algorithmic}
$$
Taichi Mapping: Use this decision template at model-design time. Most production codes default to Duvaut-Lions for simplicity and robustness; specialised dynamic-loading codes (ballistics, machining) often need Perzyna's power-law overstress for accurate rate-sensitivity calibration. Document the choice in the constitutive interface and validate against experimental rate sweeps.

**Calibrate $\eta$ from Strain-Rate-Sensitivity Data**
$$
\begin{algorithmic}
\State State \text{input} \colon \{(\sigma_Y, \dot{\bar\varepsilon}^p)\}\,\text{at multiple rates}
\State State \text{Duvaut-Lions steady state: } \sigma_Y(\dot\gamma) = \bar\sigma_Y + \eta\,\dot\gamma
\State State \text{linear regression}\,\sigma_Y\,\text{vs}\,\dot\gamma\,\text{gives slope}\,\eta\,\text{and intercept}\,\bar\sigma_Y
\State Return \eta
\end{algorithmic}
$$
Taichi Mapping: Off-line calibration. Duvaut-Lions has only ONE rate parameter ($\eta$); linear in strain rate. For materials with power-law rate sensitivity, this is a coarser model than Perzyna's two-parameter $(\eta, m)$. Default values: $\eta\sim 10^{-4}$ s for most metals; smaller for harder alloys, larger for soft polymers / rubbers.


## 4. Known Pitfalls

- **Confusion with Perzyna**: Both are rate-dependent regularisations but have DIFFERENT algorithmic structure. Perzyna: replace yield consistency with overstress; requires inner Newton. Duvaut-Lions: interpolate between trial and rate-independent stress; closed form. Don't mix the two in the same constitutive code; the calibrated $\eta$ values are not interchangeable between formulations.
- **Rate-independent return mapping must converge robustly**: Duvaut-Lions calls the rate-independent return mapping as a black box; if that subroutine fails (e.g., near Drucker-Prager apex, or for non-convex yield surface) the Duvaut-Lions wrapper fails too. Make the rate-independent code bulletproof first; THEN wrap with Duvaut-Lions for rate-dependence.
- **Wrong choice of $\eta$ relative to $\Delta t$**: The interpolation weight $w=\Delta t/(\eta+\Delta t)$ depends on the time step. For a given material $\eta$, varying $\Delta t$ changes the effective rate sensitivity: $\Delta t\ll\eta$ produces nearly-elastic response, $\Delta t\gg\eta$ produces nearly-rate-independent. Mesh / time-step independence requires $\eta$ chosen for the LOADING rate of interest, not arbitrarily.
- **Internal-variable interpolation**: Duvaut-Lions interpolates not just stress but ALL state variables (plastic strain, hardening, damage). Forgetting to interpolate the internal variables produces inconsistent state — stress evolves rate-dependently while plastic strain evolves rate-independently. Apply the same weight $w$ to every state variable.
- **Linear vs power-law rate sensitivity**: Duvaut-Lions implies LINEAR rate sensitivity (slope $\eta$ in $\sigma_Y$ vs $\dot{\bar\varepsilon}^p$). Real metals show POWER-LAW rate sensitivity ($\sigma_Y\sim(\dot{\bar\varepsilon}^p)^{1/m}$). For accurate rate-sensitivity calibration use Perzyna's power-law form; Duvaut-Lions is a first-order approximation.
- **Singular limits not numerically robust**: $\eta=0$ exactly recovers rate-independent (good); $\eta\to\infty$ recovers elastic (good). But round-off can give $\eta=10^{-15}$ which produces a noisy interpolation weight near 1. Guard with $w=\min(1, \Delta t/(\eta+\Delta t))$ and $w=\max(0, w)$ to keep the interpolation in $[0, 1]$.
- **Algorithmic tangent inherits $\bar{\mathbb{C}}^{\mathrm{alg,RI}}$ asymmetry**: For non-associated rate-independent plasticity (Drucker-Prager with $\beta\ne\alpha$), $\bar{\mathbb{C}}^{\mathrm{alg,RI}}$ is asymmetric. The Duvaut-Lions interpolation $(1-w)\mathbb{C}^e+w\,\bar{\mathbb{C}}^{\mathrm{alg,RI}}$ is also asymmetric (since $\mathbb{C}^e$ is symmetric but adding asymmetric piece breaks symmetry). Pass through to the global FEM with GMRES / Bi-CGSTAB; do not symmetrise.
- **Source notebook coverage limited**: Duvaut-Lions is mentioned in dynamic-plasticity / softening-regularisation literature but the source notebook (be555674-...) covers it less thoroughly than Perzyna. Equations and structure cross-checked from Simo-Hughes (1998); confidence reduced ($0.85$) accordingly.

## References

- Duvaut & Lions (1972) — Inequalities in Mechanics and Physics (original variational formulation)
- Simo & Hughes (1998) — Computational Inelasticity, Ch. 4 (Duvaut-Lions backward-Euler closed-form, comparison with Perzyna)
- Peirce, Shih & Needleman (1984) — A tangent modulus method for rate dependent solids (algorithmic tangent for viscoplastic regularisation)
- Souza Neto, Peric, Owen (2008) — Computational Methods for Plasticity (Duvaut-Lions in production codes)
