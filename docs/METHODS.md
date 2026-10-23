# Methods, market assumptions and accounting

## State process and value

The independent model has states -5 through +5 and a fixed terminal time. At each step, move down with probability 0.48, remain with 0.04, or move up with 0.48. A move outside the boundary remains at that boundary. Thus a boundary has 0.52 stay probability and 0.48 inward probability. The unit contract pays 1 if the terminal state is strictly positive, and 0 otherwise. The zero state belongs to the zero-payoff set, so the initial fair value is not exactly one half.

`fair_values` uses `V[0,s]=1(s>0)` and `V[n,s]=sum(P[s,j]*V[n-1,j])`. Rates and dividends are zero. This is a model conditional expectation rather than a fitted market price. An independent categorical-path Monte Carlo uses another seed to check the initial DP value.

## Quotes and policy controls

Default settings are 100 steps, 1,000 paths, initial cash 100, absolute inventory limit 20, one unit per fill, 0.001 currency fee per fill and tick 0.01. A fixed policy uses fair value as reservation price with half-spread 0.02. The inventory policy shifts reservation value by `-0.02*q/20`. The uncertainty policy adds `0.02*sqrt(p*(1-p))` to the half-spread as well as using the same inventory shift. These are predetermined illustrative coefficients, not fitted optima.

Bids round down and asks round up to the tick. Quotes are bounded in [0,1] and cannot cross. Inventory-aware controls affect the price and sometimes the flow accepted. They are evaluated under identical funding, limits, fees and underlying randomness.

## Order of events and taker model

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
