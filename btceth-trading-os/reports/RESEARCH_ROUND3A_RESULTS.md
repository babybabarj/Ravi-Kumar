# Research Round 3A: Remediated Structural Strategy Results

**Dataset Version**: `3.1.0` (48 Months: 2020-01 to 2023-12)  
**2024 Holdout**: `LOCKED` (Unopened)  
**Total Candidates Tested**: `11`  
**Preliminary Pass**: `0`  
**Rejected**: `11`  
**Approved for Shadow**: `0`  
**Approved for Paper**: `0`  

## Remediated Performance Matrix (2020–2022 Dev & 2023 Validation)

| Strategy ID | Family | Asset | Dev Return | Val Base Return | Val Stressed Return | Trades | Daily Sharpe | Max DD | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `STRUCT_A1_BTC_CARRY_8H` | `STRUCT_FAMILY_A_SPOT_PERP_CARRY` | `BTC` | 0.00% | 0.00% | 0.00% | 0 | 0.00 | 0.00% | **REJECTED** |
| `STRUCT_A2_BTC_CARRY_24H` | `STRUCT_FAMILY_A_SPOT_PERP_CARRY` | `BTC` | -0.21% | 0.00% | 0.00% | 0 | 0.00 | 0.00% | **REJECTED** |
| `STRUCT_A3_BTC_CARRY_72H` | `STRUCT_FAMILY_A_SPOT_PERP_CARRY` | `BTC` | 0.01% | 0.00% | 0.00% | 0 | 0.00 | 0.00% | **REJECTED** |
| `STRUCT_A4_ETH_CARRY_24H` | `STRUCT_FAMILY_A_SPOT_PERP_CARRY` | `ETH` | -0.12% | 0.00% | 0.00% | 0 | 0.00 | 0.00% | **REJECTED** |
| `STRUCT_B1_BTC_BASIS_Z20` | `STRUCT_FAMILY_B_BASIS_DISLOCATION` | `BTC` | -0.20% | -0.25% | -0.62% | 1 | -13.51 | 0.25% | **REJECTED** |
| `STRUCT_B2_BTC_BASIS_Z25` | `STRUCT_FAMILY_B_BASIS_DISLOCATION` | `BTC` | -0.20% | -0.24% | -0.61% | 1 | -13.51 | 0.24% | **REJECTED** |
| `STRUCT_C1_BTCETH_REL_FUNDING` | `STRUCT_FAMILY_C_RELATIVE_CARRY` | `BTC/ETH` | -5.06% | 0.00% | 0.00% | 0 | 0.00 | 0.00% | **REJECTED** |
| `STRUCT_D1_BTC_PREMIUM_DIVERGENCE` | `STRUCT_FAMILY_D_FUNDING_PREMIUM_DIVERGENCE` | `BTC` | -0.18% | -0.23% | -0.59% | 1 | -13.51 | 0.23% | **REJECTED** |
| `STRUCT_E1_BTC_CARRY_TIMING` | `STRUCT_FAMILY_E_CARRY_TIMING` | `BTC` | 0.00% | 0.00% | 0.00% | 0 | 0.00 | 0.00% | **REJECTED** |
| `STRUCT_F1_BTC_WEEKEND_REVERSION` | `STRUCT_FAMILY_F_WEEKEND_SESSION_EFFECTS` | `BTC` | -0.21% | -0.27% | -0.64% | 1 | -13.51 | 0.27% | **REJECTED** |
| `STRUCT_G1_BTC_POST_STRESS` | `STRUCT_FAMILY_G_POST_STRESS_REVERSION` | `BTC` | -0.45% | 0.00% | 0.00% | 0 | 0.00 | 0.00% | **REJECTED** |
