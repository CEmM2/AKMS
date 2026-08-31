---
id: moose-cp-hardening
title: MOOSE Crystal plasticity hardening laws
domain: constitutive
subdomain: algorithmic
tags:
- hardening
- taylor
- voce
- kocks-mecking
- latent-hardening
- slip-resistance
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-crystal-plasticity
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-crystal-plasticity
---

# MOOSE Crystal plasticity hardening laws

The MOOSE framework implements several hardening laws for crystal plasticity, primarily through the `CrystalPlasticityKalidindiUpdate` class and the `CrystalPlasticityStateVarRateComponentVoce` UserObject  . These implementations handle self and latent hardening, and store history variables like slip resistance as material properties  .

## Hardening Laws Implemented

### Kalidindi Hardening Model
The `CrystalPlasticityKalidindiUpdate` class implements the self and latent hardening crystal plasticity model developed by Kalidindi et al. (1992) .

**Equations:**
The slip rate is given by a power law relationship:
$$
\dot{\gamma}^{\alpha} = \dot{\gamma}_o \left| \frac{\tau^{\alpha}}{g^{\alpha}} \right|^{1/m} sign \left( \tau^{\alpha} \right) \quad (1)
$$ 
where $\dot{\gamma}_o$ is a reference slip rate, $\tau^{\alpha}$ is the applied shear stress, $g^{\alpha}$ is the slip system strength (resistance to slip), and $m$ is the strain rate sensitivity exponent .

The evolution of slip system strength (resistance) is given by:
$$
g^{\alpha} = g_o + \Delta \gamma^{\alpha} q^{\alpha \beta} h_o \left| 1 - \frac{g^{\alpha}}{g_{sat}} \right|^a sign \left( 1 - \frac{g^{\alpha}}{g_{sat}} \right) \quad (2)
$$ 
where $q^{\alpha \beta}$ is the hardening coefficient matrix, $h_o$ is an initial hardening term, $g_{sat}$ is the saturated hardening value, and $a$ is the hardening exponent .

The hardening coefficient matrix $q^{\alpha \beta}$ for an FCC system is defined as:
$$
q^{\alpha \beta} = \begin{Bmatrix}
                       1.0 & q   & q   & q  \\
                       q   & 1.0 & q   & q  \\
                       q   & q   & 1.0 & q  \\
                       q   & q   & q   & 1.0
                     \end{Bmatrix} \quad (3)
$$ 
where $q$ is a constant value of latent hardening among non-coplanar slip systems .

**Classes & Methods:**
*   `CrystalPlasticityKalidindiUpdate::validParams()`: Defines the input parameters for the Kalidindi hardening model .
*   `CrystalPlasticityKalidindiUpdate::initQpStatefulProperties()`: Initializes stateful properties like slip system resistances .
*   `CrystalPlasticityKalidindiUpdate::setInitialConstitutiveVariableValues()`: Sets initial values for constitutive variables .
*   `CrystalPlasticityKalidindiUpdate::calculateSlipRate()`: Calculates the slip rate for each slip system .
*   `CrystalPlasticityKalidindiUpdate::calculateStateVariableEvolutionRateComponent()`: Calculates the slip system resistance increment based on Kalidindi et al. (1992) .
*   `CrystalPlasticityKalidindiUpdate::updateStateVariables()`: Finalizes the values of state variables after convergence .

**Parameters:**
The `CrystalPlasticityKalidindiUpdate` class uses the following parameters :
*   `r`: Latent hardening coefficient (default: 1.0) 
*   `h`: Hardening constant (default: 541.5) 
*   `t_sat`: Saturated slip system strength (default: 109.8) 
*   `gss_a`: Coefficient for hardening (default: 2.5) 
*   `ao`: Slip rate coefficient (default: 0.001) 
*   `xm`: Exponent for slip rate (default: 0.1) 
*   `gss_initial`: Initial lattice friction strength (default: 60.8) 
*   `total_twin_volume_fraction`: Name of the material property for total twin volume fraction, if twinning is considered .

### Voce Hardening Model
The `CrystalPlasticityStateVarRateComponentVoce` UserObject implements a phenomenological Voce constitutive model for state variable evolution .

