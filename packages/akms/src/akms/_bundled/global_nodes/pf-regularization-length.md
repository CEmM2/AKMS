---
id: pf-regularization-length
title: 'Phase-Field Regularization Length: Physics vs Numerics'
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- length-scale
- calibration
- sigma-c
- mesh-resolution
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-at1-regularization
  type: refines
  weight: 0.7
- to: pf-at2-regularization
  type: refines
  weight: 0.7
- to: pf-cohesive-zone
  type: refines
  weight: 0.7
- to: pf-fem-implementation
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Phase-Field Regularization Length: Physics vs Numerics

## Summary

Theoretical formulation and calibration guidelines for the phase-field regularization length scale parameter (l_c, b, l_0). In classic Griffith brittle fracture formulations (e.g., Ambrosio-Tortorelli functional), the length scale b serves as a numerical regularization parameter that enables \Gamma-convergence to sharp crack surfaces as b \to 0. However, in standard AT1 and AT2 models, b acts simultaneously as a physical material length scale governing material tensile strength \sigma_c (where \sigma_c = \sqrt{3 E_0 G_f / (8 b)} for AT1 and \sigma_c \approx 0.325 \sqrt{E_0 G_f / b} for AT2). To resolve this duality and achieve true length-scale insensitivity in structural failure predictions, Wu's phase-field regularized cohesive zone model (PF-CZM) decouples b from tensile strength f_t via Irwin's characteristic length l_{ch} = E_0 G_f / f_t^2, provided b \le l_{ch}/3. Finite element spatial discretization requires mesh element sizes h \le l_c / 2 (or h \le b/5) inside active damage localization bands to resolve spatial phase-field gradients \nabla d without numerical locking or overestimating energy dissipation.

## 1. Core Concept

The phase-field regularization length scale (denoted variously as b, l, l_c, or l_0) governs the spatial spread of the diffusive crack surface density functional \Gamma_b(d) = \int_{\Omega} \frac{1}{c_{\alpha}} \left[ \frac{\alpha(d)}{b} + b |\nabla d|^2 \right] d\Omega. In standard AT1 and AT2 models, the length scale parameter is intrinsically tied to material failure strength \sigma_c. As a consequence, reducing b to model narrower crack bands artificially elevates the macroscopic peak load capacity, confusing numerical refinement with physical strengthening. Wu's unified phase-field damage theory resolves this limitation in PF-CZM by adopting a parabolic geometric crack function \alpha(d) = 2d - d^2 (c_{\alpha} = \pi) and calibrating the rational energetic degradation scaling parameter a_1 = \frac{4}{\pi} \frac{l_{ch}}{b} against Irwin's characteristic material length l_{ch} = E_0 G_f / f_t^2. So long as \\(b \le l_{ch}/3\\), the global load-displacement response and peak load become length-scale insensitive, allowing b to function purely as a numerical regularization parameter. Regardless of model choice, spatial finite element discretization must satisfy \\(h \le l_c/2\\) (or \\(h \le b/5\\)) inside active damage zones to avoid spatial locking and overestimating critical fracture energy.

## 2. Mathematical Formulation

**crack_surface_density_functional_general**
$$
\Gamma_b(d) = \int_{\Omega} \frac{1}{c_{\alpha}} \left[ \frac{\alpha(d)}{b} + b |\nabla d|^2 \right] d\Omega
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture_

**at1_at2_strength_length_scale_relation**
$$
\text{AT1: } \sigma_c = \sqrt{\frac{3 E_0 G_f}{8 b}}, \quad \text{AT2: } \sigma_c = \sqrt{\frac{27 E_0 G_f}{256 b}} \approx 0.325 \sqrt{\frac{E_0 G_f}{b}}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**pf_czm_decoupling_length_scale_bound**
$$
a_1 = \frac{4}{\pi} \frac{l_{ch}}{b}, \quad l_{ch} = \frac{E_0 G_f}{f_t^2}, \quad b \le \frac{1}{3} l_{ch}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**mesh_resolution_length_scale_bound**
$$
h \le \frac{1}{2} l_c \quad \text{or} \quad h \le \frac{1}{5} b
$$
_Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_

