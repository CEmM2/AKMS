# Repo documentation profiles

Select 1–3 profiles per repo. Each profile adds required subsections.

## A) Scientific compute (FEM, solvers, FFT, PDE)
Add:
- Numerical safeguards & stability notes
- Boundary/initial condition conventions
- Convergence criteria and tolerances
- Precision expectations (fp32/fp64/mixed)
- Patch tests / verification cases (if applicable)

Minimal example:
- small mesh / single element / manufactured solution or patch test

## B) ML / Deep Learning (VAE, training pipelines)
Add:
- Training workflow (data → augment → train → validate → export)
- Inference workflow (load model → preprocess → predict → postprocess)
- Reproducibility: seeds, determinism knobs
- Checkpoint formats and model export
- Metrics definitions and expected ranges

Minimal example:
- train on tiny subset, run inference, generate a small output visualization

## C) Image processing (segmentation, registration, filtering)
Add:
- Coordinate conventions (voxel order, spacing)
- Intensity normalization conventions
- Resampling/interpolation choices
- Stability/conditioning steps
- Performance notes for large volumes

Minimal example:
- single image/volume pipeline with before/after artifact

## D) Data analysis (ETL, stats, notebooks)
Add:
- Data provenance and transformations graph
- Schema definitions and versioning
- Reproducible environment notes
- Notebook-to-script boundaries

Minimal example:
- run a pipeline stage producing a clean dataset and one report table/plot

## E) GUI / Tooling (experimental extraction by GUI)
Add:
- GUI entrypoints and user flows
- Export formats and schemas
- Configuration and saved state files
- Troubleshooting: common user-facing failure modes

Minimal example:
- open a sample, perform one extraction, export CSV/JSON, validate schema

## F) Control / Embedded (motor control, realtime)
Add:
- State machine and lifecycle diagram
- Hardware assumptions and limits
- Safety interlocks, watchdog behavior
- Calibration and commissioning steps
- Timing constraints and jitter sensitivity

Minimal example:
- simulation loop + mock IO + logging artifacts

## G) Geometry / Mesh generation
Add:
- Mesh quality metrics and thresholds
- IO formats (VTK, OBJ, STL, Gmsh, custom)
- Coordinate and units conventions
- Conditioning steps (smoothing, decimation, repair)

Minimal example:
- generate a mesh, run quality checks, export a standard format