# Testing & Validation — correctness harness for FEM/MPM/FD/spectral + tensor math verification (SymPy)

This doc defines testing practices for this repo, focusing on:
- fast unit tests for tensor utilities
- invariants and regression tests for simulation steps
- SymPy-based verification for mathematical tensor operations (Voigt/Mandel, rotations, push/pull, tangents)

Primary conventions (must match implementation):
- Tensorial Voigt order: `[xx, yy, zz, xy, xz, yz]` with unscaled shear
- Objective corotational rotation (Hughes–Winget / Cayley)
- Pressure sign: compression-positive `p = -mean(σ)`

(See `references/continuum-tensors.md` and `references/stress-integration.md`.)

---

## 1) Test tiers (what to test, where)

### Tier A: Pure math unit tests (fast, no Taichi required)
Target:
- Voigt pack/unpack functions
- Mandel conversion maps (P matrices)
- Stress/tangent rotation operators
- Push-forward / pull-back conversions (σ ↔ P ↔ S)
- Basic tensor ops: `sym`, `skew`, `dev`, `trace`

Goal:
- catch convention/sign/index bugs early
- run in <1s in CI

### Tier B: Taichi kernel unit tests (small problem sizes)
Target:
- kinematics kernels (L, D, W, R_delta)
- corotational rotate-in/out of stress
- stress update wrapper correctness (not performance)

Goal:
- verify kernels match Tier A math results for random inputs (within tolerance)

### Tier C: Integration tests (small sim problems)
Target:
- patch tests (FEM)
- rigid rotation objectivity
- MPM mass conservation
- FD stability and boundary behavior

Goal:
- ensure “it works together” after refactors

### Tier D: Performance regression checks (optional but recommended)
Target:
- kernel time budgets and hotspot stability
- prevent accidental CPU copies, extra launches

Goal:
- avoid stealth slowdowns

---

## 2) Numeric tolerances and determinism

### Floating point tolerances
- Use relative + absolute tolerance:
  - `abs(a-b) <= atol + rtol*abs(b)`
- Expect different results across GPUs/architectures when atomics are used.
- Do not require bitwise determinism unless you explicitly design for it.

Recommended starting values (adjust to your scales):
- f32: `rtol=1e-5`, `atol=1e-6`
- f64: `rtol=1e-10`, `atol=1e-12`

---

## 3) Core invariants (cheap checks that catch real bugs)

### Tensor utility invariants
- `sym(A)` is symmetric
- `skew(A)` is skew-symmetric
- `dev(A)` has zero trace (within tolerance)
- `pack(unpack(v)) == v` and `unpack(pack(A)) == A` for symmetric tensors
- Voigt shear positions match `[xy, xz, yz]` exactly (no shear scaling)

### Corotational invariants
- rotation matrix orthogonality: `R^T R ≈ I`
- objectivity: for pure rotation (D≈0), corotational stress remains unchanged while spatial stress rotates

### Stress decomposition invariants
- `σ = dev(σ) + mean(σ) I`
- `σ_eq >= 0`
- if `||s||` small, von Mises should be ~0

### EOS sign gate invariants (when enabled)
- compression: `p_EOS > 0` ⇒ no tensile degradation
- tension: `p_EOS < 0` ⇒ tensile-only degradation applies

---

## 4) SymPy verification (tensor ops and identities)

SymPy is ideal for verifying:
- algebraic identities (rotation invariance, push/pull equivalences)
- correctness of mapping matrices (Voigt/Mandel)
- correctness of tangent rotation forms (symbolically or semi-symbolically)

Use SymPy tests to validate the *math contract* once, then use numeric tests to validate the implementation repeatedly.

### 4.1) Verify tensorial Voigt pack/unpack mapping
Contract:
- Voigt order: `[xx, yy, zz, xy, xz, yz]`
- Unscaled shear (tensorial, not engineering)

Example SymPy test:

```python
import sympy as sp

# Symbols
axx, ayy, azz, axy, axz, ayz = sp.symbols('axx ayy azz axy axz ayz')

A = sp.Matrix([[axx, axy, axz],
               [axy, ayy, ayz],
               [axz, ayz, azz]])

v = sp.Matrix([axx, ayy, azz, axy, axz, ayz])

# Pack/unpack functions (symbolic definitions)
def pack_tensorial_voigt(A):
    return sp.Matrix([A[0,0], A[1,1], A[2,2], A[0,1], A[0,2], A[1,2]])

def unpack_tensorial_voigt(v):
    return sp.Matrix([[v[0], v[3], v[4]],
                      [v[3], v[1], v[5]],
                      [v[4], v[5], v[2]]])

assert sp.simplify(pack_tensorial_voigt(A) - v) == sp.Matrix([0]*6)
assert sp.simplify(unpack_tensorial_voigt(v) - A) == sp.zeros(3)
```

### 4.2) Verify Mandel transform matrices

Contract:
	•	P = diag([1,1,1, sqrt(2), sqrt(2), sqrt(2)])
	•	C_M = P * C_V * P^{-1} and inverse mapping as specified in conventions

