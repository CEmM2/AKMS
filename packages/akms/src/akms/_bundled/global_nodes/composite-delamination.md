---
id: composite-delamination
title: Delamination & Cohesive Zone Models (CZM)
domain: computational-mechanics
subdomain: composites
tags:
- composites
- delamination
- CZM
- cohesive-zone
- BK-criterion
- interface-elements
status: established
confidence: 0.9
source: hybrid
edges:
- to: composite-laminate-theory
  type: refines
  weight: 0.7
- to: composite-progressive-damage
  type: refines
  weight: 0.7
- to: pf-cohesive-zone
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Delamination & Cohesive Zone Models (CZM)

## Summary

Cohesive zone modeling (CZM) provides a continuous non-linear damage mechanics framework for simulating delamination and fracture process zones in composite laminates without requiring pre-existing crack-tip stress singularity assumptions. Material constitutive behavior is split into linear elasticity for bulk sub-domains and non-linear traction-separation relations along cohesive interfaces. Mode I delamination is governed by intrinsic traction-separation laws (TSL)—including exponential, bilinear, and trapezoidal models—parameterized by cohesive strength, critical separation displacement, and fracture energy. Finite element implementation utilizes zero-thickness cohesive zone elements (CZE) connecting adjacent bulk elements, formulating tangent stiffness matrices and nodal force vectors via global-to-local kinematic transformations. Experimental extraction of Mode I TSL from Double Cantilever Beam (DCB) testing utilizes the effective crack method and beam theory to derive closed-form crack-tip separation equations and direct differentiation of strain energy release rate curves. Furthermore, cohesive interface elements are integrated with phase-field continuum models to capture complex multi-scale failure interactions, such as delamination migration between plies.

## 1. Core Concept

Cohesive zone models embed non-linear material degradation along interface surfaces while maintaining linear elastic behavior in surrounding bulk sub-domains. In Mode I cleavage or delamination, the closing traction across the fracture process zone is dictated by a traction-separation law relating normal traction T (or sigma_c) to displacement jump delta (or delta_c). Key parameters defining the TSL include cohesive strength (peak stress sigma_cr or sigma_cu) and cohesive fracture energy G_c (or G_Ic), corresponding to the area under the traction-separation curve. Zero-thickness cohesive elements employ kinematic shape functions and localization matrices to interpolate nodal displacement jumps to Gauss integration points, transforming global degrees of freedom to element local coordinates for evaluating the tangent stiffness matrix and cohesive force vector.

For experimental characterization, the modified direct method extracts Mode I TSL from DCB specimens without requiring non-linear finite element optimization loops. Combining corrected beam theory with the effective crack length concept, compliance measurements yield effective crack lengths that account for root rotation, shear deformation, and fracture process zone extension. A closed-form expression calculates crack-tip separation delta_c directly from applied load and specimen geometry, allowing Mode I strain energy release rate G_I to be differentiated with respect to delta_c to obtain tractions. Additionally, CZM is coupled with phase-field fracture frameworks by making cohesive toughness or separation limits dependent on local bulk phase-field damage variables, enabling objective modeling of delamination interacting with matrix cracking.

## 2. Mathematical Formulation

**Exponential Cohesive Traction-Separation Law**
$$
T(\delta) = \sigma_{cr} \left( \frac{\delta}{\delta_{cr}} \right) \exp\left(1 - \frac{\delta}{\delta_{cr}}\right), \quad G_c = \sigma_{cr} \delta_{cr} \exp(1)
$$
_Source: Alfano et al. - 2009 - Mode I fracture of adhesive joints using tailored cohesive zone models.pdf, Section 2.1, Eq. 4_

**Bilinear Cohesive Traction-Separation Law**
$$
T(\delta) = \begin{cases} \gamma_1 \delta, & 0 \le \delta \le \Delta_{cr} \\ \sigma_{cr} \frac{\Delta_f - \delta}{\Delta_f - \Delta_{cr}}, & \Delta_{cr} < \delta \le \Delta_f \\ 0, & \delta > \Delta_f \end{cases}, \quad G_c = \frac{1}{2} \sigma_{cr} \Delta_f
$$
_Source: Alfano et al. - 2009 - Mode I fracture of adhesive joints using tailored cohesive zone models.pdf, Section 2.2, Eqs. 5-6_

