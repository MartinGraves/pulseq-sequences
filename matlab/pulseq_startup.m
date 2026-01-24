function pulseq_startup()
%PULSEQ_STARTUP  On-demand setup for Pulseq development

    pulseqToolbox = 'D:\pulseq\matlab';
    seqRepo       = 'D:\Repos\pulseq-sequences';

    % Add Pulseq toolbox (idempotent)
    assert(exist(pulseqToolbox,'dir')==7, ...
        'Pulseq toolbox not found at %s', pulseqToolbox);
    if isempty(strfind(path, pulseqToolbox)) %#ok<STREMP>
        addpath(genpath(pulseqToolbox));
    end

    % Go to repo root
    assert(exist(seqRepo,'dir')==7, ...
        'Sequences repo not found at %s', seqRepo);
    cd(seqRepo);

    % Sanity check
    fprintf('Pulseq toolbox: %s\n', pulseqToolbox);
    fprintf('Repo:           %s\n', seqRepo);
    fprintf('mr.Sequence:    %s\n', which('mr.Sequence'));

    disp('Pulseq environment ready.');

    disp(' ');
    disp('=== Pulseq GitHub workflow reminder ===');
    disp('1) Before editing:  VS Code → Tasks → "Pulseq: Sync (pull)"');
    disp('2) After finishing: VS Code → Tasks → "Pulseq: Publish (commit + push)"');
    disp('Commit messages: what changed + why (include TE/TR/FOV/res/spoiling if relevant).');
    disp('======================================');
end
