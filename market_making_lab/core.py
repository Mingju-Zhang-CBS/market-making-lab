"""Dynamic-programming value, shared-path simulation and explicit account flows."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.metadata
import io
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Config:
    paths: int = 1000
    steps: int = 100
    seed: int = 20261023
    initial_cash: float = 100.
    inventory_limit: int = 20
    fee_per_contract: float = .001
    half_spread: float = .02
    inventory_coefficient: float = .02
    uncertainty_coefficient: float = .02
    tick: float = .01

    def validate(self):
        for name, minimum in [("paths", 2), ("steps", 1), ("inventory_limit", 1)]:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(name + " must be a positive integer of supported size")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("Nonnegative integer seed required")
        values = [self.initial_cash, self.fee_per_contract, self.half_spread, self.inventory_coefficient, self.uncertainty_coefficient, self.tick]
        if not np.isfinite(values).all() or self.initial_cash <= 0 or min(values[1:]) < 0 or not 0 < self.tick < .5 or self.half_spread <= 0:
            raise ValueError("Finite positive cash/spread/tick and nonnegative costs/risk coefficients required")
        if not np.isclose(1 / self.tick, round(1 / self.tick)):
            raise ValueError("Tick must divide the unit payout")


def transition_matrix():
    """Reflect by retaining attempted out-of-range moves in the boundary state."""
    result = np.zeros((11, 11))
    for state in range(11):
        for move, probability in [(-1, .48), (0, .04), (1, .48)]:
            result[state, np.clip(state + move, 0, 10)] += probability
    return result


def fair_values(steps=100):
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise ValueError("Positive integer steps required")
    values = np.empty((steps + 1, 11))
    values[0] = (np.arange(-5, 6) > 0).astype(float)
    transition = transition_matrix()
    for remaining in range(1, steps + 1):
        values[remaining] = transition @ values[remaining - 1]
    return values


def shared_paths(config):
    config.validate()
    rng = np.random.default_rng(config.seed)
    uniforms = rng.random((config.paths, config.steps))
    moves = np.where(uniforms < .48, -1, np.where(uniforms < .52, 0, 1))
    states = np.zeros((config.paths, config.steps + 1), dtype=int)
    for step in range(config.steps):
        states[:, step + 1] = np.clip(states[:, step] + moves[:, step], -5, 5)
    return {"states": states, "informed_uniform": rng.random((config.paths, config.steps)),
            "noise_buy": rng.random((config.paths, config.steps)) < .5}


def quotes(fair, inventory, policy, config):
    config.validate()
    if policy not in {"fixed_spread", "inventory_skew", "inventory_uncertainty"}:
        raise ValueError("Unknown policy")
    fair, inventory = np.broadcast_arrays(np.asarray(fair, dtype=float), np.asarray(inventory, dtype=float))
    if not np.isfinite(fair).all() or not np.isfinite(inventory).all() or ((fair < 0) | (fair > 1)).any() or (inventory != np.floor(inventory)).any() or (np.abs(inventory) > config.inventory_limit).any():
        raise ValueError("Finite fair values in [0,1] and inventory required")
    center, width = fair.copy(), np.full(fair.shape, config.half_spread)
    if policy != "fixed_spread":
        center -= config.inventory_coefficient * inventory / config.inventory_limit
    if policy == "inventory_uncertainty":
        width += config.uncertainty_coefficient * np.sqrt(fair * (1 - fair))
    bid = np.clip(np.floor((center - width + 1e-12) / config.tick) * config.tick, 0, 1 - config.tick)
    ask = np.clip(np.ceil((center + width - 1e-12) / config.tick) * config.tick, config.tick, 1)
    if (bid >= ask).any():
        raise ValueError("Noncrossing quotes required")
    return bid, ask


def execute(cash, inventory, delta, price, config):
    """delta is maker inventory change. Require fully collateralized unit contracts."""
    config.validate()
    cash, inventory, delta, price = np.broadcast_arrays(np.asarray(cash, float), np.asarray(inventory, float), np.asarray(delta), np.asarray(price, float))
    if not np.isfinite(cash).all() or not np.isfinite(price).all() or not np.isfinite(delta).all() or not np.isfinite(inventory).all() or (inventory != np.floor(inventory)).any() or (np.abs(inventory) > config.inventory_limit).any() or (cash + np.minimum(inventory, 0) < -1e-12).any() or not np.isin(delta, [-1, 0, 1]).all() or ((price < 0) | (price > 1)).any():
        raise ValueError("Valid finite unit fill inputs required")
    inventory = inventory.astype(int)
    candidate_q = inventory + delta.astype(int)
    candidate_cash = cash - delta * price - np.abs(delta) * config.fee_per_contract
    # cash + min(q,0) is the cash remaining after the worst-case short payout.
    accepted = (np.abs(candidate_q) <= config.inventory_limit) & (candidate_cash + np.minimum(candidate_q, 0) >= -1e-12)
    actual_delta = np.where(accepted, delta, 0).astype(int)
    return cash - actual_delta * price - np.abs(actual_delta) * config.fee_per_contract, inventory + actual_delta, actual_delta


def simulate(config, paths, policy, informed_fraction):
    config.validate()
    if not np.isfinite(informed_fraction) or not 0 <= informed_fraction <= 1:
        raise ValueError("Informed fraction must be in [0,1]")
    states = np.asarray(paths["states"])
    if states.shape != (config.paths, config.steps + 1) or not np.issubdtype(states.dtype, np.integer) or (np.abs(states) > 5).any() or (states[:, 0] != 0).any() or (np.abs(np.diff(states, axis=1)) > 1).any():
        raise ValueError("State array inconsistent with configuration")
    flow = np.asarray(paths["informed_uniform"])
    noise = np.asarray(paths["noise_buy"])
    if flow.shape != (config.paths, config.steps) or noise.shape != flow.shape or not np.isfinite(flow).all() or ((flow < 0) | (flow >= 1)).any() or noise.dtype != bool:
        raise ValueError("Shared flow arrays invalid")
    values = fair_values(config.steps)
    cash = np.full(config.paths, config.initial_cash)
    inventory = np.zeros(config.paths, dtype=int)
    trades = np.zeros(config.paths, dtype=int)
    fees = np.zeros(config.paths)
    peak_inventory = np.zeros(config.paths, dtype=int)
    inventory_sum = np.zeros(config.paths)
    markout_total = np.zeros(config.paths)
    spread_capture = np.zeros(config.paths)
    price_mark = np.zeros(config.paths)
    min_surplus = np.full(config.paths, config.initial_cash)
    max_bridge = 0.
    sample = []
    for step in range(config.steps):
        fair = values[config.steps - step, states[:, step] + 5]
        # The maker quotes before the next state; informed takers see that state.
        next_fair = values[config.steps - step - 1, states[:, step + 1] + 5]
        bid, ask = quotes(fair, inventory, policy, config)
        informed = flow[:, step] < informed_fraction
        informed_delta = np.where(next_fair > ask, -1, np.where(next_fair < bid, 1, 0))
        proposed_delta = np.where(informed, informed_delta, np.where(noise[:, step], -1, 1))
        price = np.where(proposed_delta > 0, bid, ask)
        old_cash, old_inventory = cash.copy(), inventory.copy()
        cash, inventory, delta = execute(cash, inventory, proposed_delta, price, config)
        fee = np.abs(delta) * config.fee_per_contract
        capture = delta * (fair - price)
        mark = inventory * (next_fair - fair)
        bridge = (cash + inventory * next_fair) - (old_cash + old_inventory * fair) - (capture + mark - fee)
        max_bridge = max(max_bridge, float(np.max(np.abs(bridge))))
        spread_capture += capture
        price_mark += mark
        trades += np.abs(delta)
        fees += fee
        peak_inventory = np.maximum(peak_inventory, np.abs(inventory))
        inventory_sum += np.abs(inventory)
        # Maker's one-step markout per fill, before fee. It uses a future mark only for evaluation.
        markout = delta * (next_fair - price)
        markout_total += markout
        min_surplus = np.minimum(min_surplus, cash + np.minimum(inventory, 0))
        sample.append({"step": step, "state": int(states[0, step]), "next_state": int(states[0, step + 1]),
                       "fair": float(fair[0]), "next_fair": float(next_fair[0]), "bid": float(bid[0]), "ask": float(ask[0]),
                       "informed_taker": bool(informed[0]), "proposed_delta": int(proposed_delta[0]), "filled_delta": int(delta[0]),
                       "fill_price": float(price[0]) if delta[0] else None, "cash_before": float(old_cash[0]),
                       "inventory_before": int(old_inventory[0]), "cash_after": float(cash[0]), "inventory_after": int(inventory[0]),
                       "fee": float(fee[0]), "maker_markout": float(markout[0]) if delta[0] else None,
                       "nav_after_next_mark": float(cash[0] + inventory[0] * next_fair[0]), "bridge_error": float(bridge[0])})
    payoff = (states[:, -1] > 0).astype(float)
    terminal = cash + inventory * payoff
    pnl = terminal - config.initial_cash
    attribution_error = np.abs(pnl - (spread_capture + price_mark - fees))
    count = max(1, int(np.ceil(config.paths * .05)))
    low_tail = np.sort(pnl)[:count]
    results = pd.DataFrame({"path": np.arange(config.paths), "pnl": pnl, "terminal_cash": terminal, "inventory_at_settlement": inventory,
                            "payoff": payoff, "fills": trades, "fees": fees, "peak_abs_inventory": peak_inventory,
                            "mean_abs_inventory": inventory_sum / config.steps, "maker_markout_sum": markout_total,
                            "spread_capture": spread_capture, "inventory_mark_pnl": price_mark, "min_collateral_surplus": min_surplus})
    summary = {"policy": policy, "informed_fraction": float(informed_fraction), "mean_pnl": float(pnl.mean()),
               "std_pnl": float(pnl.std(ddof=1)), "pnl_5pct_quantile": float(np.quantile(pnl, .05)),
               "worst_5pct_mean_pnl": float(low_tail.mean()), "loss_cvar_5pct": float(-low_tail.mean()),
               "mean_fills": float(trades.mean()), "mean_fees": float(fees.mean()),
               "mean_abs_inventory": float((inventory_sum / config.steps).mean()), "max_abs_inventory": int(peak_inventory.max()),
               "maker_markout_per_fill": float(markout_total.sum() / trades.sum()) if trades.sum() else None,
               "min_terminal_cash": float(terminal.min()), "min_collateral_surplus": float(min_surplus.min()),
               "max_nav_bridge_error": max_bridge, "max_attribution_error": float(attribution_error.max())}
    return summary, results, pd.DataFrame(sample)


def monte_carlo_value(steps=100, paths=100000, seed=9182):
    """Independent simulator using categorical moves, not the shared-path generator."""
    if not isinstance(paths, int) or isinstance(paths, bool) or paths < 2 or not isinstance(steps, int) or isinstance(steps, bool) or steps < 1:
        raise ValueError("Valid simulation size required")
    rng = np.random.default_rng(seed)
    state = np.zeros(paths, dtype=int)
    for _ in range(steps):
        state = np.clip(state + rng.choice([-1, 0, 1], size=paths, p=[.48, .04, .48]), -5, 5)
    payoff = (state > 0).astype(float)
    return {"paths": paths, "seed": seed, "estimate": float(payoff.mean()), "standard_error": float(payoff.std(ddof=1) / np.sqrt(paths))}


def run_demo(output, config=None):
    config = config or Config()
    config.validate()
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new or empty output directory")
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    paths = shared_paths(config)
    summaries, frames, ledgers = [], [], []
    for fraction in [0., .25, .5]:
        for policy in ["fixed_spread", "inventory_skew", "inventory_uncertainty"]:
            summary, frame, ledger = simulate(config, paths, policy, fraction)
            summaries.append(summary)
            frames.append(frame.assign(policy=policy, informed_fraction=fraction))
            ledgers.append(ledger.assign(policy=policy, informed_fraction=fraction))
    comparison = pd.DataFrame(summaries)
    results = pd.concat(frames, ignore_index=True)
    samples = pd.concat(ledgers, ignore_index=True)
    monte_carlo = monte_carlo_value(config.steps)
    analytical = float(fair_values(config.steps)[config.steps, 5])
    fingerprint = hashlib.sha256()
    for name in ["states", "informed_uniform", "noise_buy"]:
        fingerprint.update(name.encode()); fingerprint.update(paths[name].tobytes())
    metrics = {"data_kind": "simulated", "configuration": asdict(config), "comparison": summaries,
               "initial_fair_value": analytical, "independent_monte_carlo": monte_carlo,
               "shared_path_sha256": fingerprint.hexdigest(), "elapsed_seconds": time.perf_counter() - started,
               "measurement": {"workload": "nine shared-path policy/flow scenarios plus independent value check; before plots", "platform": platform.system(), "python": platform.python_version()}}
    manifest = {"data_kind": "simulated", "schema_version": "research-studio-run-v1", "configuration": asdict(config),
                "shared_path_sha256": fingerprint.hexdigest(),
                "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))},
                "environment": {"platform": platform.system(), "python": platform.python_version(), "dependencies": {n: importlib.metadata.version(n) for n in ["numpy", "pandas", "matplotlib"]}}}
    for name, obj in [("metrics.json", metrics), ("manifest.json", manifest)]:
        (output / name).write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    comparison.to_csv(output / "comparison.csv", index=False)
    results.to_csv(output / "path_results.csv", index=False)
    samples.to_csv(output / "sample_ledgers.csv", index=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    colors = ["#234e70", "#36B3A8", "#b37743"]
    for policy, color in zip(comparison.policy.unique(), colors):
        group = comparison[comparison.policy == policy]
        axes[0].plot(group.informed_fraction, group.mean_pnl, marker="o", label=policy, color=color)
        axes[1].plot(group.informed_fraction, group.loss_cvar_5pct, marker="o", label=policy, color=color)
    axes[0].set(title="All predetermined scenarios", xlabel="Informed taker fraction", ylabel="Mean simulated P&L")
    axes[1].set(title="Tail risk", xlabel="Informed taker fraction", ylabel="Loss CVaR: worst 5%")
    axes[0].legend(fontsize=8); fig.tight_layout(); fig.savefig(output / "policy_comparison.png", dpi=140); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    for policy, color in zip(comparison.policy.unique(), colors):
        group = results[(results.policy == policy) & (results.informed_fraction == .25)]
        ax.hist(group.pnl, bins=35, histtype="step", density=True, label=policy, color=color)
    ax.set(title="Terminal P&L at the predeclared 25% flow case", xlabel="Simulated currency units", ylabel="Density")
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(output / "pnl_distribution.png", dpi=140); plt.close(fig)
    report = f"""# Executed market-making study

