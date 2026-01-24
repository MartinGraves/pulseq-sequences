# pulseq-sequences

Small Pulseq sequence demos written in MATLAB.

## Demo: demo_gre_cartesian
- Script: `matlab/demo_gre_cartesian.m`
- Output: `seq/demo_gre_cartesian.seq`

### How to run
1. Ensure Pulseq MATLAB toolbox is on the MATLAB path (e.g. `C:\pulseq\matlab`)
2. Run the script in MATLAB
3. The `.seq` file is written into `seq/`



## Quick workflow

1) Before editing: VS Code Task → **Pulseq: Sync (pull)**
2) Do work (MATLAB scripts in `matlab/`, outputs in `seq/`)
3) After work: VS Code Task → **Pulseq: Publish (commit + push)**

Commit messages should say:
- what changed (sequence / parameters)
- why (bug fix, new feature, refactor)
