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
                        temperature=0.2,
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
        
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        match_raw = re.search(r'\{[\s\S]*\}', json_str)
        if match_raw:
            cleaned = re.sub(r',\s*([\]}])', r'\1', match_raw.group(0))
            try:
                return json.loads(cleaned)
            except Exception:
                pass
                
        # Regex note extractor fallback
        notes = []
        for m in re.finditer(r'\{\s*"bar"\s*:\s*(\d+)[\s\S]*?"beat"\s*:\s*([\d\.]+)[\s\S]*?"pitch"\s*:\s*(\d+)[\s\S]*?"vel"\s*:\s*(\d+)[\s\S]*?"dur"\s*:\s*([\d\.]+)\s*\}', text):
            notes.append({
                "bar": int(m.group(1)),
                "beat": float(m.group(2)),
                "pitch": int(m.group(3)),
                "vel": int(m.group(4)),
                "dur": float(m.group(5))
            })
            
        if notes:
            return {"notes": notes, "drums": notes}
            
        raise ValueError("Could not parse JSON note structure from response")

def analyze_master_blueprint(midi1_data, midi2_data):
    """Stage 1: Analyzes overall structure and section markers."""
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
You are an expert music analyst. Cross-reference these 2 MIDI files transcribed from Suno AI stems for the exact same song/stem.

Song Info:
- Total Bars: {total_bars}
- BPM: {bpm}

MIDI 1 Summary:
{json.dumps(summary1[:64])}

MIDI 2 Summary:
{json.dumps(summary2[:64])}

Label each section with one of: "CONSTANT_BEAT", "BUILD_UP", "BREAK_DROP", "SLOW".
Return JSON:
{{
  "total_bars": {total_bars},
  "bpm": {bpm},
  "sections": [
    {{"start_bar": 1, "end_bar": 8, "type": "CONSTANT_BEAT", "description": "Intro groove"}}
  ]
}}
"""
    try:
        response_text = call_gemini_with_failover(prompt)
        blueprint = extract_json_block(response_text)
        return blueprint
    except Exception as e:
        print(f"Blueprint analysis fallback: {e}")
        sections = []
        q = max(1, total_bars // 4)
        sections.append({"start_bar": 1, "end_bar": q, "type": "CONSTANT_BEAT", "description": "Intro"})
        sections.append({"start_bar": q + 1, "end_bar": q * 2, "type": "BUILD_UP", "description": "Build-up"})
        sections.append({"start_bar": q * 2 + 1, "end_bar": q * 3, "type": "BREAK_DROP", "description": "Drop"})
        sections.append({"start_bar": q * 3 + 1, "end_bar": total_bars, "type": "SLOW", "description": "Outro"})
        return {"total_bars": total_bars, "bpm": bpm, "sections": sections}

def llm_pattern_reconstruction(midi1_data, midi2_data, instrument_type="Drums", user_feedback=None):
    """
    LLM Pattern Recognition & Reconstruction Engine:
    Receives full note event listings of MIDI 1 and MIDI 2, performs pattern recognition,
    fills missing hits, purges spurious ghost hits, normalizes pitches, quantizes timing,
    and incorporates user feedback if provided.
    """
    total_bars = max(midi1_data['total_bars'], midi2_data['total_bars'])
    bpm = midi1_data.get('bpm', 120)
    
    # Prepare full bar-by-bar note streams
    notes1 = []
    for b in midi1_data['bars']:
        for n in b['notes']:
            notes1.append({'bar': b['bar'], 'beat': n['beat'], 'pitch': n['pitch'], 'vel': n['vel'], 'dur': n['dur']})
            
    notes2 = []
    for b in midi2_data['bars']:
        for n in b['notes']:
            notes2.append({'bar': b['bar'], 'beat': n['beat'], 'pitch': n['pitch'], 'vel': n['vel'], 'dur': n['dur']})

    feedback_instruction = ""
    if user_feedback:
        feedback_instruction = f"""
IMPORTANT USER FEEDBACK FOR THIS REVISION:
"{user_feedback}"
Apply these exact modifications to the pattern generation!
"""

    prompt = f"""
You are an elite AI MIDI producer and pattern recognition engine.
We are reconstructing an authentic '{instrument_type}' stem from 2 raw AI-transcribed MIDI files.

Song Parameters:
- Total Bars: {total_bars}
- BPM: {bpm}
- Instrument Type: {instrument_type}

{feedback_instruction}

