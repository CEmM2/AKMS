---
id: moose-allen-cahn-kernels
title: MOOSE Allen-Cahn kernel implementation details
domain: phase-field
subdomain: algorithmic
tags:
- allen-cahn
- ACInterface
- gradient-energy
- mobility
- weak-form
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-allen-cahn-cahn-hilliard
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-allen-cahn-cahn-hilliard
---

# MOOSE Allen-Cahn kernel implementation details

The Allen-Cahn kernels in MOOSE are designed to solve the Allen-Cahn equation, which describes the evolution of an order parameter ($\eta$) in phase-field models. The equation is typically split into several terms, each handled by a specific kernel for modularity. The core kernels discussed are `AllenCahn` (or `ACBulk`), `ACInterface`, and `TimeDerivative`, which together form the weak form of the Allen-Cahn equation.

## Classes & Methods

*   `AllenCahn::validParams()`: Defines the valid input parameters for the `AllenCahn` kernel. 
*   `AllenCahn::AllenCahn()`: Constructor for the `AllenCahn` kernel, initializing material properties for free energy derivatives. 
*   `AllenCahn::initialSetup()`: Performs initial validation for nonlinear coupling and derivative material properties. 
*   `AllenCahn::computeDFDOP()`: Computes the derivative of the bulk free energy with respect to the order parameter for either residual or Jacobian calculations. 
*   `ACInterface::validParams()`: Defines the valid input parameters for the `ACInterface` kernel. 
*   `ACInterface::ACInterface()`: Constructor for the `ACInterface` kernel, initializing material properties for mobility and interfacial parameters, and their derivatives. 
*   `ACInterface::initialSetup()`: Performs initial validation for mobility and kappa material properties. 
*   `ACInterface::computeQpResidual()`: Computes the residual contribution of the gradient energy term at a quadrature point. 
*   `ACInterface::computeQpJacobian()`: Computes the Jacobian contribution of the gradient energy term at a quadrature point. 
*   `ADAllenCahn::validParams()`: Defines valid parameters for the AD version of the Allen-Cahn bulk kernel. 
*   `ADACInterface::validParams()`: Defines valid parameters for the AD version of the Allen-Cahn interface kernel. 
*   `ACBulk<T>::validParams()`: Defines valid parameters for the base `ACBulk` kernel. 
*   `ACBulk<T>::precomputeQpResidual()`: Computes the residual contribution for the bulk term, multiplying the mobility by the free energy derivative. 
*   `ADAllenCahnBase<T>::precomputeQpResidual()`: Computes the residual for the AD bulk term, similar to `ACBulk`. 

## Equations

The general form of the Allen-Cahn equation is:
$$
\frac{\partial \eta_i}{\partial t} = - L \frac{\delta F}{\delta \eta_i} \quad (1)
$$ 
where $F$ is the free energy functional. The free energy functional typically includes local and gradient energy terms:
$$
F = \int_V f_{loc}(\eta_0, \eta_1, \ldots, \eta_N) + f_{add} (\eta_0, \eta_1, \ldots, \eta_N) + \kappa \sum^N_i |\nabla \eta_i|^2 \quad (2)
$$ 

The weak form of the Allen-Cahn equation, without boundary terms, is given by:
$$
\boldsymbol{\mathcal{R}}_{\eta_i} = \left( \frac{\partial \eta_j}{\partial t}, \psi_m \right) + \left( \nabla(\kappa_j\eta_j), \nabla (L\psi_m) \right) + L \left( \frac{\partial f_{loc}}{\partial \eta_j} + \frac{\partial E_d}{\partial \eta_j}, \psi_m \right) \quad (3)
$$ 
This residual is split into three parts, each handled by a specific kernel.

### 1. `AllenCahn` kernel: what weak form does it implement? ∫ L·∂f/∂η·ψ dΩ?

The `AllenCahn` kernel implements the bulk or local energy term of the Allen-Cahn equation. Its contribution to the residual is:
$$
L \left( \frac{\partial f_{loc}}{\partial \eta_j} + \frac{\partial E_d}{\partial \eta_j}, \psi_m \right) \quad (4)
$$ 
This corresponds to $\int L \cdot \frac{\partial f}{\partial \eta} \cdot \psi \, d\Omega$, where $f$ represents the local free energy density ($f_{loc} + E_d$). 
The `AllenCahn` class inherits from `ACBulk<Real>`  and uses a `DerivativeMaterial` to obtain the free energy derivatives. 
The `computeDFDOP` method returns the derivative of the free energy with respect to the order parameter, $\frac{\partial F}{\partial \eta}$, for the residual calculation. 
The `precomputeQpResidual` method in `ACBulk` then multiplies this by the mobility $L$. 

### 2. `ACInterface` kernel: the gradient energy term ∫ κ·∇η·∇ψ dΩ — how is κ specified?

