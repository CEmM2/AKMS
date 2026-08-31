---
id: plasticity-von-mises
title: Von Mises (J2) Yield Criterion
domain: computational-mechanics
subdomain: plasticity
tags:
- plasticity
- yield-criterion
- j2
- associated-flow
- von-mises
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: tensor-invariants
  type: requires
  weight: 1.0
  note: $f=\sqrt{3J_2}-\sigma_Y$ is built directly from the second deviatoric invariant
- to: constit-thermodynamic-framework
  type: requires
  weight: 0.9
  note: Associated J2 flow follows from convexity of $f$ and maximum dissipation
- to: constit-stress-update-architecture
  type: requires
  weight: 1.0
  note: Operator-split radial-return method specialised for J2
- to: plasticity-general-return-mapping
  type: feeds-into
  weight: 1.0
  note: Closed-form J2 radial return is the canonical example
- to: plasticity-consistent-tangent-j2
  type: feeds-into
  weight: 1.0
  note: J2 algorithmic tangent has a known closed form
context_size: medium
reading_priority: full
load_with:
- tensor-invariants
- plasticity-general-return-mapping
content_ref: null
akms_schema: v2
---

# Von Mises (J2) Yield Criterion

## Summary
The von Mises (J2) yield criterion $f(\boldsymbol{\sigma},\bar\varepsilon^p)=\sqrt{3J_2}-\sigma_Y(\bar\varepsilon^p)=0$ characterises pressure-independent yielding of metals: the yield surface is a circular cylinder in principal-stress space whose axis is the hydrostatic line $\sigma_1=\sigma_2=\sigma_3$. Yielding depends only on the deviatoric invariant $J_2=\tfrac12 s_{ij}s_{ij}$, expressed via the equivalent stress $\sigma_{eq}=\sqrt{3J_2}$. Associated flow $\dot{\boldsymbol{\varepsilon}}^p=\dot\gamma\,\partial f/\partial\boldsymbol{\sigma}=\dot\gamma\,\sqrt{\tfrac32}\,\mathbf{s}/\|\mathbf{s}\|$ delivers normality (flow direction along outward normal of the cylinder), automatically guarantees positive dissipation, and enforces plastic incompressibility $\mathrm{tr}\,\dot{\boldsymbol{\varepsilon}}^p=0$. Consistency $f=0,\,\dot f=0$ during plastic loading combined with the flow rule and isotropic hardening $\sigma_Y=\sigma_Y(\bar\varepsilon^p)$ produces a closed-form radial-return algorithm: $\Delta\gamma$ solves $\sqrt{3J_2^{\mathrm{trial}}}-3\mu\Delta\gamma-\sigma_Y(\bar\varepsilon^p_n+\Delta\gamma)=0$, then $\boldsymbol{\sigma}_{n+1}=\boldsymbol{\sigma}^{\mathrm{trial}}-2\mu\Delta\gamma\sqrt{\tfrac32}\mathbf{s}^{\mathrm{trial}}/\|\mathbf{s}^{\mathrm{trial}}\|$.


## 1. Core Concept
J2 plasticity is the simplest realistic plasticity model and the foundation of nearly every metals-plasticity computation. Two physical observations underpin it: (1) hydrostatic stress does NOT cause yielding in metals — submerging a metal block in fluid produces no permanent deformation no matter how large the pressure; (2) yielding is fundamentally a shear / distortion process driven by dislocation glide on slip planes, captured by the deviator. The yield function $f=\sqrt{3J_2}-\sigma_Y$ encodes both: it is built from $J_2$ alone (hydrostatic-independent) and reaches yield when the equivalent shear stress $\sqrt{3J_2}$ — the Mises equivalent stress, equal to $\sigma$ in uniaxial tension — exceeds the yield strength $\sigma_Y$. Associated flow follows from convexity of $f$ via the maximum dissipation principle: the flow direction is the outward normal to the yield surface, which for $f=\sqrt{3J_2}-\sigma_Y$ is $\sqrt{3/2}\,\mathbf{s}/\|\mathbf{s}\|$ — purely deviatoric, giving plastic incompressibility for free. The combination of (a) closed-form yield function, (b) closed-form flow rule, (c) closed-form radial-return solution makes J2 the testbed for stress-update architectures and the gold-standard benchmark before extending to GTN, Hill, Drucker-Prager. The factor-of-$\sqrt{3}$ vs $\sqrt{2}$ debate in different references is the most common source of bugs.


