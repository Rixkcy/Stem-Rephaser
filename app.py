import os
import uuid
import json
from flask import Flask, render_template, request, jsonify, send_from_directory
import midi_parser
import agent_engine
import midi_builder

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(__file__), 'output')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    if 'midi1' not in request.files or 'midi2' not in request.files:
        return jsonify({'error': 'Please upload both MIDI 1 and MIDI 2 files.'}), 400
        
    file1 = request.files['midi1']
    file2 = request.files['midi2']
    
    if file1.filename == '' or file2.filename == '':
        return jsonify({'error': 'No selected files.'}), 400
        
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    path1 = os.path.join(job_dir, 'input_stem1.mid')
    path2 = os.path.join(job_dir, 'input_stem2.mid')
    
    file1.save(path1)
    file2.save(path2)
    
    try:
        data1 = midi_parser.parse_midi_file(path1)
        data2 = midi_parser.parse_midi_file(path2)
        
        blueprint = agent_engine.analyze_master_blueprint(data1, data2)
        
        return jsonify({
            'job_id': job_id,
            'midi1': data1,
            'midi2': data2,
            'blueprint': blueprint
        })
    except Exception as e:
        return jsonify({'error': f"Error analyzing MIDI files: {str(e)}"}), 500

@app.route('/api/generate', methods=['POST'])
def generate():
    req = request.get_json()
    if not req or 'job_id' not in req or 'blueprint' not in req:
        return jsonify({'error': 'Invalid generation request parameters.'}), 400
        
    job_id = req['job_id']
    blueprint = req['blueprint']
    
    job_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], job_id)
    path1 = os.path.join(job_upload_dir, 'input_stem1.mid')
    path2 = os.path.join(job_upload_dir, 'input_stem2.mid')
    
    if not os.path.exists(path1) or not os.path.exists(path2):
        return jsonify({'error': 'Job files not found.'}), 404
        
    try:
        data1 = midi_parser.parse_midi_file(path1)
        data2 = midi_parser.parse_midi_file(path2)
        
        # Run agentic generation & critic loop
        stems_data = agent_engine.generate_authentic_stems(blueprint, data1, data2)
        
        # Build split MIDI files
        job_output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
        bpm = blueprint.get('bpm', 120)
        files = midi_builder.build_split_midi_files(stems_data, job_output_dir, bpm=bpm)
        
        download_urls = {
            k: f"/api/download/{job_id}/{os.path.basename(v)}"
            for k, v in files.items()
        }
        
        return jsonify({
            'job_id': job_id,
            'downloads': download_urls,
            'stems_data': stems_data
        })
    except Exception as e:
        return jsonify({'error': f"Error generating replacement MIDI stems: {str(e)}"}), 500

@app.route('/api/download/<job_id>/<filename>')
def download_file(job_id, filename):
    job_output_dir = os.path.join(app.config['OUTPUT_FOLDER'], job_id)
    return send_from_directory(job_output_dir, filename, as_attachment=True)

if __name__ == '__main__':
    print("Starting AI MIDI Visualizer & Authentic Stem Generator server on http://127.0.0.1:5000 ...")
    app.run(host='0.0.0.0', port=5000, debug=True)
