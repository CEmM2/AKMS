---
id: moose-return-mapping-algorithm
title: MOOSE Return mapping algorithm deep dive
domain: constitutive
subdomain: algorithmic
tags:
- return-mapping
- newton-iteration
- bisection
- line-search
- convergence
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-return-mapping-base
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-return-mapping-base
- to: cm-anisotropic-yield
  type: implements
  weight: 0.8
  note: Newton-Raphson return mapping with fallback strategies
---

# MOOSE Return mapping algorithm deep dive

The `SingleVariableReturnMappingSolution` class in MOOSE provides a framework for solving a scalar nonlinear equation using Newton-Raphson iteration, with optional line search and bisection fallback, to determine an inelastic strain increment. This class is fundamental to various stress update models in solid mechanics, such as `RadialReturnStressUpdate` and `GeneralizedRadialReturnStressUpdate`.

## Classes & Methods

*   `SingleVariableReturnMappingSolutionTempl<is_ad>::returnMappingSolve(const GenericReal<is_ad> & effective_trial_stress, GenericReal<is_ad> & scalar, const ConsoleStream & console)`: The main entry point for performing the return mapping iterations to solve for the scalar inelastic strain increment. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::computeResidual(const GenericReal<is_ad> & effective_trial_stress, const GenericReal<is_ad> & scalar)`: Computes the residual $R(\Delta\gamma)$ of the nonlinear equation. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::computeDerivative(const GenericReal<is_ad> & effective_trial_stress, const GenericReal<is_ad> & scalar)`: Computes the derivative of the residual $dR/d\Delta\gamma$. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::computeResidualAndDerivative(const GenericReal<is_ad> & effective_trial_stress, const GenericChainedReal<is_ad> & scalar)`: Computes both the residual and its derivative, used when automatic differentiation is enabled. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::initialGuess(const GenericReal<is_ad> & effective_trial_stress)`: Provides an initial guess for the scalar variable. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::minimumPermissibleValue(const GenericReal<is_ad> & effective_trial_stress)`: Returns the minimum allowed value for the scalar. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::maximumPermissibleValue(const GenericReal<is_ad> & effective_trial_stress)`: Returns the maximum allowed value for the scalar. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::computeReferenceResidual(const GenericReal<is_ad> & effective_trial_stress, const GenericReal<is_ad> & scalar)`: Computes a reference quantity for relative convergence checks. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::internalSolve(const GenericReal<is_ad> effective_trial_stress, GenericReal<is_ad> & scalar, std::stringstream * iter_output)`: The internal method that executes the Newton-Raphson iterations. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::convergedAcceptable(const unsigned int it, const Real reference)`: Checks for acceptable (relaxed) convergence. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::checkPermissibleRange(GenericReal<is_ad> & scalar, GenericReal<is_ad> & scalar_increment, const GenericReal<is_ad> & scalar_old, const GenericReal<is_ad> min_permissible_scalar, const GenericReal<is_ad> max_permissible_scalar, std::stringstream * iter_output)`: Ensures the scalar solution remains within permissible bounds. 
*   `SingleVariableReturnMappingSolutionTempl<is_ad>::updateBounds(const GenericReal<is_ad> & scalar, const GenericReal<is_ad> & residual, const Real init_resid_sign, GenericReal<is_ad> & scalar_upper_bound, GenericReal<is_ad> & scalar_lower_bound, std::stringstream * iter_output)`: Updates the bounds for bisection fallback. 
*   `RadialReturnStressUpdateTempl<is_ad>::computeStressInitialize(const GenericReal<is_ad> & effective_trial_stress, const GenericRankFourTensor<is_ad> & elasticity_tensor)`: A hook for derived classes to perform initialization before the return mapping solve. 
*   `RadialReturnStressUpdateTempl<is_ad>::computeStressFinalize(const GenericRankTwoTensor<is_ad> & inelasticStrainIncrement)`: A hook for derived classes to finalize state after the return mapping solve. 

## Algorithm Steps

The `SingleVariableReturnMappingSolution` class implements a Newton-Raphson solver with optional line search and bisection fallback. The core algorithm is executed within the `internalSolve` method. 

### 1. Trial Elastic Stress Computation and Effective Stress Evaluation

Before the return mapping iterations begin, the material model computes a trial elastic stress state. For example, in `RadialReturnStressUpdate`, the deviatoric trial stress is computed from `stress_new`, and then the effective trial stress is calculated as:
$$ \sigma_{eff}^{trial} = \sqrt{\frac{3}{2} \mathbf{s}^{trial} : \mathbf{s}^{trial}} $$
where $\mathbf{s}^{trial}$ is the deviatoric trial stress.  This `effective_trial_stress` is then passed to the `returnMappingSolve` method. 

