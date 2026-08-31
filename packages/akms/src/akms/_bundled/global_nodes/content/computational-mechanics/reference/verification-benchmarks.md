# Verification and benchmark suite

When adding or modifying mechanics features, propose or generate tests from the list below.

## 1) Taylor anvil impact (high-rate plasticity + thermo)
- Purpose: large deformation, rate dependence, adiabatic heating
- Metrics: final length, mushroom diameter ratio, Delta T
- Checks: energy balance; objectivity under rotation

## 2) Sneddon / Mode-I crack (phase-field)
- Purpose: length scale l and fracture energy dissipation
- Metrics: crack bandwidth ~ 2l, load-displacement, dissipated energy ~ Gc*crack_area
- Checks: no crack growth in compression via energy split

## 3) Periodic RVE with high-contrast inclusion (FFT)
- Purpose: LS solver robustness and contrast handling
- Metrics: convergence iterations vs contrast, equilibrium residual, average stress agreement

## 4) Biaxial tension of perforated sheet (anisotropy + localization)
- Purpose: large strain plasticity, path dependence, onset of necking
- Metrics: localization strain, yield locus response RD vs TD

## Required docstring header in test files
Each test function should include:
- PURPOSE
- DESCRIPTION
- VERIFICATION

See templates/pytest_benchmarks_template.py for a starter file.