MIDI FILE 1 NOTE STREAM (Total {len(notes1)} notes):
{json.dumps(notes1[:250])}

MIDI FILE 2 NOTE STREAM (Total {len(notes2)} notes):
{json.dumps(notes2[:250])}

YOUR PATTERN RECONSTRUCTION TASK:
1. PATTERN RECOGNITION: Analyze repeating 2-bar, 4-bar, and 8-bar rhythmic/harmonic patterns across all {total_bars} bars.
2. FILL MISSING HITS: If a hit is missing in one file but present in the other (or required by the repeating pattern), ADD IT.
3. REMOVE EXCESSIVE / GHOST HITS: Filter out spurious ghost artifacts (such as pitch 81 velocity < 25 artifacts or erratic random hits).
4. STANDARD INSTRUMENT MAPPING:
   For Drums (General MIDI / FPC layout):
   - Kick: Pitch 36 (C3)
   - Snare: Pitch 38 (D3), Rimshot: Pitch 37
   - Closed Hi-Hat: Pitch 42 (F#3), Open Hi-Hat: Pitch 46 (A#3)
   - Crash Cymbal: Pitch 49 (C#4), Ride: Pitch 51
   - Toms: Pitches 45, 47, 48, 50
   For Piano/Keyboard or Guitar: Map clean chord/melody pitches (48-84) with proper duration holds.
5. QUANTIZE & HUMANIZE: Align beats to exact 16th-note positions (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75) while preserving humanized velocity dynamics (75-120).

Return strictly JSON with this key structure:
{{
  "notes": [
    {{"bar": 1, "beat": 0.0, "pitch": 36, "vel": 105, "dur": 0.25}},
    {{"bar": 1, "beat": 0.0, "pitch": 49, "vel": 110, "dur": 0.5}},
    {{"bar": 1, "beat": 1.0, "pitch": 38, "vel": 98, "dur": 0.25}},
    {{"bar": 1, "beat": 2.0, "pitch": 36, "vel": 102, "dur": 0.25}},
    {{"bar": 1, "beat": 3.0, "pitch": 38, "vel": 95, "dur": 0.25}}
  ]
}}
"""
    try:
        response_text = call_gemini_with_failover(prompt)
        res = extract_json_block(response_text)
        reconstructed_notes = res.get('notes', res.get('drums', []))
        if not reconstructed_notes:
            raise ValueError("No notes array returned from LLM")
    except Exception as e:
        print(f"Gemini LLM pattern reconstruction fallback: {e}")
        reconstructed_notes = fallback_pattern_merge(notes1, notes2, total_bars)

    # Format into instrument stems object
    if instrument_type.lower() == 'drums':
        stems_data = {'drums': reconstructed_notes, 'piano': [], 'guitar': []}
    elif 'piano' in instrument_type.lower() or 'keyboard' in instrument_type.lower():
        stems_data = {'drums': [], 'piano': reconstructed_notes, 'guitar': []}
    else:
        stems_data = {'drums': [], 'piano': [], 'guitar': reconstructed_notes}
        
    return stems_data

def fallback_pattern_merge(notes1, notes2, total_bars):
    """Algorithmic backup if Gemini API fails or times out."""
    merged = []
    # Combine notes, map pitch 81 -> 42 (Hi-Hat), filter low velocity ghost notes
    for n in notes1 + notes2:
        p = n['pitch']
        v = n['vel']
        if p == 81 and v < 30: continue # Purge ghost note
        if p == 81: p = 42
        if p == 37: p = 36 # Rim count-in -> Kick
        
        # Quantize beat to nearest 16th note (0.25 step)
        q_beat = round(n['beat'] * 4) / 4.0
        
        merged.append({
            'bar': n['bar'],
            'beat': min(3.75, max(0.0, q_beat)),
            'pitch': p,
            'vel': max(70, min(120, v if v > 51 else random.randint(85, 112))),
            'dur': n['dur']
        })
        
    # Deduplicate notes at same bar, beat, pitch
    seen = set()
    deduped = []
    for n in merged:
        key = (n['bar'], n['beat'], n['pitch'])
        if key not in seen:
            seen.add(key)
            deduped.append(n)
            
    deduped.sort(key=lambda x: (x['bar'], x['beat'], x['pitch']))
    return deduped

def generate_authentic_stems(blueprint, midi1_data, midi2_data, instrument_type="Drums", user_feedback=None):
    return llm_pattern_reconstruction(midi1_data, midi2_data, instrument_type=instrument_type, user_feedback=user_feedback)
