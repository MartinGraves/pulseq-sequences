"""Robust optimal flip-angle design for spoiled-GRE T1 mapping.

The design criterion is the Cramer-Rao lower bound (CRLB) for log(T1), with
M0 treated as an unknown nuisance parameter. Candidate protocols containing
2--6 unique flip angles are optimised over a grid of T1 and B1 values. Fisher
information is normalised by the number of flip angles, so protocols are
compared at fixed total acquisition time.

Defaults target adult brain parenchyma at 3 T:
    T1: 500--2500 ms
    B1 scale: 0.8--1.2
    TR: 20 ms
    flip-angle limits: 1--35 degrees

Run:
    python optimal_t1_flip_angles.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch


DTYPE = torch.float64


@dataclass(frozen=True)
class DesignConfig:
    t1_min_s: float = 0.500
    t1_max_s: float = 2.500
    t1_samples: int = 81
    b1_min: float = 0.80
    b1_max: float = 1.20
    b1_samples: int = 9
    tr_s: float = 0.020
    min_flip_deg: float = 1.0
    max_flip_deg: float = 35.0
    min_separation_deg: float = 2.0
    min_angles: int = 2
    max_angles: int = 6
    restarts: int = 12
    iterations: int = 1600
    learning_rate: float = 0.045
    smooth_max_beta: float = 0.30
    efficiency_tolerance: float = 0.05
    sigma_over_m0: float = 0.001
    monte_carlo_repeats: int = 500
    seed: int = 20260922
    output_dir: str = "results/t1_design"


def scenario_grid(cfg: DesignConfig) -> tuple[torch.Tensor, torch.Tensor]:
    t1 = torch.linspace(cfg.t1_min_s, cfg.t1_max_s, cfg.t1_samples, dtype=DTYPE)
    b1 = torch.linspace(cfg.b1_min, cfg.b1_max, cfg.b1_samples, dtype=DTYPE)
    return torch.meshgrid(t1, b1, indexing="ij")


def ordered_angles(raw: torch.Tensor, cfg: DesignConfig, count: int) -> torch.Tensor:
    """Map unconstrained parameters to ordered angles with a minimum spacing."""
    mandatory = (count - 1) * cfg.min_separation_deg
    free_range = cfg.max_flip_deg - cfg.min_flip_deg - mandatory
    if free_range <= 0:
        raise ValueError("Flip-angle range is too narrow for the requested spacing.")

    allocations = torch.softmax(raw, dim=0) * free_range
    angles = []
    position = torch.as_tensor(cfg.min_flip_deg, dtype=DTYPE)
    for index in range(count):
        position = position + allocations[index]
        angles.append(position + index * cfg.min_separation_deg)
    return torch.stack(angles)


def signal_and_log_t1_derivative(
    angles_deg: torch.Tensor,
    t1_s: torch.Tensor,
    b1_scale: torch.Tensor,
    tr_s: float,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Return S/M0 and d(S/M0)/d(log T1) for ideal spoiled GRE."""
    alpha = torch.deg2rad(angles_deg)[None, None, :]
    t1 = t1_s[:, :, None]
    b1 = b1_scale[:, :, None]
    effective_alpha = b1 * alpha
    e1 = torch.exp(-tr_s / t1)
    denominator = 1.0 - e1 * torch.cos(effective_alpha)
    signal = (1.0 - e1) * torch.sin(effective_alpha) / denominator
    derivative = (
        torch.sin(effective_alpha)
        * (torch.cos(effective_alpha) - 1.0)
        * e1
        * tr_s
        / t1
        / denominator.square()
    )
    return signal, derivative


def relative_t1_crlb_coefficient(
    angles_deg: torch.Tensor,
    cfg: DesignConfig,
    t1_s: torch.Tensor,
    b1_scale: torch.Tensor,
) -> torch.Tensor:
    """Noise-normalised relative T1 SD from the two-parameter Fisher matrix.

    The returned coefficient is multiplied by sigma/M0 to obtain relative T1
    standard deviation. Averaging the Fisher information across flip angles
    gives a fixed-total-acquisition-time comparison between protocol sizes.
    """
    signal, derivative = signal_and_log_t1_derivative(
        angles_deg, t1_s, b1_scale, cfg.tr_s
    )
    f00 = torch.mean(signal.square(), dim=-1)
    f01 = torch.mean(signal * derivative, dim=-1)
    f11 = torch.mean(derivative.square(), dim=-1)
    determinant = (f00 * f11 - f01.square()).clamp_min(1e-24)
    variance_log_t1 = f00 / determinant
    return torch.sqrt(variance_log_t1)


def smooth_max(values: torch.Tensor, beta: float) -> torch.Tensor:
    flat = values.flatten()
    return torch.logsumexp(beta * flat, dim=0) / beta