**Notation:**
d: scalar phase-field damage variable (d \in [1]); b, l, l_c: regularization length scale parameter; c_{\alpha}: geometric scaling constant; \alpha(d): geometric crack function; \sigma_c: critical threshold/failure stress; f_t: uniaxial tensile strength; E_0: Young's modulus; G_f: critical energy release rate; l_{ch}: Irwin's characteristic material length (l_{ch} = E_0 G_f / f_t^2); h: finite element mesh size.


## 3. Algorithmic Implementation

**length-scale-selection-and-mesh-calibration**
$$
\begin{algorithmic}
\State $Input material parameters: Young's modulus E_0, fracture energy G_f, tensile strength f_t, and target domain geometry \Omega.$
\If{$Model formulation == AT1 or AT2.$}
\State $Calculate regularization length scale directly from target material strength: b = \frac{3 E_0 G_f}{8 \sigma_c^2} \text{ (for AT1)} \text{ or } b = \frac{27 E_0 G_f}{256 \sigma_c^2} \text{ (for AT2)}.$
\ElsIf{$Model formulation == PF-CZM.$}
\State $Compute Irwin's characteristic length l_{ch} = \frac{E_0 G_f}{f_t^2} and select regularization length scale b \le \frac{1}{3} l_{ch} based on available computational mesh limits.$
\State $Compute PF-CZM degradation scaling parameter: a_1 = \frac{4}{\pi} \frac{l_{ch}}{b}.$
\EndIf
\State $Set maximum element size in expected localization zones to satisfy h \le l_c / 2 (for AT1/AT2) or h \le b / 5 (for PF-CZM).$
\State $Construct multi-field finite element mesh with local mesh refinement around notch tips or high stress concentration zones.$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture_


## 4. Known Pitfalls

- **at1-at2-length-scale-misinterpretation-as-pure-numerics**: In standard AT1 and AT2 phase-field models, treating length scale parameter b as an arbitrary numerical regularization parameter causes unphysical variation of material tensile strength \sigma_c \propto 1/\sqrt{b}. Arbitrarily reducing b to refine crack width artificially increases structural peak load. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_
- **coarse-mesh-locking-and-gc-overestimation**: Using element size h > l_c / 2 or h > b / 5 inside active damage localization bands fails to capture phase-field gradient \nabla d. This introduces severe spatial discretization locking, overestimating macroscopic peak load and critical fracture energy dissipation. _(Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus)_
- **pf-czm-length-scale-upper-bound-violation**: In cohesive phase-field models (PF-CZM), setting regularization length scale b > l_{ch}/3 violates the positive-definiteness condition of the damage sub-problem (-\partial Q / \partial d \ge 0). This causes loss of length-scale insensitivity and leads to solver convergence failure. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_

## References

- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Borden, M. J., Hughes, T. J. R., Landis, C. M., Anvari, A., and Lee, I. J. (2016). A phase-field formulation for fracture in ductile materials: Finite deformation balance law derivation, plastic degradation, and stress triaxiality effects. Computer Methods in Applied Mechanics and Engineering, 312, 130-166.
- Pham, K., Amor, H., Marigo, J.-J., and Maurini, C. (2011). Gradient damage models and their use to approximate brittle fracture. International Journal of Damage Mechanics, 20(4), 618-652.
- Dittmann, M., Aldakheel, F., Schulte, J., Schmidt, F., Krüger, M., Wriggers, P., and Hesch, C. (2020). Phase-field modeling of porous-ductile fracture in non-linear thermo-elasto-plastic solids. Computer Methods in Applied Mechanics and Engineering, 361, 112730.
