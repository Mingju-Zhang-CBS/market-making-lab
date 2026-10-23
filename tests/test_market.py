from dataclasses import replace
import numpy as np
import pytest
from market_making_lab.core import Config, execute, fair_values, monte_carlo_value, quotes, shared_paths, simulate, transition_matrix


def test_transition_and_dp_match_independent_probability_evolution():
    transition = transition_matrix()
    assert np.allclose(transition.sum(axis=1), 1)
    assert transition[0,0] == pytest.approx(.52)
    distribution = np.zeros(11); distribution[5] = 1
    for _ in range(17):
        distribution = distribution @ transition
    assert fair_values(17)[17,5] == pytest.approx(distribution[6:].sum())
    assert np.array_equal(fair_values(1)[0], (np.arange(-5,6)>0).astype(float))


def test_independent_monte_carlo_agrees_with_dp_at_sampling_scale():
    result = monte_carlo_value(steps=23, paths=60000, seed=123)
    assert abs(result['estimate'] - fair_values(23)[23,5]) < 5 * result['standard_error']


def test_cash_fee_inventory_and_short_collateral_examples():
    c = Config()
    cash, inventory, delta = execute(10., 0, 1, .4, c)
    assert float(cash) == pytest.approx(9.599) and inventory == 1 and delta == 1
    cash2, q2, d2 = execute(cash, inventory, -1, .45, c)
    assert float(cash2) == pytest.approx(10.048) and q2 == 0 and d2 == -1
    cash, inventory, delta = execute(.1, 0, -1, .6, c)
    assert cash == .1 and inventory == 0 and delta == 0
    cash, inventory, delta = execute(10., 20, 1, .4, c)
    assert cash == 10 and inventory == 20 and delta == 0
    with pytest.raises(ValueError):
        execute(10., .5, 1, .4, c)


def test_quotes_are_bounded_grid_aligned_and_inventory_sensitive():
    c = Config(); fair = np.array([0., .2, .5, .9, 1.])
    bid, ask = quotes(fair, np.zeros(5), 'fixed_spread', c)
    assert (bid >= 0).all() and (ask <= 1).all() and (bid < ask).all()
    assert np.allclose(bid/c.tick, np.round(bid/c.tick))
    long_bid, long_ask = quotes(.5, 20, 'inventory_skew', c)
    short_bid, short_ask = quotes(.5, -20, 'inventory_skew', c)
    assert long_bid < short_bid and long_ask < short_ask


def test_paired_simulations_conserve_account_and_use_post_fill_markouts():
    c = Config(paths=40, steps=35, initial_cash=2., inventory_limit=3)
    paths = shared_paths(c); original = paths['states'].copy()
    for policy in ['fixed_spread','inventory_skew','inventory_uncertainty']:
        summary, results, ledger = simulate(c, paths, policy, .5)
        assert summary['max_nav_bridge_error'] < 1e-12 and summary['max_attribution_error'] < 1e-12
        assert results.min_collateral_surplus.min() >= -1e-12 and results.terminal_cash.min() >= -1e-12
        assert results.peak_abs_inventory.max() <= c.inventory_limit
        assert np.allclose(results.pnl, results.spread_capture + results.inventory_mark_pnl - results.fees)
        fills = ledger[ledger.filled_delta != 0]
        assert np.allclose(fills.maker_markout, fills.filled_delta*(fills.next_fair-fills.fill_price))
        assert np.array_equal(original, paths['states'])


def test_future_state_does_not_change_the_current_maker_quote():
    c = Config(paths=5, steps=8)
    original = shared_paths(c); changed = {k:v.copy() for k,v in original.items()}
    changed['states'][:,1:] = 0
    _, _, a = simulate(c, original, 'inventory_uncertainty', 1.)
    _, _, b = simulate(c, changed, 'inventory_uncertainty', 1.)
    assert a.iloc[0].bid == b.iloc[0].bid and a.iloc[0].ask == b.iloc[0].ask


def test_higher_fees_lower_results_when_quotes_and_fills_remain_identical():
    c = Config(paths=25, steps=25, initial_cash=10000.)
    shared = shared_paths(c)
    _, low, _ = simulate(c, shared, 'fixed_spread', .25)
    _, high, _ = simulate(replace(c, fee_per_contract=.01), shared, 'fixed_spread', .25)
    assert np.array_equal(low.fills, high.fills)
    assert np.allclose(low.pnl-high.pnl, low.fills*(.01-c.fee_per_contract))


@pytest.mark.parametrize('kwargs',[{'paths':1},{'steps':0},{'inventory_limit':True},{'fee_per_contract':-1},{'tick':.03},{'initial_cash':float('nan')}])
def test_invalid_configuration_rejected(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs).validate()


def test_invalid_external_paths_are_rejected():
    c = Config(paths=5, steps=8); paths = shared_paths(c)
    paths['states'][0,1] = 4
    with pytest.raises(ValueError):
        simulate(c,paths,'fixed_spread',.25)
