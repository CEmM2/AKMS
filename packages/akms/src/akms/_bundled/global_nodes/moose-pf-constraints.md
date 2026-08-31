---
id: moose-pf-constraints
title: MOOSE Constraint enforcement and numerical stabilization
domain: phase-field
subdomain: algorithmic
tags:
- constraints
- lagrange-multiplier
- penalty
- mass-conservation
- nucleation
- interface-width
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-phase-field-numerics
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-phase-field-numerics
---

# MOOSE Constraint enforcement and numerical stabilization

MOOSE employs various numerical techniques for phase field simulations, including specific approaches for nucleation events and time step adaptivity. The framework provides kernels for solving both Allen-Cahn and Cahn-Hilliard equations, allowing for different solution strategies.

## Phase Field Nucleation
MOOSE handles nucleation events through a `DiscreteNucleation` system . This system artificially triggers and stabilizes nuclei formation by locally modifying the free energy density or directly changing an order parameter .

### Classes & Methods
*   `DiscreteNucleationInserter`: A user object that manages a global list of active nucleus positions .
*   `DiscreteNucleationMap`: A user object that maintains a smooth density map for nuclei locations, obtained from a `DiscreteNucleationInserter` .
*   `DiscreteNucleation`: A material that calculates a local free energy penalty based on the difference between concentration variables and their target concentrations .
*   `DiscreteNucleationTimeStep`: A postprocessor that provides a time step limit for new nuclei, used with `IterationAdaptiveDT` .

### Parameters
*   `DiscreteNucleation::penalty`: `Real`, default `20.0`. Penalty factor for enforcing target concentrations .
*   `DiscreteNucleation::penalty_mode`: `MooseEnum`, default `MATCH`. Determines if the target concentration is matched, or taken as a minimum or maximum .
*   `DiscreteNucleationTimeStep::dt_max`: `Real`. Time step to cut back to at the start of a nucleation event .
*   `DiscreteNucleationTimeStep::p2nucleus`: `Real`, range `(0, 1)`. Maximum probability for more than one nucleus to appear during a time step .

### Free Energy Penalty Based Nucleation
The `DiscreteNucleation` material implements a harmonic form of a free energy penalty to bias the system's thermodynamics, driving the formation of nuclei .

### Direct Order Parameter Modification
For non-conserved order parameters, direct modification can be achieved by applying a `DiscreteNucleationForce` and a `Reaction` kernel to a reserved order parameter .

## Time Integration Schemes
MOOSE's `Transient` executioner allows for time-dependent simulations . The `scheme` parameter in the `Executioner` block determines the `TimeIntegrator` to use . While the documentation mentions Backward Euler as a default , it also supports other schemes like BDF2 .

## Time Step Adaptivity
Time step adaptivity is supported through objects like `DiscreteNucleationTimeStep` and `IterationAdaptiveDT` . The `DiscreteNucleationTimeStep` postprocessor limits the time step based on two criteria: a user-defined `dt_max` at nucleus insertion and a nucleation rate-based limit to control the probability of multiple nucleation events within a single time step  .

### Equations
The probability of more than two nucleation events ($p_{2nuc}$) is calculated as:
$$
p_{2nuc} = 1-(1+\lambda_{2nuc})e^{-\lambda_{2nuc}} \label{eq:p2nuc} \tag{1}
$$
where $\lambda_{2nuc}$ is the total nucleation rate over the simulation cell . This equation is numerically inverted to obtain $\lambda_{2nuc}$ for a given $p_{2nuc}$ .

## Mass Conservation for Cahn-Hilliard
The Cahn-Hilliard equation, which describes mass conservation, can be solved in two ways within MOOSE .
1.  **Direct solution of the fourth-order equation**: This involves solving the equation directly .
2.  **Split into two second-order equations**: This approach solves for concentration ($c_i$) and chemical potential ($\mu_i$) separately . This method is noted to improve solve convergence .

### Equations
The residual for the direct solution of the Cahn-Hilliard equation is:
$$
\boldsymbol{\mathcal{R}}_{c_i} = \left( \frac{\partial c_i}{\partial t}, \psi_m \right) + \left( \kappa_i \nabla^2 c_i, \nabla \cdot (M_i \nabla \psi_m ) \right) + \left( M_i \left( \nabla \frac{\partial f_{loc} }{\partial c_i} + \nabla  \frac{\partial E_d}{\partial c_i} \right), \nabla \psi_m \right) \label{eq:ch_direct_residual} \tag{2}
$$ 
For the split form, the two residual equations are:
$$
\begin{aligned}
	\boldsymbol{\mathcal{R}}_{\mu_i} &=& \left(  \frac{\partial c_i}{\partial t}, \psi_m \right) + \left( M_i  \nabla \mu_i, \nabla \psi_m \right) \\
  \boldsymbol{\mathcal{R}}_{c_i} &=& \left( \left( -\kappa_i \nabla^2 c_i +  \frac{\partial f_{loc}}{\partial c_i} + \frac{\partial E_d}{\partial c_i} - \mu_i \right), \psi_m \right)
\end{aligned} \label{eq:ch_split_residual} \tag{3}
$$ 

## Order Parameter Constraint $\Sigma\eta_i = 1$
The provided context does not explicitly detail the numerical techniques used for enforcing the order parameter constraint $\Sigma\eta_i = 1$, such as penalty methods, Lagrange multipliers, or variable elimination.

## Numerical Stabilization
The provided context does not explicitly mention numerical stabilization techniques like anti-trapping currents for sharp-interface limits.

## Interface Width Control
The provided context does not explicitly detail the relationship between $\kappa$, interface width ($W$), and mesh size requirements. However, the `DiscreteNucleationMap` user object has an `int_width` parameter for the nucleus interface width .

## Notes
The MOOSE phase field module is designed to simplify the implementation of phase field models by leveraging common structures like the Cahn-Hilliard and Allen-Cahn equations and free energy functionals . The framework uses PETSc for solving nonlinear equations  and offers different solution methods like `NEWTON`, `JFNK`, and `PJFNK` . Preconditioning options such as LU decomposition and Additive Schwartz Method (ASM) are available to improve performance .

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