```python
import sympy as sp
sqrt2 = sp.sqrt(2)
P = sp.diag(1,1,1,sqrt2,sqrt2,sqrt2)
Pinv = sp.diag(1,1,1,1/sqrt2,1/sqrt2,1/sqrt2)

# Symbolic 6x6 matrix for tangent in tensorial-Voigt
C_V = sp.Matrix(sp.symbols('c0:36')).reshape(6,6)

C_M = P * C_V * Pinv
C_V_back = Pinv * C_M * P

assert sp.simplify(C_V_back - C_V) == sp.zeros(6)
```

### 4.3) Verify rotation identities for stresses

Identity:
	•	σ' = R σ R^T
	•	stress invariants for isotropic models:
	•	tr(σ') == tr(σ)
	•	dev(σ') : dev(σ') == dev(σ) : dev(σ) (rotation preserves Frobenius norm)

Use a symbolic orthogonal matrix is hard; instead:
	•	use a parameterized rotation (e.g., around z) or
	•	do numeric-with-symbolic-structure: generate random numeric R with QR and validate identity in floating point

SymPy + numeric approach:

```python
import sympy as sp
import numpy as np

def random_rotation():
    A = np.random.randn(3,3)
    Q, _ = np.linalg.qr(A)
    # Ensure det=+1
    if np.linalg.det(Q) < 0:
        Q[:,0] *= -1
    return Q

for _ in range(100):
    R = sp.Matrix(random_rotation())
    S = sp.Matrix(np.random.randn(3,3))
    sigma = (S + S.T) / 2  # symmetric
    I = sp.eye(3)

    def dev(A): return A - sp.trace(A)/3 * I

    sigma_p = R * sigma * R.T
    assert np.allclose(np.array(sp.trace(sigma_p), dtype=float),
                       np.array(sp.trace(sigma), dtype=float), rtol=1e-10, atol=1e-12)

    n0 = float((dev(sigma).T*dev(sigma)).trace())
    n1 = float((dev(sigma_p).T*dev(sigma_p)).trace())
    assert abs(n1 - n0) < 1e-9
```

### 4.4) Verify push/pull conversions between stress measures

Common identity to verify:
	•	If P = J σ F^{-T}, then σ = (1/J) P F^T
	•	If S = F^{-1} P, then P = F S

Use random numeric invertible F with SymPy matrices:

```python
import sympy as sp
import numpy as np

def random_invertible_F():
    while True:
        F = np.random.randn(3,3)
        if abs(np.linalg.det(F)) > 0.2:
            return F

for _ in range(100):
    F = sp.Matrix(random_invertible_F())
    J = float(F.det())
    sigma = sp.Matrix(np.random.randn(3,3))
    sigma = (sigma + sigma.T) / 2

    P = J * sigma * F.inv().T
    sigma_back = (1/J) * P * F.T

    assert np.allclose(np.array(sigma_back, dtype=float),
                       np.array(sigma, dtype=float), rtol=1e-9, atol=1e-10)

    S = F.inv() * P
    P_back = F * S
    assert np.allclose(np.array(P_back, dtype=float),
                       np.array(P, dtype=float), rtol=1e-9, atol=1e-10)
```

### 4.5) Verify 6×6 tangent rotation operator (recommended strategy)

Full symbolic verification of 6×6 tangent rotation is possible but heavy.

Recommended approach:
	•	Implement the tangent rotation operator in Python using the exact algorithm from your kinematics class.
	•	Validate with randomized tests by comparing:
	•	Rotate a small symmetric strain increment δε (3×3), compute δσ = c : δε
	•	Rotate δε into rotated frame, rotate tangent, compute δσ'
	•	Ensure rotating δσ matches δσ'

This “operator equivalence” test is strong and avoids fully symbolic 4th-order algebra.

---

## 5) Taichi kernel validation patterns

Small deterministic inputs

Use tiny sizes:
	•	1 element, 1 quad
	•	1 particle, 1 cell neighborhood
	•	8×8×8 FD grid

Then compare against a pure NumPy/SymPy reference in Python.

Debug-only asserts and flags

Inside kernels:
	•	avoid print
	•	write to a debug flag field when invalid values are detected
	•	optional: write the first bad index to a debug buffer

---

## 6) Minimal domain tests (fast, brutal)

### FEM
	•	Patch test (constant strain): internal forces should match analytical response (within tolerance)
	•	Rigid motion: no stress generation (objectivity)
	•	If implicit: Newton residual should decrease (stagnation indicates tangent mismatch)

### MPM
	•	Mass conservation on grid after P2G
	•	Particle J bounds (no negative/zero)
	•	Pure rigid body rotation: stress should be objective

### FD
	•	Boundary correctness on a known solution (manufactured solution if needed)
	•	Stability check: dt below stability limit should not blow up

### Spectral-ish
	•	Parseval/energy consistency checks (if applicable)
	•	Dealiasing masks applied correctly
	•	Round-trip checks if using external FFT library

---

## 7) Regression test philosophy
	•	Every time a convention bug is found, add a unit test for it.
	•	Treat tensor mapping and sign conventions as “must never break.”
	•	Keep tests small; large tests belong in benchmarks, not CI.