### 2. Scalar Nonlinear Equation: Residual $R(\Delta\gamma)$ and its Derivative $dR/d\Delta\gamma$

The algorithm solves for a scalar variable, typically denoted as $\Delta\gamma$, which represents the effective inelastic strain increment. The specific form of the residual $R(\Delta\gamma)$ and its derivative $dR/d\Delta\gamma$ are model-dependent and must be implemented by derived classes through the `computeResidual` and `computeDerivative` virtual methods, respectively.  If automatic differentiation is enabled (`_ad_derivative = true`), the `computeResidualAndDerivative` method must be overridden.  The residual is expected to be in strain increment units for consistency. 

### 3. Newton-Raphson Iteration with Line Search

The `returnMappingSolve` method orchestrates the Newton-Raphson iterations. 

` ` `pseudocode
function returnMappingSolve(effective_trial_stress, scalar)
  scalar_old = initialGuess(effective_trial_stress)
  residual_old = computeResidual(effective_trial_stress, scalar_old)
  derivative_old = computeDerivative(effective_trial_stress, scalar_old)

  loop for _max_its iterations:
    scalar_increment = -residual_old / derivative_old

    if _line_search is true:
      // Line search activation and procedure
      alpha = 1.0
      while (new_residual > (1 - alpha * line_search_tolerance) * residual_old) and (alpha > min_line_search_step_size):
        alpha = alpha * 0.5
        scalar_trial = scalar_old + alpha * scalar_increment
        new_residual = computeResidual(effective_trial_stress, scalar_trial)
      scalar_new = scalar_old + alpha * scalar_increment
    else:
      scalar_new = scalar_old + scalar_increment

    // Check and enforce permissible range
    checkPermissibleRange(scalar_new, scalar_increment, scalar_old, min_permissible_scalar, max_permissible_scalar)

    residual_new = computeResidual(effective_trial_stress, scalar_new)
    derivative_new = computeDerivative(effective_trial_stress, scalar_new)

    // Check convergence criteria
    if converged(residual_new, reference_residual):
      break
    
    // Update bounds for bisection fallback
    updateBounds(scalar_new, residual_new, initial_residual_sign, scalar_upper_bound, scalar_lower_bound)

    scalar_old = scalar_new
    residual_old = residual_new
    derivative_old = derivative_new
` ` `

Line search activates when the `_line_search` parameter is set to `true`.  It is used to improve convergence by ensuring that each step reduces the residual. If a full Newton step does not reduce the residual sufficiently, the step size is halved until a reduction is achieved or a minimum step size is reached. 

### 4. Bisection/Bracket Fallback

If the Newton-Raphson iteration fails to converge or produces a solution outside the permissible range, a bisection method can be used as a fallback if `_bracket_solution` is `true`.  The `updateBounds` method maintains upper and lower bounds for the scalar, which are used to bracket the root.  If the solution goes out of bounds, it can be reset to the midpoint of the bracket.

### 5. Convergence Criteria

Convergence is determined by checking both absolute and relative tolerances against the residual. 

*   `_absolute_tolerance`: The absolute tolerance for the residual. 
*   `_relative_tolerance`: The relative tolerance for the residual, typically compared against a reference residual computed by `computeReferenceResidual`. 

Additionally, an "acceptable convergence" criterion is available, controlled by `_acceptable_multiplier`.  The `convergedAcceptable` method checks if the residual is within these relaxed limits, particularly when progress on reducing the residual has stalled. 

### 6. The `_effective_inelastic_strain_increment` Output and Feedback

The primary output of the `returnMappingSolve` method is the `scalar` variable, which represents the effective inelastic strain increment ($\Delta\gamma$).  In derived classes like `RadialReturnStressUpdate`, this scalar is stored in the `_effective_inelastic_strain_increment` member variable.  This value is then used to compute the tensorial `inelastic_strain_increment` and update the `stress_new`.  The `inelastic_strain_increment` is subtracted from the total `strain_increment` to obtain the elastic strain increment, which is then used to update the stress. 

### 7. `returnMappingSolve()` Entry Point and `computeStressInitialize()`/`computeStressFinalize()` Hooks

The `returnMappingSolve` method is the entry point for the return mapping algorithm.  It is typically called from the `updateState` method of a derived stress update material. For example, in `RadialReturnStressUpdate`, it is called after computing the `effective_trial_stress`. 

The `computeStressInitialize()` and `computeStressFinalize()` methods are virtual hooks provided for derived classes to perform model-specific setup and cleanup tasks before and after the return mapping iterations, respectively.  For instance, `RadialReturnStressUpdate` uses `computeStressInitialize` to set up material properties like `_three_shear_modulus` and `computeStressFinalize` to perform any final state updates.  

## Parameters

*   `_relative_tolerance`: `Real` - Relative convergence tolerance.

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
