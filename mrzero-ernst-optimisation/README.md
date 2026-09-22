# MRzero Ernst-angle optimisation

A compact, reproducible project for learning differentiable MRI sequence
optimisation. The first scientific target is deliberately one with a known
answer: gradient-based recovery of the spoiled-GRE Ernst angle.

## Current milestone

The minimum viable project is implemented:

- ideal spoiled-GRE signal model in PyTorch;
- gradient-based flip-angle optimisation;
- systematic validation over 25 T1/TR combinations;
- two-tissue contrast optimisation;
- MRzero/Pulseq verification using a spoiled-GRE sequence;
- CSV and JSON result export;
- six publication-quality figures;
- scientific regression tests.

The work follows the planned order: flip angle first, joint TR/flip angle next,
then robustness to tissue variation and B1+ scaling.

## Project files

- `ernst_optimisation.py` - differentiable signal model and core experiments.
- `mrzero_validation.py` - independent MRzero/Pulseq simulation.
- `test_ernst_optimisation.py` - analytical and autograd checks.
- `requirements.txt` - Python dependencies.
- `run_all.ps1` - Windows setup and run helper.

## Windows setup

Open PowerShell in this directory. Python 3.12 is recommended.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, the virtual environment can still be used
directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ernst_optimisation.py
```

## Run the minimum viable project

```powershell
python -m unittest -v test_ernst_optimisation.py
python ernst_optimisation.py
```

Expected output appears in `results/`:

1. signal curve with analytical and recovered Ernst angles;
2. optimisation convergence history;
3. recovered-versus-analytical identity plot;
4. validation error heatmap;
5. two-tissue contrast plot;
6. validation CSV and summary JSON.

The default single-tissue experiment uses T1 = 1.0 s and TR = 20 ms. The
analytical Ernst angle is approximately 11.42 degrees.

## Run the MRzero/Pulseq validation

```powershell
python mrzero_validation.py
```

This builds a spoiled-GRE Pulseq sequence, simulates it using MRzero Core, and
compares the steady-state flip-angle curve with the analytical model. Its
outputs appear in `results/mrzero/`.

The MRzero simulation is intentionally separate from the differentiable
signal-level optimiser. This makes the optimisation fast and transparent while
retaining an independent sequence-level validation.

## Optimise a minimal brain T1 protocol

```powershell
C:\PythonEnvs\mrzero-ernst\Scripts\python.exe optimal_t1_flip_angles.py
```

The optimiser compares protocols containing two to six unique flip angles over
T1 = 500--2500 ms and B1 = 0.8--1.2 at TR = 20 ms. It minimises the worst-case
Cramer-Rao bound for T1 with M0 as a nuisance parameter. Fisher information is
normalised by the number of angles so designs are compared at fixed total scan
time. The smallest protocol within 5% of the best design is selected.

Outputs are written to `results/t1_design/`, including optimised angles,
precision curves, a B1/T1 precision heatmap, Monte Carlo validation, CSV data,
and a JSON summary.

## Interpretation

For the first experiment, success means that the optimised angle agrees with

```text
alpha_E = arccos(exp(-TR/T1))
```

across the T1/TR grid. The two-tissue experiment then changes the objective
from maximum signal to maximum squared signal difference. The optimal contrast
angle is not generally the Ernst angle of either tissue.

## Next planned work

1. Make TR and flip angle jointly trainable with a scan-time or minimum-TR
   constraint.
2. Optimise expected performance over a distribution of T1 values.
3. Add B1+ scaling during training and compare nominal versus robust designs.
4. Replace the signal-level objective with a small-phantom MRzero objective
   where runtime permits.
5. Consolidate results into the final presentation.

## Technical basis

This implementation follows the current MRzero Core 1.0 interface and the
official MRzero examples:

- [MRzero Core](https://github.com/MRsources/MRzero-Core)
- [Official playground](https://mrsources.github.io/MRzero-Core/playground.html)
- [Original MRzero paper](https://arxiv.org/abs/2002.04265)

The code is for simulation and research training. It is not a scanner-ready
clinical sequence.
