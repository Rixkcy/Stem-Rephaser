// Unified Suite: Stem Rephaser & Media Sanitizer JavaScript Controller

let currentJobData = null;
let currentStemsData = null;
let audioCtx = null;
let sanitizerPollInterval = null;

// Tab Switching
function switchTab(tabName) {
    const tabMidiBtn = document.getElementById('tabMidiBtn');
    const tabSanitizerBtn = document.getElementById('tabSanitizerBtn');
    const tabMidiView = document.getElementById('tabMidiView');
    const tabSanitizerView = document.getElementById('tabSanitizerView');

    if (tabName === 'midi') {
        tabMidiBtn.classList.add('active');
        tabSanitizerBtn.classList.remove('active');
        tabMidiView.classList.remove('hidden');
        tabSanitizerView.classList.add('hidden');
        
        // Re-render canvases if data is present
        if (currentJobData) {
            setTimeout(redrawAllCanvases, 100);
        }
    } else {
        tabSanitizerBtn.classList.add('active');
        tabMidiBtn.classList.remove('active');
        tabSanitizerView.classList.remove('hidden');
        tabMidiView.classList.add('hidden');
    }
}

function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
}

// Web Audio Synthetic Sound Generators for preview
function playSynthSound(pitch, type = 'kick') {
    initAudio();
    const now = audioCtx.currentTime;

    if (type === 'kick') {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.frequency.setValueAtTime(150, now);
        osc.frequency.exponentialRampToValueAtTime(30, now + 0.15);
        gain.gain.setValueAtTime(1.0, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.15);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.15);
    } else if (type === 'snare') {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(180, now);
        gain.gain.setValueAtTime(0.7, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.2);
    } else if (type === 'hihat') {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'square';
        osc.frequency.setValueAtTime(8000, now);
        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.05);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.05);
    } else if (type === 'cymbals') {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(6000, now);
        gain.gain.setValueAtTime(0.4, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.5);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.5);
    } else {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        const freq = 440 * Math.pow(2, (pitch - 69) / 12);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, now);
        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.4);
    }
}

// Robust Piano-Roll Canvas Renderer with explicit parent width fallback
function renderPianoRollCanvas(canvasId, barDataOrNotes, blueprintSections = [], mainColor = '#00f0ff') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    const parentBox = canvas.parentElement;
    const parentWidth = parentBox ? parentBox.clientWidth : 0;
    const displayWidth = Math.max(900, parentWidth > 0 ? parentWidth - 32 : 1200);
    const displayHeight = 160;

    canvas.style.width = displayWidth + 'px';
    canvas.style.height = displayHeight + 'px';
    canvas.width = displayWidth * dpr;
    canvas.height = displayHeight * dpr;
    ctx.scale(dpr, dpr);

    const w = displayWidth;
    const h = displayHeight;
    ctx.clearRect(0, 0, w, h);

    // Extract flat note list
    let notes = [];
    let totalBars = 64;

    if (Array.isArray(barDataOrNotes) && barDataOrNotes.length > 0 && barDataOrNotes[0].bar && barDataOrNotes[0].notes) {
        totalBars = barDataOrNotes.length;
        barDataOrNotes.forEach(b => {
            b.notes.forEach(n => {
                notes.push({
                    bar: b.bar,
                    beat: n.beat,
                    pitch: n.pitch,
                    vel: n.vel,
                    dur: n.dur
                });
            });
        });
    } else if (Array.isArray(barDataOrNotes)) {
        notes = barDataOrNotes;
        if (notes.length > 0) {
            totalBars = Math.max(...notes.map(n => n.bar || 1));
        }
    }

    if (totalBars === 0) totalBars = 64;
    const barWidth = w / totalBars;

    // 1. Draw Section Background Highlights & Labels
    blueprintSections.forEach(sec => {
        const startX = (sec.start_bar - 1) * barWidth;
        const secW = (sec.end_bar - sec.start_bar + 1) * barWidth;

        let bg = 'rgba(16, 185, 129, 0.08)';
        if (sec.type === 'BUILD_UP') bg = 'rgba(245, 158, 11, 0.12)';
        if (sec.type === 'BREAK_DROP') bg = 'rgba(239, 68, 68, 0.15)';
        if (sec.type === 'SLOW') bg = 'rgba(139, 92, 246, 0.12)';

        ctx.fillStyle = bg;
        ctx.fillRect(startX, 0, secW, h);

        ctx.fillStyle = 'rgba(255, 255, 255, 0.45)';
        ctx.font = '10px JetBrains Mono';
        ctx.fillText(sec.type, startX + 4, 14);
    });

    // 2. Draw Bar Lines & Numbers
    for (let i = 0; i <= totalBars; i++) {
        const x = i * barWidth;
        ctx.strokeStyle = i % 4 === 0 ? 'rgba(255, 255, 255, 0.15)' : 'rgba(255, 255, 255, 0.04)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();

        if (i > 0 && i % 4 === 0 && i < totalBars) {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
            ctx.font = '8px JetBrains Mono';
            ctx.fillText(`Bar ${i}`, x + 2, h - 4);
        }
    }

    // 3. Draw Piano Roll Notes
    const minP = 32;
    const maxP = 84;
    const pRange = maxP - minP;

    notes.forEach(note => {
        const bar = note.bar || 1;
        const beat = note.beat || 0;
        const pitch = Math.min(maxP, Math.max(minP, note.pitch || 60));
        const vel = note.vel || 90;
        const dur = note.dur || 0.25;

        const noteX = (bar - 1) * barWidth + (beat / 4.0) * barWidth;
        const noteW = Math.max(3, (dur / 4.0) * barWidth);
        
        const relP = (pitch - minP) / pRange;
        const noteY = h - (relP * (h - 24)) - 16;
        const noteH = 5;

        const alpha = Math.min(1.0, Math.max(0.4, vel / 127.0));
        ctx.fillStyle = mainColor;
        ctx.globalAlpha = alpha;

        ctx.fillRect(noteX, noteY, noteW, noteH);
        ctx.globalAlpha = 1.0;
    });
}