## 2. Mathematical Formulation
Throughout, $\boldsymbol{\sigma}$ Cauchy stress, $\mathbf{s}=\mathrm{dev}\,\boldsymbol{\sigma}=\boldsymbol{\sigma}-\tfrac13\,\mathrm{tr}\boldsymbol{\sigma}\,\mathbf{I}$ deviator, $J_2=\tfrac12\,\mathbf{s}\colon\mathbf{s}=\tfrac12 s_{ij}s_{ij}$, $\sigma_{eq}=\sqrt{3J_2}$ Mises equivalent stress. $\bar\varepsilon^p$ accumulated equivalent plastic strain, $H=d\sigma_Y/d\bar\varepsilon^p$ isotropic hardening modulus. $\mu$ shear modulus, $\kappa$ bulk modulus.


**von Mises yield function:**

$$
f(\boldsymbol{\sigma}, \bar\varepsilon^p) = \sqrt{3 J_2} - \sigma_Y(\bar\varepsilon^p) = \sigma_{eq} - \sigma_Y
$$

where Equivalent forms; $\sigma_{eq}=\sqrt{3J_2}$

**Equivalent stress and equivalent plastic strain:**

$$
\sigma_{eq} = \sqrt{\tfrac{3}{2}\,\mathbf{s}\colon\mathbf{s}} = \sqrt{3 J_2},\qquad
\bar\varepsilon^p = \int_0^t \sqrt{\tfrac{2}{3}\,\dot{\boldsymbol{\varepsilon}}^p\colon\dot{\boldsymbol{\varepsilon}}^p}\,d\tau
$$

where Both reduce to $\sigma_{11}$ and $\varepsilon^p_{11}$ in uniaxial tension; the factors $\sqrt{3/2},\sqrt{2/3}$ ensure consistency with uniaxial yield strength

**Flow direction (associated flow):**

$$
\mathbf{N} = \frac{\partial f}{\partial \boldsymbol{\sigma}}
          = \sqrt{\tfrac{3}{2}}\,\frac{\mathbf{s}}{\|\mathbf{s}\|}
          = \frac{3}{2\,\sigma_{eq}}\,\mathbf{s}
$$

where $\|\mathbf{s}\|=\sqrt{\mathbf{s}\colon\mathbf{s}}=\sqrt{2J_2}$; equivalent forms

**Plastic flow rule:**

$$
\dot{\boldsymbol{\varepsilon}}^p = \dot\gamma\,\mathbf{N},\qquad
\dot{\bar\varepsilon}^p = \dot\gamma
$$

where Flow direction $\mathbf{N}$ deviatoric $\Rightarrow$ $\mathrm{tr}\,\dot{\boldsymbol{\varepsilon}}^p=0$ (plastic incompressibility)

**Karush-Kuhn-Tucker conditions:**

$$
\dot\gamma\ge 0,\qquad f\le 0,\qquad \dot\gamma\,f = 0
$$

where Either elastic ($\dot\gamma=0$, $f<0$) or plastic ($\dot\gamma>0$, $f=0$)

**Consistency during plastic loading:**

$$
\dot f = \mathbf{N}\colon\dot{\boldsymbol{\sigma}} - H\,\dot\gamma = 0
$$

where $H=d\sigma_Y/d\bar\varepsilon^p$ isotropic hardening modulus; gives the consistency condition for $\dot\gamma$

