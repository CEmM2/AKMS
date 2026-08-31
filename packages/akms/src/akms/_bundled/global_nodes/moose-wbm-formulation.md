---
id: moose-wbm-formulation
title: MOOSE WBM multi-phase field model formulation
domain: phase-field
subdomain: algorithmic
tags:
- WBM
- KKS
- per-phase-composition
- equal-chemical-potential
- lagrange-multiplier
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

# MOOSE WBM multi-phase field model formulation

The Wheeler-Boettinger-McFadden (WBM) multi-phase field model in MOOSE is a framework for simulating phase transformations with multiple phases and compositions. It distinguishes itself by allowing each phase to have its own composition field, unlike models with a single global composition. MOOSE implements this through specific material and kernel classes that handle the free energy functional, enforce chemical potential equality, and manage phase and composition evolution.

## 1. The WBM Free Energy Functional

The total free energy in the WBM model, as implemented in MOOSE, is expressed as a sum over the individual phase free energies, weighted by switching functions, and includes gradient energy terms. For a multi-phase KKS system, the total free energy $F$ is given by:
$$
F = \sum_i h_i F_i + W \sum_i g_i + \sum_i \frac{\kappa_i}{2} |\nabla \eta_i|^2 \quad (1)
$$ 
Here, $h_i$ are switching functions, $F_i$ are the free energies of each phase $i$, $W$ is a double-well height parameter, $g_i$ are barrier functions, and $\kappa_i$ are gradient energy coefficients associated with the phase field variables $\eta_i$. 
The `KKSMultiFreeEnergy` AuxKernel calculates this total free energy. 

## 2. Key Distinction: Per-Phase Composition Fields

In the WBM model, each phase $i$ has its own composition field $c_i^k$ for component $k$. This is a key distinction from models that use a single global composition. MOOSE handles this by using a nested Newton iteration to solve for these per-phase concentrations.  The `KKSPhaseConcentrationMultiPhaseMaterial` class is responsible for computing these phase concentrations. 

## 3. Equal Chemical Potential Constraint

The constraint of equal chemical potential $\mu_i^k = \mu_j^k$ across phases for each component is enforced through a kernel. For a two-phase system, this is expressed as $dF_a/dc_a = dF_b/dc_b$.  The `KKSPhaseChemicalPotential` kernel enforces this equality.  This kernel takes the free energy functions for two phases (`fa_name` and `fb_name`) and their corresponding concentrations (`variable` for $c_a$ and `cb` for $c_b$) as parameters.  

## 4. Phase Evolution Equation