**Equations:**
The hardening rate `hb(i)` for a slip system `i` is calculated as:
$$
hb(i) = h_0 \left| 1 - \frac{g^{\alpha} - \tau_0}{\tau_{sat} - \tau_0} \right|^{hardening\_exponent} \text{sign}\left(1 - \frac{g^{\alpha} - \tau_0}{\tau_{sat} - \tau_0}\right) \quad (4)
$$ 
where $h_0$ is an initial hardening constant, $\tau_0$ is the initial critical resolved shear stress, $\tau_{sat}$ is the saturation resolved shear stress, and $hardening\_exponent$ is the hardening exponent .
The evolution rate of the state variable `val[i]` is then calculated by summing contributions from all slip systems `j`, considering self and latent hardening coefficients `q_ab`:
$$
val[i] += |\dot{\gamma}_{j}| \cdot q_{ab} \cdot hb(j) \quad (5)
$$ 

**Classes & Methods:**
*   `CrystalPlasticityStateVarRateComponentVoce::validParams()`: Defines input parameters for the Voce hardening model .
*   `CrystalPlasticityStateVarRateComponentVoce::calcStateVariableEvolutionRateComponent()`: Computes the slip system hardening rate .
*   `CrystalPlasticityStateVarRateComponentVoce::getHardeningCoefficient()`: Retrieves the appropriate self/latent hardening coefficient .

**Parameters:**
The `CrystalPlasticityStateVarRateComponentVoce` class uses the following parameters :
*   `uo_slip_rate_name`: Name of the slip rate property.
*   `uo_state_var_name`: Name of the state variable property.
*   `crystal_lattice_type`: Type of crystal lattice structure (e.g., "FCC", "BCC").
*   `groups`: Defines slip system groups (e.g., '0 12 24 48').
*   `h0_group_values`: `h0` hardening constant for each group.
*   `tau0_group_values`: Initial critical resolved shear stress for each group.
*   `tauSat_group_values`: Saturation resolved shear stress for each group.
*   `hardeningExponent_group_values`: Hardening exponent for each group.
*   `selfHardening_group_values`: Self-hardening coefficient `q_aa` for each group.
*   `coplanarHardening_group_values`: Coplanar latent hardening coefficient `q_ab` for each group.
*   `GroupGroup_Hardening_group_values`: Group-to-group latent hardening coefficient `q_ab` (N x N matrix).

**MOOSE Input Syntax Example:**
` ` `ini
[UserObjects]
  [./state_var_evol_rate_comp_voce]
    type = CrystalPlasticityStateVarRateComponentVoce
    variable_size = 48
    crystal_lattice_type = 'BCC'
    groups = '0 12 24 48'
    h0_group_values = '1 2 3'
    tau0_group_values = '50 51 52'
    tauSat_group_values = '70 81 92'
    hardeningExponent_group_values = '1 2 3'
    selfHardening_group_values ='4 5 6'
    coplanarHardening_group_values='7 8 9'
    GroupGroup_Hardening_group_values = '10 20 30
                                         40 50 60
                                         70 80 90'
    uo_slip_rate_name = slip_rate_gss
    uo_state_var_name = state_var_gss
  [../]
[]
` ` ` 

### Beyerlein Hardening Model (HCP)
The `CrystalPlasticityHCPDislocationSlipBeyerleinUpdate` class implements a constitutive model for the glide and evolution of forest dislocations within an HCP crystal lattice . This model considers contributions from initial lattice friction, Hall-Petch type hardening, forest dislocations, and substructure density .

**Equations:**
The total slip resistance $g^{\alpha}$ is the sum of four terms:
$$
g^{\alpha} = g^{\alpha}_o + g^{\alpha}_{HP} + g^{\alpha}_{forest} + g^{\alpha}_{sub} \quad (6)
$$ 
where $g^{\alpha}_o$ is initial lattice friction, $g^{\alpha}_{HP}$ is Hall-Petch hardening, $g^{\alpha}_{forest}$ is forest dislocation hardening, and $g^{\alpha}_{sub}$ is substructure hardening .

Hall-Petch hardening:
$$
g^{\alpha}_{HP} = HP^{\alpha}\mu^{\alpha} \sqrt{\frac{b^{\alpha}}{d_g}} \quad (7)
$$

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