Data: **simulated**. This independently designed environment is not an Akuna task, official ranking, market-data replay or executable trading strategy.

Nine predeclared cases use {config.paths:,} common paths and {config.steps} steps. Starting state is zero. All policies share a reflecting walk, flow uniforms, noise-side draws and settlement outcomes. Initial cash is {config.initial_cash}; the absolute inventory cap is {config.inventory_limit}; the fee is {config.fee_per_contract} per unit fill.

## Fair value

Backward DP initial value: **{analytical:.6f}**. Independent simulation: **{monte_carlo['estimate']:.6f}**, standard error **{monte_carlo['standard_error']:.6f}**, {monte_carlo['paths']:,} paths using a different seed and categorical generator.

## Results

{comparison[['policy','informed_fraction','mean_pnl','loss_cvar_5pct','mean_abs_inventory','maker_markout_per_fill']].to_csv(index=False)}

![Mean P&L and tail loss](policy_comparison.png)

![Terminal distribution](pnl_distribution.png)

No policy is promoted from the best row. Inventory-aware quotes can change both inventory exposure and the mix of accepted flow; these effects must be read together. This simulated taker model has no queue or capacity calibration.

## Accounting

Cash after fill = prior cash - maker inventory change * fill price - fee. Worst-case short collateral requires cash + min(inventory, 0) >= 0. NAV is cash + inventory * current fair value. Terminal cash is cash + inventory * binary payoff.

P&L attribution = spread capture + inventory mark changes - fees. The largest daily bridge residual across cases is {comparison.max_nav_bridge_error.max():.3g}, and the largest terminal attribution residual is {comparison.max_attribution_error.max():.3g} currency units. sample_ledgers.csv traces the first path for every scenario.

## Interpretation limits

The informed customer sees the next state, while the maker does not; this is a declared stress assumption. Uninformed takers demand a randomly selected side. One potential customer arrives per step. Fills, collateral and costs are modeled conventions, not exchange guarantees. One-step maker markouts are evaluated after the fill and never fed into current quotes. A single seed is illustrative; paired paths support comparisons but do not remove model risk. Loss CVaR is the negative mean of the worst ceil(5% * paths) P&Ls; it can be negative if even those paths earn money. No real-market or contest score is claimed.
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    return metrics