def optimise_protocol(
    count: int,
    cfg: DesignConfig,
    t1_grid: torch.Tensor,
    b1_grid: torch.Tensor,
) -> dict:
    best: dict | None = None
    generator = torch.Generator().manual_seed(cfg.seed + count)

    for restart in range(cfg.restarts):
        if restart == 0:
            raw = torch.zeros(count + 1, dtype=DTYPE)
        else:
            raw = torch.randn(count + 1, generator=generator, dtype=DTYPE)
        raw = torch.nn.Parameter(raw)
        optimiser = torch.optim.Adam([raw], lr=cfg.learning_rate)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimiser, T_max=cfg.iterations, eta_min=cfg.learning_rate * 0.03
        )

        for _ in range(cfg.iterations):
            optimiser.zero_grad()
            angles = ordered_angles(raw, cfg, count)
            coefficient = relative_t1_crlb_coefficient(
                angles, cfg, t1_grid, b1_grid
            )
            loss = smooth_max(coefficient, cfg.smooth_max_beta)
            loss.backward()
            optimiser.step()
            scheduler.step()

        with torch.no_grad():
            angles = ordered_angles(raw, cfg, count)
            coefficient = relative_t1_crlb_coefficient(
                angles, cfg, t1_grid, b1_grid
            )
            hard_worst = float(coefficient.max())
            candidate = {
                "count": count,
                "angles_deg": [float(x) for x in angles],
                "worst_coefficient": hard_worst,
                "mean_coefficient": float(coefficient.mean()),
                "median_coefficient": float(coefficient.median()),
            }
            if best is None or hard_worst < best["worst_coefficient"]:
                best = candidate

    assert best is not None
    return best


