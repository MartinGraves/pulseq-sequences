function pulseq_viewer(seq, varargin)
%PULSEQ_VIEWER  Advanced interactive waveform viewer for Pulseq sequences.
%
% Usage:
%   pulseq_viewer(seq, 'TR', 20e-3)
%   pulseq_viewer(seq, 'TR', 20e-3, 'Window', 30e-3)
%   pulseq_viewer(seq, 'TR', 20e-3, 'Window', 1*20e-3, 'Start', 0)
%
% Export:
%   - In the UI, click "Export GIF" or "Export AVI"
%
% Notes:
%   - Zoom/pan are linked across all axes.
%   - Navigation steps by one TR (or by Window if TR not provided).
%   - Designed for Pulseq MATLAB toolbox (mr.Sequence).

% ---------------------------
% Parse inputs
% ---------------------------
p = inputParser;
p.addParameter('TR', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('Window', [], @(x) isempty(x) || (isscalar(x) && x>0));
p.addParameter('Start', 0, @(x) isscalar(x) && x>=0);
p.addParameter('Title', 'Pulseq Viewer', @(s) ischar(s) || isstring(s));
p.addParameter('ShowADCAsStems', true, @(b) islogical(b) && isscalar(b));
p.parse(varargin{:});
TR = p.Results.TR;
win = p.Results.Window;
tStart0 = p.Results.Start;
mainTitle = char(p.Results.Title);
showADCStems = p.Results.ShowADCAsStems;

% ---------------------------
% Extract waveforms (best-effort across Pulseq versions)
% ---------------------------
[w, meta] = local_get_waveforms(seq);

t = w.t(:);                       % seconds
rf = w.rf(:);
gx = w.gx(:);
gy = w.gy(:);
gz = w.gz(:);
adc = w.adc(:);

tEnd = t(end);
dt = median(diff(t));
if isempty(win)
    if ~isempty(TR)
        win = TR;
    else
        % Default: show 30 ms or full if shorter
        win = min(30e-3, tEnd);
    end
end
step = TR;
if isempty(step), step = win; end

% Clamp start
tStart0 = max(0, min(tStart0, max(0, tEnd - win)));

% ---------------------------
% Build UI
% ---------------------------
fig = figure('Name', mainTitle, 'NumberTitle', 'off', ...
    'Color', 'w', 'Units', 'pixels', 'Position', [80 80 1200 760]);

% Controls panel
panelH = uipanel(fig, 'Units', 'pixels', 'Position', [10 10 1180 110], ...
    'Title', 'Controls');

% Plot area
plotPanel = uipanel(fig, 'Units', 'pixels', 'Position', [10 130 1180 620], ...
    'BorderType', 'none');

tl = tiledlayout(plotPanel, 5, 1, 'Padding', 'compact', 'TileSpacing', 'compact');

axRF  = nexttile(tl); axGx = nexttile(tl); axGy = nexttile(tl); axGz = nexttile(tl); axADC = nexttile(tl);
axs = [axRF axGx axGy axGz axADC];
linkaxes(axs, 'x');

% Labels
ylabel(axRF,'RF (a.u.)'); ylabel(axGx,'Gx'); ylabel(axGy,'Gy'); ylabel(axGz,'Gz'); ylabel(axADC,'ADC');
xlabel(axADC,'Time (s)');

% Enable interactive tools
zoom(fig,'on');  % user can toggle off
pan(fig,'on');

% Info text
txtInfo = uicontrol(panelH, 'Style', 'text', 'Units', 'pixels', ...
    'Position', [10 68 720 22], 'HorizontalAlignment', 'left', ...
    'String', '');

% Start/Window/TR display
txtParams = uicontrol(panelH, 'Style', 'text', 'Units', 'pixels', ...
    'Position', [10 42 720 22], 'HorizontalAlignment', 'left', ...
    'String', '');

% Slider for window start
slider = uicontrol(panelH, 'Style', 'slider', 'Units', 'pixels', ...
    'Position', [10 12 720 22], ...
    'Min', 0, 'Max', max(0, tEnd - win), 'Value', tStart0);

% Step buttons
btnPrev = uicontrol(panelH, 'Style', 'pushbutton', 'Units', 'pixels', ...
    'Position', [750 12 90 30], 'String', sprintf('<< %.3gs', step), ...
    'Callback', @(~,~) local_step(-1));

btnNext = uicontrol(panelH, 'Style', 'pushbutton', 'Units', 'pixels', ...
    'Position', [850 12 90 30], 'String', sprintf('%.3gs >>', step), ...
    'Callback', @(~,~) local_step(+1));

btnHome = uicontrol(panelH, 'Style', 'pushbutton', 'Units', 'pixels', ...
    'Position', [750 52 90 30], 'String', 'Home', ...
    'Callback', @(~,~) local_setStart(0));

btnEnd = uicontrol(panelH, 'Style', 'pushbutton', 'Units', 'pixels', ...
    'Position', [850 52 90 30], 'String', 'End', ...
    'Callback', @(~,~) local_setStart(max(0,tEnd-win)));

% Export controls
btnGif = uicontrol(panelH, 'Style', 'pushbutton', 'Units', 'pixels', ...
    'Position', [960 12 100 30], 'String', 'Export GIF', ...
    'Callback', @(~,~) local_export('gif'));

btnAvi = uicontrol(panelH, 'Style', 'pushbutton', 'Units', 'pixels', ...
    'Position', [1070 12 100 30], 'String', 'Export AVI', ...
    'Callback', @(~,~) local_export('avi'));

% Export settings
uicontrol(panelH, 'Style', 'text', 'Units', 'pixels', ...
    'Position', [960 52 80 18], 'String', 'Frames:', 'HorizontalAlignment', 'left');
editFrames = uicontrol(panelH, 'Style', 'edit', 'Units', 'pixels', ...
    'Position', [1015 50 55 22], 'String', '0'); % 0 => auto
uicontrol(panelH, 'Style', 'text', 'Units', 'pixels', ...
    'Position', [1075 52 80 18], 'String', 'FPS:', 'HorizontalAlignment', 'left');
editFps = uicontrol(panelH, 'Style', 'edit', 'Units', 'pixels', ...
    'Position', [1105 50 55 22], 'String', '10');

% Slider callback
slider.Callback = @(~,~) local_update();

% Plot handles
hRF  = plot(axRF,  t, rf,  'LineWidth', 1); grid(axRF,'on');
hGx  = plot(axGx,  t, gx,  'LineWidth', 1); grid(axGx,'on');
hGy  = plot(axGy,  t, gy,  'LineWidth', 1); grid(axGy,'on');
hGz  = plot(axGz,  t, gz,  'LineWidth', 1); grid(axGz,'on');

if showADCStems
    hADC = stem(axADC, t(adc>0), adc(adc>0), 'filled'); %#ok<NASGU>
else
    plot(axADC, t, adc, 'LineWidth', 1);
end
grid(axADC,'on');

% Make axes tight vertically but not horizontally
for a = axs
    a.Box = 'on';
    a.FontSize = 11;
end
title(tl, sprintf('%s  |  dt≈%.3g ms  |  points=%d', mainTitle, dt*1e3, numel(t)));

% Info line
txtInfo.String = sprintf('Waveforms source: %s', meta.source);

% Initial draw
local_update();

% ---------------------------
% Nested functions
% ---------------------------
    function local_update()
        % Enforce slider range if window changed or rounding issues
        slider.Max = max(0, tEnd - win);
        slider.Value = max(slider.Min, min(slider.Value, slider.Max));

        t0 = slider.Value;
        t1 = t0 + win;

        % Set x-limits consistently
        for a = axs
            xlim(a, [t0 t1]);
        end

        % Update status text
        if isempty(TR)
            txtParams.String = sprintf('Start = %.6f s   Window = %.6f s   (step=Window)', t0, win);
        else
            trIdx = floor(t0 / TR) + 1;
            txtParams.String = sprintf('Start = %.6f s   Window = %.6f s   TR = %.6f s   (TR #%d)', t0, win, TR, trIdx);
        end
        drawnow;
    end

    function local_step(direction)
        t0 = slider.Value;
        t0 = t0 + direction * step;
        local_setStart(t0);
    end

    function local_setStart(t0)
        t0 = max(0, min(t0, max(0, tEnd - win)));
        slider.Value = t0;
        local_update();
    end

    function local_export(kind)
        % Decide filename
        ts = datestr(now,'yyyymmdd_HHMMSS');
        if strcmpi(kind,'gif')
            [file, path] = uiputfile('*.gif', 'Save animated GIF', sprintf('pulseq_%s.gif', ts));
        else
            [file, path] = uiputfile('*.avi', 'Save AVI', sprintf('pulseq_%s.avi', ts));
        end
        if isequal(file,0), return; end
        outFile = fullfile(path, file);

        fps = str2double(editFps.String);
        if isnan(fps) || fps<=0, fps = 10; end

        nFrames = str2double(editFrames.String);
        if isnan(nFrames) || nFrames < 0, nFrames = 0; end

        % Determine frame starts
        if nFrames == 0
            % Auto: cover entire sequence with step increments
            starts = 0:step:max(0, tEnd - win);
        else
            % Fixed number: span 0..(tEnd-win)
            if tEnd <= win
                starts = 0;
            else
                starts = linspace(0, tEnd - win, nFrames);
            end
        end

        % Temporarily disable user interaction spam
        oldZoom = zoom(fig); oldPan = pan(fig);
        zoom(fig,'off'); pan(fig,'off');

        % Export
        switch lower(kind)
            case 'avi'
                v = VideoWriter(outFile);
                v.FrameRate = fps;
                open(v);
                for i = 1:numel(starts)
                    local_setStart(starts(i));
                    frame = getframe(fig);
                    writeVideo(v, frame);
                end
                close(v);

            case 'gif'
                delay = 1 / fps;
                for i = 1:numel(starts)
                    local_setStart(starts(i));
                    frame = getframe(fig);
                    im = frame2im(frame);
                    [A, map] = rgb2ind(im, 256);
                    if i == 1
                        imwrite(A, map, outFile, 'gif', 'LoopCount', inf, 'DelayTime', delay);
                    else
                        imwrite(A, map, outFile, 'gif', 'WriteMode', 'append', 'DelayTime', delay);
                    end
                end
            otherwise
                error('Unknown export kind: %s', kind);
        end

        % Restore interaction
        zoom(fig, oldZoom.Enable);
        pan(fig, oldPan.Enable);

        msgbox(sprintf('Exported %s\n%s', upper(kind), outFile), 'Export complete');
    end
end

% ========================================================================
% Helper: waveform extraction compatible with common Pulseq MATLAB versions
% ========================================================================
function [w, meta] = local_get_waveforms(seq)
meta = struct('source','unknown');

% Preferred: seq.waveforms() (common in many Pulseq MATLAB versions)
try
    wf = seq.waveforms();  % may return [t, ...] depending on version
    % Try to interpret typical struct output
    if isstruct(wf)
        w = struct();
        w.t  = wf.t(:);
        w.rf = local_field_or_zeros(wf, 'rf', numel(w.t));
        w.gx = local_field_or_zeros(wf, 'gx', numel(w.t));
        w.gy = local_field_or_zeros(wf, 'gy', numel(w.t));
        w.gz = local_field_or_zeros(wf, 'gz', numel(w.t));
        w.adc= local_field_or_zeros(wf, 'adc', numel(w.t));
        meta.source = 'seq.waveforms() struct';
        return;
    end
catch
end

% Alternate: some versions expose mr.Sequence.getWaveforms or similar
try
    wf = mr.calcWaveforms(seq); %#ok<NASGU>
catch
end

% Last resort: use seq.plot() internals not accessible → fail with guidance
error(['Could not extract waveforms from this Pulseq version.\n' ...
       'Try one of:\n' ...
       '  1) In MATLAB: methods(seq) and look for a waveform export method\n' ...
       '  2) Open D:\\pulseq\\matlab\\+mr\\Sequence.m and search for "function plot" or "waveforms"\n' ...
       '     then tell me the method name your version provides.\n']);
end

function v = local_field_or_zeros(s, name, n)
if isfield(s, name)
    v = s.(name);
    v = v(:);
    if numel(v) ~= n
        % best-effort pad/truncate
        v = local_pad_or_trunc(v, n);
    end
else
    v = zeros(n,1);
end
end

function v = local_pad_or_trunc(v, n)
if numel(v) < n
    v(end+1:n,1) = 0;
else
    v = v(1:n);
end
end
