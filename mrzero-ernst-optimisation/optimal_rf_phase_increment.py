"""Optimise a quadratic RF-spoiling phase increment for VFA T1 mapping.

This script uses an extended phase graph (EPG) simulation to choose the RF
phase increment that minimises bias when EPG signals are fitted with the ideal
spoiled-GRE variable-flip-angle (VFA) signal model.  The default protocol is
the two-angle design produced by ``optimal_t1_flip_angles.py``.

The result is sequence-model specific.  Defaults assume one complete EPG
coherence-order shift per TR, no diffusion, 300 preparation/readout pulses,
and averaging of the final 40 signals.  Change these settings to match the
scanner sequence before treating the result as a protocol value.

RF phase convention (degrees)::

    increment_n = (increment_(n-1) + seed) mod 360
    phase_n = (phase_(n-1) + increment_n) mod 360

Run:
    python optimal_rf_phase_increment.py
    python optimal_rf_phase_increment.py --quick
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


@dataclass(frozen=True)
class PhaseDesignConfig:
    t1_min_s: float = 0.500
    t1_max_s: float = 2.500
    t1_samples: int = 9
    t2_min_s: float = 0.040
    t2_max_s: float = 0.120
    t2_samples: int = 5
    b1_min: float = 0.80
    b1_max: float = 1.20
    b1_samples: int = 3
    tr_s: float = 0.020
    flip_angles_deg: tuple[float, ...] = (3.284, 20.075)
    repetitions: int = 300
    steady_state_average: int = 40
    epg_states: int = 80
    coarse_step_deg: float = 2.0
    refine_half_width_deg: float = 3.0
    refine_step_deg: float = 0.1
    output_dir: str = "results/rf_spoiling"


def quadratic_rf_phases(seed_deg: float, count: int) -> np.ndarray:
    """Return RF phases for the documented recursive convention."""
    phases = np.empty(count, dtype=float)
    phase = 0.0
    increment = 0.0
    for index in range(count):
        increment = (increment + seed_deg) % 360.0
        phase = (phase + increment) % 360.0
        phases[index] = phase
    return phases


def scenario_grid(cfg: PhaseDesignConfig) -> tuple[np.ndarray, ...]:
    """Flatten the Cartesian T1/T2/B1 design grid."""
    t1 = np.linspace(cfg.t1_min_s, cfg.t1_max_s, cfg.t1_samples)
    t2 = np.linspace(cfg.t2_min_s, cfg.t2_max_s, cfg.t2_samples)
    b1 = np.linspace(cfg.b1_min, cfg.b1_max, cfg.b1_samples)
    return tuple(x.ravel() for x in np.meshgrid(t1, t2, b1, indexing="ij"))


def epg_spgr_signal(
    flip_deg: float,
    seed_deg: float,
    t1_s: np.ndarray,
    t2_s: np.ndarray,
    b1_scale: np.ndarray,
    cfg: PhaseDesignConfig,
) -> np.ndarray:
    """Simulate the steady-state magnitude using a vectorised EPG model."""
    scenario_count = t1_s.size
    states = np.zeros((scenario_count, 3, cfg.epg_states), dtype=np.complex128)
    states[:, 2, 0] = 1.0
    e1 = np.exp(-cfg.tr_s / t1_s)
    e2 = np.exp(-cfg.tr_s / t2_s)
    alpha = np.deg2rad(flip_deg * b1_scale)
    cosine = np.cos(alpha)
    sine = np.sin(alpha)
    cosine_half_sq = np.cos(alpha / 2.0) ** 2
    sine_half_sq = np.sin(alpha / 2.0) ** 2
    phases = np.deg2rad(quadratic_rf_phases(seed_deg, cfg.repetitions))
    tail = np.empty((cfg.steady_state_average, scenario_count), dtype=float)
    tail_start = cfg.repetitions - cfg.steady_state_average

    for repetition, phase in enumerate(phases):
        f_plus = states[:, 0].copy()
        f_minus = states[:, 1].copy()
        z = states[:, 2].copy()
        exp_phase = np.exp(1j * phase)
        exp_two_phase = exp_phase * exp_phase

        states[:, 0] = (
            cosine_half_sq[:, None] * f_plus
            + (exp_two_phase * sine_half_sq)[:, None] * f_minus
            - (1j * exp_phase * sine)[:, None] * z
        )
        states[:, 1] = (
            (np.conj(exp_two_phase) * sine_half_sq)[:, None] * f_plus
            + cosine_half_sq[:, None] * f_minus
            + (1j * np.conj(exp_phase) * sine)[:, None] * z
        )
        states[:, 2] = (
            (-0.5j * np.conj(exp_phase) * sine)[:, None] * f_plus
            + (0.5j * exp_phase * sine)[:, None] * f_minus
            + cosine[:, None] * z
        )

        if repetition >= tail_start:
            # Receiver demodulation does not affect magnitude, but makes the
            # signal definition explicit and useful for future complex fits.
            tail[repetition - tail_start] = np.abs(
                states[:, 0, 0] * np.conj(exp_phase)
            )

        states[:, 0] *= e2[:, None]
        states[:, 1] *= e2[:, None]
        states[:, 2] *= e1[:, None]
        states[:, 2, 0] += 1.0 - e1

        # One full coherence-order shift represents the gradient spoiler.
        shifted_plus = np.zeros_like(states[:, 0])
        shifted_minus = np.zeros_like(states[:, 1])
        shifted_plus[:, 1:] = states[:, 0, :-1]
        shifted_minus[:, :-1] = states[:, 1, 1:]
        shifted_plus[:, 0] = np.conj(shifted_minus[:, 0])
        states[:, 0] = shifted_plus
        states[:, 1] = shifted_minus

    return np.mean(tail, axis=0)


def ideal_spgr_dictionary(
    t1_fit_s: np.ndarray,
    b1_scale: float,
    cfg: PhaseDesignConfig,
) -> np.ndarray:
    angles = np.deg2rad(np.asarray(cfg.flip_angles_deg) * b1_scale)[None, :]
    e1 = np.exp(-cfg.tr_s / t1_fit_s[:, None])
    return (1.0 - e1) * np.sin(angles) / (1.0 - e1 * np.cos(angles))


def fit_t1_from_signals(
    signals: np.ndarray,
    b1_scale: np.ndarray,
    cfg: PhaseDesignConfig,
) -> np.ndarray:
    """Fit T1 and nuisance M0 using an ideal-SPGR dictionary."""
    fit_grid = np.linspace(cfg.t1_min_s * 0.4, cfg.t1_max_s * 1.8, 4301)
    estimates = np.empty(signals.shape[0])
    for scale in np.unique(b1_scale):
        selection = np.isclose(b1_scale, scale)
        dictionary = ideal_spgr_dictionary(fit_grid, float(scale), cfg)
        norm = np.sum(dictionary * dictionary, axis=1)
        observed = signals[selection]
        dot = observed @ dictionary.T
        residual = (
            np.sum(observed * observed, axis=1)[:, None]
            - np.square(dot) / norm[None, :]
        )
        estimates[selection] = fit_grid[np.argmin(residual, axis=1)]
    return estimates


def evaluate_seed(seed_deg: float, cfg: PhaseDesignConfig) -> dict[str, float]:
    t1, t2, b1 = scenario_grid(cfg)
    signals = np.column_stack(
        [epg_spgr_signal(angle, seed_deg, t1, t2, b1, cfg) for angle in cfg.flip_angles_deg]
    )
    estimate = fit_t1_from_signals(signals, b1, cfg)
    bias = 100.0 * (estimate - t1) / t1
    return {
        "seed_deg": float(seed_deg),
        "worst_absolute_bias_percent": float(np.max(np.abs(bias))),
        "rms_bias_percent": float(np.sqrt(np.mean(np.square(bias)))),
        "mean_absolute_bias_percent": float(np.mean(np.abs(bias))),
    }


def optimise_seed(cfg: PhaseDesignConfig) -> tuple[dict[str, float], list[dict[str, float]]]:
    coarse_seeds = np.arange(0.0, 180.0 + cfg.coarse_step_deg / 2.0, cfg.coarse_step_deg)
    print(f"Coarse sweep: {len(coarse_seeds)} seeds")
    coarse = [evaluate_seed(float(seed), cfg) for seed in coarse_seeds]
    coarse_best = min(
        coarse,
        key=lambda row: (row["worst_absolute_bias_percent"], row["rms_bias_percent"]),
    )
    start = max(0.0, coarse_best["seed_deg"] - cfg.refine_half_width_deg)
    stop = min(180.0, coarse_best["seed_deg"] + cfg.refine_half_width_deg)
    refine_seeds = np.arange(start, stop + cfg.refine_step_deg / 2.0, cfg.refine_step_deg)
    print(f"Refining {start:.2f}--{stop:.2f} degrees: {len(refine_seeds)} seeds")
    refined = [evaluate_seed(float(seed), cfg) for seed in refine_seeds]
    best = min(
        refined,
        key=lambda row: (row["worst_absolute_bias_percent"], row["rms_bias_percent"]),
    )
    return best, coarse + refined


def detailed_bias(seed_deg: float, cfg: PhaseDesignConfig) -> dict[str, np.ndarray]:
    t1, t2, b1 = scenario_grid(cfg)
    signals = np.column_stack(
        [epg_spgr_signal(angle, seed_deg, t1, t2, b1, cfg) for angle in cfg.flip_angles_deg]
    )
    estimate = fit_t1_from_signals(signals, b1, cfg)
    return {"t1_s": t1, "t2_s": t2, "b1_scale": b1, "bias_percent": 100.0 * (estimate - t1) / t1}


def write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_figures(
    sweep: list[dict[str, float]], best: dict[str, float], cfg: PhaseDesignConfig, out: Path
) -> None:
    unique = {}
    for row in sweep:
        unique[round(row["seed_deg"], 8)] = row
    rows = sorted(unique.values(), key=lambda row: row["seed_deg"])
    seeds = np.asarray([row["seed_deg"] for row in rows])
    worst = np.asarray([row["worst_absolute_bias_percent"] for row in rows])
    rms = np.asarray([row["rms_bias_percent"] for row in rows])

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(seeds, worst, label="Worst absolute bias", lw=1.7)
    ax.plot(seeds, rms, label="RMS bias", lw=1.5)
    ax.scatter([best["seed_deg"]], [best["worst_absolute_bias_percent"]], color="#c62828", zorder=4, label=f"Selected: {best['seed_deg']:.2f}°")
    for benchmark in (50.0, 84.0, 115.4, 117.0, 169.0):
        ax.axvline(benchmark, color="0.75", lw=0.7, zorder=0)
    ax.set(xlabel="Quadratic RF phase increment (degrees)", ylabel="T1 bias (%)", title="EPG optimisation of RF spoiling for VFA T1 mapping")
    ax.set_xlim(0, 180)
    ax.grid(alpha=0.22)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "figure_11_rf_phase_seed_sweep.png", dpi=220)
    plt.close(fig)

    detail = detailed_bias(best["seed_deg"], cfg)
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    combinations = sorted(set(zip(detail["t2_s"], detail["b1_scale"])))
    for t2, b1 in combinations:
        chosen = np.isclose(detail["t2_s"], t2) & np.isclose(detail["b1_scale"], b1)
        order = np.argsort(detail["t1_s"][chosen])
        ax.plot(
            detail["t1_s"][chosen][order] * 1000.0,
            detail["bias_percent"][chosen][order],
            alpha=0.65,
            lw=1.0,
            label=f"T2={t2 * 1000:.0f} ms, B1={b1:.1f}",
        )
    ax.axhline(0, color="black", lw=0.8)
    ax.set(xlabel="True T1 (ms)", ylabel="Fitted T1 bias (%)", title=f"Bias at selected RF phase seed ({best['seed_deg']:.2f}°)")
    ax.grid(alpha=0.22)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(ncol=3, fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "figure_12_rf_phase_t1_bias.png", dpi=220)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Use a smaller grid for a rapid software check.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = PhaseDesignConfig()
    if args.quick:
        cfg = PhaseDesignConfig(
            t1_samples=5,
            t2_samples=3,
            repetitions=180,
            steady_state_average=20,
            epg_states=50,
            coarse_step_deg=10.0,
            refine_half_width_deg=2.0,
            refine_step_deg=0.5,
        )

    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    best, sweep = optimise_seed(cfg)
    benchmarks = [evaluate_seed(seed, cfg) for seed in (50.0, 84.0, 115.4, 117.0, 169.0)]

    unique = {round(row["seed_deg"], 8): row for row in sweep}
    write_csv(out / "rf_phase_seed_sweep.csv", sorted(unique.values(), key=lambda row: row["seed_deg"]))
    write_csv(out / "rf_phase_benchmarks.csv", benchmarks)
    make_figures(sweep, best, cfg, out)

    summary = {
        "configuration": asdict(cfg),
        "selected_seed": best,
        "benchmarks": benchmarks,
        "objective": "lexicographic minimum of worst absolute T1 bias, then RMS bias",
        "fit_model": "ideal spoiled-GRE VFA with fitted M0 and known B1",
        "epg_spoiler_model": "one complete coherence-order shift per TR; no diffusion",
        "warning": "Sequence-specific simulation result; validate with the exact RF pulse, gradient spoiler, diffusion model, and scanner implementation.",
    }
    (out / "optimal_rf_phase_increment_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print("\nSelected quadratic RF phase increment")
    print(f"  Seed: {best['seed_deg']:.2f} degrees")
    print(f"  Worst absolute T1 bias: {best['worst_absolute_bias_percent']:.3f}%")
    print(f"  RMS T1 bias: {best['rms_bias_percent']:.3f}%")
    print("  This value is specific to the documented EPG assumptions.")
    print(f"  Results written to: {out.resolve()}")


if __name__ == "__main__":
    main()
