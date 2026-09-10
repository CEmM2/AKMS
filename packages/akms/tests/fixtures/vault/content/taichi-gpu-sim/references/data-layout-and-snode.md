# Data Layout & SNodes (Taichi) — GPU-first guidelines

This doc is about choosing Taichi containers (`ti.field` / SNode trees vs `ti.ndarray`) and building SNode layouts that keep GPU kernels fast for FEM / FD / spectral-ish / MPM.

---

## 1) Fields vs NDArrays: pick the right hammer

### Use `ti.field` (SNode-backed) when you want:
- Flexible layouts (tiling, AoS/SoA hybrids, sparse structures)
- Potential Taichi-side optimizations that rely on fields (e.g., some reduction/TLS optimizations)
- Spatial sparsity (activate/deactivate regions)

Taichi fields hide SNode complexity behind an N-D array interface, but the storage is defined by the SNode tree you build.

### Use `ti.ndarray` when you want:
- A contiguous dense block (interop-friendly)
- Dense-only data, fixed layout, easy exchange with NumPy/PyTorch

Taichi ndarray is explicitly a contiguous multi-dimensional array allocated on the chosen arch and managed by Taichi runtime.

### Performance footnote that matters
Taichi’s TLS reduction optimization (thread-local storage reduction) currently applies to **0D** scalar/vector/matrix `ti.field` reductions (add/sub/min/max), and is **not** supported on `ti.ndarray`.

**Rule of thumb**
- Hot simulation state that benefits from layout tricks: **fields**
- Interop buffers / “just a dense tensor”: **ndarray**

---

## 2) SNode tree mental model (how storage actually exists)

A Taichi data structure (dense or sparse) is a **tree of SNodes** with interleaved *container* and *cell* levels. Each node can contain multiple components (children).

Example from the docs (conceptually):
- `S = ti.root.dense(ti.i, 128)` creates a container `S` with 128 cells
- then you can add children like `P = S.dense(ti.i, 4)` etc.

This matters because:
- **memory contiguity** and **index-to-address mapping** come from this tree
- you control tiling and locality by how you group indices into SNodes

---

## 3) Dense layout basics (what you should do by default)

### Baseline: straightforward dense field
```python
x = ti.field(dtype=ti.f32, shape=(nx, ny, nz))  # dense field
v = ti.Vector.field(3, dtype=ti.f32, shape=(nx, ny, nz))  # dense field
```

This uses a default dense layout derived from shape=... (Taichi builds a root-to-leaf dense SNode chain for you).

### When you need control: explicit ti.root layout

You use ti.root.X(...) statements to define advanced organizations. Taichi documents this as the “layout 101” pathway beyond shape=.  

A common performance pattern is to tile the domain so nearby cells sit near each other in memory and kernels get better locality:

```python
ti.root.dense(ti.ijk, (Bx, By, Bz)).dense(ti.ijk, (tx, ty, tz)).place(x)
# total shape: (Bx*tx, By*ty, Bz*tz)
```

### Axis order matters (contiguity)

Dense SNodes store children contiguously along their defined axes. If your kernel iterates i fastest, you generally want memory laid out so the fastest-varying index maps to contiguous addresses.

Practical advice:
	•	Keep your loop order and your dense axis order aligned.
	•	Prefer regular, predictable access over “clever” indexing.

---

## 4) AoS vs SoA (and the Taichi-flavored compromise)

### SoA: separate fields (often best for bandwidth-bound kernels)

Good for stencils (FD), vector updates, streaming passes.

```python
u = ti.field(ti.f32, shape=(nx, ny))
v = ti.field(ti.f32, shape=(nx, ny))
w = ti.field(ti.f32, shape=(nx, ny))
```

### AoS: vectors/matrices per cell (good for small fixed state)

Useful in MPM/FEM where each particle/node has a small vector/matrix.

```python
xp = ti.Vector.field(3, ti.f32, shape=n_particles)
Fp = ti.Matrix.field(3, 3, ti.f32, shape=n_particles)
```

### Struct fields (mixed)

Taichi fields can be primitive, vector, matrix, or struct per element.

Guideline
	•	If a kernel uses only one component most of the time, SoA often wins.
	•	If components are always consumed together and fit in cache/registers, AoS is fine.

---

## 5) Sparse SNodes (pointer / bitmasked / dynamic): use when sparsity is real

Taichi sparse spatial structures are composed of pointer, bitmasked, dynamic, and dense SNodes. A tree of only dense SNodes is not “sparse” in Taichi’s sense.

### pointer SNode
	•	Allocates blocks on demand via pointers (spatial sparsity)
	•	Good when large regions are empty (adaptive domains, localized activity)

