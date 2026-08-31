---
id: moose-wbm-calphad
title: MOOSE WBM thermodynamic coupling and CALPHAD integration
domain: phase-field
subdomain: algorithmic
tags:
- CALPHAD
- TDB
- parabolic-approximation
- Redlich-Kister
- temperature-dependence
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-wbm-kks-model
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-wbm-kks-model
---

# MOOSE WBM thermodynamic coupling and CALPHAD integration

The WBM/KKS models in MOOSE connect to thermodynamic databases primarily through the `python/calphad/free_energy.py` script, which extracts free energy expressions from CALPHAD `.tdb` files and formats them for use with MOOSE's `DerivativeParsedMaterial` . This allows per-phase free energies to be directly incorporated into phase-field simulations. Temperature dependence and multi-component extensions like Redlich-Kister and sublattice models are handled by the CALPHAD data itself and then parsed into MOOSE's symbolic expression system .

## Connecting CALPHAD Data to MOOSE

### 1. Per-phase free energies from CALPHAD data and TDB file interface

MOOSE can utilize per-phase free energies derived from CALPHAD data . The primary interface for this is the `python/calphad/free_energy.py` script . This script uses the `pycalphad` Python module to parse `.tdb` thermodynamic database files . It then exports these free energy expressions as MOOSE `Material` blocks, specifically using the `DerivativeParsedMaterial` class .

**Algorithm Steps:**
` ` `pseudocode
1. User runs `free_energy.py` with a .tdb file and optional phase list.
2. `free_energy.py` opens the .tdb file using `pycalphad.Database`.
3. For each specified phase, a thermodynamic model is created using `pycalphad.Model`.
4. The free energy expression from the model is exported as a string using `fparser`.
5. MOOSE input file blocks are generated, defining a `DerivativeParsedMaterial` for each phase with the extracted function and its arguments.
` ` `


**MOOSE Input Syntax:**
The `free_energy.py` script generates output similar to this for each phase:
` ` `ini
  [./F_phase_name]
    type = DerivativeParsedMaterial
    function = 'CALPHAD_free_energy_expression'
    args = 'variable1 variable2 ...'
  [../]
` ` `


### 2. Parabolic approximation of CALPHAD data

The MOOSE documentation indicates that the `free_energy.py` tool directly exports CALPHAD functional expressions . This implies that MOOSE uses the full CALPHAD expressions rather than relying on parabolic approximations. The `DerivativeParsedMaterial` is designed to handle these complex functional forms and their derivatives symbolically .

### 3. `TabulatedFluidProperties` for tabulated thermodynamic data

While `TabulatedFluidProperties` exists in MOOSE for fluid simulations , it is part of the `fluid_properties` module and is designed for single-phase fluid properties based on pressure and temperature tables . It is not directly applicable to phase-field models for solid-state transformations where free energies are typically functions of order parameters and concentrations, and often derived from CALPHAD. The phase-field module uses `DerivativeParsedMaterial` for free energy expressions .

### 4. Temperature dependence in per-phase free energies

Temperature dependence is inherently included in the CALPHAD free energy expressions extracted by `free_energy.py` . When these expressions are parsed into `DerivativeParsedMaterial`, temperature can be included as one of the `args` (arguments) to the function .

### 5. Multi-component extensions (Redlich-Kister, sublattice models)

CALPHAD databases often incorporate multi-component extensions like Redlich-Kister and sublattice models . Since the `free_energy.py` script uses `pycalphad` to interpret the `.tdb` files , these complex models are handled by `pycalphad` during the extraction process. The resulting free energy expressions, which can be quite complex, are then passed to `DerivativeParsedMaterial` . `DerivativeParsedMaterial` is capable of handling arbitrary symbolic functions and their derivatives, making it suitable for these extensions .

### 6. Higher-order derivatives from CALPHAD and numerical stability

The `DerivativeParsedMaterial` class in MOOSE is designed to automatically compute derivatives of the free energy expressions . This symbolic differentiation capability helps in maintaining numerical stability by providing exact derivatives, rather than relying on numerical approximations that can introduce errors. The `KKSPhaseConcentrationMultiPhaseMaterial` uses nested Newton iterations to solve for phase concentrations, which requires derivatives of the free energies . The accuracy of these derivatives is crucial for the stability and convergence of the solver.

## Practical Approaches for Connecting Phase Field with Thermodynamic Data

### Classes & Methods:
*   `python/calphad/free_energy.py`: A Python script that extracts free energy expressions from `.tdb` files and generates MOOSE input blocks .
*   `DerivativeParsedMaterial`: A MOOSE material class that takes a symbolic function string and its arguments, and automatically computes its derivatives .
*   `KKSMultiFreeEnergy::validParams()`: Defines the input parameters for the `KKSMultiFreeEnergy` AuxKernel, including lists of free energy functions, switching functions, and barrier functions for each phase .
*   `KKSPhaseConcentrationMultiPhaseMaterial::validParams()`: Defines input parameters for the `KKSPhaseConcentrationMultiPhaseMaterial`, which computes KKS phase concentrations using a nested Newton iteration . It requires free energy material objects (`Fj_names`) and their derivatives .

### Relationships:
` ` `mermaid
classDiagram
    direction LR
    class "python/calphad/free_energy.py" as FreeEnergyScript
    class "pycalphad" as Pycalphad
    class "Database" as TDBDatabase
    class "Model" as PycalphadModel
    class "DerivativeParsedMaterial" as DerivativeParsedMaterial
    class "KKSMultiFreeEnergy" as KKSMultiFreeEnergy
    class "KKSPhaseConcentrationMultiPhaseMaterial" as KKSPhaseConcentrationMultiPhaseMaterial
    class "TotalFreeEnergyBase" as TotalFreeEnergyBase
    class "Material" as Material

    FreeEnergyScript --> Pycalphad : uses
    Pycalphad --> TDBDatabase : parses
    Pycalphad --> PycalphadModel : creates
    FreeEnergyScript --> DerivativeParsedMaterial : generates_input_for
    DerivativeParsedMaterial --|> Material : inherits
    KKSMultiFreeEnergy --|> TotalFreeEnergyBase : inherits
    KKSPhaseConcentrationMultiPhaseMaterial --|> Material : inherits
    KKSMultiFreeEnergy ..> DerivativeParsedMaterial : uses_Fj_names
    KKSPhaseConcentrationMultiPhaseMaterial ..> DerivativeParsedMaterial : uses_Fj_names
` ` `


## Notes
The `CALPHAD.md` documentation explicitly states that the `free_energy.py` script is a "work in progress" . This suggests that while the functionality exists, it may still be under active development or refinement. The `PFParamsPolyFreeEnergy` material  is mentioned as calculating properties for a single-component phase field model using polynomial free energies, which is a simpler approach compared to direct CALPHAD coupling and might be used for quantitative models as indicated in `modules/phase_field/doc/content/modules/phase_field/index.md` .

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