**Closed-form radial return for J2:**

$$
\Delta\gamma\,\text{solves}\,\sqrt{3 J_2^{\mathrm{trial}}} - 3\mu\,\Delta\gamma - \sigma_Y(\bar\varepsilon^p_n+\Delta\gamma) = 0,\qquad
\mathbf{s}_{n+1} = \frac{\sigma_Y(\bar\varepsilon^p_{n+1})}{\sqrt{3 J_2^{\mathrm{trial}}}}\,\mathbf{s}^{\mathrm{trial}}
$$

where Single scalar nonlinear equation in $\Delta\gamma$; linear hardening gives closed form $\Delta\gamma=(\sqrt{3J_2^{\mathrm{trial}}}-\sigma_Y(\bar\varepsilon^p_n))/(3\mu+H)$

**Algorithmic consistent tangent (J2):**

$$
\mathbb{C}^{\mathrm{alg}}_{ijkl}
= \kappa\,\delta_{ij}\delta_{kl}
+ 2\mu\,\theta\,\!\left(\mathbb{I}^{\mathrm{sym}}_{ijkl} - \tfrac{1}{3}\delta_{ij}\delta_{kl}\right)
- 2\mu\,\bar\theta\,\hat n_{ij}\hat n_{kl}
$$

where $\theta=1-2\mu\Delta\gamma/\|\mathbf{s}^{\mathrm{trial}}\|$, $\bar\theta=1/(1+H/(3\mu))-(1-\theta)$, $\hat{\mathbf{n}}=\mathbf{s}^{\mathrm{trial}}/\|\mathbf{s}^{\mathrm{trial}}\|$

**Plastic incompressibility:**

$$
\mathrm{tr}\,\dot{\boldsymbol{\varepsilon}}^p = 0\;\Rightarrow\;
\det\,\mathbf{F}^p = 1\,\text{(finite strain)},\;\;
\mathrm{tr}\,\boldsymbol{\varepsilon}^p_n = 0\,\text{(small strain)}
$$

where Automatic consequence of associated J2 flow

**Continuum tangent (NOT for use in implicit Newton):**

$$
\mathbb{C}^{ep}_{ijkl} = \mathbb{C}^e_{ijkl}
- \frac{(\mathbb{C}^e\colon\mathbf{N})_{ij}\,(\mathbf{N}\colon\mathbb{C}^e)_{kl}}{\mathbf{N}\colon\mathbb{C}^e\colon\mathbf{N} + H}
$$

where Mistakenly equating $\mathbb{C}^{ep}$ with $\mathbb{C}^{\mathrm{alg}}$ is the most common Newton-convergence pitfall

**Notation:**

- $J_2$ — Second deviatoric invariant, $\tfrac12\mathbf{s}\colon\mathbf{s}$
- $\sigma_{eq}$ — von Mises equivalent stress, $\sqrt{3J_2}$
- $\mathbf{s}$ — Stress deviator
- $\sigma_Y(\bar\varepsilon^p)$ — Yield strength as function of accumulated plastic strain
- $\bar\varepsilon^p$ — Equivalent plastic strain
- $H$ — Isotropic hardening modulus, $H=d\sigma_Y/d\bar\varepsilon^p$
- $\mathbf{N}$ — Flow direction $\partial f/\partial \boldsymbol{\sigma}$
- $\dot\gamma,\Delta\gamma$ — Plastic multiplier (rate / increment)
- $\mathbb{C}^{\mathrm{alg}}$ — Algorithmically consistent tangent
- $\theta,\bar\theta$ — Coefficients in the algorithmic tangent (Souza Neto et al.)
- $\hat{\mathbf{n}}$ — Unit deviator direction $\mathbf{s}^{\mathrm{trial}}/\|\mathbf{s}^{\mathrm{trial}}\|$


