% demo_gre_cartesian.m
% Pulseq demo: simple 2D Cartesian GRE
clear; clc;

% --- Paths (edit if needed) ---
addpath(genpath('C:\pulseq\matlab'));   % Pulseq MATLAB toolbox
repoRoot = 'D:\Repos\pulseq-sequences'; % your sequences repo
outSeq   = fullfile(repoRoot, 'seq', 'demo_gre_cartesian.seq');

% --- Scanner limits (generic 3T-ish; adjust to your system) ---
sys = mr.opts( ...
    'MaxGrad', 32, 'GradUnit', 'mT/m', ...
    'MaxSlew', 130, 'SlewUnit', 'T/m/s', ...
    'rfRingdownTime', 30e-6, ...
    'rfDeadTime', 100e-6, ...
    'adcDeadTime', 10e-6);

seq = mr.Sequence(sys);

% --- Imaging parameters ---
fov = 220e-3;     % m
Nx  = 128;
Ny  = 128;
slice_thk = 5e-3; % m
flip = 15;        % degrees
TR = 20e-3;       % s
TE = 6e-3;        % s

% --- RF + slice select ---
rf_dur = 3e-3;
tbw = 4;
[rf, gz, gzReph] = mr.makeSincPulse( ...
    flip*pi/180, ...
    'Duration', rf_dur, ...
    'SliceThickness', slice_thk, ...
    'apodization', 0.5, ...
    'timeBwProduct', tbw, ...
    'system', sys);

% --- Readout gradient + ADC ---
dwell = 10e-6;                 % ADC dwell
adc   = mr.makeAdc(Nx, 'Dwell', dwell, 'system', sys);

gx = mr.makeTrapezoid('x', ...
    'FlatArea', Nx/fov, ...
    'FlatTime', Nx*dwell, ...
    'system', sys);

gxPre = mr.makeTrapezoid('x', 'Area', -gx.area/2, 'system', sys);

% --- Phase encode areas ---
dky = 1/fov;
ky = ((-Ny/2):(Ny/2-1)) * dky;

% --- TE delay (approx, relative to center of readout) ---
tPre = max([mr.calcDuration(gxPre), mr.calcDuration(gzReph)]);
tToROCenter = TE - (tPre + mr.calcDuration(gx)/2);
delayTE = mr.makeDelay(max(0, tToROCenter));

% --- TR delay (approx per line) ---
tLine = mr.calcDuration(rf) + mr.calcDuration(gz) + tPre + mr.calcDuration(delayTE) + mr.calcDuration(gx);
delayTR = mr.makeDelay(max(0, TR - tLine));

% --- Sequence loop ---
for iy = 1:Ny
    gyPre = mr.makeTrapezoid('y', 'Area', ky(iy), 'system', sys);

    seq.addBlock(rf, gz);                 % excitation
    seq.addBlock(gxPre, gyPre, gzReph);   % prephasers
    seq.addBlock(delayTE);                % TE delay
    seq.addBlock(gx, adc);                % readout
    seq.addBlock(delayTR);                % TR delay
end

% --- Checks + write ---
[ok, report] = seq.checkTiming;
if ~ok
    disp(report);
    error('Timing check failed');
end

seq.setDefinition('Name', 'demo_gre_cartesian');
seq.setDefinition('FOV', [fov fov slice_thk]);

seq.write(outSeq);
fprintf('Wrote: %s\n', outSeq);

% --- Plot (if available in your Pulseq MATLAB version) ---
try
    seq.plot();
catch
    disp('seq.plot() not available in this Pulseq MATLAB version.');
end
