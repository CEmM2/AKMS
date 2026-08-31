---
id: solver-matrix-free-gpu
title: 'Matrix-Free on GPU: Data Layout & Kernel Patterns'
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- matrix-free
- GPU
- taichi
- FEniCS
- shared-memory
- occupancy
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-matrix-free-operator
  type: refines
  weight: 0.7
- to: solver-gpu-data-layout
  type: requires
  weight: 1.0
- to: precond-gpu-alternatives
  type: feeds-into
  weight: 0.5
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Matrix-Free on GPU: Data Layout & Kernel Patterns

## Summary

Matrix-free operator evaluation on GPUs circumvents sparse matrix assembly and storage bottlenecks by evaluating element integrals on-the-fly via quadrature-point tensor contractions. In high-order finite element discretizations, matrix-free partial assembly reduces memory streaming footprint from ~750 bytes/DoF (for assembled CSR sparse matrices) down to ~140 bytes/DoF (for Q2 elements), overcoming the <2% peak FLOPS memory bandwidth saturation typical of assembled sparse matrix-vector products (SpMV). Modern libraries like libCEED and PETSc leverage JIT compilation (via NVRTC or hipRTC) to inline quadrature-point constitutive models into fused CUDA/HIP device kernels, maximizing parallel execution throughput on modern GPU hardware.

## 1. Core Concept

Finite element solvers relying on assembled compressed sparse row (CSR) matrices are strictly memory-bandwidth bound on modern GPU hardware. Storing double-precision matrix entries and integer column indices yields an arithmetic intensity of roughly 1 FLOP per 6 bytes, causing iterative Krylov solvers to saturate memory bandwidth at less than 2% of a GPU's peak floating-point performance. Matrix-free partial assembly restructures linear operator evaluation into a sequence of dense, localized tensor operations: global-to-local restriction (\mathcal{P}), element restriction (\mathcal{E}), basis evaluation at quadrature points (B), diagonal/block constitutive evaluation at quadrature points (D), and their transposed operations. By evaluating basis gradients and material constitutive laws on-the-fly at quadrature points, matrix-free representations reduce memory bandwidth demand by 5x or more compared to assembled SpMV. To eliminate overheads on modern architectures (NVIDIA V100/A100, AMD MI250X), runtime kernel generation (via NVRTC/hipRTC) inlines user-defined material constitutive functions (or automatic differentiation derivatives from tools like Enzyme) directly into CUDA/HIP device functions. Loop bounds and memory strides become compile-time constants, optimizing thread register allocation.

## 2. Mathematical Formulation

**matrix-free-operator-decomposition**
$$
A = \mathcal{P}^T \mathcal{E}^T B^T D \mathcal{E} \mathcal{P}
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section II.C, p. 2, Fig. 1_

**arithmetic-intensity-and-memory-footprint**
$$
\text{Memory Footprint}_{\text{MF}} \approx 140 \text{ B/DoF} \ll \text{Memory Footprint}_{\text{CSR}} \approx 750 \text{ B/DoF}
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section V.B, p. 5_

**Notation:**
A represents global matrix-free operator; \mathcal{P} represents global scatter/gather restriction operator; \mathcal{E} represents element restriction operator; B represents basis evaluation matrix at quadrature points; D represents quadrature point constitutive tensor matrix; v_T, v_L, v_E, q represent global, local, element, and quadrature point field vectors.


## 3. Algorithmic Implementation

**matrix-free-quadrature-operator-apply**
$$
\begin{algorithmic}
\State $v_L = \mathcal{P} v_T \quad \text{(gather global T-vector degrees of freedom to local sub-domain L-vector)}$
\State $v_E = \mathcal{E} v_L \quad \text{(extract element-level E-vector DOFs)}$
\State $q = B v_E \quad \text{(evaluate gradients/fields at element quadrature points Q-vector via tensor contractions)}$
\State $q' = D q \quad \text{(apply material constitutive tangent transformation at quadrature points)}$
\State $w_E = B^T q' \quad \text{(apply transposed basis gradients at quadrature points)}$
\State $w_L = \mathcal{E}^T w_E \quad \text{(accumulate element contributions into local sub-domain vector)}$
\State $w_T = \mathcal{P}^T w_L \quad \text{(scatter and sum local contributions into global T-vector)}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section II.C, p. 2, Fig. 1; Section V.B, p. 5_


## 4. Known Pitfalls

- **high-order-element-register-spilling-occupancy-drop**: Evaluating high-order finite elements (such as Q3 or higher) on GPUs in matrix-free kernels requires storing large basis transformation matrices and intermediate quadrature arrays in thread registers. High register consumption per thread causes register spilling to local GPU memory and reduces thread block occupancy, increasing latency on smaller problem sizes. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section II.C, p. 3; Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 4.5, p. 8)_
- **assembled-spmv-memory-bandwidth-saturation**: Iterative solvers relying on assembled sparse CSR matrix-vector products (SpMV) require streaming 12-16 bytes per nonzero (double precision value plus integer column index), yielding an arithmetic intensity of ~1 FLOP per 6 bytes. On GPU architectures with >10 FLOPs/byte streaming capacity, SpMV saturates memory bandwidth at less than 2% of peak FLOPS performance. Matrix-free partial assembly bypasses sparse matrix streaming, achieving up to 6x higher throughput. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section I, p. 1; Section V.B, p. 5)_
- **cpu-gpu-latency-synchronization-penalty**: Unnecessary host-device synchronization or CPU-GPU memory transfers during linear solver iterations or residual evaluations introduces severe latency penalties that dominate small-to-medium problem sizes, degrading parallel efficiency unless all operator evaluations and solver sweeps reside entirely in GPU device memory. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section V.A, p. 5; Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.3, p. 4)_

## References

- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf
- Trotter et al_2023_Targeting performance and user-friendliness.pdf
- Xue et al_2023_JAX-FEM.pdf
