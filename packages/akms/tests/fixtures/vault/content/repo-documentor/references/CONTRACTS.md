# API Contract blocks

Every documented function/kernel/class should include a contract block.

## Function/Kernel contract
- Purpose (1–2 lines)
- Inputs: name, type/dtype, shape, units, device (CPU/GPU), valid ranges
- Outputs: same
- Side effects: state mutation, caching, RNG usage, IO
- Errors: exceptions/return codes/warnings
- Performance: complexity and memory notes
- Determinism: seed requirements, nondeterministic ops, parallel effects

## Class contract
- Responsibility
- Key state: fields, types, invariants
- Lifecycle: init/reset/update/finalize
- Thread safety / reentrancy
- External resources (files, GPU buffers, devices)

## Standard wording for dependency surfaces
- Public: stable, documented, tested
- Semi-public: used by scripts/tools, may change
- Internal: no stability promises