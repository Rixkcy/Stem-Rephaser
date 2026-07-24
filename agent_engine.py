import os
import json
import re
import time
import random
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(r"D:\apps\columbina-bot\.env")

API_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_1")
]
API_KEYS = [k for k in API_KEYS if k]

SUPPORTED_MODELS = [
    'gemini-2.5-flash',
    'gemini-2.0-flash'
]

def call_gemini_with_failover(prompt, system_instruction="You are an expert AI music producer, MIDI analyzer, and agentic assistant."):
    """
    Calls Gemini API trying all available API keys and supported models with retries.
    """
    last_error = None

    for key in API_KEYS:
        client = genai.Client(api_key=key)
        for model_name in SUPPORTED_MODELS:
            for attempt in range(2):
                try:
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.3,
                        max_output_tokens=8192
                    )
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config
                    )
                    if response and response.text:
                        return response.text.strip()
                except Exception as e:
                    last_error = e
                    time.sleep(1)
                    continue
                    
    raise RuntimeError(f"Gemini API failover exhausted. Last error: {last_error}")

def extract_json_block(text):
    """Robust JSON extraction and repair for LLM responses."""
    text = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        json_str = match.group(1)
    else:
        json_str = text
        
    # Clean up common LLM JSON syntax errors (trailing commas, quotes)
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback 1: Extract main dict
        match_raw = re.search(r'\{[\s\S]*\}', json_str)
        if match_raw:
            cleaned = re.sub(r',\s*([\]}])', r'\1', match_raw.group(0))
            try:
                return json.loads(cleaned)
            except Exception:
                pass
                
        # Fallback 2: Robust regex object extraction for note lists
        drums_notes = []
        for m in re.finditer(r'\{\s*"bar"\s*:\s*(\d+)[\s\S]*?"beat"\s*:\s*([\d\.]+)[\s\S]*?"pitch"\s*:\s*(\d+)[\s\S]*?"vel"\s*:\s*(\d+)[\s\S]*?"dur"\s*:\s*([\d\.]+)\s*\}', text):
            drums_notes.append({
                "bar": int(m.group(1)),
                "beat": float(m.group(2)),
                "pitch": int(m.group(3)),
                "vel": int(m.group(4)),
                "dur": float(m.group(5))
            })
            
        if drums_notes:
            return {"drums": drums_notes, "piano": [], "guitar": []}
            
        raise ValueError("Could not parse JSON from response")

