import numpy as np
import pytest
from market_making_lab.core import Config, shared_paths, customer_demand, simulate, quotes
from market_making_lab.demand_study import paired_interval


def test_wider_quotes_reduce_fixed_customer_acceptance():
    draws = np.linspace(0, .99999, 10000)
    buys = np.arange(len(draws)) % 2 == 0
    narrow = customer_demand(.5, .49, .51, buys, draws, .04)
    wide = customer_demand(.5, .47, .53, buys, draws, .04)
    assert np.count_nonzero(wide) < np.count_nonzero(narrow)


def test_reservation_rejections_and_accounting():
    config = Config(paths=40, steps=20)
    paths = shared_paths(config)
    paths['states'][:] = 0
    summary, results, _ = simulate(config, paths, 'fixed_spread', 0, demand='reservation', reservation_width=.001)
    assert summary['fill_rate'] == 0
    assert (results.pnl == 0).all()
    summary, _, _ = simulate(config, paths, 'inventory_skew', .5, demand='reservation')
    assert summary['max_nav_bridge_error'] < 1e-10
    assert summary['max_attribution_error'] < 1e-10
    assert summary['min_collateral_surplus'] >= -1e-10


def test_shared_draws_and_quote_information_boundary():
    config = Config(paths=20)
    first = shared_paths(config)
    second = shared_paths(config)
    assert all(np.array_equal(first[key], second[key]) for key in first)
    _, _, original = simulate(config, first, 'inventory_uncertainty', .25, demand='reservation')
    for step in range(51, config.steps + 1):
        second['states'][:, step] = np.clip(second['states'][:, step - 1] + 1, -5, 5)
    second['reservation_uniform'][:, 50:] = .999
    _, _, perturbed = simulate(config, second, 'inventory_uncertainty', .25, demand='reservation')
    assert original.iloc[:50].equals(perturbed.iloc[:50])


def test_invalid_demand_and_paired_zero_difference():
    config = Config(paths=10)
    paths = shared_paths(config)
    with pytest.raises(ValueError):
        simulate(config, paths, 'fixed_spread', .25, demand='reservation', reservation_width=-1)
    paths['reservation_uniform'][0, 0] = 1.
    with pytest.raises(ValueError):
        simulate(config, paths, 'fixed_spread', .25, demand='reservation')
    assert paired_interval(np.zeros(50)) == [0., 0., 0.]
