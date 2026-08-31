# Gotchas (Taichi GPU) — Bugs, slowdowns, and other hobbies humans choose

This document is the “things that will waste your day” list for Taichi on GPU,
especially for FEM / FD / spectral-ish / MPM style kernels.

Each gotcha includes:
- what happens
- why it happens
- what to do instead

---

## 1) Benchmarking lies (JIT + warmup)

### Gotcha: first run is slow
**Symptom:** “My kernel takes 300 ms” (first call), then 2 ms afterwards.  
**Why:** JIT compilation and runtime setup on first execution.  
**Do instead:**
- run warmup steps (5–50) before timing
- benchmark steady state, not first call

---

## 2) Death by a thousand kernel launches

### Gotcha: Python loops driving many tiny kernels
**Symptom:** GPU utilization low, step time dominated by overhead.  
**Why:** Kernel launch overhead + sync points + fragmented work.  
**Do instead:**
- fuse trivial passes (especially “read A, write B” micro-kernels)
- keep the main step loop kernel-heavy, Python-light
- batch operations that naturally belong together

---

## 3) Hidden synchronizations (host reads, debug prints, “just checking”)

### Gotcha: reading a field in Python inside the hot loop
**Symptom:** performance tanks after you add a single diagnostic.  
**Why:** Host access forces device sync and stalls the pipeline.  
**Do instead:**
- only read diagnostics every N steps
- keep checks in kernels when possible (write flags, counters)
- do not print from kernels in production runs

### Gotcha: printing inside kernels
**Symptom:** everything becomes 100x slower and your terminal becomes a landfill.  
**Why:** printf-style debugging is basically a denial-of-service attack on throughput.  
**Do instead:**
- write to a debug field for a small subset of indices
- run small problem sizes with debug mode only

---

## 4) Atomics: correctness tax + performance tax

### Gotcha: scatter-add without atomics
**Symptom:** results change run-to-run; conservation breaks; chaos.  
**Why:** multiple threads write the same location (data race).  
**Do instead:**
- use atomic adds for true scatter patterns (P2G, assembly)
- or restructure algorithm to reduce write conflicts (staging, coloring, two-pass)

### Gotcha: assuming atomic sums are deterministic
**Symptom:** tiny numeric differences across runs/hardware.  
**Why:** floating-point atomic accumulation order is not fixed.  
**Do instead:**
- validate with tolerances and invariants, not bitwise equality
- if you truly need determinism, change the reduction strategy (often slower)

---

## 5) `ti.loop_config(...)` scope surprises

### Gotcha: setting block_dim but it affects a different loop
**Symptom:** tuning seems to do nothing or affects the wrong kernel section.  
**Why:** `ti.loop_config(...)` applies to the *next* parallel loop.  
**Do instead:**
- place `ti.loop_config(block_dim=...)` immediately before the hotspot loop
- tune only after profiling

---

## 6) `ti.static` misuse (compile-time explosion)

### Gotcha: `ti.static` unrolling big loops
**Symptom:** compilation takes forever, memory spikes, or the compiler hates you.  
**Why:** you asked the compiler to generate a gigantic unrolled kernel.  
**Do instead:**
- use `ti.static` only for small fixed loops (3, 4, 8, 27 taps)
- keep large loops runtime, not compile-time

---

## 7) Silent dtype disasters (f64 everywhere, int truncation, mixed types)

### Gotcha: accidentally promoting to f64
**Symptom:** performance drops; memory bandwidth doubles; register pressure rises.  
**Why:** one f64 constant or field can pull expressions into f64.  
**Do instead:**
- define constants with explicit dtype where needed (e.g., `ti.cast(1.0, ti.f32)`)
- keep storage f32 unless you have a proven stability issue
- be explicit about dtype conversions at boundaries

### Gotcha: integer division or truncation in indexing math
**Symptom:** wrong base node, wrong cell id, weird off-by-one artifacts.  
**Why:** integer ops truncate; mixed int/float math can bite.  
**Do instead:**
- keep indexing math explicit (`ti.floor`, casts)
- compute base indices carefully in MPM/PIC/FLIP style code