def analyze_master_blueprint(midi1_data, midi2_data):
    total_bars = max(midi1_data['total_bars'], midi2_data['total_bars'])
    bpm = midi1_data.get('bpm', 120)
    
    summary1 = [{
        'bar': b['bar'], 'notes': b['note_count'],
        'density': b['rhythmic_density'], 'avg_vel': b['avg_velocity']
    } for b in midi1_data['bars']]
    
    summary2 = [{
        'bar': b['bar'], 'notes': b['note_count'],
        'density': b['rhythmic_density'], 'avg_vel': b['avg_velocity']
    } for b in midi2_data['bars']]
    
    prompt = f"""
You are an expert music analyst. We have 2 MIDI files transcribed from Suno AI stems for the exact same song/stem.
Your job is to cross-reference both files to identify the song structure blueprint.

Song Info:
- Total Bars: {total_bars}
- BPM: {bpm}

MIDI 1 Summary (Bar by Bar):
{json.dumps(summary1[:64])}

MIDI 2 Summary (Bar by Bar):
{json.dumps(summary2[:64])}

Analyze note counts, density, and velocity curves to identify structural sections.
Label each section with one of these exact types:
- "CONSTANT_BEAT": Steady, recurring rhythmic foundation/groove.
- "BUILD_UP": Rising note density, increasing velocity/crescendo leading to a drop.
- "BREAK_DROP": Sudden drop, high energy punch, heavy beat or breakdown.
- "SLOW": Sparse notes, low density, slow/mellow feel.

Return strictly a JSON object with this exact key structure:
{{
  "total_bars": {total_bars},
  "bpm": {bpm},
  "sections": [
    {{
      "start_bar": 1,
      "end_bar": 8,
      "type": "CONSTANT_BEAT",
      "description": "Steady intro groove"
    }}
  ]
}}
"""
    try:
        response_text = call_gemini_with_failover(prompt)
        blueprint = extract_json_block(response_text)
        return blueprint
    except Exception as e:
        print(f"Gemini API Blueprint analysis fallback triggered: {e}")
        sections = []
        q = max(1, total_bars // 4)
        sections.append({"start_bar": 1, "end_bar": q, "type": "CONSTANT_BEAT", "description": "Intro Groove"})
        sections.append({"start_bar": q + 1, "end_bar": q * 2, "type": "BUILD_UP", "description": "Rhythm Build-Up"})
        sections.append({"start_bar": q * 2 + 1, "end_bar": q * 3, "type": "BREAK_DROP", "description": "Main Beat Drop"})
        sections.append({"start_bar": q * 3 + 1, "end_bar": total_bars, "type": "SLOW", "description": "Outro Breakdown"})
        return {"total_bars": total_bars, "bpm": bpm, "sections": sections}

def generate_authentic_stems(blueprint, midi1_data, midi2_data):
    total_bars = blueprint['total_bars']
    sections = blueprint['sections']
    
    prompt = f"""
You are an expert drum programmer and FL Studio producer.
Generate authentic, humanized replacement MIDI notes for:
1. Drums (FPC / General MIDI note layout):
   - Kick: Note 36 (C3)
   - Snare: Note 38 (D3), Rimshot: Note 37
   - Closed Hi-Hat: Note 42 (F#3), Open Hi-Hat: Note 46 (A#3)
   - Crash Cymbal: Note 49 (C#4), Ride: Note 51
2. Piano (Melodic/Harmonic chord notes, e.g. pitches 60-76)
3. Guitar (Rhythmic/Arpeggio notes, e.g. pitches 48-67)

Master Blueprint Sections:
{json.dumps(sections)}

Rules:
1. Generate notes from bar 1 to bar {total_bars}.
2. Ensure humanized velocity dynamics (range 75 to 118, never flat 100).
3. Respect section dynamics:
   - CONSTANT_BEAT: Kick on beat 0 and 2, Snare on beat 1 and 3, 8th note hi-hats.
   - BUILD_UP: 16th note snare rolls with rising velocities (60 -> 115) near the end.
   - BREAK_DROP: Heavy Kick + Crash on beat 0, syncopated snare & hats.
   - SLOW: Sparse kick on beat 0, subtle closed hats on beat 2.
4. Output beats in range 0.0 to 3.75 per bar (4 beats per bar).

Return strictly JSON format:
{{
  "drums": [
    {{"bar": 1, "beat": 0.0, "pitch": 36, "vel": 105, "dur": 0.25}},
    {{"bar": 1, "beat": 0.0, "pitch": 49, "vel": 110, "dur": 0.5}},
    {{"bar": 1, "beat": 1.0, "pitch": 38, "vel": 95, "dur": 0.25}}
  ],
  "piano": [
    {{"bar": 1, "beat": 0.0, "pitch": 60, "vel": 85, "dur": 1.0}}
  ],
  "guitar": [
    {{"bar": 1, "beat": 0.5, "pitch": 52, "vel": 78, "dur": 0.5}}
  ]
}}
"""
    try:
        response_text = call_gemini_with_failover(prompt)
        candidate = extract_json_block(response_text)
    except Exception as e:
        print(f"Gemini API stem generation fallback triggered: {e}")
        candidate = generate_algorithmic_stems(blueprint)
        
    critic_passed, refined_candidate = critic_loop_evaluation(candidate, blueprint)
    return refined_candidate

def critic_loop_evaluation(candidate, blueprint):
    total_bars = blueprint['total_bars']
    drums = candidate.get('drums', [])
    piano = candidate.get('piano', [])
    guitar = candidate.get('guitar', [])
    
    bars_with_drums = set(n.get('bar') for n in drums)
    if len(bars_with_drums) < total_bars:
        drums = fill_missing_drum_bars(drums, blueprint)
        
    if not piano:
        piano = generate_algorithmic_piano(blueprint)
        
    if not guitar:
        guitar = generate_algorithmic_guitar(blueprint)
        
    for n in drums:
        if n.get('vel', 90) == 100 or 'vel' not in n:
            n['vel'] = random.randint(82, 112)
            
    candidate['drums'] = drums
    candidate['piano'] = piano
    candidate['guitar'] = guitar
    
    return True, candidate

def generate_algorithmic_stems(blueprint):
    total_bars = blueprint['total_bars']
    sections = blueprint.get('sections', [])
    
    drums = []
    for bar in range(1, total_bars + 1):
        sec_type = "CONSTANT_BEAT"
        for s in sections:
            if s['start_bar'] <= bar <= s['end_bar']:
                sec_type = s['type']
                break
                
        if sec_type == "BUILD_UP":
            drums.append({'bar': bar, 'beat': 0.0, 'pitch': 36, 'vel': 100, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 0.0, 'pitch': 49, 'vel': 110, 'dur': 0.5})
            for b in [0.0, 0.5, 1.0, 1.5, 2.0, 2.25, 2.5, 2.75, 3.0, 3.125, 3.25, 3.375, 3.5, 3.625, 3.75]:
                vel = int(60 + (b / 4.0) * 55)
                drums.append({'bar': bar, 'beat': b, 'pitch': 38, 'vel': vel, 'dur': 0.125})
        elif sec_type == "BREAK_DROP":
            drums.append({'bar': bar, 'beat': 0.0, 'pitch': 36, 'vel': 118, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 0.0, 'pitch': 49, 'vel': 115, 'dur': 0.5})
            drums.append({'bar': bar, 'beat': 1.0, 'pitch': 38, 'vel': 110, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 1.5, 'pitch': 36, 'vel': 105, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 2.0, 'pitch': 36, 'vel': 112, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 3.0, 'pitch': 38, 'vel': 108, 'dur': 0.25})
            for b in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]:
                drums.append({'bar': bar, 'beat': b, 'pitch': 42, 'vel': 92, 'dur': 0.25})
        elif sec_type == "SLOW":
            drums.append({'bar': bar, 'beat': 0.0, 'pitch': 36, 'vel': 88, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 2.0, 'pitch': 37, 'vel': 80, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 1.0, 'pitch': 42, 'vel': 75, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 3.0, 'pitch': 42, 'vel': 75, 'dur': 0.25})
        else:
            drums.append({'bar': bar, 'beat': 0.0, 'pitch': 36, 'vel': 105, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 1.0, 'pitch': 38, 'vel': 98, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 2.0, 'pitch': 36, 'vel': 102, 'dur': 0.25})
            drums.append({'bar': bar, 'beat': 3.0, 'pitch': 38, 'vel': 100, 'dur': 0.25})
            for b in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]:
                drums.append({'bar': bar, 'beat': b, 'pitch': 42, 'vel': 85, 'dur': 0.25})

    return {
        'drums': drums,
        'piano': generate_algorithmic_piano(blueprint),
        'guitar': generate_algorithmic_guitar(blueprint)
    }

