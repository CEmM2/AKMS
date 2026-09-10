# Interop (Taichi ↔ NumPy / PyTorch / CuPy / AOT runtime)

This doc is about getting data **in and out of Taichi efficiently** (preferably zero-copy on GPU), and avoiding the classic trap of “interop” meaning “accidentally copying 20 GB through the CPU.”

---

## 0) Two interop modes (know which one you’re using)

### A) **Copy-based interop** (safe, simple, not always fast)
Use when you can afford a copy or you’re moving across devices/layouts:
- `field.from_numpy(...)`, `field.to_numpy()`
- `field.from_torch(...)`, `field.to_torch(device=...)`

Taichi manages its own copy for these conversions, and they work even if the source is non-contiguous.  

### B) **Reference / zero-copy interop** (fast, sharp edges)
Use when you want kernels to operate on external buffers directly:
- pass arrays/tensors into kernels via `ti.types.ndarray(...)`

This passes by reference (no copy) and kernel writes mutate the original object.  

---

## 1) Kernel arguments: `ti.types.ndarray(...)` (the main interop gateway)

### Supported “external arrays”
Taichi’s external array docs currently list:
- NumPy arrays
- PyTorch tensors
- Paddle tensors (We do not support this)

You pass them into kernels via `ti.types.ndarray()` type hints.

### Contiguity requirement (important)
- `from_numpy()/from_torch()` can take contiguous or non-contiguous inputs (Taichi copies internally).
- **Kernel arguments** only support **contiguous** NumPy arrays / PyTorch tensors.

Practical rule:
- If you want zero-copy kernel interop, call `.contiguous()` (Torch) or `np.ascontiguousarray(...)` (NumPy) first.

### Device matching (where “zero-copy” actually happens)
If Taichi and the external container are on the **same device**, passing arguments incurs **no additional overhead**. Taichi can access the original CUDA buffer of a CUDA tensor directly.  
If devices differ (e.g., NumPy CPU array into CUDA Taichi), Taichi automatically manages transfer.

---

## 2) Fields ↔ external arrays (copy semantics)

### NumPy
- Import: `x.from_numpy(arr)` copies into the field
- Export: `x.to_numpy()` returns a NumPy array copy

### PyTorch
- Import: `x.from_torch(tensor)` copies into the field
- Export: `x.to_torch(device=...)` copies out, and you must specify the torch device

Use this route when:
- you want Taichi-optimized layouts (SNodes) internally
- you don’t need true zero-copy

---

## 3) Taichi `ndarray` (best for dense interop + AOT)

Taichi `ndarray` is:
- **contiguous** multi-dimensional memory
- allocated on the Taichi arch, managed by Taichi runtime
- designed to be straightforward for external libraries to interpret compared to SNode-backed fields

### Don’t index ndarrays from Python in hot paths
The docs explicitly warn that element-wise Python access can create many small kernel launches; do real work in kernels.

### Template compilation behavior (dtype/ndim matters)
If you annotate kernel args as `ti.types.ndarray()` (templated), Taichi will compile variants per `(dtype, ndim)` and cache them.
- **Changing shape does not trigger compilation**
- **Changing dtype or ndim does**

This is great for flexibility, but can cause compile churn if you keep changing dtypes/dimensions mid-run.

---

## 4) PyTorch ↔ Taichi: recommended patterns

### Pattern A: “Torch owns memory, Taichi kernel mutates it” (GPU-friendly)
- Create Torch CUDA tensors
- Pass into Taichi kernels as `ti.types.ndarray(...)`
- Keep everything on GPU for the whole pipeline

Taichi’s docs position this as a complementary workflow: use Taichi for granular element-level operators, Torch for tensor-level ML composition.

**Skeleton**
```python
import taichi as ti
import torch

ti.init(arch=ti.cuda)

@ti.kernel
def add_one(x: ti.types.ndarray(dtype=ti.f32, ndim=2)):
    for I in ti.grouped(x):
        x[I] += 1.0

x = torch.zeros((1024, 1024), device="cuda", dtype=torch.float32)
add_one(x)  # mutates x in-place (by reference)
# (Contiguity note still applies.)
```

---

## 5) CuPy ↔ Taichi (there’s no direct path, so we cheat politely)

### Current state: no direct “CuPy -> Taichi field/ndarray” API

A Taichi issue (feature request) indicates there isn’t a direct API to create Taichi objects from cupy.ndarray at the moment; the suggested workaround was converting via NumPy (which is a CPU round-trip).

### Recommended workaround: CuPy ⇄ Torch zero-copy, then Torch ⇄ Taichi

CuPy supports zero-copy exchange with PyTorch using __cuda_array_interface__ and also via DLPack.
Taichi can accept a Torch CUDA tensor as an external array argument with no extra overhead when both use CUDA.

Bridge recipe (conceptual)
	1.	CuPy array cp_x (on CUDA)
	2.	Convert to Torch tensor zero-copy (via torch.as_tensor(cp_x, device='cuda') or DLPack)
	3.	Pass Torch tensor into Taichi kernel as ti.types.ndarray(...)

Why this works
	•	CuPy ↔ Torch can share device memory pointers (zero-copy)
	•	Taichi can operate on Torch CUDA buffers directly when device matches

### Interop gotcha (general GPU reality)
When sharing buffers across frameworks, you must ensure correct synchronization and lifetime (streams, object ownership). CuPy’s docs explicitly warn about lifetime rules for exported CUDA array interface objects.

---

## 6) NumPy ↔ Taichi on GPU (avoid accidental CPU traffic)

If Taichi is running on CUDA and you pass a NumPy CPU array into a kernel, Taichi will manage a device transfer.
That’s convenient, but if you do it every step, you’ve built a PCIe stress test, not a solver.

Rule
	•	Use NumPy only for infrequent IO / initialization / debugging
	•	Keep step-to-step state in Taichi fields/ndarrays or Torch CUDA tensors

---

## 7) AOT deployment interop (native apps, mobile, etc.)

Taichi AOT compiles kernels ahead-of-time into backend instructions (e.g., SPIR-V shaders) and runs them via a runtime library, without Python.

### Why ndarray matters in AOT

The AOT blog explicitly highlights ndarrays as flexible for AOT:
	•	independent buffers (easier binding than field offsets)
	•	dynamic size allocation without regenerating shaders
	•	easier runtime binding vs templated fields

### Running AOT in native apps (TiRT + C interface)

The official tutorial describes compiling AOT modules and launching them in C++ apps via TiRT, noting the C interface can integrate with multiple languages (Swift, Rust, C#, Java, etc.).
The API docs also describe taichi.aot.Module as serializing kernels for a specific arch to run without Python.

---

## 8) Interop gotchas checklist (print this in your brain)
	•	Kernel args must be contiguous (NumPy/Torch).
	•	from_numpy/from_torch is copy-based (safe but not zero-copy).
	•	Passing external arrays to kernels is by reference, mutates originals.
	•	Same-device Torch CUDA tensor → Taichi kernel can be no-overhead.
	•	ti.types.ndarray() templating: changing dtype/ndim triggers new compilation; shape doesn’t.
	•	CuPy direct ingest into Taichi isn’t currently a first-class API; use Torch as the bridge if you want zero-copy.
