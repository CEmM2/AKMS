---
id: moose-allen-cahn-cahn-hilliard
title: MOOSE Allen-Cahn and Cahn-Hilliard Kernels — Detailed Implementation
domain: phase-field
subdomain: algorithmic
tags:
- allen-cahn
- cahn-hilliard
- split-form
- weak-form
- gradient-energy
- chemical-potential
- mobility
- AD-kernel
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: moose-derivative-parsed-material
  type: requires
  weight: 0.6
  note: Uses DerivativeParsedMaterial for free energy definitions
- to: cm-phase-field-fracture
  type: implements
  weight: 0.7
  note: AC/CH kernels are the core discretization for all phase field models
- to: tgs-dom-fem
  type: implements
  weight: 0.5
  note: Allen-Cahn and Cahn-Hilliard weak forms as FEM kernels
---

# MOOSE Allen-Cahn and Cahn-Hilliard Kernels — Detailed Implementation

Framework knowledge node covering 2 aspect(s) of Allen-Cahn and Cahn-Hilliard Kernels — Detailed Implementation.

## Allen-Cahn kernel implementation details

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


## Cahn-Hilliard kernel implementation details

The MOOSE framework provides two primary implementations for the Cahn-Hilliard equation: a direct form and a split form. The direct form uses the `CahnHilliard` and `CHInterface` kernels to solve the fourth-order equation directly, while the split form decomposes the problem into two second-order equations solved by `SplitCHParsed` and `SplitCHWRes` kernels. The split form is generally preferred due to improved convergence properties and avoidance of C1 continuity requirements.

## 1. Direct Form: `CahnHilliard` kernel — the biharmonic $\nabla^4 c$ problem — how handled?

The direct form of the Cahn-Hilliard equation is solved using a combination of kernels, primarily `CahnHilliard` and `CHInterface` . The full weak form for the direct solution of the Cahn-Hilliard equation is given by:
$$
\boldsymbol{\mathcal{R}}_{c_i} = \left( \frac{\partial c_i}{\partial t}, \psi_m \right) + \left( \kappa_i \nabla^2 c_i, \nabla \cdot (M_i \nabla \psi_m ) \right) + \left( M_i \left( \nabla \frac{\partial f_{loc} }{\partial c_i} + \nabla  \frac{\partial E_d}{\partial c_i} \right), \nabla \psi_m \right) \quad (1)
$$ 

The `CahnHilliard` kernel implements the bulk free energy term :
$$
\left(M \sum_j\nabla c_j\frac{\partial^2 f}{\partial c_i c_j}, \nabla \psi\right)
$$ 
This corresponds to the term $\left( M_i \left( \nabla \frac{\partial f_{loc} }{\partial c_i} + \nabla  \frac{\partial E_d}{\partial c_i} \right), \nabla \psi_m \right)$ in Equation (1) .

The `CHInterface` kernel handles the gradient energy term :
$$
\left( \kappa_i \nabla^2 c_i, \nabla \cdot (M_i \nabla \psi_m ) \right)
$$ 
This term involves second-order derivatives of the concentration variable, which, when combined with the test function's derivatives, effectively addresses the biharmonic nature of the direct Cahn-Hilliard equation.

## 2. Split Form: separate equations for $\mu$ and $c$ — `SplitCHParsed` + `SplitCHWRes` — what does each solve?

The split form of the Cahn-Hilliard equation introduces an auxiliary variable, the chemical potential $\mu$, to break down the fourth-order equation into two coupled second-order equations . The two residual equations in weak form are:
$$
\begin{aligned}
	\boldsymbol{\mathcal{R}}_{\mu_i} &=& \left(  \frac{\partial c_i}{\partial t}, \psi_m \right) + \left( M_i  \nabla \mu_i, \nabla \psi_m \right) \\
  \boldsymbol{\mathcal{R}}_{c_i} &=& \left( \left( -\kappa_i \nabla^2 c_i +  \frac{\partial f_{loc}}{\partial c_i} + \frac{\partial E_d}{\partial c_i} - \mu_i \right), \psi_m \right)
\end{aligned} \quad (2)
$$ 

*   **`SplitCHWRes`**: This kernel contributes to the residual equation for the chemical potential $\mu$ . Specifically, it implements the term $\left( M_i  \nabla \mu_i, \nabla \psi_m \right)$ from the first equation in (2) . It takes the mobility `mob_name` as a parameter .
*   **`SplitCHParsed`**: This kernel contributes to the residual equation for the concentration $c$ . It implements the term $\left( \left( -\kappa_i \nabla^2 c_i +  \frac{\partial f_{loc}}{\partial c_i} + \frac{\partial E_d}{\partial c_i} - \mu_i \right), \psi_m \right)$ from the second equation in (2) . It requires the free energy function name `f_name`, the gradient energy coefficient `kappa_name`, and the chemical potential variable `w` (which represents $\mu$) .

## 3. Why is the split form preferred? Avoids C1 continuity requirements?

The split form is preferred because it improves solve convergence . While the documentation doesn't explicitly state "avoids C1 continuity requirements," the decomposition of the fourth-order equation into two second-order equations inherently relaxes the continuity requirements for the finite element basis functions. Solving a fourth-order PDE directly typically requires C1 continuous basis functions (i.e., functions whose first derivatives are also continuous), which are more complex to implement and computationally more expensive than the C0 continuous basis functions (only the function itself is continuous) sufficient for second-order PDEs.