**Trapezoidal Cohesive Traction-Separation Law**
$$
T(\delta) = \begin{cases} \gamma_1 \delta, & 0 \le \delta \le \Delta_{cr} = \lambda_1 \Delta_f \\ \sigma_{cr}, & \Delta_{cr} < \delta \le \Delta_2 = \lambda_2 \Delta_f \\ \sigma_{cr} \frac{\Delta_f - \delta}{\Delta_f - \Delta_2}, & \Delta_2 < \delta \le \Delta_f \\ 0, & \delta > \Delta_f \end{cases}, \quad G_c = \frac{1}{2} \sigma_{cr} \Delta_f (1 + \lambda_2 - \gamma_1)
$$
_Source: Alfano et al. - 2009 - Mode I fracture of adhesive joints using tailored cohesive zone models.pdf, Section 2.3, Eqs. 7-8_

**4-Node Cohesive Zone Element Kinematics and Stiffness Matrix**
$$
K = w \int_c B^T \left(\frac{\partial T}{\partial \delta}\right) B \, dc, \quad F_{Coh} = w \int_c B^T T \, dc
$$
_Source: Alfano et al. - 2009 - Mode I fracture of adhesive joints using tailored cohesive zone models.pdf, Section 2.4, Eqs. 12, 17, 19_

**Modified Direct Method DCB Crack-Tip Separation**
$$
\delta_c = \frac{12 P a_e}{E_1 b h} \left[ \left( \frac{a_e - a}{h} \right)^2 - \frac{E_1}{10 G_{13}} \right]
$$
_Source: De Morais - 2024 - A new modified direct method for determining the mode I delamination traction-separation law.pdf, Section 2.1, Eqs. 4, 10_

**Phase-Field Coupling with Cohesive Interface Degradation**
$$
D_{CE,eff} = \max\left\{D_{CE}, \, D_{d,up}, \, D_{d,low}\right\}, \quad D_d = 1 - \omega(d)
$$
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.4, Eqs. 110-111_

**Notation:**
- T: Normal opening traction across cohesive interface
- \delta: Relative displacement jump (separation) across crack faces
- \sigma_{cr}: Critical peak stress / cohesive strength of the material
- \delta_{cr}: Displacement jump at peak stress
- \Delta_f: Final opening displacement jump at complete separation (zero traction)
- G_c: Critical strain energy release rate / cohesive fracture energy
- \gamma_1: Initial stiffness parameter of the cohesive traction-separation model
- \lambda_2: Shape parameter controlling plateau length in trapezoidal CZM
- u_g: Global nodal displacement vector for a 4-node cohesive element
- L: Operator localization matrix filtering relative nodal displacement pairs
- N(\xi): Shape function matrix evaluated at natural coordinate \xi
- R: Orthogonal coordinate transformation matrix from global to element local frame
- B: Strain-displacement matrix mapping global displacements to local jumps (B = R N L)
- P: Applied mechanical load in Double Cantilever Beam (DCB) test
- a: Initial crack length
- a_e: Effective crack length incorporating root rotation and process zone length
- C: Specimen compliance (C = \delta / P)
- b: Specimen width
- h: Thickness of individual DCB specimen leg
- E_1: Longitudinal elastic Young's modulus of composite substrate
- G_{13}: Through-thickness shear modulus of composite substrate
- \delta_c: Crack-tip opening displacement jump in DCB specimen
- G_I: Mode I strain energy release rate
- d: Phase-field damage variable ranging from 0 (intact) to 1 (fully broken)
- D_{CE,eff}: Effective cohesive element damage index coupled with bulk phase field


## 3. Algorithmic Implementation

