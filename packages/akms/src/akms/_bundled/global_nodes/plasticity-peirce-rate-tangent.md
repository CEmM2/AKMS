---
id: plasticity-peirce-rate-tangent
title: Peirce-Shih-Needleman Rate Tangent Method
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- viscoplasticity
- rate-tangent
- forward-gradient
- peirce-needleman
- crystal-plasticity
status: tentative
confidence: 0.85
source: hybrid
confidence_floor: 0.7
edges:
- to: plasticity-von-mises
  type: refines
  weight: 0.8
  note: 'Rate-dependent generalisation of J2: replaces the consistency condition with an explicit viscoplastic flow rate integrated
    by a forward gradient'
- to: plasticity-perzyna
  type: contradicts
  weight: 0.5
  note: Same viscoplastic flow law, different integration — PSN uses a non-iterative forward-gradient tangent; Perzyna requires
    an inner Newton on the overstress residual
- to: plasticity-duvaut-lions
  type: feeds-into
  weight: 0.6
  note: Duvaut-Lions borrows the Peirce tangent-modulus relation for its consistent tangent; PSN is the original source of
    that rate-tangent linearisation
- to: constit-stress-update-architecture
  type: requires
  weight: 1.0
  note: Same elastic-predictor / plastic-corrector scaffolding; the corrector is a single linear solve rather than a return-mapping
    Newton loop
- to: plasticity-consistent-tangent-general
  type: feeds-into
  weight: 0.7
  note: Supplies a rate-dependent algorithmic tangent that smoothly limits to the rate-independent consistent tangent as m
    -> 0
load_with:
- plasticity-perzyna
- plasticity-duvaut-lions
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Peirce-Shih-Needleman Rate Tangent Method

## Summary

The Peirce-Shih-Needleman (PSN, 1984) rate-tangent method integrates rate-dependent (viscoplastic) constitutive laws with a non-iterative forward-gradient scheme. The plastic strain rate is an EXPLICIT function of state, $\dot{\bar\varepsilon}^p=h(\sigma_e,\bar\varepsilon^p)$ — typically the power law $\dot{\bar\varepsilon}^p=\dot\varepsilon_0(\sigma_e/g(\bar\varepsilon^p))^{1/m}$ — so there is no yield surface and no KKT consistency to enforce. The increment is sampled at $t+\theta\Delta t$: $\Delta\bar\varepsilon^p=\Delta t[(1-\theta)\dot{\bar\varepsilon}^p_t+\theta\dot{\bar\varepsilon}^p_{t+\Delta t}]$, and $\dot{\bar\varepsilon}^p_{t+\Delta t}$ is replaced by its first-order Taylor expansion (the "tangent" of the rate) about the current state. Eliminating $\Delta\bar\varepsilon^p$ gives a closed-form, rate-dependent TANGENT MODULUS $\mathbb{L}^{\mathrm{tan}}$ plus an additive relaxation/creep term — a stress update with NO local Newton iteration. The forward-gradient parameter $\theta\ge 1/2$ makes the scheme unconditionally stable, permitting time steps far larger than the viscoplastic relaxation time (where explicit forward Euler, $\theta=0$, would be conditionally stable and require tiny steps). The method is designed so that as the rate-sensitivity $m\to 0$, $\mathbb{L}^{\mathrm{tan}}$ smoothly recovers the rate-independent elastoplastic consistent tangent — one algorithm spans the rate-independent-to-strongly-rate-dependent spectrum. It is the workhorse integrator for rate-dependent crystal plasticity, where the forward gradient removes the active-slip-set ambiguity of the rate-independent formulation.

## 1. Core Concept

Rate-independent plasticity enforces $f\le 0$, $\dot\gamma\,f=0$ (KKT) and solves a return mapping; rate-dependent (viscoplastic) plasticity instead postulates that the plastic flow rate is a smooth, single-valued function of the current stress and internal state, $\dot{\bar\varepsilon}^p=h(\sigma_e,\bar\varepsilon^p)$, so stress can lie OUTSIDE the quasi-static flow surface (overstress) and the flow magnitude is determined directly — no consistency condition, no active-set decision. The numerical challenge is that this rate law is stiff: for low rate-sensitivity (small $m$) a tiny change in stress produces a large change in plastic rate, so an explicit forward-Euler update needs prohibitively small time steps. PSN's insight is to evaluate the plastic increment with a generalised-midpoint (forward-gradient) rule, $\Delta\bar\varepsilon^p=\Delta t[(1-\theta)\dot{\bar\varepsilon}^p_t+\theta\dot{\bar\varepsilon}^p_{t+\Delta t}]$, and to LINEARISE the unknown end-of-step rate $\dot{\bar\varepsilon}^p_{t+\Delta t}$ rather than solve for it implicitly. The linearisation introduces the partial derivatives $h_\sigma=\partial\dot{\bar\varepsilon}^p/\partial\sigma_e$ and $h_\varepsilon=\partial\dot{\bar\varepsilon}^p/\partial\bar\varepsilon^p$; combined with the elastic relation between stress and plastic-strain increments, $\Delta\bar\varepsilon^p$ is obtained from a single scalar division, and the stress update collapses to $\Delta\boldsymbol{\sigma}=\mathbb{L}^{\mathrm{tan}}\colon\Delta\boldsymbol{\varepsilon}-\Delta\boldsymbol{\sigma}^{\mathrm{relax}}$. The tangent modulus $\mathbb{L}^{\mathrm{tan}}$ has the familiar rank-one-down structure of the elastoplastic tangent, but its plastic-correction strength is governed by $\theta\Delta t\,h_\sigma$ instead of a hardening modulus — and crucially it limits continuously to the rate-independent consistent tangent as $m\to 0$. With $\theta\ge 1/2$ the implicit weighting damps the stiff response and gives unconditional linear stability, so the same code handles quasi-static ($\Delta t\gg$ relaxation time) and dynamic loading without switching algorithms. This is why PSN is the standard integrator in rate-dependent crystal plasticity (forward gradient on each slip rate $\dot\gamma^\alpha$) and a common regulariser for shear-band and localisation problems.

## 2. Mathematical Formulation

**Viscoplastic flow rate (power law)**
$$
\dot{\bar\varepsilon}^p = h(\sigma_e,\bar\varepsilon^p)
= \dot\varepsilon_0\!\left[\frac{\sigma_e}{g(\bar\varepsilon^p)}\right]^{1/m},
\qquad
\dot{\boldsymbol{\varepsilon}}^p = \dot{\bar\varepsilon}^p\,\mathbf{P}
$$

**Forward-gradient (theta-rule) plastic increment**
$$
\Delta\bar\varepsilon^p = \Delta t\left[(1-\theta)\,\dot{\bar\varepsilon}^p_t + \theta\,\dot{\bar\varepsilon}^p_{t+\Delta t}\right],
\qquad \theta\in[0,1]
$$

**Rate tangent (first-order linearisation of the end-of-step rate)**
$$
\dot{\bar\varepsilon}^p_{t+\Delta t} \approx \dot{\bar\varepsilon}^p_t
+ h_\sigma\,\Delta\sigma_e + h_\varepsilon\,\Delta\bar\varepsilon^p,
\qquad
h_\sigma=\frac{\partial\dot{\bar\varepsilon}^p}{\partial\sigma_e},\;\;
h_\varepsilon=\frac{\partial\dot{\bar\varepsilon}^p}{\partial\bar\varepsilon^p}
$$

**Power-law derivatives**
$$
h_\sigma = \frac{\dot{\bar\varepsilon}^p}{m\,\sigma_e} > 0,
\qquad
h_\varepsilon = -\,\frac{\dot{\bar\varepsilon}^p}{m}\,\frac{g'(\bar\varepsilon^p)}{g(\bar\varepsilon^p)} \le 0
$$

**Elastic stress/Mises-stress increment relation**
$$
\Delta\boldsymbol{\sigma} = \mathbb{C}^e\colon\Delta\boldsymbol{\varepsilon} - \Delta\bar\varepsilon^p\,(\mathbb{C}^e\colon\mathbf{P}),
\qquad
\Delta\sigma_e = \mathbf{P}\colon\mathbb{C}^e\colon\Delta\boldsymbol{\varepsilon} - a\,\Delta\bar\varepsilon^p
$$

**Closed-form plastic increment**
$$
\Delta\bar\varepsilon^p =
\frac{\Delta t\,\dot{\bar\varepsilon}^p_t + \theta\Delta t\,h_\sigma\,(\mathbf{P}\colon\mathbb{C}^e\colon\Delta\boldsymbol{\varepsilon})}{D},
\qquad
D = 1 - \theta\Delta t\,h_\varepsilon + \theta\Delta t\,h_\sigma\,a
$$

**Rate-tangent stress update**
$$
\Delta\boldsymbol{\sigma} = \mathbb{L}^{\mathrm{tan}}\colon\Delta\boldsymbol{\varepsilon} - \Delta\boldsymbol{\sigma}^{\mathrm{relax}}
$$

**Rate tangent modulus**
$$
\mathbb{L}^{\mathrm{tan}} = \mathbb{C}^e
- \frac{\theta\Delta t\,h_\sigma}{D}\,(\mathbb{C}^e\colon\mathbf{P})\otimes(\mathbf{P}\colon\mathbb{C}^e)
$$

**Relaxation (creep) term**
$$
\Delta\boldsymbol{\sigma}^{\mathrm{relax}} = \frac{\Delta t\,\dot{\bar\varepsilon}^p_t}{D}\,(\mathbb{C}^e\colon\mathbf{P})
$$

**Rate-independent limit (m -> 0)**
$$
\frac{\theta\Delta t\,h_\sigma}{D} \;\xrightarrow{\,m\to 0\,}\; \frac{1}{a + h},
\qquad
\mathbb{L}^{\mathrm{tan}} \to \mathbb{C}^e - \frac{(\mathbb{C}^e\colon\mathbf{P})\otimes(\mathbf{P}\colon\mathbb{C}^e)}{\mathbf{P}\colon\mathbb{C}^e\colon\mathbf{P} + h}
$$

**Linear stability of the forward gradient**
$$
\theta \ge \tfrac12:\ \text{unconditionally stable};\qquad
\theta < \tfrac12:\ \Delta t \lesssim \frac{1}{(1-2\theta)\,a\,h_\sigma}
$$

**Crystal-plasticity form (per slip system)**
$$
\dot\gamma^\alpha = \dot\gamma_0\left|\frac{\tau^\alpha}{g^\alpha}\right|^{1/m}\!\operatorname{sgn}(\tau^\alpha),
\qquad
\Delta\gamma^\alpha = \Delta t\left[(1-\theta)\dot\gamma^\alpha_t + \theta\dot\gamma^\alpha_{t+\Delta t}\right]
$$

**Notation:**
{'\\dot{\\bar\\varepsilon}^p': 'Effective viscoplastic strain rate (explicit function of state)', '\\sigma_e': 'Mises effective stress, $\\sqrt{\\tfrac32\\mathbf{s}\\colon\\mathbf{s}}$', 'g(\\bar\\varepsilon^p)': "Flow strength / hardening function; $h=g'$ is the hardening modulus", 'm': 'Strain-rate sensitivity exponent ($m\\to 0$ rate-independent, $m=1$ linear viscous)', '\\dot\\varepsilon_0': 'Reference strain rate', '\\theta': 'Forward-gradient / time-integration parameter in $[0,1]$', '\\mathbf{P}': 'Mises stress gradient / flow direction, $\\tfrac{3}{2}\\mathbf{s}/\\sigma_e$', 'h_\\sigma': '$\\partial\\dot{\\bar\\varepsilon}^p/\\partial\\sigma_e$ (rate sensitivity to stress)', 'h_\\varepsilon': '$\\partial\\dot{\\bar\\varepsilon}^p/\\partial\\bar\\varepsilon^p$ (rate sensitivity to hardening)', 'a': '$\\mathbf{P}\\colon\\mathbb{C}^e\\colon\\mathbf{P}=3\\mu$ for isotropic elasticity', 'D': 'Forward-gradient denominator $1-\\theta\\Delta t\\,h_\\varepsilon+\\theta\\Delta t\\,h_\\sigma a$', '\\mathbb{L}^{\\mathrm{tan}}': 'Rate tangent modulus', '\\dot\\gamma^\\alpha': 'Slip rate on system $\\alpha$ (crystal plasticity form)'}


## 3. Algorithmic Implementation

**PSN Rate-Tangent Stress Update (J2)**
$$
\begin{algorithmic}
\State State \text{input} \colon \boldsymbol{\sigma}_n,\bar\varepsilon^p_n,\Delta\boldsymbol{\varepsilon},\mathbb{C}^e,\dot\varepsilon_0,m,g(\cdot),g'(\cdot),\theta,\Delta t
\State State \boldsymbol{\sigma}^{\mathrm{trial}} \gets \boldsymbol{\sigma}_n + \mathbb{C}^e\colon\Delta\boldsymbol{\varepsilon},\quad \mathbf{s}\gets\operatorname{dev}\boldsymbol{\sigma}^{\mathrm{trial}}
\State State \sigma_e \gets \sqrt{\tfrac32\,\mathbf{s}\colon\mathbf{s}},\quad \mathbf{P}\gets \tfrac{3}{2}\,\mathbf{s}/\sigma_e
\State State \dot{\bar\varepsilon}^p_t \gets \dot\varepsilon_0\,(\sigma_e/g(\bar\varepsilon^p_n))^{1/m}
\State State h_\sigma \gets \dot{\bar\varepsilon}^p_t/(m\,\sigma_e),\quad h_\varepsilon \gets -\,\dot{\bar\varepsilon}^p_t\,g'(\bar\varepsilon^p_n)/(m\,g(\bar\varepsilon^p_n))
\State State a \gets \mathbf{P}\colon\mathbb{C}^e\colon\mathbf{P}\;(=3\mu),\quad D \gets 1 - \theta\Delta t\,h_\varepsilon + \theta\Delta t\,h_\sigma\,a
\State State \Delta\bar\varepsilon^p \gets [\Delta t\,\dot{\bar\varepsilon}^p_t + \theta\Delta t\,h_\sigma\,(\mathbf{P}\colon\mathbb{C}^e\colon\Delta\boldsymbol{\varepsilon})]/D
\State State \boldsymbol{\sigma}_{n+1} \gets \boldsymbol{\sigma}^{\mathrm{trial}} - \Delta\bar\varepsilon^p\,(\mathbb{C}^e\colon\mathbf{P})
\State State \bar\varepsilon^p_{n+1} \gets \bar\varepsilon^p_n + \Delta\bar\varepsilon^p
\State State \mathbb{L}^{\mathrm{tan}} \gets \mathbb{C}^e - (\theta\Delta t\,h_\sigma/D)\,(\mathbb{C}^e\colon\mathbf{P})\otimes(\mathbf{P}\colon\mathbb{C}^e)
\State Return \boldsymbol{\sigma}_{n+1},\bar\varepsilon^p_{n+1},\mathbb{L}^{\mathrm{tan}}
\end{algorithmic}
$$
Taichi Mapping: Per-Gauss-point `@ti.func`, NON-iterative: one evaluation of the rate and its two derivatives, one scalar denominator $D$, one rank-one tangent update. Far cheaper than implicit Perzyna (no inner Newton). Guard the elastic branch with $\sigma_e>\sigma_{\min}$ to avoid divide-by-zero in $\mathbf{P}$ and $h_\sigma$ (when $\sigma_e\to 0$ set $\dot{\bar\varepsilon}^p=0$, $\Delta\bar\varepsilon^p=0$). Use $\theta\in[0.5,1]$ for unconditional stability; $\theta=0.5$ is second-order accurate but lightly damped, $\theta=1$ is first-order and strongly damped (robust for very stiff $m$). The whole update is branch-light and vectorises well on GPU.

**Compute Rate-Tangent Modulus (standalone)**
$$
\begin{algorithmic}
\State State \text{input} \colon \mathbf{P},\mathbb{C}^e,h_\sigma,h_\varepsilon,a,\theta,\Delta t
\State State D \gets 1 - \theta\Delta t\,h_\varepsilon + \theta\Delta t\,h_\sigma\,a
\State State \mathbb{L}^{\mathrm{tan}} \gets \mathbb{C}^e - (\theta\Delta t\,h_\sigma/D)\,(\mathbb{C}^e\colon\mathbf{P})\otimes(\mathbf{P}\colon\mathbb{C}^e)
\State Return \mathbb{L}^{\mathrm{tan}}
\end{algorithmic}
$$
Taichi Mapping: Consistent tangent for the global Newton solve. As $m\to 0$ the factor $\theta\Delta t\,h_\sigma/D\to 1/(a+h)$ and $\mathbb{L}^{\mathrm{tan}}$ becomes the rate-independent J2 consistent tangent — so the SAME assembly path serves quasi-static and dynamic regimes. The tangent is symmetric for associated J2 (rank-one symmetric correction); reuse $\mathbb{C}^e\colon\mathbf{P}$ from the stress update to avoid recomputing the double contraction.

**Forward-Gradient Crystal-Plasticity Slip Update**
$$
\begin{algorithmic}
\State State \text{input} \colon \{\tau^\alpha\},\{g^\alpha\},\dot\gamma_0,m,\theta,\Delta t,\{\mathbf{m}^\alpha\otimes\mathbf{n}^\alpha\}
\State For \alpha = 1,\ldots,N_{\mathrm{slip}}
\State State \dot\gamma^\alpha_t \gets \dot\gamma_0\,|\tau^\alpha/g^\alpha|^{1/m}\operatorname{sgn}(\tau^\alpha)
\State State \frac{\partial\dot\gamma^\alpha}{\partial\tau^\beta} \gets \frac{\dot\gamma_0}{m\,g^\alpha}|\tau^\alpha/g^\alpha|^{1/m-1}\,\delta^{\alpha\beta}
\State EndFor
\State State \text{assemble } \Delta\gamma^\alpha = \Delta t[(1-\theta)\dot\gamma^\alpha_t + \theta\dot\gamma^\alpha_{t+\Delta t}]\,\text{with the linearised}\,\dot\gamma^\alpha_{t+\Delta t}
\State State \text{solve the } N_{\mathrm{slip}}\times N_{\mathrm{slip}}\,\text{linear system for}\,\{\Delta\gamma^\alpha\}
\State State \Delta\boldsymbol{\varepsilon}^p \gets \sum_\alpha \Delta\gamma^\alpha\,\operatorname{sym}(\mathbf{m}^\alpha\otimes\mathbf{n}^\alpha)
\State Return \Delta\boldsymbol{\varepsilon}^p,\{\Delta\gamma^\alpha\}
\end{algorithmic}
$$
Taichi Mapping: The forward gradient turns the otherwise stiff, non-unique rate-independent slip problem into one well-conditioned linear solve of size $N_{\mathrm{slip}}$ ($12$ for FCC, $24/48$ for BCC). This is the canonical PSN application (Peirce, Asaro & Needleman 1983). Build the slip-interaction Jacobian once per increment; with $\theta\ge 1/2$ the step is stable even when individual slip systems are very rate-sensitive. For small $m$ (near rate-independent) reduce $\Delta t$ or raise $\theta$ to keep the linear system well-conditioned.


## 4. Known Pitfalls

- **Forward Euler (theta = 0) is only conditionally stable**: With $\theta=0$ the scheme is explicit forward Euler and the stable step is bounded by $\Delta t\lesssim 1/(a\,h_\sigma)$ — for low rate-sensitivity (small $m$, large $h_\sigma$) this is prohibitively small. Always use $\theta\ge 1/2$ for unconditional linear stability; the original PSN paper recommends $\theta\in[0.5,1]$. Reserve $\theta=0$ only for explicit-dynamics codes where $\Delta t$ is already tiny for other reasons.
- **Rate-independent limit makes the derivatives blow up**: As $m\to 0$ both $h_\sigma=\dot{\bar\varepsilon}^p/(m\sigma_e)$ and $|h_\varepsilon|$ diverge like $1/m$. The TANGENT is well-behaved (the ratio $\theta\Delta t\,h_\sigma/D\to 1/(a+h)$ is finite) but computing $h_\sigma$ literally overflows in floating point. Reformulate in terms of the bounded ratio $\theta\Delta t\,h_\sigma/D$, or floor the exponent at $m\ge m_{\min}\sim 10^{-3}$, or switch to a rate-independent return mapping below $m_{\min}$.
- **theta trades accuracy against numerical damping**: $\theta=1/2$ (midpoint) is second-order accurate but lightly damped — it can produce stress oscillations for stiff problems or large steps. $\theta=1$ (backward) is only first-order but strongly damped and robust. Pick $\theta$ per regime: $0.5$ for smooth quasi-static loading where accuracy matters, closer to $1$ for impact / very rate-sensitive materials. Document the choice; results depend on it.
- **Single linearisation is inaccurate for large strain increments**: The forward gradient is a FIRST-ORDER Taylor expansion of the rate about the start-of-step state. If $\Delta\sigma_e$ over the step is a large fraction of $\sigma_e$ (large $\Delta t$ or sharp loading), the single linearisation is inaccurate and the flow rule is not satisfied to tight tolerance. Sub-step the increment, reduce $\Delta t$, or iterate the rate-tangent update (re-linearise about the updated state) when accuracy is critical.
- **Not a fully implicit return mapping**: PSN is SEMI-explicit: it satisfies a linearised flow rule, not the exact rate equation, each step. Do not expect machine-precision satisfaction of $\dot{\bar\varepsilon}^p=h(\sigma_e,\bar\varepsilon^p)$ at end of step the way an implicit Perzyna return mapping delivers. For tight per-step tolerance use implicit Perzyna (inner Newton) or iterate the rate tangent; PSN trades that for speed and robustness across rate regimes.
- **Omitting the relaxation (creep) term**: The stress update has TWO parts: $\mathbb{L}^{\mathrm{tan}}\colon\Delta\boldsymbol{\varepsilon}$ and the strain-independent relaxation term $\Delta t\,\dot{\bar\varepsilon}^p_t/D\,(\mathbb{C}^e\colon\mathbf{P})$. Forgetting the second term means stress does not relax under a strain hold ($\Delta\boldsymbol{\varepsilon}=0$), so creep and stress-relaxation responses are lost while monotonic loading may still look plausible — a subtle bug. Always include it.
- **Crystal plasticity: stiff/ill-conditioned slip Jacobian at small m**: For strongly rate-dependent crystal plasticity (small $m$), the $N_{\mathrm{slip}}\times N_{\mathrm{slip}}$ forward-gradient Jacobian becomes stiff and can be ill-conditioned, especially with many near-active systems. Raise $\theta$ toward $1$, reduce $\Delta t$, or add latent-hardening regularisation. The forward gradient still beats rate-independent active-set search (which is non-unique for $\ge 5$ active systems), but it is not unconditionally cheap.
- **sigma_0 / reference-rate and exponent conventions**: Two exponent conventions coexist: $\dot{\bar\varepsilon}^p\propto(\sigma_e/g)^{1/m}$ (rate-sensitivity $m$, used here and in PSN/crystal-plasticity) versus $\propto(\sigma_e/g)^{n}$ with $n=1/m$ (creep-exponent form). Mixing them inverts the rate dependence. State which exponent is the rate-sensitivity and which is its reciprocal, and keep $\dot\varepsilon_0$, $g$ consistent with the calibration data.

## References

- Peirce, Shih & Needleman (1984) — A tangent modulus method for rate dependent solids, Computers & Structures 18(5):875-887 (the rate-tangent / forward-gradient method)
- Peirce, Asaro & Needleman (1983) — Material rate dependence and localized deformation in crystalline solids, Acta Metall. 31:1951-1976 (forward gradient for rate-dependent crystal plasticity)
- Zhang (1995) — Explicit consistent tangent moduli with a return mapping algorithm for elastoplasticity (companion explicit-tangent approach)
- Zabaras & Arif (1992) — A family of integration algorithms for constitutive equations in finite-deformation elasto-viscoplasticity (generalised-midpoint integrators)
- Simo & Hughes (1998) — Computational Inelasticity (viscoplastic integration, generalized-midpoint stability context)