def evaluate_protocol(
    angles_deg: list[float], cfg: DesignConfig
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t1 = torch.linspace(cfg.t1_min_s, cfg.t1_max_s, cfg.t1_samples, dtype=DTYPE)
    b1 = torch.linspace(cfg.b1_min, cfg.b1_max, cfg.b1_samples, dtype=DTYPE)
    t1_grid, b1_grid = torch.meshgrid(t1, b1, indexing="ij")
    coefficient = relative_t1_crlb_coefficient(
        torch.tensor(angles_deg, dtype=DTYPE), cfg, t1_grid, b1_grid
    )
    return t1.numpy(), b1.numpy(), coefficient.numpy()


def monte_carlo_validation(
    angles_deg: list[float], cfg: DesignConfig
) -> list[dict[str, float]]:
    """Validate selected angles using nonlinear grid-search T1 fitting."""
    rng = np.random.default_rng(cfg.seed)
    angles = np.deg2rad(np.asarray(angles_deg))[None, :]
    fit_t1 = np.linspace(max(0.25, cfg.t1_min_s * 0.6), cfg.t1_max_s * 1.4, 2201)
    truth_t1 = np.linspace(cfg.t1_min_s, cfg.t1_max_s, 5)
    truth_b1 = np.linspace(cfg.b1_min, cfg.b1_max, 3)
    records: list[dict[str, float]] = []

    for b1 in truth_b1:
        effective = b1 * angles
        e1_fit = np.exp(-cfg.tr_s / fit_t1[:, None])
        dictionary = (1.0 - e1_fit) * np.sin(effective) / (
            1.0 - e1_fit * np.cos(effective)
        )
        dictionary_norm = np.sum(np.square(dictionary), axis=1)

        for t1_true in truth_t1:
            e1 = np.exp(-cfg.tr_s / t1_true)
            clean = (1.0 - e1) * np.sin(effective[0]) / (
                1.0 - e1 * np.cos(effective[0])
            )
            noisy = clean[None, :] + cfg.sigma_over_m0 * rng.standard_normal(
                (cfg.monte_carlo_repeats, len(angles_deg))
            )
            dot = noisy @ dictionary.T
            fitted_m0 = dot / dictionary_norm[None, :]
            residual = (
                np.sum(noisy.square(), axis=1)[:, None]
                - 2.0 * fitted_m0 * dot
                + fitted_m0.square() * dictionary_norm[None, :]
            )
            estimate = fit_t1[np.argmin(residual, axis=1)]
            records.append(
                {
                    "true_t1_ms": float(t1_true * 1000.0),
                    "b1_scale": float(b1),
                    "mean_t1_ms": float(np.mean(estimate) * 1000.0),
                    "bias_percent": float(100.0 * (np.mean(estimate) - t1_true) / t1_true),
                    "sd_percent": float(100.0 * np.std(estimate, ddof=1) / t1_true),
                }
            )
    return records


def write_csv(path: Path, records: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def make_figures(
    protocols: list[dict], selected: dict, cfg: DesignConfig, out: Path
) -> None:
    counts = [p["count"] for p in protocols]
    worst = [p["worst_coefficient"] * cfg.sigma_over_m0 * 100 for p in protocols]

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.plot(counts, worst, "o-", lw=2)
    ax.scatter([selected["count"]], [worst[counts.index(selected["count"])]], s=100, color="#c62828", zorder=3)
    ax.set(xlabel="Number of unique flip angles", ylabel="Worst-case relative T1 SD (%)", title="Precision versus protocol size at fixed total scan time")
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "figure_07_protocol_size.png", dpi=220)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    for p in protocols:
        ax.scatter([p["count"]] * p["count"], p["angles_deg"], s=45, label=f"K={p['count']}")
    ax.set(xlabel="Number of unique flip angles", ylabel="Optimised flip angle (degrees)", title="Optimised robust T1 protocols")
    ax.set_xticks(counts)
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "figure_08_optimised_angles.png", dpi=220)
    plt.close(fig)

    t1, b1, coefficient = evaluate_protocol(selected["angles_deg"], cfg)
    precision = coefficient * cfg.sigma_over_m0 * 100.0
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    for index, scale in enumerate(b1):
        ax.plot(t1 * 1000.0, precision[:, index], label=f"B1={scale:.2f}")
    ax.set(xlabel="T1 (ms)", ylabel="Predicted relative T1 SD (%)", title=f"Selected {selected['count']}-angle protocol")
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "figure_09_precision_curves.png", dpi=220)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    image = ax.imshow(
        precision.T,
        origin="lower",
        aspect="auto",
        extent=[t1[0] * 1000, t1[-1] * 1000, b1[0], b1[-1]],
        cmap="viridis",
    )
    ax.set(xlabel="T1 (ms)", ylabel="B1 scale", title="Robust-design precision map")
    fig.colorbar(image, ax=ax, label="Relative T1 SD (%)")
    fig.tight_layout()
    fig.savefig(out / "figure_10_precision_heatmap.png", dpi=220)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Use fewer iterations and restarts for a rapid check.")
    parser.add_argument("--no-monte-carlo", action="store_true", help="Skip Monte Carlo validation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = DesignConfig()
    if args.quick:
        cfg = DesignConfig(restarts=3, iterations=400, monte_carlo_repeats=100)

    torch.manual_seed(cfg.seed)
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    t1_grid, b1_grid = scenario_grid(cfg)

    protocols = []
    for count in range(cfg.min_angles, cfg.max_angles + 1):
        print(f"Optimising {count} flip angles...")
        result = optimise_protocol(count, cfg, t1_grid, b1_grid)
        protocols.append(result)
        print(
            f"  angles: {', '.join(f'{x:.3f}' for x in result['angles_deg'])} degrees; "
            f"worst coefficient: {result['worst_coefficient']:.3f}"
        )

    best_worst = min(p["worst_coefficient"] for p in protocols)
    threshold = best_worst * (1.0 + cfg.efficiency_tolerance)
    selected = next(p for p in protocols if p["worst_coefficient"] <= threshold)
    selected = dict(selected)
    selected["predicted_worst_relative_sd_percent"] = (
        selected["worst_coefficient"] * cfg.sigma_over_m0 * 100.0
    )

    protocol_rows = []
    for p in protocols:
        protocol_rows.append(
            {
                "angle_count": p["count"],
                "angles_deg": "; ".join(f"{x:.6f}" for x in p["angles_deg"]),
                "worst_crlb_coefficient": p["worst_coefficient"],
                "mean_crlb_coefficient": p["mean_coefficient"],
                "predicted_worst_relative_sd_percent": p["worst_coefficient"] * cfg.sigma_over_m0 * 100.0,
            }
        )
    write_csv(out / "optimised_protocols.csv", protocol_rows)

    monte_carlo = []
    if not args.no_monte_carlo:
        print("Running Monte Carlo validation...")
        monte_carlo = monte_carlo_validation(selected["angles_deg"], cfg)
        write_csv(out / "monte_carlo_validation.csv", monte_carlo)

    make_figures(protocols, selected, cfg, out)
    summary = {
        "configuration": asdict(cfg),
        "comparison_basis": "fixed total acquisition time; equal allocation per flip angle",
        "parameter_model": ["M0", "log(T1)"],
        "b1_assumption": "B1 is known at fitting but design is robust over the configured B1 range",
        "protocols": protocols,
        "selected_protocol": selected,
        "selection_rule": f"smallest K within {100 * cfg.efficiency_tolerance:.1f}% of the best worst-case CRLB",
        "monte_carlo_scenarios": len(monte_carlo),
    }
    (out / "optimal_t1_design_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print("\nSelected protocol")
    print(f"  Number of flip angles: {selected['count']}")
    print("  Flip angles: " + ", ".join(f"{x:.3f} degrees" for x in selected["angles_deg"]))
    print(f"  Predicted worst relative T1 SD: {selected['predicted_worst_relative_sd_percent']:.2f}%")
    print(f"  Results written to: {out.resolve()}")


if __name__ == "__main__":
    main()
