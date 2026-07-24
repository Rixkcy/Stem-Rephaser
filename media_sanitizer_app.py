import os
import sys
import uuid
import time
import threading
import numpy as np
import scipy.signal as signal
import librosa
import soundfile as sf
from pydub import AudioSegment
from flask import Flask, render_template, request, jsonify, send_from_directory
from scipy.interpolate import interp1d
from pedalboard import Pedalboard, Reverb, Limiter

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(__file__), 'output')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# In-memory job status tracking
jobs_status = {}

def load_vbr_mp3_safe(path, sr=44100):
    """Safely converts VBR MP3/Audio to temporary WAV and loads using soundfile/librosa."""
    if path.lower().endswith('.mp3'):
        seg = AudioSegment.from_file(path)
        temp_wav = path + '_temp.wav'
        seg.export(temp_wav, format='wav')
        data, samplerate = sf.read(temp_wav)
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
        return data, samplerate
    else:
        return sf.read(path)

def spatialise_3d(audio, sr=44100, width=1.5, delay_ms=24):
    """Applies 3D stereo widening, micro-delay Haas effect, and pedalboard reverb/limiter."""
    if len(audio.shape) == 1:
        audio = np.column_stack([audio, audio])
        
    left = audio[:, 0]
    right = audio[:, 1]
    
    mid = (left + right) / 2.0
    side = (left - right) / 2.0 * width
    
    left_wide = mid + side
    right_wide = mid - side
    
    # Haas delay
    delay_samples = int(sr * delay_ms / 1000.0)
    if delay_samples > 0:
        right_delayed = np.pad(right_wide, (delay_samples, 0))[:len(right_wide)]
    else:
        right_delayed = right_wide
        
    board = Pedalboard([
        Reverb(room_size=0.15, wet_level=0.1, dry_level=0.9),
        Limiter(threshold_db=-0.5)
    ])
    
    processed_l = board(left_wide, sample_rate=sr)
    processed_r = board(right_delayed, sample_rate=sr)
    
    min_len = min(len(processed_l), len(processed_r))
    return np.column_stack([processed_l[:min_len], processed_r[:min_len]])

def apply_pitch_shift(audio, sr=44100, cents=0):
    """Applies resampled pitch shift (cents)."""
    if cents == 0:
        return audio
        
    factor = 2.0 ** (cents / 1200.0)
    target_sr = int(round(sr / factor))
    
    L = librosa.resample(audio[:, 0], orig_sr=sr, target_sr=target_sr)
    R = librosa.resample(audio[:, 1], orig_sr=sr, target_sr=target_sr)
    
    min_len = min(len(L), len(R))
    return np.column_stack([L[:min_len], R[:min_len]])

def apply_micro_wow(audio, drift=0.0015, sr=44100):
    """Applies low-frequency wow & flutter pitch/time drift."""
    if drift == 0.0:
        return audio
        
    n_samples = audio.shape[0]
    t = np.arange(n_samples) / sr
    mod_freq = 0.35  # 0.35 Hz sinusoidal drift
    
    speed_curve = 1.0 + drift * np.sin(2 * np.pi * mod_freq * t)
    cumulative_phase = np.cumsum(speed_curve)
    cumulative_phase = cumulative_phase / cumulative_phase[-1] * (n_samples - 1)
    
    result = []
    for ch in range(audio.shape[1]):
        warped = np.interp(cumulative_phase, np.arange(n_samples), audio[:, ch])
        result.append(warped)
        
    return np.column_stack(result)

def process_audio_files_async(job_id, input_files, model_type='44khz', n_quantizers=9, pitch_shift_cents=24, wow_drift=0.0015, output_stems=False):
    jobs_status[job_id] = {
        'status': 'running',
        'progress': 'Initializing Media Sanitization...',
        'result': None,
        'error': None
    }
    
    try:
        job_out_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
        os.makedirs(job_out_dir, exist_ok=True)
        
        sanitized_files = []
        for idx, fpath in enumerate(input_files):
            fname = os.path.basename(fpath)
            jobs_status[job_id]['progress'] = f"Processing file {idx+1}/{len(input_files)}: {fname}..."
            
            audio, sr = load_vbr_mp3_safe(fpath)
            if len(audio.shape) == 1:
                audio = np.column_stack([audio, audio])
                
            # 1. Spatial 3D Widening & Haas
            audio_3d = spatialise_3d(audio, sr=sr, width=1.5, delay_ms=24)
            
            # 2. Resampled Pitch Shift
            if pitch_shift_cents != 0:
                audio_pitched = apply_pitch_shift(audio_3d, sr=sr, cents=pitch_shift_cents)
            else:
                audio_pitched = audio_3d
                
            # 3. Micro Wow & Flutter
            if wow_drift > 0:
                audio_final = apply_micro_wow(audio_pitched, drift=wow_drift, sr=sr)
            else:
                audio_final = audio_pitched
                
            # Save sanitized WAV
            out_filename = os.path.splitext(fname)[0] + ' [Sanitized].wav'
            out_filepath = os.path.join(job_out_dir, out_filename)
            sf.write(out_filepath, audio_final, sr)
            sanitized_files.append(out_filepath)
            
        jobs_status[job_id]['status'] = 'completed'
        jobs_status[job_id]['progress'] = 'Sanitization complete!'
        jobs_status[job_id]['result'] = {
            'success': True,
            'files': [os.path.basename(f) for f in sanitized_files]
        }
    except Exception as e:
        jobs_status[job_id]['status'] = 'failed'
        jobs_status[job_id]['error'] = str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_upload', methods=['POST'])
def process_upload():
    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded.'}), 400
        
    uploaded_files = request.files.getlist('files')
    if not uploaded_files or uploaded_files[0].filename == '':
        return jsonify({'error': 'No selected files.'}), 400
        
    job_id = str(uuid.uuid4())[:8]
    job_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    os.makedirs(job_upload_dir, exist_ok=True)
    
    saved_paths = []
    for f in uploaded_files:
        path = os.path.join(job_upload_dir, f.filename.replace(' ', '_'))
        f.save(path)
        saved_paths.append(path)
        
    pitch_shift = int(request.form.get('pitch_shift_cents', 24))
    wow_drift = float(request.form.get('wow_drift', 0.0015))
    
    threading.Thread(
        target=process_audio_files_async,
        args=(job_id, saved_paths, '44khz', 9, pitch_shift, wow_drift, False)
    ).start()
    
    return jsonify({'success': True, 'job_id': job_id})

@app.route('/job_status/<job_id>')
def job_status(job_id):
    if job_id not in jobs_status:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(jobs_status[job_id])

@app.route('/download/<job_id>/<filename>')
def download(job_id, filename):
    job_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
    return send_from_directory(job_dir, filename, as_attachment=True)

if __name__ == '__main__':
    print("Starting Media Sanitizer Web App on http://127.0.0.1:5001 ...")
    app.run(host='0.0.0.0', port=5001, debug=True)
