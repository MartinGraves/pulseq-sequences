"""MRzero/Pulseq verification of the spoiled-GRE Ernst-angle experiment.

This script deliberately separates the full MRzero simulation from the fast
PyTorch signal model in ernst_optimisation.py. The latter supplies autograd;
this script verifies that a Pulseq sequence simulated by MRzero reproduces the
same steady-state flip-angle dependence.

Run after installing requirements:
    python mrzero_validation.py
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pypulseq as pp
import torch
import MRzeroCore as mr0


def analytical_signal(flip_deg: np.ndarray, tr_s: float, t1_s: float) -> np.ndarray:
    flip_rad = np.deg2rad(flip_deg)
    e1 = np.exp(-tr_s / t1_s)
    return (1.0 - e1) * np.sin(flip_rad) / (1.0 - e1 * np.cos(flip_rad))


def make_phantom(t1_s: float, spins: int = 201) -> mr0.CustomVoxelPhantom:
    """Uniform isochromats across 10 mm so the spoiler dephases transverse signal."""
    x = torch.linspace(-5e-3, 5e-3, spins)
    positions = torch.stack([x, torch.zeros_like(x), torch.zeros_like(x)], dim=1)
    return mr0.CustomVoxelPhantom(
        positions,
        PD=torch.full((spins,), 1.0 / spins),
        T1=t1_s,
        T2=1.0,
        T2dash=1.0,
        D=0.0,
        B0=0.0,
        B1=1.0,
        voxel_size=0.25e-3,
        voxel_shape="sinc",
    )


def make_spoiled_gre(
    flip_deg: float,
    tr_s: float,
    repetitions: int = 180,
) -> pp.Sequence:
    system = pp.Opts(
        max_grad=28,
        grad_unit="mT/m",
        max_slew=150,
        slew_unit="T/m/s",
        rf_ringdown_time=20e-6,
        rf_dead_time=100e-6,
        adc_dead_time=20e-6,
    )
    seq = pp.Sequence(system)
    spoiler = pp.make_trapezoid(
        channel="x", area=500.0, duration=1.0e-3, system=system
    )
    pre_adc_delay = pp.make_delay(1.0e-3)

    rf_phase_deg = 0.0
    rf_increment_deg = 0.0
    rf_spoiling_increment_deg = 117.0

    for _ in range(repetitions):
        rf = pp.make_block_pulse(
            flip_angle=math.radians(flip_deg),
            duration=0.5e-3,
            phase_offset=math.radians(rf_phase_deg),
            system=system,
        )
        adc = pp.make_adc(
            num_samples=1,
            duration=0.2e-3,
            phase_offset=math.radians(rf_phase_deg),
            system=system,
        )
        occupied = (
            pp.calc_duration(rf)
            + pp.calc_duration(pre_adc_delay)
            + pp.calc_duration(adc)
            + pp.calc_duration(spoiler)
        )
        remaining = tr_s - occupied
        if remaining <= 0:
            raise ValueError(
                f"TR={tr_s * 1e3:.2f} ms is too short; sequence needs "
                f"more than {occupied * 1e3:.2f} ms."
            )

        seq.add_block(rf)
        seq.add_block(pre_adc_delay)
        seq.add_block(adc)
        seq.add_block(spoiler)
        seq.add_block(pp.make_delay(remaining))

        rf_increment_deg = (rf_increment_deg + rf_spoiling_increment_deg) % 360.0
        rf_phase_deg = (rf_phase_deg + rf_increment_deg) % 360.0

    ok, errors = seq.check_timing()
    if not ok:
        raise RuntimeError("Pulseq timing check failed:\n" + "\n".join(errors))
    seq.set_definition("Name", "mrzero_ernst_validation")
    return seq


def simulate_curve(
    flip_angles_deg: np.ndarray,
    tr_s: float,
    t1_s: float,
) -> list[dict[str, float]]:
    phantom = make_phantom(t1_s)
    records: list[dict[str, float]] = []

    for flip_deg in flip_angles_deg:
        seq = make_spoiled_gre(float(flip_deg), tr_s)
        signal, _ = mr0.util.simulate(
            seq,
            phantom=phantom,
            accuracy=1e-4,
            noise_level=None,
        )
        steady_state = float(signal[-20:].abs().mean())
        records.append(
            {
                "flip_deg": float(flip_deg),
                "mrzero_signal": steady_state,
                "analytical_signal": float(
                    analytical_signal(np.array([flip_deg]), tr_s, t1_s)[0]
                ),
            }
        )
        print(f"Flip {flip_deg:5.1f} degrees: MRzero signal {steady_state:.6g}")

    return records


def main() -> None:
    tr_s = 0.020
    t1_s = 1.000
    flip_angles = np.linspace(2.0, 35.0, 23)
    out = Path("results") / "mrzero"
    out.mkdir(parents=True, exist_ok=True)

    records = simulate_curve(flip_angles, tr_s, t1_s)
    mrzero_signal = np.array([r["mrzero_signal"] for r in records])
    analytical = np.array([r["analytical_signal"] for r in records])
    mrzero_normalised = mrzero_signal / mrzero_signal.max()
    analytical_normalised = analytical / analytical.max()

    for row, mr0_n, analytic_n in zip(records, mrzero_normalised, analytical_normalised):
        row["mrzero_normalised"] = float(mr0_n)
        row["analytical_normalised"] = float(analytic_n)

    with (out / "mrzero_curve.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    analytical_ernst_deg = math.degrees(math.acos(math.exp(-tr_s / t1_s)))
    mrzero_peak_deg = float(flip_angles[int(np.argmax(mrzero_signal))])
    rmse = float(np.sqrt(np.mean((mrzero_normalised - analytical_normalised) ** 2)))
    summary = {
        "tr_ms": tr_s * 1000.0,
        "t1_s": t1_s,
        "analytical_ernst_deg": analytical_ernst_deg,
        "mrzero_sampled_peak_deg": mrzero_peak_deg,
        "normalised_curve_rmse": rmse,
        "mrzero_core_version": getattr(mr0, "__version__", "unknown"),
    }
    (out / "mrzero_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.plot(flip_angles, analytical_normalised, lw=2, label="Analytical spoiled GRE")
    ax.scatter(flip_angles, mrzero_normalised, color="#c62828", label="MRzero/Pulseq")
    ax.axvline(analytical_ernst_deg, color="black", ls="--", label="Analytical Ernst angle")
    ax.set(
        xlabel="Flip angle (degrees)",
        ylabel="Normalised steady-state signal",
        title="MRzero validation of the spoiled-GRE Ernst angle",
    )
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "figure_06_mrzero_validation.png", dpi=220)
    plt.close(fig)

    print(json.dumps(summary, indent=2))
    print(f"\nMRzero validation outputs written to: {out.resolve()}")


if __name__ == "__main__":
    main()
