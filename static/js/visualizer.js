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

// 3-Way Piano-Roll Canvas Renderer
function renderPianoRollCanvas(canvasId, barDataOrNotes, blueprintSections = [], mainColor = '#00f0ff') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    ctx.clearRect(0, 0, w, h);

    // Extract flat note list
    let notes = [];
    let totalBars = 32;

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

    if (totalBars === 0) totalBars = 32;
    const barWidth = w / totalBars;

    // 1. Draw Section Background Badges
    blueprintSections.forEach(sec => {
        const startX = (sec.start_bar - 1) * barWidth;
        const secW = (sec.end_bar - sec.start_bar + 1) * barWidth;

        let bg = 'rgba(16, 185, 129, 0.08)';
        if (sec.type === 'BUILD_UP') bg = 'rgba(245, 158, 11, 0.12)';
        if (sec.type === 'BREAK_DROP') bg = 'rgba(239, 68, 68, 0.15)';
        if (sec.type === 'SLOW') bg = 'rgba(139, 92, 246, 0.12)';

        ctx.fillStyle = bg;
        ctx.fillRect(startX, 0, secW, h);

        ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.font = '9px JetBrains Mono';
        ctx.fillText(sec.type, startX + 4, 12);
    });

    // 2. Draw Bar Dividers
    for (let i = 0; i <= totalBars; i++) {
        const x = i * barWidth;
        ctx.strokeStyle = i % 4 === 0 ? 'rgba(255, 255, 255, 0.15)' : 'rgba(255, 255, 255, 0.05)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
    }

    // 3. Draw Piano Roll Notes
    // Pitch range 32 to 84 (52 semitones)
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
        
        // Inverted Y (higher pitch = higher Y)
        const relP = (pitch - minP) / pRange;
        const noteY = h - (relP * (h - 24)) - 16;
        const noteH = 6;

        // Alpha based on velocity
        const alpha = Math.min(1.0, Math.max(0.4, vel / 127.0));
        ctx.fillStyle = mainColor;
        ctx.globalAlpha = alpha;

        // Draw note block
        ctx.beginPath();
        ctx.roundRect(noteX, noteY, noteW, noteH, 2);
        ctx.fill();
        ctx.globalAlpha = 1.0;
    });
}

// UI Event Controllers
document.addEventListener('DOMContentLoaded', () => {
    const file1Input = document.getElementById('midi1File');
    const file2Input = document.getElementById('midi2File');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const generateBtn = document.getElementById('generateBtn');
    const rerunFeedbackBtn = document.getElementById('rerunFeedbackBtn');
    const instrumentSelect = document.getElementById('instrumentTypeSelect');

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

    // Audio Sanitizer
    const audioInput = document.getElementById('audioFilesInput');
    const audioLabel = document.getElementById('audioFilesLabel');
    const startSanitizerBtn = document.getElementById('startSanitizerBtn');

    setupDropZone('zoneAudio', 'audioFilesInput', 'audioFilesLabel');

    audioInput.addEventListener('change', () => {
        if (audioInput.files.length > 0) {
            audioLabel.innerText = `${audioInput.files.length} audio file(s) selected`;
        }
    });

    startSanitizerBtn.addEventListener('click', async () => {
        if (!audioInput.files || audioInput.files.length === 0) {
            alert('Please select audio file(s) to sanitize.');
            return;
        }

        const formData = new FormData();
        for (let i = 0; i < audioInput.files.length; i++) {
            formData.append('files', audioInput.files[i]);
        }
        formData.append('pitch_shift_cents', document.getElementById('pitchShiftInput').value);
        formData.append('wow_drift', document.getElementById('wowDriftInput').value);

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
    setLoading(targetBtn, true, userFeedback ? 'Rerunning with Feedback...' : 'Running Pattern Recognition...');

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
    document.getElementById('analysisSection').classList.remove('hidden');

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
}

function displayGeneratedStems(data) {
    document.getElementById('outputSection').classList.remove('hidden');
    const downloads = data.downloads;
    
    // Set master download and ZIP links
    const masterBtn = document.getElementById('downloadMasterBtn');
    masterBtn.href = downloads['reconstructed_master.mid'];

    const zipBtn = document.getElementById('downloadZipBtn');
    zipBtn.href = downloads.zip;

    const dlNotice = document.getElementById('downloadsPathNotice');
    if (data.downloads_path) {
        dlNotice.innerText = `Auto-Exported to: ${data.downloads_path}`;
    }

    // Set individual stem download links
    document.getElementById('dlKick').href = downloads['kick.mid'];
    document.getElementById('dlSnare').href = downloads['snare.mid'];
    document.getElementById('dlHiHat').href = downloads['hihat.mid'];
    document.getElementById('dlCymbals').href = downloads['cymbals.mid'];
    document.getElementById('dlPiano').href = downloads['piano.mid'];
    document.getElementById('dlGuitar').href = downloads['guitar.mid'];

    // Render 3-Way Piano Roll Canvases
    const blueprintSections = currentJobData ? currentJobData.blueprint.sections : [];
    renderPianoRollCanvas('midi1Canvas', data.midi1_data.bars, blueprintSections, '#00f0ff');
    renderPianoRollCanvas('midi2Canvas', data.midi2_data.bars, blueprintSections, '#7000ff');

    const genNotes = data.stems_data.drums.length > 0 ? data.stems_data.drums : 
                    (data.stems_data.piano.length > 0 ? data.stems_data.piano : data.stems_data.guitar);
    renderPianoRollCanvas('genCanvas', genNotes, blueprintSections, '#10b981');

    // Audio Previews
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