def fill_missing_drum_bars(existing_drums, blueprint):
    bars_present = set(n.get('bar') for n in existing_drums)
    algo_stems = generate_algorithmic_stems(blueprint)
    for n in algo_stems['drums']:
        if n.get('bar') not in bars_present:
            existing_drums.append(n)
    existing_drums.sort(key=lambda x: (x['bar'], x['beat']))
    return existing_drums

def generate_algorithmic_piano(blueprint):
    total_bars = blueprint['total_bars']
    piano = []
    chords = [[60, 64, 67], [59, 62, 67], [57, 60, 64], [53, 57, 60]]
    for bar in range(1, total_bars + 1):
        chord = chords[(bar - 1) % len(chords)]
        for p in chord:
            piano.append({'bar': bar, 'beat': 0.0, 'pitch': p, 'vel': 82, 'dur': 2.0})
            piano.append({'bar': bar, 'beat': 2.0, 'pitch': p, 'vel': 80, 'dur': 1.8})
    return piano

def generate_algorithmic_guitar(blueprint):
    total_bars = blueprint['total_bars']
    guitar = []
    notes = [48, 52, 55, 57, 60]
    for bar in range(1, total_bars + 1):
        for idx, beat in enumerate([0.5, 1.5, 2.5, 3.5]):
            p = notes[(bar + idx) % len(notes)]
            guitar.append({'bar': bar, 'beat': beat, 'pitch': p, 'vel': 76, 'dur': 0.4})
    return guitar
