// AI MIDI Visualizer & Tone Web Audio Synth Engine

let currentJobData = null;
let currentStemsData = null;
let audioCtx = null;
let isPlaying = false;
let playInterval = null;

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
        // Noise burst + triangle tone
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
        // High frequency click
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
        // Piano / Guitar melodic note
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

    // 1. Draw Section Background Highlights
    blueprintSections.forEach(sec => {
        const startX = (sec.start_bar - 1) * barWidth;
        const secW = (sec.end_bar - sec.start_bar + 1) * barWidth;

        let bg = 'rgba(16, 185, 129, 0.1)';
        if (sec.type === 'BUILD_UP') bg = 'rgba(245, 158, 11, 0.15)';
        if (sec.type === 'BREAK_DROP') bg = 'rgba(239, 68, 68, 0.2)';
        if (sec.type === 'SLOW') bg = 'rgba(139, 92, 246, 0.15)';

        ctx.fillStyle = bg;
        ctx.fillRect(startX, 0, secW, h);

        // Draw Section Label Text
        ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
        ctx.font = '10px JetBrains Mono';
        ctx.fillText(sec.type, startX + 6, 14);
    });

    // 2. Draw Note Density Bars & Bar Dividers
    barData.forEach((bar, idx) => {
        const x = idx * barWidth;

        // Bar Line
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();

        // Density Bar
        const maxDensityHeight = h - 30;
        const densityH = bar.rhythmic_density * maxDensityHeight;
        const y = h - densityH - 5;

        // Gradient based on velocity
        const grad = ctx.createLinearGradient(0, y, 0, h);
        grad.addColorStop(0, '#00f0ff');
        grad.addColorStop(1, '#7000ff');

        ctx.fillStyle = grad;
        ctx.fillRect(x + 2, y, Math.max(2, barWidth - 4), densityH);

        // Note dots
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
    const file1Input = document.getElementById('midi1File');
    const file2Input = document.getElementById('midi2File');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const generateBtn = document.getElementById('generateBtn');

    // Drag and drop setup
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
});

function setupDropZone(zoneId, inputId, labelId) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);
    const label = document.getElementById(labelId);

    zone.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
        if (input.files[0]) label.innerText = input.files[0].name;
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
            label.innerText = input.files[0].name;
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

    // Set individual stem download links
    document.getElementById('dlKick').href = downloads['kick.mid'];
    document.getElementById('dlSnare').href = downloads['snare.mid'];
    document.getElementById('dlHiHat').href = downloads['hihat.mid'];
    document.getElementById('dlCymbals').href = downloads['cymbals.mid'];
    document.getElementById('dlPiano').href = downloads['piano.mid'];
    document.getElementById('dlGuitar').href = downloads['guitar.mid'];

    // Play preview buttons
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
    
    // Sort notes and schedule synth audio playback
    const bpm = currentJobData ? currentJobData.blueprint.bpm : 120;
    const secPerBeat = 60.0 / bpm;

    notes.slice(0, 64).forEach(n => {
        const delay = ((n.bar - 1) * 4 + n.beat) * secPerBeat;
        setTimeout(() => {
            playSynthSound(n.pitch, type);
        }, delay * 1000);
    });
}