## 3. Algorithmic Implementation
**Algorithm: Closed-Form Small-Strain J2 Radial Return (Linear Hardening)**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{s}^{\mathrm{trial}},\,p^{\mathrm{trial}},\,\bar\varepsilon^p_n,\,\mu,\kappa,\,\sigma_Y(\bar\varepsilon^p)=\sigma_{Y0}+H\bar\varepsilon^p$
\State $\sqrt{3J_2^{\mathrm{trial}}} \gets \sqrt{\tfrac{3}{2}\,\mathbf{s}^{\mathrm{trial}}\colon\mathbf{s}^{\mathrm{trial}}}$
\State $f^{\mathrm{trial}} \gets \sqrt{3J_2^{\mathrm{trial}}} - (\sigma_{Y0} + H\,\bar\varepsilon^p_n)$
\If{$f^{\mathrm{trial}} \le 0$}
\State $\Delta\gamma \gets 0,\,\boldsymbol{\sigma}_{n+1} \gets \mathbf{s}^{\mathrm{trial}} - p^{\mathrm{trial}}\mathbf{I}$
\Return $\boldsymbol{\sigma}_{n+1},\bar\varepsilon^p_n,\mathbb{C}^{\mathrm{alg}}=\mathbb{C}^e$
\EndIf
\State $\Delta\gamma \gets f^{\mathrm{trial}} / (3\mu + H) \;\text{(closed-form for linear hardening)}$
\State $\hat{\mathbf{n}} \gets \mathbf{s}^{\mathrm{trial}} / \|\mathbf{s}^{\mathrm{trial}}\|$
\State $\mathbf{s}_{n+1} \gets \mathbf{s}^{\mathrm{trial}} - 2\mu\,\Delta\gamma\,\sqrt{\tfrac{3}{2}}\,\hat{\mathbf{n}}$
\State $\boldsymbol{\sigma}_{n+1} \gets -p^{\mathrm{trial}}\,\mathbf{I} + \mathbf{s}_{n+1}$
\State $\bar\varepsilon^p_{n+1} \gets \bar\varepsilon^p_n + \Delta\gamma$
\State $\boldsymbol{\varepsilon}^p_{n+1} \gets \boldsymbol{\varepsilon}^p_n + \Delta\gamma\,\sqrt{\tfrac{3}{2}}\,\hat{\mathbf{n}}$
\Return $\boldsymbol{\sigma}_{n+1},\bar\varepsilon^p_{n+1},\boldsymbol{\varepsilon}^p_{n+1},\mathbb{C}^{\mathrm{alg}}$
\end{algorithmic}
$$

**Taichi Mapping:**
Closed form for linear hardening: NO local Newton needed. Per-Gauss-point cost: ~30 FMAs + 1 sqrt + 1 division. For nonlinear hardening ($\sigma_Y(\bar\varepsilon^p)$ tabulated / power-law / Voce) replace the closed-form $\Delta\gamma$ by a 1D Newton on $g(\Delta\gamma)=\sqrt{3J_2^{\mathrm{trial}}}-3\mu\Delta\gamma-\sigma_Y(\bar\varepsilon^p_n+\Delta\gamma)=0$ — typically 3-5 iterations to $\tau=10^{-10}\sigma_Y$. Cache $\hat{\mathbf{n}}$ since it equals the post-update flow direction (radial return).


**Algorithm: J2 Algorithmic Consistent Tangent**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{s}^{\mathrm{trial}},\Delta\gamma,\mu,\kappa,H$
\State $\hat{\mathbf{n}} \gets \mathbf{s}^{\mathrm{trial}}/\|\mathbf{s}^{\mathrm{trial}}\|$
\State $\theta \gets 1 - 2\mu\Delta\gamma/\|\mathbf{s}^{\mathrm{trial}}\|$
\State $\bar\theta \gets 1/(1+H/(3\mu)) - (1-\theta)$
\For{$i,j,k,l = 1,2,3$}
\State $\mathbb{C}^{\mathrm{alg}}_{ijkl} \gets \kappa\,\delta_{ij}\delta_{kl} + 2\mu\,\theta\,(\mathbb{I}^{\mathrm{sym}}_{ijkl}-\tfrac{1}{3}\delta_{ij}\delta_{kl}) - 2\mu\,\bar\theta\,\hat n_{ij}\hat n_{kl}$
\EndFor
\Return $\mathbb{C}^{\mathrm{alg}}$
\end{algorithmic}
$$

