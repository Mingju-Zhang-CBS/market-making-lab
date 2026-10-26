# Methods, market assumptions and accounting

## State process and value

The independent model has states -5 through +5 and a fixed terminal time. At each step, move down with probability 0.48, remain with 0.04, or move up with 0.48. A move outside the boundary remains at that boundary. Thus a boundary has 0.52 stay probability and 0.48 inward probability. The unit contract pays 1 if the terminal state is strictly positive, and 0 otherwise. The zero state belongs to the zero-payoff set, so the initial fair value is not exactly one half.

`fair_values` uses `V[0,s]=1(s>0)` and `V[n,s]=sum(P[s,j]*V[n-1,j])`. Rates and dividends are zero. This is a model conditional expectation rather than a fitted market price. An independent categorical-path Monte Carlo uses another seed to check the initial DP value.

## Quotes and policy controls

Default settings are 100 steps, 1,000 paths, initial cash 100, absolute inventory limit 20, one unit per fill, 0.001 currency fee per fill and tick 0.01. A fixed policy uses fair value as reservation price with half-spread 0.02. The inventory policy shifts reservation value by `-0.02*q/20`. The uncertainty policy adds `0.02*sqrt(p*(1-p))` to the half-spread as well as using the same inventory shift. These are predetermined illustrative coefficients, not fitted optima.

Bids round down and asks round up to the tick. Quotes are bounded in [0,1] and cannot cross. Inventory-aware controls affect the price and sometimes the flow accepted. They are evaluated under identical funding, limits, fees and underlying randomness.

## Price-sensitive demand study

The current extension retains the valuation and account below, fixes all quote coefficients before evaluation, and changes only uninformed customer acceptance. A potential customer first selects a side. Its reservation price is uniform on `[fair-width, fair+width]`; a buyer accepts only when the ask does not exceed its reservation price, and a seller accepts only when the bid is at least its reservation price. The reservation distribution is deliberately untruncated, preserving the specified uniform law near payoff boundaries. It is an assumed willingness-to-trade model, not calibrated market utility.

For an ask `fair+a` within the reservation support, acceptance conditional on a potential buyer is `(width-a)/(2*width)`. Increasing `a` can improve capture per fill while reducing fills. Inventory skew can alter the two sides differently. Informed customers retain the next-state mechanism below; no next-state value enters the maker's quote.

The packaged `demand_protocol.json` fixes reservation widths 0.01/0.04/0.10, informed fractions 0%/25%/50%, three policies, 1,000 paths of 100 steps and seeds 20261026/20261027/20261028. All 108 combinations, including 27 legacy inelastic cases, are reported. Each environment shares state, informed-status, side and reservation draws across policies; policy-dependent fills never advance a random stream differently. Added reservation draws follow the legacy draws, preserving the original stream.

Policy differences are paired by path within each environment and seed. The study uses 2,000 paired bootstrap draws and pointwise 95% intervals, not simultaneous intervals across all comparisons. Additional seeds are prespecified replication checks, not tuning opportunities. Fill rate divides fills by potential requests, including risk-rejected requests; risk rejections and markout remain separately recorded. Read tail losses, fills, capture and inventory together in the [executed report](../reports/demand/REPORT.md).

## Legacy order of events and taker model

At t the maker sees current state, remaining time, inventory and cash, and quotes. The next state is then realized. A potential informed taker sees that next state's conditional fair value and buys from the ask if it is lower, or sells to the bid if it is higher; otherwise that taker does not trade. An uninformed taker selects a side with equal probability and accepts the quoted side. The maker never reads next state to generate quotes.

Each step has one potential customer. Shared arrays contain the complete state path, informed-status uniforms and noise-side uniforms before any policy runs. Fractions 0, 0.25 and 0.5 and the three policies produce all nine cases. Policy-dependent fills do not change the underlying random draws.

Uninformed demand is price-inelastic in this toy model. Wider quotes can mechanically collect more spread without losing those customers. This is a major limitation: the result is not evidence that wider spreads are optimal in a competitive market. There is no queue, fill-intensity calibration, latency, impact or exchange implementation.

## Account and risk

Let delta be the maker's filled inventory change: +1 buys at bid; -1 sells at ask. Cash changes by `-delta*price - abs(delta)*fee`. A fill is accepted only if resulting absolute inventory <=20 and `cash + min(q,0) >= 0`. The second inequality fully reserves the worst-case unit payout of a net short position; long contracts are already paid for in cash. No interest, borrowing or margin netting is modeled.

NAV at a mark p is `cash+q*p`. Its change is `delta*(p-price) + q_after*(p_next-p) - fee`. At terminal time p_next is the binary payout. Summed spread capture plus inventory mark changes minus fees equals terminal P&L, including unrealized inventory settlement. One-step maker markout is `delta*(p_next-price)` before fee; it is a diagnostic calculated after the trade.

Loss CVaR is minus the mean of the worst ceil(5%*paths) P&Ls. The P&L quantile and worst-tail P&L are also saved to prevent sign ambiguity. Mean absolute inventory averages post-fill inventory over the discrete grid; it is not continuous-time exposure. No Sharpe or hidden contest score is constructed.

## Reproducibility and evidence

The manifest records configuration, package-source hashes, dependency environment and a fingerprint of all common random arrays. comparison.csv contains nine aggregate rows; path_results.csv contains every path-policy-flow outcome; sample_ledgers.csv contains the first full path for each case. Timing measures the declared simulation workload before plotting. It is not exchange latency or production throughput.

This model and implementation were independently designed for this portfolio. Akuna competition original questions, interfaces, opponents, rankings and source code are not distributed. The account owner's reported competition achievement is separate from every number generated here.


## Worked example and interpretation


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
