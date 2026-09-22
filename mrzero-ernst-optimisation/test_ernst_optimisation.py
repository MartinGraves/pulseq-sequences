"""Scientific regression tests for the signal-level optimisation."""

import math
import unittest

import torch

from ernst_optimisation import (
    Config,
    ernst_angle_rad,
    single_tissue_experiment,
    spoiled_gre_signal,
)


class ErnstOptimisationTests(unittest.TestCase):
    def test_analytical_ernst_condition(self) -> None:
        tr_s = 0.020
        t1_s = 1.000
        angle = torch.tensor(
            ernst_angle_rad(tr_s, t1_s),
            dtype=torch.float64,
            requires_grad=True,
        )
        signal = spoiled_gre_signal(angle, tr_s, t1_s)
        gradient = torch.autograd.grad(signal, angle)[0]
        self.assertLess(abs(float(gradient)), 1e-10)

    def test_signal_gradient_is_finite(self) -> None:
        angle = torch.tensor(math.radians(15.0), dtype=torch.float64, requires_grad=True)
        signal = spoiled_gre_signal(angle, 0.020, 1.000)
        signal.backward()
        self.assertTrue(torch.isfinite(angle.grad))

    def test_optimizer_recovers_ernst_angle(self) -> None:
        result = single_tissue_experiment(Config(iterations=700))
        self.assertLess(result["absolute_error_deg"], 0.10)


if __name__ == "__main__":
    unittest.main()