**Taichi Mapping:**
Three contributions: bulk ($\kappa\,\mathbf{I}\otimes\mathbf{I}$), shear-symmetric ($2\mu\theta\,\mathbb{I}^{\mathrm{sym},\mathrm{dev}}$), correction ($-2\mu\bar\theta\,\hat{\mathbf{n}}\otimes\hat{\mathbf{n}}$). Store directly in Mandel form ($6\times 6$); the structure is symmetric major / minor by construction. The factor $\theta<1$ on the deviatoric block reflects shear softening due to plastic flow; $\bar\theta$ encodes the projection onto the flow direction.


**Algorithm: Nonlinear Hardening Local Newton**

$$
\begin{algorithmic}
\State $\text{input} \colon \sqrt{3J_2^{\mathrm{trial}}},\bar\varepsilon^p_n,\mu,\sigma_Y(\bar\varepsilon^p)\,\text{(possibly nonlinear)}$
\State $\Delta\gamma^0 \gets f^{\mathrm{trial}}/(3\mu+H_0) \;\text{(linear-hardening initial guess)}$
\For{$k = 0,1,\ldots,K-1$}
\State $\bar\varepsilon^p \gets \bar\varepsilon^p_n + \Delta\gamma^k$
\State $g \gets \sqrt{3J_2^{\mathrm{trial}}} - 3\mu\Delta\gamma^k - \sigma_Y(\bar\varepsilon^p)$
\State $g' \gets -3\mu - H(\bar\varepsilon^p)$
\State $\Delta\gamma^{k+1} \gets \Delta\gamma^k - g/g'$
\If{$|g| < \tau\,\sigma_{Y0}$}
\State $\textbf{break}$
\EndIf
\EndFor
\Return $\Delta\gamma$
\end{algorithmic}
$$

**Taichi Mapping:**
1D Newton on $\Delta\gamma$ — converges in 3-5 iterations to $\tau=10^{-10}\sigma_{Y0}$. The derivative $g'(\Delta\gamma)=-3\mu-H(\bar\varepsilon^p)$ involves the local hardening modulus $H$ at the current $\bar\varepsilon^p$. For tabulated $\sigma_Y$ use linear interpolation between tabulated points (and constant-$H$ within each interval); for power-law $\sigma_Y=\sigma_{Y0}+K(\bar\varepsilon^p)^n$, $H=Kn(\bar\varepsilon^p)^{n-1}$.



## 4. Known Pitfalls
**Confusion between $\sqrt{3J_2}$ and $\sqrt{2J_2}$:** Different conventions exist: Mises equivalent stress $\sigma_{eq}=\sqrt{3J_2}$ (matches uniaxial $\sigma_{11}$) vs effective shear stress $\tau_{eq}=\sqrt{J_2}$ (Tresca / max-shear convention). The factor $\sqrt{3}$ vs $\sqrt{2}$ determines whether yield strength is reported in tension or shear. Document the convention and verify on a uniaxial test ($\sigma_{eq}$ should equal $\sigma_{11}$) and a pure-shear test ($\sigma_{eq}=\sqrt{3}\tau$).


**Wrong factor in flow rule normalisation:** Associated flow gives $\mathbf{N}=\sqrt{3/2}\,\mathbf{s}/\|\mathbf{s}\|$, not $\mathbf{s}/\|\mathbf{s}\|$ (which would be the unit deviator direction without the $\sqrt{3/2}$ factor). Forgetting the factor halves the plastic strain rate; the simulation appears to "harden too quickly" because $\bar\varepsilon^p$ accumulates more slowly than expected.