## 4. The chemical potential variable $\mu$: how is it defined as $\mu = \partial f/\partial c$?

In the split form, the chemical potential $\mu$ is implicitly defined through the second residual equation in (2) . The term $\left( \left( -\kappa_i \nabla^2 c_i +  \frac{\partial f_{loc}}{\partial c_i} + \frac{\partial E_d}{\partial c_i} - \mu_i \right), \psi_m \right)$ effectively enforces the relationship:
$$
\mu_i = \frac{\partial f_{loc}}{\partial c_i} + \frac{\partial E_d}{\partial c_i} - \kappa_i \nabla^2 c_i \quad (3)
$$
This equation defines $\mu_i$ as the variational derivative of the total free energy with respect to $c_i$. The `SplitCHParsed` kernel uses the free energy function and its derivatives, typically provided by a `DerivativeParsedMaterial`, to compute the $\frac{\partial f_{loc}}{\partial c_i}$ and $\frac{\partial E_d}{\partial c_i}$ terms .

## 5. `CHInterface` kernel for the gradient energy: $\int \kappa \cdot \nabla c \cdot \nabla \psi \, d\Omega$

The `CHInterface` kernel implements the interfacial or gradient energy term of the Cahn-Hilliard equation . In the direct form, this corresponds to the term $\left( \kappa_i \nabla^2 c_i, \nabla \cdot (M_i \nabla \psi_m ) \right)$ in Equation (1) . The `computeQpResidual` method in `CHInterfaceBase` shows the calculation of this residual term .

## 6. Mobility in Cahn-Hilliard: `CoupledMaterialDerivative` or how $\nabla \cdot (M \nabla \mu)$ is discretized

The mobility term $\nabla \cdot (M \nabla \mu)$ appears in the strong form of the Cahn-Hilliard equation. In the weak form for the split formulation, this term becomes $\left( M_i  \nabla \mu_i, \nabla \psi_m \right)$ . This term is implemented by the `SplitCHWRes` kernel . The `computeQpResidual` method in `ADSplitCHWResBase` (an AD version of `SplitCHWResBase`) shows the calculation of this term as `_mob[_qp] * _grad_u[_qp]` , where `_grad_u` is the gradient of the variable the kernel is operating on (which is $\mu$ in this case) and `_mob` is the mobility material property.

## 7. Variable mobility: $M(c)$ — how its derivative enters the Jacobian

When the mobility $M$ is a function of concentration $c$, i.e., $M(c)$, its derivative with respect to $c$ enters the Jacobian. In the `CHInterfaceBase` kernel, which is used in the direct formulation, the `computeQpJacobian` method explicitly includes terms involving derivatives of the mobility, such as `_dMdc` and `_d2Mdc2` . These represent $\frac{\partial M}{\partial c}$ and $\frac{\partial^2 M}{\partial c^2}$ respectively. Similarly, for coupled variables, `_dMdarg` and `_d2Mdcdarg` are used .

In the split form, for the `SplitCHWResBase` kernel, if the mobility `_mob` depends on coupled variables, its derivatives `_dmobdarg` are used in `computeQpOffDiagJacobian` to calculate the off-diagonal Jacobian entries .

## Classes & Methods

*   `CahnHilliard::CahnHilliard()`: Implements the bulk free energy term for the direct Cahn-Hilliard formulation. 
*   `CHInterface::CHInterface()`: Implements the gradient energy term for the direct Cahn-Hilliard formulation. 
*   `SplitCHParsed::SplitCHParsed()`: Implements the concentration residual equation in the split Cahn-Hilliard formulation, including free energy and gradient terms. 
*   `SplitCHWRes::SplitCHWRes()`: Implements the chemical potential residual equation in the split Cahn-Hilliard formulation, including the mobility term. 
*   `CHInterfaceBase::computeQpResidual()`: Calculates the residual for the gradient energy term in the direct Cahn-Hilliard equation. 
*   `CHInterfaceBase::computeQpJacobian()`: Calculates the Jacobian for the gradient energy term, including mobility derivatives. 
*   `ADSplitCHWResBase::precomputeQpResidual()`: Calculates the residual for the chemical potential equation in the split Cahn-Hilliard formulation. 
*   `SplitCHWResBase::computeQpOffDiagJacobian()`: Calculates off-diagonal Jacobian entries for the chemical potential equation, considering mobility derivatives. 
*   `SplitCHCRes::computeQpResidual()`: Calculates the residual for the concentration equation in the split Cahn-Hilliard formulation. 
*   `SplitCHCRes::computeQpJacobian()`: Calculates the Jacobian for the concentration equation. 
*   `SplitCHCRes::computeQpOffDiagJacobian()`: Calculates off-diagonal Jacobian entries for the concentration equation. 

## Equations

**Direct Cahn-Hilliard Weak Form:**
$$
\boldsymbol{\mathcal{R}}_{c_i} = \left(  \frac{\partial c_i}{\partial t}, \psi_m \right) + \left( \kappa_i \nabla^2 c_i, \nabla \cdot (

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