### bitmasked SNode
	•	Like dense, but with an allocation mask (one bit per child)
	•	Good when most blocks exist but many cells inside blocks are inactive

### dynamic SNode
	•	Variable-length list up to a max length
	•	Useful for per-cell lists (neighbor lists, contact candidates, particles-in-cell lists), when you genuinely need variable occupancy

### Minimal sparse example (block sparse grid)

```python
x = ti.field(dtype=ti.f32)
block = ti.root.pointer(ti.ij, (Bx, By))
cell  = block.dense(ti.ij, (tx, ty))
cell.place(x)
```

Taichi’s sparse tutorial examples use exactly this pointer-then-dense style, optionally swapping dense for bitmasked.  ￼

### Activation model

In Taichi sparse structures, a voxel/node is “active” if it’s allocated and involved in computation; inactive regions don’t consume storage.  ￼

---

## 6) Layout patterns by domain

### FD / regular grids

	•	Dense fields almost always
	•	Tile if stencils are wide or 3D caches are stressed
	•	Separate boundary handling to avoid divergence (see kernel-patterns.md)

### MPM grids
	•	Usually dense grid fields (regular background grid)
	•	Hot loops: P2G and G2P. You often get more from:
	•	better kernel structure
	•	fewer atomics / contention
	•	launch tuning
than from exotic SNodes, unless you have true spatial sparsity.

### Particles (MPM)
	•	If particle count is fixed: dense 1D fields/vectors/matrices
	•	If occupancy varies or you need per-cell lists: consider dynamic (but measure, it adds overhead)

### FEM
	•	Structured grids (voxel FEM): dense/tiled SNodes
	•	Unstructured meshes: Taichi can store connectivity in dense 1D arrays/fields; sparse SNodes help less unless your domain is spatially sparse.

---

## 7) Iteration: what loops actually traverse

### Dense fields

for I in x: iterates over the full index space.

### Sparse fields

Iteration respects activation. You can iterate:
	•	over active leaf coordinates via for I in x:
	•	over higher-level sparse nodes (blocks) via iterating the SNode variable itself (example patterns appear in Taichi sparse tutorials)  ￼

Guideline
	•	For sparse layouts, avoid kernels that implicitly touch the entire virtual domain.
	•	Iterate active regions when possible.

---

## 8) Gotchas (things that waste days)

### “Sparse” that isn’t sparse

If your data is dense in practice, pointer/bitmasked overhead can slow you down.
Sparse SNodes are for real sparsity, not aesthetic minimalism.  ￼

### Reduction + ndarray mismatch

If you rely on Taichi’s TLS reduction optimization, remember it’s currently supported for 0D ti.field reductions, not ti.ndarray.  ￼

### Layout changes and compilation behavior

Advanced layouts are powerful, but they also “lock in” how data is stored. Keep shapes/layout stable in benchmarks to avoid recompilation churn.

---

## 9) Practical recipes (copy-paste patterns)

### Recipe A: Tiled dense 3D scalar + vector fields

```python
x = ti.field(ti.f32)
v = ti.Vector.field(3, ti.f32)

root = ti.root.dense(ti.ijk, (Bx, By, Bz))
tile = root.dense(ti.ijk, (tx, ty, tz))
tile.place(x, v)
# total resolution: (Bx*tx, By*ty, Bz*tz)
```

### Recipe B: Block sparse 3D grid with dense tiles (common sparse grid form)

```python
x = ti.field(ti.f32)
root  = ti.root.pointer(ti.ijk, (Bx, By, Bz))
tile  = root.dense(ti.ijk, (tx, ty, tz))
tile.place(x)
```

### Recipe C: Particle arrays (dense, fixed N)

```python
xp = ti.Vector.field(3, ti.f32, shape=N)
vp = ti.Vector.field(3, ti.f32, shape=N)
Fp = ti.Matrix.field(3, 3, ti.f32, shape=N)
```

### Recipe D: Particle arrays (dense, fixed N)

```python
xp = ti.Vector.field(3, ti.f32, shape=N)
vp = ti.Vector.field(3, ti.f32, shape=N)
Fp = ti.Matrix.field(3, 3, ti.f32, shape=N)
```

## 10) What to decide early (so your codebase stays coherent)

	•	Are grid fields dense or sparse?
	•	Is particle count fixed or variable?
	•	Do you store tensor state as ti.Matrix (small) or flattened arrays?
	•	What is your canonical axis order (and do your hot loops match it)?

Keep those consistent and your kernels will stop fighting your memory subsystem.

