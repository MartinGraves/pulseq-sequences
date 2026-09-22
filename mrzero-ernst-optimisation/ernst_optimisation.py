"""Differentiable spoiled-GRE Ernst-angle and contrast experiments.

This is the fast signal-level layer of the project. It uses PyTorch autograd to:
1. recover the analytical Ernst angle;
2. validate recovery over a grid of T1 and TR values; and
3. optimise flip angle for contrast between two tissues.

Run:
    python ernst_optimisation.py

Outputs are written beneath results/.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch


DTYPE = torch.float64


@dataclass(frozen=True)
class Config:
    t1_s: float = 1.0
    tr_s: float = 0.020
    pd: float = 1.0
    initial_flip_deg: float = 30.0
    iterations: int = 700
    learning_rate: float = 0.04
    tissue_a_t1_s: float = 0.900
    tissue_b_t1_s: float = 1.300
    output_dir: str = "results"


def tensor(value: float) -> torch.Tensor:
    return torch.tensor(value, dtype=DTYPE)


def spoiled_gre_signal(
    flip_rad: torch.Tensor,
    tr_s: torch.Tensor | float,
    t1_s: torch.Tensor | float,
    pd: torch.Tensor | float = 1.0,
    b1_scale: torch.Tensor | float = 1.0,
) -> torch.Tensor:
    """Ideal steady-state spoiled-GRE signal, ignoring T2* and receiver scaling."""
    tr = torch.as_tensor(tr_s, dtype=DTYPE)
    t1 = torch.as_tensor(t1_s, dtype=DTYPE)
    rho = torch.as_tensor(pd, dtype=DTYPE)
    b1 = torch.as_tensor(b1_scale, dtype=DTYPE)
    effective_flip = b1 * flip_rad
    e1 = torch.exp(-tr / t1)
    return rho * (1.0 - e1) * torch.sin(effective_flip) / (
        1.0 - e1 * torch.cos(effective_flip)
    )


def ernst_angle_rad(tr_s: float, t1_s: float) -> float:
    return math.acos(math.exp(-tr_s / t1_s))


def optimise_flip(
    objective,
    initial_flip_deg: float,
    iterations: int,
    learning_rate: float,
) -> tuple[float, list[dict[str, float]]]:
    """Maximise a differentiable scalar objective over 0.05 to 89.95 degrees."""
    flip = torch.nn.Parameter(tensor(math.radians(initial_flip_deg)))
    optimiser = torch.optim.Adam([flip], lr=learning_rate)
    history: list[dict[str, float]] = []

    for step in range(iterations):
        optimiser.zero_grad()
        value = objective(flip)
        (-value).backward()
        optimiser.step()
        with torch.no_grad():
            flip.clamp_(math.radians(0.05), math.radians(89.95))
        history.append(
            {
                "iteration": float(step),
                "flip_deg": math.degrees(float(flip.detach())),
                "objective": float(value.detach()),
            }
        )

    return math.degrees(float(flip.detach())), history


def single_tissue_experiment(cfg: Config) -> dict:
    objective = lambda flip: spoiled_gre_signal(flip, cfg.tr_s, cfg.t1_s, cfg.pd)
    recovered, history = optimise_flip(
        objective, cfg.initial_flip_deg, cfg.iterations, cfg.learning_rate
    )
    analytical = math.degrees(ernst_angle_rad(cfg.tr_s, cfg.t1_s))
    return {
        "analytical_deg": analytical,
        "recovered_deg": recovered,
        "absolute_error_deg": abs(recovered - analytical),
        "history": history,
    }


def systematic_validation(cfg: Config) -> list[dict[str, float]]:
    t1_values = [0.50, 0.75, 1.00, 1.25, 1.50]
    tr_values_ms = [5.0, 10.0, 20.0, 40.0, 60.0]
    records: list[dict[str, float]] = []

    for t1_s in t1_values:
        for tr_ms in tr_values_ms:
            tr_s = tr_ms / 1000.0
            objective = lambda flip, tr=tr_s, t1=t1_s: spoiled_gre_signal(
                flip, tr, t1
            )
            analytical = math.degrees(ernst_angle_rad(tr_s, t1_s))
            recovered, _ = optimise_flip(
                objective,
                initial_flip_deg=max(8.0, analytical + 12.0),
                iterations=cfg.iterations,
                learning_rate=cfg.learning_rate,
            )
            records.append(
                {
                    "t1_s": t1_s,
                    "tr_ms": tr_ms,
                    "analytical_deg": analytical,
                    "recovered_deg": recovered,
                    "error_deg": recovered - analytical,
                }
            )
    return records


def two_tissue_experiment(cfg: Config) -> dict:
    def objective(flip: torch.Tensor) -> torch.Tensor:
        signal_a = spoiled_gre_signal(flip, cfg.tr_s, cfg.tissue_a_t1_s)
        signal_b = spoiled_gre_signal(flip, cfg.tr_s, cfg.tissue_b_t1_s)
        return (signal_a - signal_b).square()

    recovered, history = optimise_flip(
        objective, cfg.initial_flip_deg, cfg.iterations, cfg.learning_rate
    )
    flip = tensor(math.radians(recovered))
    signal_a = float(spoiled_gre_signal(flip, cfg.tr_s, cfg.tissue_a_t1_s))
    signal_b = float(spoiled_gre_signal(flip, cfg.tr_s, cfg.tissue_b_t1_s))
    return {
        "optimal_flip_deg": recovered,
        "signal_a": signal_a,
        "signal_b": signal_b,
        "absolute_contrast": abs(signal_a - signal_b),
        "history": history,
    }


def write_csv(path: Path, records: list[dict[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def style_axes(ax: plt.Axes) -> None:
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)


def make_figures(
    cfg: Config, single: dict, validation: list[dict], contrast: dict, out: Path
) -> None:
    angles_deg = np.linspace(0.1, 70.0, 700)
    angles_rad = torch.tensor(np.deg2rad(angles_deg), dtype=DTYPE)
    signals = spoiled_gre_signal(angles_rad, cfg.tr_s, cfg.t1_s).numpy()

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.plot(angles_deg, signals, lw=2, label="Spoiled-GRE signal")
    ax.axvline(single["analytical_deg"], color="black", ls="--", label="Ernst angle")
    ax.scatter(
        [single["recovered_deg"]],
        [float(spoiled_gre_signal(tensor(math.radians(single["recovered_deg"])), cfg.tr_s, cfg.t1_s))],
        color="#c62828",
        zorder=3,
        label="Autograd result",
    )
    ax.set(xlabel="Flip angle (degrees)", ylabel="Relative signal", title="Ernst-angle recovery")
    style_axes(ax)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "figure_01_ernst_signal_curve.png", dpi=220)
    plt.close(fig)

    history = single["history"]
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.plot([row["iteration"] for row in history], [row["flip_deg"] for row in history])
    ax.axhline(single["analytical_deg"], color="black", ls="--", label="Analytical")
    ax.set(xlabel="Optimisation iteration", ylabel="Flip angle (degrees)", title="Gradient optimisation convergence")
    style_axes(ax)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "figure_02_optimisation_history.png", dpi=220)
    plt.close(fig)

    analytical = np.array([r["analytical_deg"] for r in validation])
    recovered = np.array([r["recovered_deg"] for r in validation])
    lim = [0.0, max(analytical.max(), recovered.max()) * 1.08]
    fig, ax = plt.subplots(figsize=(5.8, 5.4))
    ax.scatter(analytical, recovered, c=[r["t1_s"] for r in validation], cmap="viridis", s=55)
    ax.plot(lim, lim, color="black", ls="--")
    ax.set(xlim=lim, ylim=lim, xlabel="Analytical angle (degrees)", ylabel="Recovered angle (degrees)", title="Systematic Ernst-angle validation")
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(out / "figure_03_validation_identity.png", dpi=220)
    plt.close(fig)

    t1_values = sorted({r["t1_s"] for r in validation})
    tr_values = sorted({r["tr_ms"] for r in validation})
    error = np.zeros((len(t1_values), len(tr_values)))
    for row in validation:
        error[t1_values.index(row["t1_s"]), tr_values.index(row["tr_ms"])] = row["error_deg"]
    fig, ax = plt.subplots(figsize=(7.0, 4.8))
    image = ax.imshow(error, cmap="coolwarm", aspect="auto")
    ax.set_xticks(range(len(tr_values)), labels=[f"{v:g}" for v in tr_values])
    ax.set_yticks(range(len(t1_values)), labels=[f"{v:.2f}" for v in t1_values])
    ax.set(xlabel="TR (ms)", ylabel="T1 (s)", title="Recovered minus analytical angle")
    fig.colorbar(image, ax=ax, label="Error (degrees)")
    fig.tight_layout()
    fig.savefig(out / "figure_04_validation_error_heatmap.png", dpi=220)
    plt.close(fig)

    signal_a = spoiled_gre_signal(angles_rad, cfg.tr_s, cfg.tissue_a_t1_s).numpy()
    signal_b = spoiled_gre_signal(angles_rad, cfg.tr_s, cfg.tissue_b_t1_s).numpy()
    difference = np.abs(signal_a - signal_b)
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.plot(angles_deg, signal_a, label=f"Tissue A: T1={cfg.tissue_a_t1_s:.2f} s")
    ax.plot(angles_deg, signal_b, label=f"Tissue B: T1={cfg.tissue_b_t1_s:.2f} s")
    ax.plot(angles_deg, difference, lw=2.2, label="Absolute contrast")
    ax.axvline(contrast["optimal_flip_deg"], color="black", ls="--", label="Optimised angle")
    ax.set(xlabel="Flip angle (degrees)", ylabel="Relative signal / contrast", title="Two-tissue contrast optimisation")
    style_axes(ax)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "figure_05_two_tissue_contrast.png", dpi=220)
    plt.close(fig)


def main() -> None:
    torch.manual_seed(20260922)
    cfg = Config()
    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    single = single_tissue_experiment(cfg)
    validation = systematic_validation(cfg)
    contrast = two_tissue_experiment(cfg)
    write_csv(out / "ernst_validation.csv", validation)
    make_figures(cfg, single, validation, contrast, out)

    summary = {
        "configuration": asdict(cfg),
        "single_tissue": {k: v for k, v in single.items() if k != "history"},
        "systematic_validation": {
            "experiments": len(validation),
            "mean_absolute_error_deg": float(np.mean(np.abs([r["error_deg"] for r in validation]))),
            "maximum_absolute_error_deg": float(np.max(np.abs([r["error_deg"] for r in validation]))),
        },
        "two_tissue": {k: v for k, v in contrast.items() if k != "history"},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nResults written to: {out.resolve()}")


if __name__ == "__main__":
    main()
