"""Regression tests for robust flip-angle design."""

import unittest

import torch

from optimal_t1_flip_angles import (
    DTYPE,
    DesignConfig,
    ordered_angles,
    relative_t1_crlb_coefficient,
    scenario_grid,
    signal_and_log_t1_derivative,
)


class OptimalT1FlipAngleTests(unittest.TestCase):
    def test_ordered_parameterisation_obeys_constraints(self) -> None:
        cfg = DesignConfig()
        raw = torch.zeros(5, dtype=DTYPE)
        angles = ordered_angles(raw, cfg, count=4)
        self.assertGreaterEqual(float(angles[0]), cfg.min_flip_deg)
        self.assertLessEqual(float(angles[-1]), cfg.max_flip_deg)
        self.assertTrue(
            torch.all(torch.diff(angles) >= cfg.min_separation_deg - 1e-12)
        )

    def test_analytic_log_t1_derivative_matches_autograd(self) -> None:
        cfg = DesignConfig()
        angles = torch.tensor([3.0, 20.0], dtype=DTYPE)
        t1 = torch.tensor([[1.2]], dtype=DTYPE, requires_grad=True)
        b1 = torch.tensor([[0.9]], dtype=DTYPE)
        signal, analytic = signal_and_log_t1_derivative(
            angles, t1, b1, cfg.tr_s
        )
        for index in range(angles.numel()):
            gradient = torch.autograd.grad(
                signal[0, 0, index], t1, retain_graph=True
            )[0]
            automatic = gradient * t1
            self.assertAlmostEqual(
                float(analytic[0, 0, index].detach()),
                float(automatic.detach()),
                places=10,
            )

    def test_two_angle_crlb_is_finite(self) -> None:
        cfg = DesignConfig(t1_samples=5, b1_samples=3)
        t1, b1 = scenario_grid(cfg)
        coefficient = relative_t1_crlb_coefficient(
            torch.tensor([3.2, 20.6], dtype=DTYPE), cfg, t1, b1
        )
        self.assertTrue(torch.all(torch.isfinite(coefficient)))
        self.assertTrue(torch.all(coefficient > 0))


if __name__ == "__main__":
    unittest.main()