**ComputeCohesiveElementResStiff**
$$
\begin{algorithmic}
\State $F_{Coh} = \text{zeros}(8, 1), \quad K_{elem} = \text{zeros}(8, 8)$
\State $\xi_{gauss} = \left[-\frac{1}{\sqrt{3}}, \frac{1}{\sqrt{3}}\right], \quad w_{gauss} = [1.0, 1.0]$
\State $L = \begin{bmatrix} 1 & 0 & 0 & 0 & 0 & 0 & -1 & 0 \\ 0 & 1 & 0 & 0 & 0 & 0 & 0 & -1 \\ 0 & 0 & 1 & 0 & -1 & 0 & 0 & 0 \\ 0 & 0 & 0 & 1 & 0 & -1 & 0 & 0 \end{bmatrix}$
\For{$i = 1 \text{ To } 2$}
\State $\xi = \xi_{gauss}[i]$
\State $N = \begin{bmatrix} \frac{1-\xi}{2} & 0 & \frac{1+\xi}{2} & 0 \\ 0 & \frac{1-\xi}{2} & 0 & \frac{1+\xi}{2} \end{bmatrix}$
\State $R = \text{ComputeLocalRotationMatrix}(X_{elem}, \xi)$
\State $B = R \cdot N \cdot L$
\State $\delta_{local} = B \cdot u_g$
\State $T_{local} = \text{ComputeCohesiveTraction}(\delta_{local}, \sigma_{cr}, G_c, \gamma_1)$
\State $D_{local} = \text{ComputeCohesiveJacobian}(\delta_{local}, \sigma_{cr}, G_c, \gamma_1)$
\State $dA = w \cdot \det(J(\xi)) \cdot w_{gauss}[i]$
\State $F_{Coh} = F_{Coh} + (B^T \cdot T_{local}) \cdot dA$
\State $K_{elem} = K_{elem} + (B^T \cdot D_{local} \cdot B) \cdot dA$
\EndFor
\Return $F_{Coh}, K_{elem}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Alfano et al. - 2009 - Mode I fracture of adhesive joints using tailored cohesive zone models.pdf, Section 2.4, Eqs. 9-19_

**ExtractDCBModeITSL**
$$
\begin{algorithmic}
\State $\text{tsl\_points} = []$
\State $n_{pts} = \text{Length}(load\_disp\_data)$
\For{$k = 1 \text{ To } n_{pts}$}
\State $P = load\_disp\_data[k].P, \quad \delta = load\_disp\_data[k].\delta, \quad C = \delta / P$
\State $a_e = \frac{h}{2} \left( \frac{E_1 b C}{2} \right)^{1/3}$
\State $G_I = \frac{12 P^2 a_e^2}{E_1 b^2 h^3}$
\State $\delta_c = \frac{12 P a_e}{E_1 b h} \left[ \left(\frac{a_e - a}{h}\right)^2 - \frac{E_1}{10 G_{13}} \right]$
\State $G_I\_list[k] = G_I, \quad \delta_c\_list[k] = \delta_c$
\EndFor
\For{$k = 1 \text{ To } n_{pts}$}
\State $\sigma_c = \text{ComputeNumericalDerivative}(G_I\_list, \delta_c\_list, k)$
\State $\text{tsl\_points.Append}((\delta_c\_list[k], G_I\_list[k], \sigma_c))$
\EndFor
\Return $\text{tsl\_points}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: De Morais - 2024 - A new modified direct method for determining the mode I delamination traction-separation law.pdf, Section 2.1, Eqs. 4, 10, 12_


## 4. Known Pitfalls

- **cohesive-mesh-dependency-and-element-size-limit**: Cohesive zone elements require fine spatial discretization along the fracture process zone to avoid severe mesh size dependency and inaccurate load-displacement predictions; standard numerical practice requires inserting at least 3 or more cohesive elements within the non-linear process zone. _(Source: Alfano et al. - 2009 - Mode I fracture of adhesive joints using tailored cohesive zone models.pdf, Section 3.1)_
- **trapezoidal-czm-damage-onset-overestimation**: Using a trapezoidal traction-separation law can overpredict structural load at damage onset compared to bilinear or exponential CZMs due to its altered interfacial stress profile, requiring a reduced cohesive strength parameter during calibration. _(Source: Alfano et al. - 2009 - Mode I fracture of adhesive joints using tailored cohesive zone models.pdf, Section 5)_
- **anticlastic-bending-edge-delamination-bias**: Anticlastic bending in double cantilever beam legs generates non-uniform strain energy release rate distributions across the specimen width, causing crack initiation in the interior rather than at the edges and rendering single-edge displacement measurements unrepresentative of width-averaged crack-tip separation. _(Source: De Morais - 2024 - A new modified direct method for determining the mode I delamination traction-separation law.pdf, Section 1)_
- **un-degraded-cohesive-element-delamination-migration-failure**: Failing to couple cohesive element damage degradation with adjacent bulk continuum phase-field damage variables prevents finite element models from capturing complex delamination migration phenomena across ply interfaces. _(Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.1.3, Fig. 19)_

## References

- Alfano et al. - 2009 - Mode I fracture of adhesive joints using tailored cohesive zone models.pdf
- De Morais - 2024 - A new modified direct method for determining the mode I delamination traction-separation law.pdf
- Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf
