---
id: solver-gpu-data-layout
title: GPU Data Layout & Performance Patterns
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- GPU
- data-layout
- SoA
- AoS
- coalescing
- atomics
- taichi
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-matrix-free-gpu
  type: requires
  weight: 1.0
- to: precond-gpu-alternatives
  type: feeds-into
  weight: 0.5
- to: precond-amg-gpu
  type: refines
  weight: 0.7
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# GPU Data Layout & Performance Patterns

## Summary

GPU data layout and memory access patterns determine performance in finite element simulations, as sparse matrix assembly and Krylov solver sweeps are memory-bandwidth bound. To maximize throughput on heterogeneous GPU hardware, finite element codes eliminate CPU-GPU data transfers using direct device memory array pointers (such as PETSc MatSeqAIJCUSPARSEGetArray), avoid thread branch divergence in sparse matrix assembly using precomputed lookup tables or split-phase COO formats (MatSetValuesCOO), and optimize memory coalescing through rowwise assembly algorithms or matrix-free tensor contractions.

## 1. Core Concept

Finite element calculations on GPUs—including local element assembly, sparse matrix insertion, and iterative linear solves—are fundamentally memory-bandwidth bound. Traditional assembly algorithms that perform binary searches on the CPU or within GPU threads suffer from severe branch divergence (up to 90%) and thread stalls. Replacing binary searches with precomputed lookup tables (nonzero_locations) or split-phase Coordinate (COO) interfaces eliminates branch divergence and enables coalesced memory access. Furthermore, performing matrix assembly rowwise rather than cellwise groups memory updates by degree of freedom, reducing atomic write contention and L2 cache writeback traffic by up to 4x. In high-order discretizations, matrix-free partial assembly (fusing element restriction, basis evaluations, and quadrature point tensors into single GPU device kernels) bypasses sparse matrix allocation entirely, achieving high memory throughput on NVIDIA and AMD GPUs. Frameworks like Taichi (MeshTaichi) and JAX-FEM provide compiler-level GPU acceleration for parallel mesh operations and automatic differentiation.

## 2. Mathematical Formulation

**gpu-matrix-free-bandwidth-model**
$$
\text{Throughput} = \frac{\text{STREAM\_Bandwidth}}{\text{Bytes\_per\_DoF}}
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Section V.B, p. 5; Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3, p. 4_

**lookup-table-sparse-matrix-indexing**
$$
r = \text{nonzero\_locations}[l]
$$
_Source: Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.6, p. 5_

**atomic-global-matrix-assembly-update**
$$
A[r] \leftarrow A[r] + A_e[j, k]
$$
_Source: Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.5, p. 5_

**Notation:**
A represents global CSR sparse matrix values array on GPU device; A_e represents element stiffness/residual matrix; r represents destination CSR array offset; nonzero_locations represents precomputed lookup table array; STREAM_Bandwidth represents GPU memory bandwidth capacity.


## 3. Algorithmic Implementation

**lookup-table-gpu-global-assembly**
$$
\begin{algorithmic}
\State $\text{Precompute } \text{nonzero\_locations} \text{ lookup table mapping each element matrix entry } (j, k) \text{ to its global CSR array position } r$
\State $\text{Launch GPU CUDA kernel } \text{cuda\_global\_assembly} \text{ with grid-stride thread loops}$
\For{$i = \text{blockIdx.x} \times \text{blockDim.x} + \text{threadIdx.x} \text{ to } N_{\text{cells}} \text{ stride } \text{blockDim.x} \times \text{gridDim.x}$}
\State $\text{Compute element matrix } A_e \text{ via auto-generated } \text{tabulate\_tensor} \text{ in thread registers}$
\For{$j = 0 \text{ to } n_e - 1, \quad k = 0 \text{ to } n_e - 1$}
\State $r = \text{nonzero\_locations}[i \times n_e^2 + j \times n_e + k]$
\State $\text{atomicAdd}(\&A[r], A_e[j, k]) \quad \text{(direct device memory update without binary search)}$
\EndFor
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.6, pp. 5-6, Algorithm 5_

**rowwise-gpu-matrix-assembly**
$$
\begin{algorithmic}
\State $\text{Construct } \text{cells\_per\_dof} \text{ mapping to assign GPU threads rowwise to global matrix DOFs}$
\State $\text{Launch CUDA kernel } \text{cuda\_rowwise\_assembly} \text{ using warp-coalesced thread access}$
\For{$p = \text{blockIdx.x} \times \text{blockDim.x} + \text{threadIdx.x} \text{ to } \text{cells\_per\_dof\_ptr}[N_{\text{rows}}]$}
\State $\text{Compute element matrix } A_e \text{ and identify row match } j == \text{element\_matrix\_rows}[p]$
\State $l = ((p / \text{warpSize}) \times 4 + k) \times \text{warpSize} + p \pmod{\text{warpSize}}$
\State $r = \text{nonzero\_locations}[l]$
\State $\text{atomicAdd}(\&A[r], A_e[j, k]) \quad \text{(coalesced write reducing L2 cache memory traffic by 4x)}$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.7, p. 6, Algorithm 6_


## 4. Known Pitfalls

- **cpu-gpu-data-transfer-latency-penalty**: Transferring global stiffness matrices or solution vectors between CPU host memory and GPU device memory after assembly increases solution time by 3x to 5x, completely negating GPU compute acceleration. Assembly and linear solves must remain entirely on the GPU, using direct device array pointers (such as PETSc MatSeqAIJCUSPARSEGetArray). _(Source: Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.3, p. 4; Section 4.4, p. 8, Fig. 1)_
- **branch-divergence-in-binary-search**: Performing binary searches within GPU threads to locate column insertion points during sparse CSR matrix assembly causes severe thread branch divergence within warps (~90% divergence), stalling 95% of execution samples on memory dependencies. Replacing binary searches with a precomputed lookup table eliminates divergence and restores memory throughput. _(Source: Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.6, p. 5)_
- **atomic-contention-in-global-assembly**: Uncoordinated atomic updates (atomicAdd) from multiple concurrent GPU threads writing to shared global matrix DOFs cause atomic write contention and irregular cache writes. Switching from cellwise to rowwise assembly improves write locality, reducing L2 cache writeback traffic from >2 GiB to ~500 MiB on NVIDIA V100 GPUs. _(Source: Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.7, p. 6; Section 4.2, p. 7)_

## References

- Trotter et al_2023_Targeting performance and user-friendliness.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf
- Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf
- Xue et al_2023_JAX-FEM.pdf
