# Quality gates (must pass)

## Structural coverage
- Every module has: Purpose, Dependencies, Public surfaces
- Every public class has: Responsibility, Key state, Lifecycle, Methods list
- Every public function/kernel has: Contract block + failure modes

## Glossary consistency
- Every equation symbol appears in the glossary
- Units/frames referenced by artifacts and APIs are defined in conventions

## Diagram integrity
- Diagram nodes correspond to real modules/classes/functions
- No “ghost components” not found in repo inventory

## Inference labeling
- Anything not explicitly stated is marked **Inferred**
- “Intentionally unused parameter” admonitions only where verified

## Workflow completeness
- Entrypoints listed
- At least one “typical run” per chosen profile
- Examples specify commands + expected artifacts

## Validation completeness
- Tests-to-modules mapping exists (even if sparse)
- At least one verification strategy documented (unit, regression, sanity)
- Reproducibility notes included where relevant

## Stability policy
- Public/Semi-public/Internal surfaces documented
- Breaking-change guidance present