import os
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

import midi_parser
import agent_engine
import midi_builder

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(__file__), 'output')
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

sanitizer_jobs = {}

# ==========================================
# AUDIO SANITIZER DSP ENGINE
# ==========================================

def load_vbr_mp3_safe(path, sr=44100):
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
    if len(audio.shape) == 1:
        audio = np.column_stack([audio, audio])
        
    left = audio[:, 0]
    right = audio[:, 1]
    
    mid = (left + right) / 2.0
    side = (left - right) / 2.0 * width
    
    left_wide = mid + side
    right_wide = mid - side
    
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
    if cents == 0:
        return audio
        
    factor = 2.0 ** (cents / 1200.0)
    target_sr = int(round(sr / factor))
    
    L = librosa.resample(audio[:, 0], orig_sr=sr, target_sr=target_sr)
    R = librosa.resample(audio[:, 1], orig_sr=sr, target_sr=target_sr)
    
    min_len = min(len(L), len(R))
    return np.column_stack([L[:min_len], R[:min_len]])

def apply_micro_wow(audio, drift=0.0015, sr=44100):
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

def process_audio_files_async(job_id, input_files, pitch_shift_cents=24, wow_drift=0.0015):
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
        total_files = len(input_files)
        
        for idx, fpath in enumerate(input_files):
            fname = os.path.basename(fpath)
            sanitizer_jobs[job_id]['progress'] = f"Processing ({idx+1}/{total_files}): {fname}..."
            sanitizer_jobs[job_id]['progress_pct'] = int(((idx) / total_files) * 100)
            
            audio, sr = load_vbr_mp3_safe(fpath)
            if len(audio.shape) == 1:
                audio = np.column_stack([audio, audio])
                
            audio_3d = spatialise_3d(audio, sr=sr, width=1.5, delay_ms=24)
            audio_pitched = apply_pitch_shift(audio_3d, sr=sr, cents=pitch_shift_cents) if pitch_shift_cents != 0 else audio_3d
            audio_final = apply_micro_wow(audio_pitched, drift=wow_drift, sr=sr) if wow_drift > 0 else audio_pitched
                
            out_filename = os.path.splitext(fname)[0] + ' [Sanitized].wav'
            out_filepath = os.path.join(job_out_dir, out_filename)
            sf.write(out_filepath, audio_final, sr)
            
            download_url = f"/api/download/{job_id}/{out_filename}"
            sanitized_files.append({
                'name': out_filename,
                'url': download_url
            })
            
        sanitizer_jobs[job_id]['status'] = 'completed'
        sanitizer_jobs[job_id]['progress'] = 'Sanitization Completed Successfully!'
        sanitizer_jobs[job_id]['progress_pct'] = 100
        sanitizer_jobs[job_id]['files'] = sanitized_files
    except Exception as e:
        sanitizer_jobs[job_id]['status'] = 'failed'
        sanitizer_jobs[job_id]['error'] = str(e)


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
        
        # LLM Pattern Recognition Engine & User Feedback
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
        
    pitch_shift = int(request.form.get('pitch_shift_cents', 24))
    wow_drift = float(request.form.get('wow_drift', 0.0015))
    
    threading.Thread(
        target=process_audio_files_async,
        args=(job_id, saved_paths, pitch_shift, wow_drift)
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