function redrawAllCanvases() {
    if (!currentJobData) return;
    const blueprintSections = currentJobData.blueprint ? currentJobData.blueprint.sections : [];
    
    if (currentJobData.midi1) {
        renderPianoRollCanvas('midi1Canvas', currentJobData.midi1.bars, blueprintSections, '#00f0ff');
    }
    if (currentJobData.midi2) {
        renderPianoRollCanvas('midi2Canvas', currentJobData.midi2.bars, blueprintSections, '#7000ff');
    }
    if (currentStemsData) {
        const genNotes = currentStemsData.stems_data.drums.length > 0 ? currentStemsData.stems_data.drums : 
                        (currentStemsData.stems_data.piano.length > 0 ? currentStemsData.stems_data.piano : currentStemsData.stems_data.guitar);
        renderPianoRollCanvas('genCanvas', genNotes, blueprintSections, '#10b981');
    }
}

window.addEventListener('resize', () => {
    redrawAllCanvases();
});

// UI Event Handlers
document.addEventListener('DOMContentLoaded', () => {
    const file1Input = document.getElementById('midi1File');
    const file2Input = document.getElementById('midi2File');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const generateBtn = document.getElementById('generateBtn');
    const rerunFeedbackBtn = document.getElementById('rerunFeedbackBtn');

    setupDropZone('zone1', 'midi1File', 'file1Name');
    setupDropZone('zone2', 'midi2File', 'file2Name');

    analyzeBtn.addEventListener('click', async () => {
        if (!file1Input.files[0] || !file2Input.files[0]) {
            alert('Please select both MIDI 1 and MIDI 2 files.');
            return;
        }

        const formData = new FormData();
        formData.append('midi1', file1Input.files[0]);
        formData.append('midi2', file2Input.files[0]);

        setLoading(analyzeBtn, true, 'Analyzing MIDIs...');

        try {
            const res = await fetch('/api/analyze', { method: 'POST', body: formData });
            const data = await res.json();

            if (!res.ok) throw new Error(data.error || 'Failed to analyze MIDI files.');

            currentJobData = data;
            displayAnalysisResults(data);
            generateBtn.disabled = false;
        } catch (err) {
            alert(err.message);
        } finally {
            setLoading(analyzeBtn, false, '🔍 Cross-Analyze MIDIs');
        }
    });

    generateBtn.addEventListener('click', () => runPatternGenerator());
    rerunFeedbackBtn.addEventListener('click', () => runPatternGenerator(document.getElementById('userFeedbackText').value));


    // Audio Sanitizer Setup
    const audioInput = document.getElementById('audioFilesInput');
    const audioLabel = document.getElementById('audioFilesLabel');
    const startSanitizerBtn = document.getElementById('startSanitizerBtn');

    setupDropZone('zoneAudio', 'audioFilesInput', 'audioFilesLabel');

    audioInput.addEventListener('change', () => {
        if (audioInput.files.length > 0) {
            audioLabel.innerText = `${audioInput.files.length} audio file(s) selected`;
        }
    });

    // Wire up effect toggle checkboxes to enable/disable their control panels
    const effectToggles = [
        { chk: 'chkPitchShift', ctrl: 'ctrlPitchShift' },
        { chk: 'chkWow', ctrl: 'ctrlWow' },
        { chk: 'chkSpatial', ctrl: 'ctrlSpatial' },
        { chk: 'chkBinaryCleanup', ctrl: 'ctrlBinaryCleanup' },
        { chk: 'chkNoiseGate', ctrl: 'ctrlNoiseGate' },
    ];

    effectToggles.forEach(({ chk, ctrl }) => {
        const checkbox = document.getElementById(chk);
        const controls = document.getElementById(ctrl);
        if (checkbox && controls) {
            checkbox.addEventListener('change', () => {
                if (checkbox.checked) {
                    controls.classList.remove('effect-controls-disabled');
                } else {
                    controls.classList.add('effect-controls-disabled');
                }
            });
        }
    });

    // Wire up slider <-> number input sync pairs
    const sliderPairs = [
        { slider: 'sliderPitchShift', input: 'pitchShiftInput', scale: 1 },
        { slider: 'sliderWow', input: 'wowDriftInput', scale: 0.0001 },
        { slider: 'sliderSpatialWidth', input: 'spatialWidthInput', scale: 0.1 },
        { slider: 'sliderSpatialDelay', input: 'spatialDelayInput', scale: 1 },
        { slider: 'sliderNoiseGate', input: 'noiseGateInput', scale: 1 },
    ];

    sliderPairs.forEach(({ slider, input, scale }) => {
        const sl = document.getElementById(slider);
        const inp = document.getElementById(input);
        if (sl && inp) {
            sl.addEventListener('input', () => {
                inp.value = (parseFloat(sl.value) * scale).toFixed(scale < 1 ? 4 : 0);
            });
            inp.addEventListener('change', () => {
                sl.value = Math.round(parseFloat(inp.value) / scale);
            });
        }
    });

    // Sanitizer Submit Button
    startSanitizerBtn.addEventListener('click', async () => {
        if (!audioInput.files || audioInput.files.length === 0) {
            alert('Please select audio file(s) to sanitize.');
            return;
        }

        const formData = new FormData();
        for (let i = 0; i < audioInput.files.length; i++) {
            formData.append('files', audioInput.files[i]);
        }

        // Append effect enabled flags and parameter values
        formData.append('pitch_shift_enabled', document.getElementById('chkPitchShift').checked);
        formData.append('pitch_shift_cents', document.getElementById('pitchShiftInput').value);
        formData.append('wow_enabled', document.getElementById('chkWow').checked);
        formData.append('wow_drift', document.getElementById('wowDriftInput').value);
        formData.append('spatial_enabled', document.getElementById('chkSpatial').checked);
        formData.append('spatial_width', document.getElementById('spatialWidthInput').value);
        formData.append('spatial_delay_ms', document.getElementById('spatialDelayInput').value);
        formData.append('binary_cleanup_enabled', document.getElementById('chkBinaryCleanup').checked);
        formData.append('noise_gate_enabled', document.getElementById('chkNoiseGate').checked);
        formData.append('noise_gate_db', document.getElementById('noiseGateInput').value);

        setLoading(startSanitizerBtn, true, 'Submitting Audio Job...');

        try {
            const res = await fetch('/api/sanitize_upload', { method: 'POST', body: formData });
            const data = await res.json();

            if (!res.ok) throw new Error(data.error || 'Failed to submit audio job.');

            startSanitizationPolling(data.job_id);
        } catch (err) {
            alert(err.message);
            setLoading(startSanitizerBtn, false, '✨ Start Media Sanitization');
        }
    });
});

