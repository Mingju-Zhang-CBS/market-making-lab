from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import platform
import time

import numpy as np
import pandas as pd
from .core import Config, shared_paths, simulate


def paired_interval(differences, seed=8675309, draws=2000):
    differences = np.asarray(differences, float)
    if differences.ndim != 1 or len(differences) < 2 or not np.isfinite(differences).all():
        raise ValueError("Finite paired path differences required")
    rng = np.random.default_rng(seed)
    estimates = np.empty(draws)
    for start in range(0, draws, 100):
        count = min(100, draws - start)
        estimates[start:start + count] = differences[rng.integers(0, len(differences), (count, len(differences)))].mean(axis=1)
    return [float(differences.mean()), *np.quantile(estimates, [.025, .975]).tolist()]


def run(output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty result directory")
    output.mkdir(parents=True, exist_ok=True)
    protocol_path = Path(__file__).with_name('demand_protocol.json')
    protocol = json.loads(protocol_path.read_text())
    (output / 'protocol.json').write_bytes(protocol_path.read_bytes())
    started = time.perf_counter()
    summaries, paired, ledgers, fingerprints = [], [], [], {}
    for seed in protocol['seeds']:
        config = Config(seed=seed, paths=protocol['paths_per_seed'], steps=protocol['steps'])
        paths = shared_paths(config)
        fingerprints[str(seed)] = hashlib.sha256(b''.join(paths[key].tobytes() for key in sorted(paths))).hexdigest()
        for demand, width in [('inelastic', None)] + [('reservation', width) for width in protocol['reservation_half_widths']]:
            for fraction in protocol['informed_fractions']:
                baseline = None
                for policy in protocol['policies']:
                    summary, frame, ledger = simulate(config, paths, policy, fraction, demand=demand, reservation_width=width if width is not None else .04)
                    summaries.append(dict(summary, seed=seed))
                    if baseline is None:
                        baseline = frame.set_index('path')
                    else:
                        aligned = frame.set_index('path').join(baseline[['pnl', 'fills']], rsuffix='_base', validate='one_to_one')
                        estimate, low, high = paired_interval(aligned.pnl - aligned.pnl_base)
                        paired.append(dict(seed=seed, demand=demand, width=width, informed_fraction=fraction, policy=policy,
                                           mean_difference=estimate, ci_low=low, ci_high=high,
                                           fills_difference=float((aligned.fills - aligned.fills_base).mean())))
                    if seed == protocol['seeds'][0] and fraction == .25:
                        ledgers.append(ledger.assign(policy=policy, demand=demand, width=width))
    comparison = pd.DataFrame(summaries)
    intervals = pd.DataFrame(paired)
    comparison.to_csv(output / 'comparison.csv', index=False)
    intervals.to_csv(output / 'paired_intervals.csv', index=False)
    pd.concat(ledgers).to_csv(output / 'sample_ledgers.csv', index=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = ['#234e70', '#36B3A8', '#b37743']
    primary = comparison[(comparison.seed == protocol['seeds'][0]) & (comparison.demand == 'reservation')]
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.7), sharex=True)
    for column, fraction in enumerate(protocol['informed_fractions']):
        for policy, color in zip(protocol['policies'], colors):
            group = primary[(primary.informed_fraction == fraction) & (primary.policy == policy)]
            axes[0, column].plot(group.reservation_width, group.mean_pnl, 'o-', color=color, label=policy)
            axes[1, column].plot(group.reservation_width, group.fill_rate, 'o-', color=color)
        axes[0, column].set_title(f'{fraction:.0%} informed customers')
        axes[1, column].set_xlabel('Reservation half-width (assumed)')
    axes[0, 0].set_ylabel('Mean terminal P&L')
    axes[1, 0].set_ylabel('Fills / customer arrivals')
    axes[0, 0].legend(fontsize=7)
    fig.suptitle('Quote width competes with customer willingness to trade', fontsize=13)
    fig.tight_layout(); fig.savefig(output / 'demand_tradeoff.png', dpi=160); plt.close(fig)
    group = intervals[(intervals.seed == protocol['seeds'][0]) & (intervals.demand == 'reservation')]
    fig, ax = plt.subplots(figsize=(10, 6))
    labels = []
    for position, row in enumerate(group.itertuples()):
        ax.plot([row.ci_low, row.ci_high], [position, position], color='#36B3A8')
        ax.scatter(row.mean_difference, position, color='#234e70', s=20)
        labels.append(f'{row.policy} | width {row.width:g} | informed {row.informed_fraction:.0%}')
    ax.axvline(0, color='#777777', linewidth=.8)
    ax.set_yticks(range(len(labels)), labels, fontsize=7)
    ax.set_xlabel('Mean P&L difference from fixed spread; pointwise paired 95% interval')
    ax.set_title('All predeclared demand scenarios, primary seed')
    fig.tight_layout(); fig.savefig(output / 'paired_policy_differences.png', dpi=160); plt.close(fig)
    mid = primary[(primary.reservation_width == .04) & (primary.informed_fraction == .25)]
    table = mid[['policy', 'mean_pnl', 'fill_rate', 'loss_cvar_5pct', 'mean_abs_inventory', 'spread_capture_per_fill', 'maker_markout_per_fill']]
    report = f'''# Price-sensitive order flow

**Executed simulation, no market calibration.** The protocol fixes three policies, three informed-flow fractions, three reservation-price widths and three independent seeds. All {len(comparison)} rows are retained in [comparison.csv](comparison.csv), including 27 legacy inelastic-demand rows. Each row uses 1,000 shared paths of 100 steps. Quote coefficients remain unchanged from the legacy study.

## Mechanism

An uninformed customer first draws a side, then a reservation value uniformly from fair value plus or minus the declared width. A buyer accepts only ask <= reservation; a seller accepts only bid >= reservation. The draw represents heterogeneous surplus, so reservation values are not truncated at payout bounds. This is an assumption, not a fitted distribution. Informed takers still observe the next state; the maker quotes before observing it. State, side, informed and reservation draws are common across policies.

![Demand and P&L](demand_tradeoff.png)

## Predetermined middle scenario

Primary seed {protocol['seeds'][0]}, width 0.04, informed fraction 25%:

```csv
{table.to_csv(index=False).strip()}
```

The narrowest width can remove almost all uninformed trade; an informed customer can still trade against a stale quote. Wider quotes may improve capture on accepted trades while reducing fills and changing adverse-selection exposure. Compare all widths and seeds before interpreting a policy ranking.

![Paired policy comparisons](paired_policy_differences.png)

## Uncertainty and accounting

[Paired intervals](paired_intervals.csv) bootstrap differences on the same independent simulated paths (2,000 draws). They are pointwise intervals, not multiplicity-adjusted evidence of market profitability. The independent seeds are separately reported rather than pooled after selecting a winner. Model uncertainty dominates sampling precision here.

Maximum cash/NAV bridge error: {comparison.max_nav_bridge_error.max():.3g}; maximum terminal attribution error: {comparison.max_attribution_error.max():.3g}. Fees, short collateral and inventory limits are identical across policies. Fill rate uses every potential arrival as denominator; risk rejection uses proposed fills. Markout is measured one step after execution and is never an input to the quote. [Sample ledgers](sample_ledgers.csv) expose first-path accounting for every primary-seed demand model at 25% informed flow.

## Reproduce and limits

Run `python -m market_making_lab --demand-study --output local-runs/demand` from a clean installation. [protocol.json](protocol.json) records assumed distributions and seeds. There is no queue, competition, latency calibration, intraday quote replay or real execution claim. EOD OptionMetrics quotes are not used to calibrate fills. Zero or negative results are retained.
'''
    (output / 'REPORT.md').write_text(report, encoding='utf-8')
    metrics = {'data_kind': 'simulated', 'scenarios': len(comparison), 'seeds': protocol['seeds'], 'primary_middle_scenario': json.loads(table.to_json(orient='records')),
               'elapsed_seconds': time.perf_counter() - started, 'max_bridge_error': float(comparison.max_nav_bridge_error.max()),
               'max_attribution_error': float(comparison.max_attribution_error.max())}
    (output / 'metrics.json').write_text(json.dumps(metrics, indent=2, allow_nan=False), encoding='utf-8')
    manifest = {'protocol_sha256': hashlib.sha256(protocol_path.read_bytes()).hexdigest(), 'shared_paths_sha256': fingerprints,
                'source_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in Path(__file__).parent.glob('*.py')},
                'python': platform.python_version(), 'config': asdict(Config()),
                'outputs_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in output.iterdir() if path.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return metrics