**Plastic incompressibility drift under explicit integration:** Forward-Euler $\boldsymbol{\varepsilon}^p_{n+1}=\boldsymbol{\varepsilon}^p_n+\Delta t\,\dot\gamma\mathbf{N}_n$ accumulates round-off in $\mathrm{tr}\,\boldsymbol{\varepsilon}^p$ that drifts away from zero. Detect $|\mathrm{tr}\,\boldsymbol{\varepsilon}^p|>10^{-10}$ and project back to deviatoric. Implicit (radial return) is exact in plastic incompressibility because $\mathbf{N}$ is recomputed from the deviator at $n+1$.


**Applying J2 to pressure-sensitive materials:** J2 is correct for non-porous metals but wrong for soils, concrete, foams, geomaterials where yielding depends on hydrostatic pressure (friction angle, dilatancy). Use Drucker-Prager or Mohr-Coulomb (`plasticity-drucker-prager`) or porous-plasticity GTN for those. Mistakenly using J2 on rock predicts no shear band and no failure under triaxial compression.


**Wrong sign on consistent-tangent denominator:** Continuum tangent $\mathbb{C}^{ep}=\mathbb{C}^e-(\mathbb{C}^e\colon\mathbf{N})\otimes(\mathbf{N}\colon\mathbb{C}^e)/(\mathbf{N}\colon\mathbb{C}^e\colon\mathbf{N}+H)$. For softening ($H<0$) the denominator can vanish (localisation onset) — the tangent diverges. For purely-plastic ($H=0$) it is finite. Check the denominator sign before dividing; near-zero indicates onset of localisation / instability.


**Continuum vs algorithmic tangent:** The continuum tangent $\mathbb{C}^{ep}$ above relates infinitesimal stress / strain rates; the algorithmic tangent $\mathbb{C}^{\mathrm{alg}}$ (with $\theta,\bar\theta$ corrections) relates FINITE step increments. They differ by the implicit dependence of $\Delta\gamma$ on $\Delta\boldsymbol{\varepsilon}$. Using $\mathbb{C}^{ep}$ in implicit Newton degrades convergence to linear; always use $\mathbb{C}^{\mathrm{alg}}$.


**Negative $\Delta\gamma$ from poor initial guess:** Local Newton on $\Delta\gamma$ can briefly produce $\Delta\gamma^k<0$ if the initial guess overshoots. Project to $\Delta\gamma^{k+1}=\max(\Delta\gamma^{k+1}, 0)$ — KKT requires $\Delta\gamma\ge 0$. Without the projection the algorithm can converge to a non-physical negative root.


**Hardening evaluation at wrong state:** $\sigma_Y(\bar\varepsilon^p_{n+1})$ MUST use the END-of-step plastic strain $\bar\varepsilon^p_{n+1}=\bar\varepsilon^p_n+\Delta\gamma$, NOT $\bar\varepsilon^p_n$. A common bug uses $\sigma_Y(\bar\varepsilon^p_n)$ in the residual $g$, which produces explicit Euler hardening instead of implicit. The residual then misses the hardening contribution and the simulation predicts wrong yield evolution.


## 5. References
- von Mises (1913) — Mechanik der festen Korper im plastisch deformablen Zustand (original formulation of $J_2$ yield criterion)
- Simo & Hughes (1998) — Computational Inelasticity, Ch. 2 (radial return, algorithmic consistent tangent for J2)
- Souza Neto, Peric, Owen (2008) — Computational Methods for Plasticity (closed-form J2 algorithmic tangent with $\theta, \bar\theta$)
- Dunne & Petrinic (2005) — Introduction to Computational Plasticity, Ch. 5 (radial return method, Figs 5.1a/b explicit vs implicit)

