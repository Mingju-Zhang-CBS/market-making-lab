# Executed market-making study

Data: **simulated**. This independently designed environment is not an Akuna task, official ranking, market-data replay or executable trading strategy.

Nine predeclared cases use 1,000 common paths and 100 steps. Starting state is zero. All policies share a reflecting walk, flow uniforms, noise-side draws and settlement outcomes. Initial cash is 100.0; the absolute inventory cap is 20; the fee is 0.001 per unit fill.

## Fair value

Backward DP initial value: **0.454545**. Independent simulation: **0.453600**, standard error **0.001574**, 100,000 paths using a different seed and categorical generator.

## Results

policy,informed_fraction,mean_pnl,loss_cvar_5pct,mean_abs_inventory,maker_markout_per_fill
fixed_spread,0.0,2.116916999999488,6.991660000000497,5.364809999999999,0.02452193389387057
inventory_skew,0.0,2.1162269999994954,6.896120000000485,5.364809999999999,0.0245150112568475
inventory_uncertainty,0.0,3.0405669999994918,5.984920000000495,5.364809999999999,0.033788736337862425
fixed_spread,0.25,1.273101999999577,7.286720000000411,4.84186,0.018068549005725052
inventory_skew,0.25,1.2928149999995808,6.666440000000413,4.4930900000000005,0.017996147517484393
inventory_uncertainty,0.25,2.0490199999995875,5.910000000000407,4.583469999999999,0.02773854736694157
fixed_spread,0.5,0.2648089999996683,7.578760000000327,4.01529,0.00798450704450197
inventory_skew,0.5,0.3133299999996689,6.261920000000331,3.5220200000000004,0.007912848483798434
inventory_uncertainty,0.5,0.9084709999996834,5.78306000000033,3.6066299999999996,0.017818037464515952


![Mean P&L and tail loss](policy_comparison.png)

![Terminal distribution](pnl_distribution.png)

No policy is promoted from the best row. Inventory-aware quotes can change both inventory exposure and the mix of accepted flow; these effects must be read together. This simulated taker model has no queue or capacity calibration.

## Accounting

Cash after fill = prior cash - maker inventory change * fill price - fee. Worst-case short collateral requires cash + min(inventory, 0) >= 0. NAV is cash + inventory * current fair value. Terminal cash is cash + inventory * binary payoff.

P&L attribution = spread capture + inventory mark changes - fees. The largest daily bridge residual across cases is 2.62e-14, and the largest terminal attribution residual is 6.61e-13 currency units. sample_ledgers.csv traces the first path for every scenario.

## Interpretation limits

The informed customer sees the next state, while the maker does not; this is a declared stress assumption. Uninformed takers demand a randomly selected side. One potential customer arrives per step. Fills, collateral and costs are modeled conventions, not exchange guarantees. One-step maker markouts are evaluated after the fill and never fed into current quotes. A single seed is illustrative; paired paths support comparisons but do not remove model risk. Loss CVaR is the negative mean of the worst ceil(5% * paths) P&Ls; it can be negative if even those paths earn money. No real-market or contest score is claimed.