async function runPatternGenerator(userFeedback = null) {
    if (!currentJobData) return;

    const generateBtn = document.getElementById('generateBtn');
    const rerunBtn = document.getElementById('rerunFeedbackBtn');
    const instType = document.getElementById('instrumentTypeSelect').value;

    const targetBtn = userFeedback ? rerunBtn : generateBtn;
    setLoading(targetBtn, true, userFeedback ? 'Rerunning with Feedback...' : 'Running Pattern Recognition (approx 15s)...');

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: currentJobData.job_id,
                blueprint: currentJobData.blueprint,
                instrument_type: instType,
                user_feedback: userFeedback
            })
        });
        const data = await res.json();

        if (!res.ok) throw new Error(data.error || 'Failed to generate stems.');

        currentStemsData = data;
        displayGeneratedStems(data);
    } catch (err) {
        alert(err.message);
    } finally {
        setLoading(generateBtn, false, '⚡ Run LLM Pattern Recognition & Reconstruct MIDI');
        setLoading(rerunBtn, false, '🔄 Rerun AI Generator with Feedback');
    }
}

function setupDropZone(zoneId, inputId, labelId) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);
    const label = document.getElementById(labelId);

    if (!zone || !input || !label) return;

    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
        if (input.files[0] && input.files.length === 1) {
            label.innerText = input.files[0].name;
        }
    });

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            input.files = e.dataTransfer.files;
            if (input.files.length === 1) {
                label.innerText = input.files[0].name;
            } else {
                label.innerText = `${input.files.length} file(s) selected`;
            }
        }
    });
}