---

## 8) Layout mismatch: your loop order fights memory

### Gotcha: non-coalesced access in the hot loop
**Symptom:** kernel is “simple” but bandwidth is awful.  
**Why:** adjacent threads access scattered addresses.  
**Do instead:**
- align loop order with memory layout
- tile dense grids for locality if needed
- keep access patterns regular (especially in stencils)

---

## 9) Sparse SNodes: overhead when sparsity is fake

### Gotcha: using pointer/bitmasked when data is basically dense
**Symptom:** slower than dense fields, plus more complexity.  
**Why:** sparse metadata and activation checks add overhead.  
**Do instead:**
- use sparse only when you have real sparsity (inactive regions dominate)
- otherwise use dense/tiled dense fields and optimize kernels

### Gotcha: forgetting to activate sparse regions
**Symptom:** kernels “do nothing” or miss updates; arrays look empty.  
**Why:** sparse nodes need allocation/activation for regions you touch.  
**Do instead:**
- ensure activation strategy is correct (often via writes/explicit activation patterns)
- validate active region coverage with debug counters

---

## 10) Dynamic SNodes: variable-length lists are not free

### Gotcha: using `dynamic` for everything
**Symptom:** unpredictable performance, high overhead, difficult debugging.  
**Why:** dynamic lists add indirection and bookkeeping.  
**Do instead:**
- use dynamic only when you truly need variable occupancy per cell
- otherwise use fixed-size dense arrays and a separate “count” field

---

## 11) `ti.ndarray` vs `ti.field`: choosing the wrong container

### Gotcha: expecting field-like optimizations on ndarray
**Symptom:** reductions slower than expected; missing conveniences.  
**Why:** some Taichi optimizations/features target SNode-backed fields.  
**Do instead:**
- use `ti.field` for core simulation state and layout control
- use `ti.ndarray` mainly for dense interop buffers and contiguous arrays

---

## 12) “Small matrices everywhere” doesn’t scale

### Gotcha: building large matrices out of `ti.Matrix`
**Symptom:** compile times explode, kernels bloat, performance tanks.  
**Why:** `ti.Matrix` is meant for small fixed matrices (think 2x2, 3x3, 6x6).  
**Do instead:**
- keep tensors small (F, stress, strain) as matrices
- store large operators/vectors as scalar fields / arrays

---

## 13) Branch divergence: the boundary-condition trap

### Gotcha: branch-heavy kernels
**Symptom:** GPU runs slow despite low arithmetic.  
**Why:** warps diverge and serialize paths.  
**Do instead:**
- separate interior and boundary kernels
- replace branches with masked operations only when it actually helps

---

## 14) Randomness and reproducibility

### Gotcha: “Why isn’t it reproducible?”
**Symptom:** different results across runs for stochastic sampling or particle shuffling.  
**Why:** parallel execution order and floating-point non-associativity.  
**Do instead:**
- treat reproducibility as a feature you must design for
- use deterministic seeds and deterministic algorithms if required
- validate statistically where exact reproducibility isn’t realistic

---

## 15) Validation gotchas: “it runs” is not “it’s correct”

### Gotcha: no invariants, no sanity checks
**Symptom:** the sim looks fine until it suddenly isn’t.  
**Do instead:** build cheap invariants:
- MPM: mass conservation (grid mass), NaN scans, reasonable J bounds
- FEM: symmetry checks (where applicable), residual decreases in solvers
- FD: CFL stability checks, max/min bounds for stable PDEs

---

## 16) Quick triage checklist (when it’s slow or wrong)
When something breaks:
1. Warmup done? (JIT)
2. Too many kernels? (launch overhead)
3. Host reads/prints causing sync?
4. Atomics/races in scatter paths?
5. Divergence from boundary logic?
6. Dtype drift to f64?
7. Layout/loop order mismatch?
8. Sparse overhead without sparsity?
9. `ti.static` unrolling too much?

Fix the first one that applies. Repeat until simulation is boring again.