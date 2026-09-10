# Performance (Taichi on GPU) — Best Practices + Tuning Checklist

This doc is about making Taichi kernels go fast on GPU for simulation workloads (FEM / FD / spectral-ish / MPM), without sacrificing correctness or turning your code into unreadable wizardry.

## 0) The only performance workflow that works
1. **Warm up** (JIT cost is real).
2. **Measure** with the kernel profiler.
3. **Fix the top hotspot** (usually memory traffic or atomics).
4. Repeat until gains flatten.


---

## 1) Profiling and benchmarking without lying to yourself

### Warm up before timing
- The first time you call a kernel, Taichi may compile it (JIT).
- Always run a few warmup iterations before recording timings.

### Use Taichi’s kernel profiler
Enable it in `ti.init()`:
- `kernel_profiler=True`
Then print results after running steps.

Profiler modes include:
- `count`: aggregate stats (min/max/avg per kernel)
- `trace`: per-launch records, plus extra metrics depending on backend

### Keep profiling memory in mind
Kernel profiling can record a lot of per-launch information. If you loop forever with profiling enabled, you can inflate memory usage depending on mode and workload characteristics. 

### Benchmarking rules
- Fix: resolution, dt, number of steps, backend, precision.
- Don’t mix validation logging + IO into the timed region.
- Prefer steady-state “step loop” timing, not single-step timing (kernel launch overhead noise).

---

## 2) GPU fundamentals that actually matter in Taichi

### You’re usually memory-bound
Most simulation kernels are bandwidth-limited:
- Stencils (FD): load neighbors, store results.
- MPM: scatter/gather plus grid traffic.
- FEM: operator application / assembly is often memory dominated.

Optimization priority:
1) reduce global memory passes  
2) improve access locality / coalescing  
3) reduce atomics and sync  
4) only then micro-opt math

---

## 3) Kernel design patterns for speed

### Push loops into kernels (avoid Python-side loops)
- Python loops around kernels = tons of launches + sync points.
- Prefer kernels that run many iterations’ worth of data-parallel work per launch, when feasible.

### Fuse passes when it reduces memory traffic
Kernel fusion helps when:
- intermediate arrays are large
- you were writing and re-reading them

But don’t fuse so hard that:
- the kernel becomes branchy and divergent
- register pressure explodes and tanks occupancy

Rule: fuse for *memory*, not for aesthetics.

### Separate boundary handling (avoid divergence)
For grids/stencils:
- Run one kernel for the interior (no branches).
- Run another for boundaries / BCs.

Branchy kernels are slow kernels.

---

## 4) Loop-level tuning: block_dim and friends

### Use `ti.loop_config(block_dim=...)` on GPU hotspots
Taichi exposes a knob to set GPU “threads per block” for a loop. The docs explicitly note that choosing a proper `block_dim` can yield large speedups (their MPM example cites nearly 3x). 

Typical workflow:
- Start with 128 or 256.
- Profile and compare.
- Tune per kernel (different kernels prefer different launch shapes).

### `ti.block_dim` is deprecated
If you see old code or muscle memory trying to use `ti.block_dim`, don’t. Taichi moved this to `ti.loop_config(...)` and deprecated the old API. 

### Don’t tune blindly
Changing `block_dim` can:
- help occupancy and latency hiding
- or worsen performance via register pressure / memory patterns

So: tune only for hotspots you’ve measured.

---

## 5) Atomics: the performance tax you keep paying

Atomics are unavoidable in scatter-heavy algorithms (MPM P2G, FEM assembly), but you should treat them as a last resort.

### Strategies to reduce atomic pain
- **Accumulate locally** (register / small local vector) then atomic once per destination.
- **Two-pass**: write contributions to a buffer, then reduce in a structured way (sometimes faster than contended atomics).
- **Coloring / partitioning** (when applicable): reduce write conflicts by processing independent sets.
- **Change formulation**: matrix-free operator application can avoid assembly atomics in FEM.

Rule: if profiling shows atomics dominate, you need an algorithmic change, not micro-optimizations.

---

## 6) Precision and stability trade-offs

### Default `f32` for speed, but be deliberate
- `f32` is usually much faster and smaller.
- Some solvers (ill-conditioned FEM, long horizon integration) may need `f64`.

Recommendation:
- Keep storage in `f32` if possible.
- Use `f64` selectively for accumulations / reductions if it improves stability.

### Determinism note
Floating-point atomics change summation order, so results can be non-bitwise-deterministic across runs/hardware.
Plan validation tests accordingly (tolerances, invariants).

---

## 7) Data layout and access patterns (brief but critical)

### Coalesced access wins
- Adjacent threads should access adjacent memory.
- Avoid random indexing in inner loops if you care about GPU performance.

### Prefer SoA-style storage for streaming kernels
- Separate arrays/fields for each component often stream better than large AoS structs.
- For small per-item state, `ti.Vector` is fine, but watch total bytes touched per step.

(See `data-layout-and-snode.md` for the full layout playbook.)

---

## 8) Common GPU gotchas in Taichi performance

### Too many kernel launches
If each simulation step is 20–100 tiny kernels, you’re donating runtime to overhead.
- Combine trivial passes.
- Batch operations when you can.

### Hidden sync points
Some host-side reads or debug prints force sync.
- Keep host reads out of the hot loop.
- Validate periodically, not every iteration.

### “It’s slow” because you’re recompiling
Changing Python-side shapes/types dynamically can trigger recompilation or different kernel variants.
- Keep shapes static for the benchmark run.
- Avoid creating new fields/arrays inside the step loop.

---

## 9) A practical tuning checklist (print this mentally)
When a kernel is slow:
1. Is it JIT cost? (warm up)
2. Is it memory traffic? (count loads/stores, reduce passes)
3. Is it atomics? (contention? can you restructure?)
4. Is it divergence? (split boundaries / branches)
5. Is launch config suboptimal? (`ti.loop_config(block_dim=...)`)
6. Is precision overkill? (`f64` everywhere?)
7. Is layout wrong? (coalescing, SoA vs AoS)

---

## 10) Minimal profiler-driven loop (template mindset)
- run warmup steps
- run N timed steps
- print kernel profiler results
- optimize top 1–3 kernels
- repeat