The `ACInterface` kernel implements the gradient energy term. Its contribution to the residual is:
$$
\left( \nabla(\kappa_j\eta_j), \nabla (L\psi_m) \right) \quad (5)
$$ 
This term is derived from $\int \kappa \nabla \eta \cdot \nabla (L\psi) \, d\Omega$. 
The parameter $\kappa$ (interfacial parameter) is specified as a `MaterialProperty<Real>` named `kappa_name` in the input file.  It can be a constant value or a function of MOOSE variables. 
The `ACInterface` kernel retrieves $\kappa$ using `getMaterialProperty<Real>("kappa_name")`. 

### 3. `TimeDerivative` for ∂η/∂t

The `TimeDerivative` kernel implements the transient term of the Allen-Cahn equation. Its contribution to the residual is:
$$
\left( \frac{\partial \eta_j}{\partial t}, \psi_m \right) \quad (6)
$$ 
This term is standard in MOOSE for time-dependent problems. 

### 4. How do these three kernels combine to solve ∂η/∂t = -L·(∂f/∂η - κ∇²η)?

The three kernels (`TimeDerivative`, `AllenCahn`, and `ACInterface`) combine to solve the weak form of the Allen-Cahn equation. The strong form of the equation is:
$$
\frac{\partial \eta}{\partial t} = -L \left( \frac{\partial f}{\partial \eta} - \nabla \cdot (\kappa \nabla \eta) \right) \quad (7)
$$
Rearranging this to a residual form for finite element solution:
$$
\mathcal{R} = \frac{\partial \eta}{\partial t} + L \frac{\partial f}{\partial \eta} - L \nabla \cdot (\kappa \nabla \eta) = 0 \quad (8)
$$
Multiplying by a test function $\psi$ and integrating over the domain $\Omega$:
$$
\int_\Omega \left( \frac{\partial \eta}{\partial t} \right) \psi \, d\Omega + \int_\Omega L \frac{\partial f}{\partial \eta} \psi \, d\Omega - \int_\Omega L \nabla \cdot (\kappa \nabla \eta) \psi \, d\Omega = 0 \quad (9)
$$
Applying integration by parts to the third term (gradient energy term):
$$
- \int_\Omega L \nabla \cdot (\kappa \nabla \eta) \psi \, d\Omega = \int_\Omega L \kappa \nabla \eta \cdot \nabla \psi \, d\Omega - \int_{\partial\Omega} L \kappa (\nabla \eta \cdot \mathbf{n}) \psi \, dS \quad (10)
$$
Assuming natural boundary conditions (the surface integral is zero), the weak form becomes:
$$
\left( \frac{\partial \eta}{\partial t}, \psi \right) + \left( L \frac{\partial f}{\partial \eta}, \psi \right) + \left( L \kappa \nabla \eta, \nabla \psi \right) = 0 \quad (11)
$$
The MOOSE implementation uses a slightly different form for the gradient term, $\left( \nabla(\kappa_j\eta_j), \nabla (L\psi_m) \right)$, which is equivalent under certain assumptions or when $L$ and $\kappa$ are constants. 
Each kernel contributes its part to the overall residual:
*   `TimeDerivative`: $\left( \frac{\partial \eta_j}{\partial t}, \psi_m \right)$ 
*   `AllenCahn`: $L \left( \frac{\partial f_{loc}}{\partial \eta_j} + \frac{\partial E_d}{\partial \eta_j}, \psi_m \right)$ 
*   `ACInterface`: $\left( \nabla(\kappa_j\eta_j), \nabla (L\psi_m) \right)$ 

These terms are summed up by the MOOSE framework to form the complete residual equation for the order parameter $\eta$.

### 5. `ACBulk` vs `AllenCahn` — is there a difference?

`ACBulk` is a templated base class for the bulk or local energy term of the Allen-Cahn equation.  It handles the mobility `L` and its derivatives. 
`AllenCahn` is a concrete implementation that inherits from `ACBulk<Real>`.  It specifically uses a `DerivativeMaterial` to obtain the free energy function and its derivatives. 
Therefore, `ACBulk` provides the general framework for the bulk term, while `AllenCahn` is a specific kernel that uses a `DerivativeParsedMaterial` for the free energy.

### 6. AD versions: `ADAllenCahn`, `ADACInterface` — advantages?

`ADAllenCahn` and `ADACInterface` are the Automatic Differentiation (AD) versions of the `AllenCahn` and `ACInterface` kernels, respectively.  
The primary advantage of using AD kernels is that they automatically compute the Jacobian terms required for Newton's method, which is used to solve the nonlinear system of equations. This eliminates the need for manual derivation and implementation of complex Jacobian expressions, reducing the potential for errors and simplifying code maintenance. 
For example, `ADACInterface` inherits from `ADKernel` and `DerivativeMaterialPropertyNameInterface`

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
