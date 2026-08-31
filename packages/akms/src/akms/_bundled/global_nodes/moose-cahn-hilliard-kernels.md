---
id: moose-cahn-hilliard-kernels
title: MOOSE Cahn-Hilliard kernel implementation details
domain: phase-field
subdomain: algorithmic
tags:
- cahn-hilliard
- split-form
- SplitCHParsed
- SplitCHWRes
- biharmonic
- chemical-potential
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

# MOOSE Cahn-Hilliard kernel implementation details

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
