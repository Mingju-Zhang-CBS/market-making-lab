# Walkthrough: value, trade, mark and settle

## Backward valuation

At expiry, state +1 pays 1 and state 0 pays 0. One step before expiry at state 0, the up branch reaches +1 and the stay/down branches pay 0, giving value 0.48. At state +5, the up move stays at +5. `transition_matrix()` therefore combines boundary probabilities rather than dropping probability mass.

With 100 remaining steps at starting state zero, the default analytical value is about 0.454545. The independently simulated 100,000-path value and its sampling error are recorded in the report. Agreement checks the implementation under the model; it does not validate the model against an exchange.

## One fill, calculated independently

Start with cash 10, inventory zero and a fee of 0.001. The maker buys one contract at bid 0.40:

```text
Cash after fill = 10 - 1*0.40 - 0.001 = 9.599
Inventory after fill = 1
NAV marked at fair value 0.42 = 9.599 + 1*0.42 = 10.019
```

The 0.019 NAV gain is 0.02 spread capture minus 0.001 fee. If the next fair value is 0.43, the one-step maker markout is 0.03 before fee, and NAV becomes 10.029. If the contract ultimately pays zero, terminal cash is 9.599; if it pays one, terminal cash is 10.599. The favorable immediate markout does not eliminate terminal risk.

If the maker sells the position at 0.45 first, cash becomes `9.599+0.45-0.001=10.048`, inventory returns to zero and later settlement has no account effect.

## Short collateral is a different constraint

With cash only 0.10, selling one contract at 0.60 would produce cash 0.699 and inventory -1. Worst-case settlement requires 1, leaving collateral surplus -0.301. The engine rejects the fill. Merely receiving option premium is not enough to fund a guaranteed terminal liability.

## Compare policies on shared paths

All policies receive the same state path and external random uniforms. At the first step, changing the next state does not change their current quotes. Informed takers can act on the next state, so fills can change. This separation is exercised by a future-state perturbation test.

Read all nine rows of comparison.csv. At zero informed flow, inventory skew cannot change the exogenous, price-inelastic side demands except through account constraints. At informed fractions, quote changes can affect which orders are accepted. Wider quotes benefit mechanically from the assumed inelastic noise demand; this simulator cannot select a production-optimal spread.

## Follow a real simulated ledger row

Open sample_ledgers.csv and select any row with nonzero filled_delta. Recalculate cash_after from cash_before, price and fee; then recalculate nav_after_next_mark. Its bridge_error should be floating-point noise. Match the final step's inventory with the first path's payoff in path_results.csv to verify terminal settlement. The executable `examples/explain_account.py` reproduces the small cash example above without a market-data file.