function setLoading(btn, isLoading, text) {
    if (isLoading) {
        btn.disabled = true;
        btn.innerHTML = `<div class="spinner"></div> ${text}`;
    } else {
        btn.disabled = false;
        btn.innerHTML = text;
    }
}

function displayAnalysisResults(data) {
    const analysisSec = document.getElementById('analysisSection');
    analysisSec.classList.remove('hidden');

    const blueprint = data.blueprint;
    const badgeContainer = document.getElementById('blueprintBadges');
    badgeContainer.innerHTML = '';

    blueprint.sections.forEach(sec => {
        const b = document.createElement('div');
        let cls = 'badge-constant';
        if (sec.type === 'BUILD_UP') cls = 'badge-buildup';
        if (sec.type === 'BREAK_DROP') cls = 'badge-drop';
        if (sec.type === 'SLOW') cls = 'badge-slow';
        b.className = `badge ${cls}`;
        b.innerText = `Bars ${sec.start_bar}-${sec.end_bar}: ${sec.type}`;
        badgeContainer.appendChild(b);
    });

    // Render Timeline 1 and Timeline 2 immediately after analysis
    setTimeout(() => {
        renderPianoRollCanvas('midi1Canvas', data.midi1.bars, blueprint.sections, '#00f0ff');
        renderPianoRollCanvas('midi2Canvas', data.midi2.bars, blueprint.sections, '#7000ff');
        renderPianoRollCanvas('genCanvas', [], blueprint.sections, '#10b981');
    }, 50);
}

