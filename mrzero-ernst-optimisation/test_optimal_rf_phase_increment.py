"""Regression tests for quadratic RF phase-increment optimisation."""

import unittest

import numpy as np

from optimal_rf_phase_increment import (
    PhaseDesignConfig,
    epg_spgr_signal,
    evaluate_seed,
    quadratic_rf_phases,
    scenario_grid,
)


class OptimalRfPhaseIncrementTests(unittest.TestCase):
    def test_quadratic_phase_recurrence(self) -> None:
        phases = quadratic_rf_phases(117.0, 4)
        np.testing.assert_allclose(phases, [117.0, 351.0, 342.0, 90.0])

    def test_epg_signal_is_finite_and_positive(self) -> None:
        cfg = PhaseDesignConfig(
            t1_samples=2,
            t2_samples=2,
            b1_samples=2,
            repetitions=40,
            steady_state_average=10,
            epg_states=20,
        )
        t1, t2, b1 = scenario_grid(cfg)
        signal = epg_spgr_signal(12.0, 117.0, t1, t2, b1, cfg)
        self.assertTrue(np.all(np.isfinite(signal)))
        self.assertTrue(np.all(signal > 0.0))

    def test_seed_evaluation_returns_finite_metrics(self) -> None:
        cfg = PhaseDesignConfig(
            t1_samples=2,
            t2_samples=2,
            b1_samples=2,
            repetitions=40,
            steady_state_average=10,
            epg_states=20,
        )
        result = evaluate_seed(117.0, cfg)
        self.assertAlmostEqual(result["seed_deg"], 117.0)
        self.assertTrue(np.isfinite(result["worst_absolute_bias_percent"]))
        self.assertTrue(np.isfinite(result["rms_bias_percent"]))


if __name__ == "__main__":
    unittest.main()
