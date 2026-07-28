import os
import uuid
import time
import threading
import numpy as np
import scipy.signal as signal
import soundfile as sf
from pydub import AudioSegment
from flask import Flask, render_template, request, jsonify, send_from_directory
from pedalboard import Pedalboard, Reverb, Limiter

import midi_parser
import agent_engine
import midi_builder

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(__file__), 'output')
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024 * 1024  # 128MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

sanitizer_jobs = {}

# ==========================================
# AUDIO SANITIZER DSP ENGINE
# ==========================================

def load_audio_safe(path):
    """Load any audio file (mp3/wav/flac/m4a) into numpy stereo array + sample rate."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.mp3', '.m4a', '.ogg'):
        seg = AudioSegment.from_file(path)
        temp_wav = path + '_temp.wav'
        seg.export(temp_wav, format='wav')
        data, samplerate = sf.read(temp_wav)
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
        return data, samplerate
    else:
        return sf.read(path)

def ensure_stereo(audio):
    """Ensure audio is stereo (N, 2) shape."""
    if audio.ndim == 1:
        return np.column_stack([audio, audio])
    if audio.shape[1] == 1:
        return np.column_stack([audio[:, 0], audio[:, 0]])
    return audio

# --- Effect 1: Pitch Shift (Resampling) ---
def apply_pitch_shift(audio, sr, cents):
    """Shift pitch by resampling. cents > 0 = pitch up, cents < 0 = pitch down."""
    if cents == 0:
        return audio
    
    import librosa
    factor = 2.0 ** (cents / 1200.0)
    target_sr = int(round(sr / factor))
    
    channels = []
    for ch in range(audio.shape[1]):
        resampled = librosa.resample(audio[:, ch], orig_sr=sr, target_sr=target_sr)
        channels.append(resampled)
    
    min_len = min(len(c) for c in channels)
    return np.column_stack([c[:min_len] for c in channels])

# --- Effect 2: Micro Wow & Flutter Drift ---
def apply_micro_wow(audio, sr, drift):
    """Apply sinusoidal wow drift to break fixed-rate neural codec framing."""
    if drift == 0.0:
        return audio
    
    n_samples = audio.shape[0]
    t = np.arange(n_samples) / sr
    mod_freq = 0.35
    
    speed_curve = 1.0 + drift * np.sin(2 * np.pi * mod_freq * t)
    cumulative_phase = np.cumsum(speed_curve)
    cumulative_phase = cumulative_phase / cumulative_phase[-1] * (n_samples - 1)
    
    result = []
    for ch in range(audio.shape[1]):
        warped = np.interp(cumulative_phase, np.arange(n_samples), audio[:, ch])
        result.append(warped)
    
    return np.column_stack(result)

# --- Effect 3: 3D Spatial Vector Widening ---
def apply_3d_spatial(audio, sr, width, delay_ms):
    """
    Mid/Side stereo widening + Haas delay + light reverb diffusion.
    Splits audio into 3D vector space to break mono-correlated watermark carriers.
    """
    left = audio[:, 0]
    right = audio[:, 1]
    
    # Mid/Side decomposition
    mid = (left + right) / 2.0
    side = (left - right) / 2.0
    
    # Apply width scaling to the side channel only (not mid)
    # Cap effective width to prevent extreme imbalance
    effective_width = min(width, 2.5)
    side_widened = side * effective_width
    
    left_wide = mid + side_widened
    right_wide = mid - side_widened
    
    # Symmetric Haas delay: split delay between BOTH channels
    # Left gets half-delay forward, Right gets half-delay forward
    # This preserves perceived center while adding spatial depth
    half_delay = int(sr * (delay_ms / 2.0) / 1000.0)
    if half_delay > 0:
        left_wide = np.pad(left_wide, (half_delay, 0))[:len(left_wide)]
        right_wide = np.pad(right_wide, (0, half_delay))[:len(right_wide)]
    
    # Normalize L/R RMS levels to preserve stereo balance
    rms_l = np.sqrt(np.mean(left_wide**2)) + 1e-12
    rms_r = np.sqrt(np.mean(right_wide**2)) + 1e-12
    rms_avg = (rms_l + rms_r) / 2.0
    left_wide = left_wide * (rms_avg / rms_l)
    right_wide = right_wide * (rms_avg / rms_r)
    
    # Light reverb diffusion + limiter
    board = Pedalboard([
        Reverb(room_size=0.15, wet_level=0.1, dry_level=0.9),
        Limiter(threshold_db=-0.5)
    ])
    
    processed_l = board(left_wide, sample_rate=sr)
    processed_r = board(right_wide, sample_rate=sr)
    
    min_len = min(len(processed_l), len(processed_r))
    return np.column_stack([processed_l[:min_len], processed_r[:min_len]])

# --- Effect 4: Inaudible Binary / Sub-threshold Noise Cleanup ---
def apply_binary_cleanup(audio, sr):
    """
    Scrub inaudible binary data & watermark carriers:
    1. Notch filter at 8kHz (common Suno watermark carrier)
    2. Flatten LSB noise floor (dither with clean TPDF noise)
    3. Strip ultrasonic content above 20kHz
    """
    result = audio.copy()
    
    # Notch out 8kHz watermark carrier tone
    for freq in [8000, 8016]:
        if freq < sr / 2:
            b_notch, a_notch = signal.iirnotch(freq / (sr / 2), Q=30)
            for ch in range(result.shape[1]):
                result[:, ch] = signal.filtfilt(b_notch, a_notch, result[:, ch])
    
    # Low-pass at 20kHz (remove ultrasonic data above human hearing)
    if sr > 40000:
        nyq = sr / 2
        cutoff = min(20000, nyq - 100)
        b_lp, a_lp = signal.butter(6, cutoff / nyq, btype='low')
        for ch in range(result.shape[1]):
            result[:, ch] = signal.filtfilt(b_lp, a_lp, result[:, ch])
    
    # Redither LSBs with clean TPDF noise (strips any steganographic data in LSBs)
    bit_depth = 16
    lsb_level = 1.0 / (2 ** (bit_depth - 1))
    tpdf_noise = (np.random.triangular(-1, 0, 1, size=result.shape) * lsb_level)
    
    # Quantize to 16-bit grid then add fresh TPDF dither
    quantized = np.round(result * (2 ** (bit_depth - 1))) / (2 ** (bit_depth - 1))
    result = quantized + tpdf_noise * 0.5
    result = np.clip(result, -1.0, 1.0)
    
    return result

# --- Effect 5: Intelligent Adaptive Noise Gate ---
def apply_noise_gate(audio, sr, threshold_db):
    """
    Smart noise gate with hold time + smooth release (cool-off zone).
    Silences audio below threshold_db while preserving natural decay tails.
    """
    threshold_linear = 10.0 ** (threshold_db / 20.0)
    
    mono_abs = np.max(np.abs(audio), axis=1)
    num_samples = len(mono_abs)
    
    hold_samples = int(sr * 0.050)      # 50ms hold
    release_samples = int(sr * 0.100)   # 100ms smooth release
    attack_samples = int(sr * 0.002)    # 2ms attack
    
    gain = np.zeros(num_samples, dtype=np.float64)
    hold_ctr = 0
    current_gain = 0.0
    
    for i in range(num_samples):
        level = mono_abs[i]
        
        if level >= threshold_linear:
            target = 1.0
            hold_ctr = hold_samples
        elif hold_ctr > 0:
            target = 1.0
            hold_ctr -= 1
        else:
            target = 0.0
        
        if target > current_gain:
            current_gain = min(1.0, current_gain + (1.0 / max(1, attack_samples)))
        elif target < current_gain:
            current_gain = max(0.0, current_gain - (1.0 / max(1, release_samples)))
        
        gain[i] = current_gain
    
    return audio * gain[:, np.newaxis]

# --- Main Async Processing Pipeline ---
def process_sanitizer_job(job_id, input_files, params):
    """
    Run the full sanitizer pipeline on all input files with user-selected effects.
    params dict keys:
      - pitch_shift_enabled (bool), pitch_shift_cents (int)
      - wow_enabled (bool), wow_drift (float)
      - spatial_enabled (bool), spatial_width (float), spatial_delay_ms (float)
      - binary_cleanup_enabled (bool)
      - noise_gate_enabled (bool), noise_gate_db (float)
    """
    sanitizer_jobs[job_id] = {
        'status': 'running',
        'progress': 'Initializing Media Sanitizer...',
        'progress_pct': 0,
        'files': [],
        'error': None
    }
    
    try:
        job_out_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
        os.makedirs(job_out_dir, exist_ok=True)
        
        sanitized_files = []
        total = len(input_files)
        
        for idx, fpath in enumerate(input_files):
            fname = os.path.basename(fpath)
            sanitizer_jobs[job_id]['progress'] = f"Processing ({idx+1}/{total}): {fname}..."
            sanitizer_jobs[job_id]['progress_pct'] = int((idx / total) * 100)
            
            audio, sr = load_audio_safe(fpath)
            audio = ensure_stereo(audio)
            
            # Apply enabled effects in order
            if params.get('pitch_shift_enabled'):
                cents = params.get('pitch_shift_cents', 24)
                sanitizer_jobs[job_id]['progress'] = f"({idx+1}/{total}) {fname}: Pitch Shift {cents} cents..."
                audio = apply_pitch_shift(audio, sr, cents)
            
            if params.get('wow_enabled'):
                drift = params.get('wow_drift', 0.0015)
                sanitizer_jobs[job_id]['progress'] = f"({idx+1}/{total}) {fname}: Micro Wow & Flutter..."
                audio = apply_micro_wow(audio, sr, drift)
            
            if params.get('spatial_enabled'):
                width = params.get('spatial_width', 1.5)
                delay_ms = params.get('spatial_delay_ms', 24)
                sanitizer_jobs[job_id]['progress'] = f"({idx+1}/{total}) {fname}: 3D Spatial Widening..."
                audio = apply_3d_spatial(audio, sr, width, delay_ms)
            
            if params.get('binary_cleanup_enabled'):
                sanitizer_jobs[job_id]['progress'] = f"({idx+1}/{total}) {fname}: Binary/Watermark Cleanup..."
                audio = apply_binary_cleanup(audio, sr)
            
            if params.get('noise_gate_enabled'):
                gate_db = params.get('noise_gate_db', -30)
                sanitizer_jobs[job_id]['progress'] = f"({idx+1}/{total}) {fname}: Noise Gate @ {gate_db} dBFS..."
                audio = apply_noise_gate(audio, sr, gate_db)
            
            # Export
            out_filename = os.path.splitext(fname)[0] + ' [Sanitized].wav'
            out_filepath = os.path.join(job_out_dir, out_filename)
            sf.write(out_filepath, audio, sr)
            
            sanitized_files.append({
                'name': out_filename,
                'url': f"/api/download/{job_id}/{out_filename}"
            })
        
        sanitizer_jobs[job_id]['status'] = 'completed'
        sanitizer_jobs[job_id]['progress'] = 'Sanitization Completed Successfully!'
        sanitizer_jobs[job_id]['progress_pct'] = 100
        sanitizer_jobs[job_id]['files'] = sanitized_files
    except Exception as e:
        sanitizer_jobs[job_id]['status'] = 'failed'
        sanitizer_jobs[job_id]['error'] = str(e)
        sanitizer_jobs[job_id]['progress'] = f"Error: {str(e)}"


# ==========================================
# FLASK ROUTE CONTROLLERS
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

# --- TAB 1: AI MIDI STEM ENGINE ENDPOINTS ---

@app.route('/api/analyze', methods=['POST'])
def analyze_midi():
    if 'midi1' not in request.files or 'midi2' not in request.files:
        return jsonify({'error': 'Please upload both MIDI 1 and MIDI 2 files.'}), 400
    
    file1 = request.files['midi1']
    file2 = request.files['midi2']
    
    if file1.filename == '' or file2.filename == '':
        return jsonify({'error': 'No selected files.'}), 400
    
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    path1 = os.path.join(job_dir, file1.filename.replace(' ', '_'))
    path2 = os.path.join(job_dir, file2.filename.replace(' ', '_'))
    
    file1.save(path1)
    file2.save(path2)
    
    try:
        data1 = midi_parser.parse_midi_file(path1)
        data2 = midi_parser.parse_midi_file(path2)
        
        blueprint = agent_engine.analyze_master_blueprint(data1, data2)
        
        return jsonify({
            'job_id': job_id,
            'file1_path': path1,
            'file2_path': path2,
            'filename1': file1.filename,
            'filename2': file2.filename,
            'midi1': data1,
            'midi2': data2,
            'blueprint': blueprint
        })
    except Exception as e:
        return jsonify({'error': f"Error analyzing MIDI files: {str(e)}"}), 500

@app.route('/api/generate', methods=['POST'])
def generate_midi():
    req = request.get_json()
    if not req or 'job_id' not in req or 'blueprint' not in req:
        return jsonify({'error': 'Invalid generation parameters.'}), 400
    
    job_id = req['job_id']
    blueprint = req['blueprint']
    instrument_type = req.get('instrument_type', 'Drums')
    user_feedback = req.get('user_feedback', None)
    
    job_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    upload_files = os.listdir(job_upload_dir)
    if len(upload_files) < 2:
        return jsonify({'error': 'Job upload files missing.'}), 404
    
    path1 = os.path.join(job_upload_dir, upload_files[0])
    path2 = os.path.join(job_upload_dir, upload_files[1])
    
    try:
        data1 = midi_parser.parse_midi_file(path1)
        data2 = midi_parser.parse_midi_file(path2)
        
        stems_data = agent_engine.generate_authentic_stems(
            blueprint, data1, data2,
            instrument_type=instrument_type,
            user_feedback=user_feedback
        )
        
        job_output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
        bpm = blueprint.get('bpm', 120)
        base_name = os.path.splitext(upload_files[0])[0]
        
        files = midi_builder.build_split_midi_files(
            stems_data, job_output_dir, bpm=bpm,
            target_downloads_dir=r"C:\Users\ricky\Downloads",
            original_filename_base=base_name
        )
        
        download_urls = {
            k: f"/api/download/{job_id}/{os.path.basename(v)}"
            for k, v in files.items() if k != 'downloads_path'
        }
        
        return jsonify({
            'job_id': job_id,
            'downloads': download_urls,
            'downloads_path': files.get('downloads_path', ''),
            'stems_data': stems_data,
            'midi1_data': data1,
            'midi2_data': data2
        })
    except Exception as e:
        return jsonify({'error': f"Error generating replacement MIDIs: {str(e)}"}), 500

@app.route('/api/rerun_feedback', methods=['POST'])
def rerun_feedback():
    return generate_midi()

# --- TAB 2: MEDIA SANITIZER ENDPOINTS ---

@app.route('/api/sanitize_upload', methods=['POST'])
def sanitize_upload():
    if 'files' not in request.files:
        return jsonify({'error': 'No audio files uploaded.'}), 400
    
    uploaded_files = request.files.getlist('files')
    if not uploaded_files or uploaded_files[0].filename == '':
        return jsonify({'error': 'No selected audio files.'}), 400
    
    job_id = str(uuid.uuid4())[:8]
    job_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    os.makedirs(job_upload_dir, exist_ok=True)
    
    saved_paths = []
    for f in uploaded_files:
        path = os.path.join(job_upload_dir, f.filename.replace(' ', '_'))
        f.save(path)
        saved_paths.append(path)
    
    # Parse effect parameters from form data
    params = {
        'pitch_shift_enabled': request.form.get('pitch_shift_enabled') == 'true',
        'pitch_shift_cents': int(request.form.get('pitch_shift_cents', 24)),
        'wow_enabled': request.form.get('wow_enabled') == 'true',
        'wow_drift': float(request.form.get('wow_drift', 0.0015)),
        'spatial_enabled': request.form.get('spatial_enabled') == 'true',
        'spatial_width': float(request.form.get('spatial_width', 1.5)),
        'spatial_delay_ms': float(request.form.get('spatial_delay_ms', 24)),
        'binary_cleanup_enabled': request.form.get('binary_cleanup_enabled') == 'true',
        'noise_gate_enabled': request.form.get('noise_gate_enabled') == 'true',
        'noise_gate_db': float(request.form.get('noise_gate_db', -30)),
    }
    
    threading.Thread(
        target=process_sanitizer_job,
        args=(job_id, saved_paths, params)
    ).start()
    
    return jsonify({'success': True, 'job_id': job_id})

@app.route('/api/job_status/<job_id>')
def job_status(job_id):
    if job_id not in sanitizer_jobs:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(sanitizer_jobs[job_id])

@app.route('/api/download/<job_id>/<filename>')
def download_file(job_id, filename):
    job_output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
    return send_from_directory(job_output_dir, filename, as_attachment=True)

if __name__ == '__main__':
    print("Starting Unified AI MIDI Stem Engine & Media Sanitizer Suite on http://127.0.0.1:5000 ...")
    app.run(host='0.0.0.0', port=5000, debug=True)
