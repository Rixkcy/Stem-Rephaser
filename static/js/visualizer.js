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

// Web Audio Synthetic Sound Generators for authentic drum/stem preview
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

// Canvas Visualizer Renderer
function renderTimelineCanvas(canvasId, barData, blueprintSections = []) {
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

    const totalBars = barData.length;
    if (totalBars === 0) return;

    const barWidth = w / totalBars;

    blueprintSections.forEach(sec => {
        const startX = (sec.start_bar - 1) * barWidth;
        const secW = (sec.end_bar - sec.start_bar + 1) * barWidth;

        let bg = 'rgba(16, 185, 129, 0.1)';
        if (sec.type === 'BUILD_UP') bg = 'rgba(245, 158, 11, 0.15)';
        if (sec.type === 'BREAK_DROP') bg = 'rgba(239, 68, 68, 0.2)';
        if (sec.type === 'SLOW') bg = 'rgba(139, 92, 246, 0.15)';

        ctx.fillStyle = bg;
        ctx.fillRect(startX, 0, secW, h);

        ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
        ctx.font = '10px JetBrains Mono';
        ctx.fillText(sec.type, startX + 6, 14);
    });

    barData.forEach((bar, idx) => {
        const x = idx * barWidth;

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();

        const maxDensityHeight = h - 30;
        const densityH = bar.rhythmic_density * maxDensityHeight;
        const y = h - densityH - 5;

        const grad = ctx.createLinearGradient(0, y, 0, h);
        grad.addColorStop(0, '#00f0ff');
        grad.addColorStop(1, '#7000ff');

        ctx.fillStyle = grad;
        ctx.fillRect(x + 2, y, Math.max(2, barWidth - 4), densityH);

        if (bar.notes) {
            bar.notes.forEach(note => {
                const noteX = x + (note.beat / 4.0) * barWidth;
                const noteY = h - (note.pitch / 128.0) * (h - 20);
                ctx.fillStyle = '#ff007a';
                ctx.beginPath();
                ctx.arc(noteX, noteY, 2, 0, Math.PI * 2);
                ctx.fill();
            });
        }
    });
}

// UI Event Handlers
document.addEventListener('DOMContentLoaded', () => {
    // --- TAB 1: MIDI STREAMS SETUP ---
    const file1Input = document.getElementById('midi1File');
    const file2Input = document.getElementById('midi2File');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const generateBtn = document.getElementById('generateBtn');

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

    generateBtn.addEventListener('click', async () => {
        if (!currentJobData) return;

        setLoading(generateBtn, true, 'Generating Fresh Stems...');

        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: currentJobData.job_id,
                    blueprint: currentJobData.blueprint
                })
            });
            const data = await res.json();

            if (!res.ok) throw new Error(data.error || 'Failed to generate stems.');

            currentStemsData = data;
            displayGeneratedStems(data);
        } catch (err) {
            alert(err.message);
        } finally {
            setLoading(generateBtn, false, '⚡ Generate Authentic Replacement MIDIs');
        }
    });

    // --- TAB 2: AUDIO SANITIZER SETUP ---
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

    renderTimelineCanvas('midi1Canvas', data.midi1.bars, blueprint.sections);
    renderTimelineCanvas('midi2Canvas', data.midi2.bars, blueprint.sections);
}

function displayGeneratedStems(data) {
    document.getElementById('outputSection').classList.remove('hidden');
    const downloads = data.downloads;
    const zipBtn = document.getElementById('downloadZipBtn');
    zipBtn.href = downloads.zip;

    document.getElementById('dlKick').href = downloads['kick.mid'];
    document.getElementById('dlSnare').href = downloads['snare.mid'];
    document.getElementById('dlHiHat').href = downloads['hihat.mid'];
    document.getElementById('dlCymbals').href = downloads['cymbals.mid'];
    document.getElementById('dlPiano').href = downloads['piano.mid'];
    document.getElementById('dlGuitar').href = downloads['guitar.mid'];

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

// Media Sanitizer Job Polling
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
