# Pull Request Review Template: Taichi Simulation Code

**PR Number:** #XXX
**Title:** [PR Title]
**Author:** @username
**Reviewer:** @reviewer-name
**Date:** YYYY-MM-DD

---

## Summary

[Brief 1-3 sentence summary of what this PR does]

**Type:** [Bug Fix / New Feature / Performance Improvement / Refactoring / Documentation]

**Complexity:** [Low / Medium / High]

---

## Review Status

**Decision:** [ ] ✅ Approve | [ ] 🔄 Request Changes | [ ] 💬 Comment

**Severity Summary:**
- 🔴 Critical Issues: X (blocks merge)
- 🟡 Major Issues: X (should fix)
- 🟢 Minor Issues: X (suggestions)
- ℹ️ Questions: X

---

## Checklist (Core Review Areas)

### 1. Correctness ✓
- [ ] **Physical laws respected** (conservation, invariants, sign conventions)
- [ ] **Math verified** (tensor operations, indices, formulas)
- [ ] **No data races** (proper buffering, atomics used correctly)
- [ ] **Boundary conditions** correct and well-defined
- [ ] **Numerical stability** (CFL conditions, conditioning)

### 2. Performance & Taichi Patterns ⚡
- [ ] **Architecture explicit** (`ti.init(arch=...)` specified)
- [ ] **Hot loops in kernels** (no Python loops over grid/particles)
- [ ] **Data layout optimal** (SoA where appropriate, field vs ndarray)
- [ ] **Atomics minimized** (scatter patterns optimized)
- [ ] **No thread divergence** (boundaries handled separately)
- [ ] **Block dimensions tuned** (if critical path, `ti.loop_config` used)

### 3. Style & Architecture 📐
- [ ] **Clear naming** (follows conventions: `F`, `sigma`, `v`, descriptive kernel names)
- [ ] **Modular structure** (domain logic separated from core solver)
- [ ] **Data ownership clear** (Field vs Ndarray vs external, no redundant copies)

### 4. Documentation 📝
- [ ] **Docstrings present** (kernels explain what, inputs, outputs)
- [ ] **Complex math explained** (non-obvious steps have comments)
- [ ] **Magic numbers documented** (tuning parameters explained)

### 5. Testing & Validation ✅
- [ ] **Unit tests added** (if new functionality)
- [ ] **Regression tests pass** (existing tests still green)
- [ ] **Validation included** (sanity checks, conservation tests, symmetry)

---

## Detailed Review Comments

### 🔴 Critical Issues (Must Fix Before Merge)

#### Issue #1: [Title]
**Location:** `file.py:line`

**Problem:**
[Detailed description of the issue]

**Impact:**
[What breaks, performance impact, or correctness issue]

**Fix:**
```python
# Suggested code or approach
```

**Reference:** [Link to relevant docs]

---

### 🟡 Major Issues (Should Fix)

#### Issue #1: [Title]
**Location:** `file.py:line`

**Problem:**
[Description]

**Suggestion:**
[Recommended fix]

---

### 🟢 Minor Issues / Suggestions

#### Issue #1: [Title]
**Location:** `file.py:line`

**Suggestion:**
[Nice-to-have improvement]

---

### ℹ️ Questions for Author

1. **Q:** [Question about design choice or unclear code]
   - **Context:** [Why this matters]

2. **Q:** [Another question]

---

## Domain-Specific Review

### [FEM / FD / FFT / MPM]

**Domain Checklist:**

For FEM:
- [ ] Matrix-free for large problems?
- [ ] Assembly minimizes atomics?
- [ ] Quadrature weights precomputed?
- [ ] Corotational stress update correct?

For FD:
- [ ] Double-buffering used?
- [ ] CFL condition validated?
- [ ] Stencil pattern correct?
- [ ] Boundaries separate from interior?

For FFT:
- [ ] Interop strategy clear (CuPy/cuFFT)?
- [ ] Wavenumber convention correct?
- [ ] Dealiasing applied if needed?
- [ ] Complex arithmetic correct?

For MPM:
- [ ] Clear → P2G → Grid → G2P structure?
- [ ] B-spline weights unrolled?
- [ ] APIC affine matrix updated?
- [ ] Plasticity return mapping correct?

**Domain-Specific Comments:**
[Specific feedback related to the physics/domain]

---

## Performance Considerations

**Expected Performance Impact:** [Improves / Neutral / Degrades]

**Profiling Needed:** [ ] Yes [ ] No

**Comments:**
- [Any performance-related observations]
- [Suggestions for optimization if needed]

---

## Test Plan Verification

**Tests Included:** [ ] Yes [ ] No

**Tests Needed:**
- [ ] Unit tests for new functions
- [ ] Regression tests for modified code
- [ ] Integration test for feature
- [ ] Performance benchmark (if relevant)

**Validation Strategy:**
- [ ] Conservation checks
- [ ] Symmetry tests
- [ ] Known solution comparison
- [ ] Convergence analysis

---

## CI/CD Status

**Build:** [ ] ✅ Pass [ ] ❌ Fail
**Tests:** [ ] ✅ Pass [ ] ❌ Fail
**Linting:** [ ] ✅ Pass [ ] ❌ Fail
**Coverage:** [XX]%

**CI Comments:**
[Any CI-related issues or notes]

---

## Dependencies & Breaking Changes

**External Dependencies Added/Changed:**
- [List any new dependencies or version changes]

**Breaking Changes:** [ ] Yes [ ] No

**If Yes:**
- [Describe what breaks]
- [Migration path for users]

---

## Documentation Updates

**Documentation Changed:** [ ] Yes [ ] No [ ] N/A

**Locations:**
- [ ] Inline code comments
- [ ] Docstrings
- [ ] README
- [ ] API docs
- [ ] Tutorials/examples

---

## Required Actions (Summary)

### Before Merge:
1. [ ] Fix critical issue #1: [brief description]
2. [ ] Fix critical issue #2: [brief description]
3. [ ] Address major issue #1: [brief description]
4. [ ] Add tests for new functionality
5. [ ] Update documentation

### Nice to Have (Can be follow-up):
1. [ ] Minor improvement #1
2. [ ] Minor improvement #2

---

## Estimated Effort for Fixes

**Critical fixes:** ~X hours
**Major fixes:** ~X hours
**Tests + docs:** ~X hours

**Total:** ~X hours

---

## Additional Notes / Context

[Any additional context, related PRs, discussion points, or future work]

---

## References

- Taichi GPU Sim Guide: `skills/taichi-gpu-sim/SKILL.md`
- Review Checklist: `skills/taichi-sim-reviewer/references/review-checklist.md`
- Testing Guide: `skills/taichi-sim-reviewer/references/testing-verification.md`
- CI/CD Guide: `skills/taichi-sim-reviewer/references/ci-cd-guidance.md`
- Domain Guides: `skills/taichi-gpu-sim/domains/[fem|fd|fft|mpm].md`

---

## Final Recommendation

**Status:** [Approve / Request Changes / Comment Only]

**Rationale:**
[2-3 sentences explaining the decision]

**Next Steps:**
1. [What author should do next]
2. [What reviewer will do after changes]

---

**Reviewed by:** @reviewer
**Review completed:** YYYY-MM-DD
**Review time:** ~X minutes