The phase evolution equation for $\phi_i$ (or $\eta_i$ in MOOSE's implementation) is generally given by:
$$
\frac{\partial \phi_i}{\partial t} = -L \left( \frac{\partial f}{\partial \phi_i} - \kappa \nabla^2 \phi_i + \lambda \right) \quad (2)
$$
where $\lambda$ is a Lagrange multiplier to enforce the constraint $\sum \phi_i = 1$.  MOOSE uses a Lagrange multiplier based constraint for keeping the sum of all phase order parameters equal to one.  This is demonstrated in input files like `lagrange_multiplier.i` where `eta1 + eta2 = 1` is enforced. 

## 5. Diffusion Equations

The evolution of each phase's composition and interdiffusion is handled by ensuring concentration conservation. The `KKSMultiPhaseConcentration` kernel enforces the concentration conservation equation $c = \sum_j h_j c_j$, where $c$ is the physical concentration and $c_j$ are the phase concentrations.  This kernel takes an array of phase concentrations (`cj`), the physical concentration (`c`), and switching functions (`hj_names`) as input. 

## 6. Implementation Classes

The primary MOOSE classes implementing the WBM model, particularly for multi-phase KKS, include:

*   `KKSPhaseChemicalPotential`: A kernel that enforces the equality of chemical potentials between phases. 
*   `KKSMultiPhaseConcentration`: A kernel that enforces the concentration conservation equation for multiple phases. 
*   `KKSPhaseConcentrationMultiPhaseMaterial`: A material class that computes the KKS phase concentrations using a nested Newton iteration to solve the equal chemical potential and concentration conservation equations for multiphase systems. 
*   `KKSMultiFreeEnergy`: An AuxKernel that computes the total free energy in a multi-phase KKS system, including chemical, barrier, and gradient terms. 

## 7. WBM vs. KKS in MOOSE

In MOOSE, the WBM and KKS models are closely related and often discussed within the same framework, particularly for multi-phase systems. The KKS model is a specific type of phase-field model for binary alloys.  The `KKSPhaseChemicalPotential` and `KKSMultiPhaseConcentration` classes are explicitly named with "KKS", indicating their role in implementing the KKS framework.   The documentation refers to "KKS" as a model with "per-phase concentrations, two phases" or "per-phase concentrations, per-sublattice concentrations, multiple phases" . The WBM model is described as handling "$N$ phases, $N$ phase order parameters" . Essentially, the KKS model, as implemented in MOOSE, leverages the WBM framework's ability to handle per-phase compositions and multiple order parameters to describe multi-component, multi-phase systems. The `KKSMultiFreeEnergy` AuxKernel, for instance, computes the total free energy in a "multi-phase KKS system". 

## Classes & Methods

*   `KKSPhaseChemicalPotential::validParams()`: Defines the valid input parameters for the `KKSPhaseChemicalPotential` kernel. 
*   `KKSPhaseChemicalPotential::KKSPhaseChemicalPotential()`: Constructor for the `KKSPhaseChemicalPotential` kernel, initializing member variables. 
*   `KKSMultiPhaseConcentration::validParams()`: Defines the valid input parameters for the `KKSMultiPhaseConcentration` kernel. 
*   `KKSMultiPhaseConcentration::KKSMultiPhaseConcentration()`: Constructor for the `KKSMultiPhaseConcentration` kernel. 
*   `KKSPhaseConcentrationMultiPhaseMaterial::validParams()`: Defines the valid input parameters for the `KKSPhaseConcentrationMultiPhaseMaterial`. 
*   `KKSPhaseConcentrationMultiPhaseMaterial::KKSPhaseConcentrationMultiPhaseMaterial()`: Constructor for the `KKSPhaseConcentrationMultiPhaseMaterial`. 
*   `KKSMultiFreeEnergy::validParams()`: Defines the valid input parameters for the `KKSMultiFreeEnergy` AuxKernel. 
*   `KKSMultiFreeEnergy::KKSMultiFreeEnergy()`: Constructor for the `KKSMultiFreeEnergy` AuxKernel. 

## Equations

### Total Free Energy Functional
$$
F = \sum_i h_i F_i + W \sum_i g_i + \sum_i \frac{\kappa_i}{2} |\nabla \eta_i|^2 \quad (1)
$$ 

### Equal Chemical Potential Constraint
$$
\frac{dF_a}{dc_a} = \frac{dF_b}{dc_b} \quad (2)
$$ 

### Phase Evolution Equation
$$
\frac{\partial \phi_i}{\partial t} = -L \left( \frac{\partial f}{\partial \phi_i} - \kappa \nabla^2 \phi_i + \lambda \right) \quad (3)
$$

### Concentration Conservation
$$
c = \sum_j h_j c_j \quad (4)
$$ 

## Parameters

*   `KKSPhaseChemicalPotential` parameters:
    *   `cb`: Coupled variable for phase b concentration. 
    *   `fa_name`: Base name of the free energy function for phase a. 
    *   `fb_name`: Base name of the free energy function for phase b. 
    *   `ka`: Site fraction for the $c_a$ variable (default: 1.0). 
    *   `kb`: Site fraction for the $c_b$ variable (default: 1.0). 
    *   `args_a`: Vector of further parameters to $F_a$. 
    *   `args_b`: Vector of further parameters to $F_b$. 
*   `KKSMultiPhaseConcentration` parameters:
    *   `cj`: Array of phase concentrations. 
    *   `c`: Physical concentration. 
    *   `etas`: Order parameters for all phases. 
    *   `hj_names`: Switching Function Materials that provide $h(\eta_1, \eta_2, \dots)$. 
*   `KKSPhaseConcentrationMultiPhaseMaterial` parameters:
    *   `global_cs`: The interpolated concentrations. 
    *   `all_etas`: Order parameters. 
    *   `hj_names`: Switching functions in the same order as `all_etas`. 
    *   `Fj_names`: Free energy material objects in the same order as `all_etas

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