function displayGeneratedStems(data) {
    const outputSec = document.getElementById('outputSection');
    outputSec.classList.remove('hidden');
    
    const downloads = data.downloads;
    
    const masterBtn = document.getElementById('downloadMasterBtn');
    masterBtn.href = downloads['reconstructed_master.mid'];

    const zipBtn = document.getElementById('downloadZipBtn');
    zipBtn.href = downloads.zip;

    const dlNotice = document.getElementById('downloadsPathNotice');
    if (data.downloads_path) {
        dlNotice.innerText = `Auto-Exported to: ${data.downloads_path}`;
    }

    document.getElementById('dlKick').href = downloads['kick.mid'];
    document.getElementById('dlSnare').href = downloads['snare.mid'];
    document.getElementById('dlHiHat').href = downloads['hihat.mid'];
    document.getElementById('dlCymbals').href = downloads['cymbals.mid'];
    document.getElementById('dlPiano').href = downloads['piano.mid'];
    document.getElementById('dlGuitar').href = downloads['guitar.mid'];

    // Render Timeline 3 (Generated Reconstructed AI MIDI)
    const blueprintSections = currentJobData ? currentJobData.blueprint.sections : [];
    
    setTimeout(() => {
        renderPianoRollCanvas('midi1Canvas', data.midi1_data.bars, blueprintSections, '#00f0ff');
        renderPianoRollCanvas('midi2Canvas', data.midi2_data.bars, blueprintSections, '#7000ff');

        const genNotes = data.stems_data.drums.length > 0 ? data.stems_data.drums : 
                        (data.stems_data.piano.length > 0 ? data.stems_data.piano : data.stems_data.guitar);
        renderPianoRollCanvas('genCanvas', genNotes, blueprintSections, '#10b981');
    }, 50);

    const stems = data.stems_data;
    document.getElementById('playKick').onclick = () => playStemSequence(stems.drums, 'kick');
    document.getElementById('playSnare').onclick = () => playStemSequence(stems.drums, 'snare');
    document.getElementById('playHiHat').onclick = () => playStemSequence(stems.drums, 'hihat');
    document.getElementById('playCymbals').onclick = () => playStemSequence(stems.drums, 'cymbals');
    document.getElementById('playPiano').onclick = () => playStemSequence(stems.piano, 'piano');
    document.getElementById('playGuitar').onclick = () => playStemSequence(stems.guitar, 'guitar');
}

function playStemSequence(notes, type) {
    if (!notes || notes.length === 0) return;
    initAudio();
    
    const bpm = currentJobData ? currentJobData.blueprint.bpm : 120;
    const secPerBeat = 60.0 / bpm;

    notes.slice(0, 64).forEach(n => {
        const delay = ((n.bar - 1) * 4 + n.beat) * secPerBeat;
        setTimeout(() => {
            playSynthSound(n.pitch, type);
        }, delay * 1000);
    });
}

function startSanitizationPolling(jobId) {
    const card = document.getElementById('sanitizerResultsCard');
    const bar = document.getElementById('sanitizerProgressBar');
    const text = document.getElementById('sanitizerProgressText');
    const grid = document.getElementById('sanitizerOutputGrid');
    const startBtn = document.getElementById('startSanitizerBtn');

    card.classList.remove('hidden');
    grid.innerHTML = '';

    if (sanitizerPollInterval) clearInterval(sanitizerPollInterval);

    sanitizerPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/job_status/${jobId}`);
            const data = await res.json();

            if (!res.ok) throw new Error(data.error || 'Job failed');

            bar.style.width = `${data.progress_pct}%`;
            text.innerText = data.progress;

            if (data.status === 'completed') {
                clearInterval(sanitizerPollInterval);
                setLoading(startBtn, false, '✨ Start Media Sanitization');
                document.getElementById('sanitizerStatusBadge').innerText = 'Completed';
                document.getElementById('sanitizerStatusBadge').className = 'badge badge-constant';

                grid.innerHTML = '';
                data.files.forEach(f => {
                    const card = document.createElement('div');
                    card.className = 'stem-card';
                    card.innerHTML = `
                        <div class="stem-card-header">
                            <div class="stem-title">🔊 ${f.name}</div>
                            <span class="badge badge-constant">Sanitized WAV</span>
                        </div>
                        <div class="stem-actions">
                            <a class="btn" href="${f.url}" download="${f.name}">Download Audio</a>
                        </div>
                    `;
                    grid.appendChild(card);
                });
            } else if (data.status === 'failed') {
                clearInterval(sanitizerPollInterval);
                setLoading(startBtn, false, '✨ Start Media Sanitization');
                text.innerText = `Error: ${data.error}`;
                document.getElementById('sanitizerStatusBadge').innerText = 'Failed';
                document.getElementById('sanitizerStatusBadge').className = 'badge badge-drop';
            }
        } catch (err) {
            clearInterval(sanitizerPollInterval);
            setLoading(startBtn, false, '✨ Start Media Sanitization');
            text.innerText = `Error: ${err.message}`;
        }
    }, 1000);
}
