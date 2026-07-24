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
    Calls Gemini API with API key failover, retries, and rate limit backoff.
    """
    last_error = None

    for key_idx, key in enumerate(API_KEYS):
        client = genai.Client(api_key=key)
        for model_name in SUPPORTED_MODELS:
            for attempt in range(3): # 3 retries per model
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
                    err_str = str(e)
                    if '429' in err_str or 'RESOURCE_EXHAUSTED' in err_str:
                        sleep_time = 4.0 + attempt * 2.0  # Exponential backoff for rate limits
                        time.sleep(sleep_time)
                    else:
                        time.sleep(1.5)
                    continue
                    
    raise RuntimeError(f"Gemini API failover exhausted. Last error: {last_error}")

def extract_json_block(text):
    text = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        json_str = match.group(1)
    else:
        json_str = text
        
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    
    try:
        res = json.loads(json_str)
        if isinstance(res, list):
            return {"notes": res}
        return res
    except json.JSONDecodeError:
        match_raw = re.search(r'\{[\s\S]*\}', json_str)
        if match_raw:
            cleaned = re.sub(r',\s*([\]}])', r'\1', match_raw.group(0))
            try:
                res = json.loads(cleaned)
                if isinstance(res, list):
                    return {"notes": res}
                return res
            except Exception:
                pass
                
        match_list = re.search(r'\[\s*\{[\s\S]*\}\s*\]', json_str)
        if match_list:
            cleaned_list = re.sub(r',\s*([\]}])', r'\1', match_list.group(0))
            try:
                return {"notes": json.loads(cleaned_list)}
            except Exception:
                pass

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
            return {"notes": notes}
            
        raise ValueError("Could not parse JSON note structure from response")

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
You are an expert music analyst. Cross-reference these 2 MIDI files transcribed from Suno AI stems for the exact same song/stem.

Song Info:
- Total Bars: {total_bars}
- BPM: {bpm}

MIDI 1 Summary:
{json.dumps(summary1[:64])}

MIDI 2 Summary:
{json.dumps(summary2[:64])}

Label each section with one of: "CONSTANT_BEAT", "BUILD_UP", "BREAK_DROP", "SLOW".
Return strictly JSON format:
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
        if 'sections' in blueprint:
            return blueprint
    except Exception as e:
        print(f"Blueprint analysis fallback: {e}")

    sections = []
    q = max(1, total_bars // 4)
    sections.append({"start_bar": 1, "end_bar": q, "type": "CONSTANT_BEAT", "description": "Intro Groove"})
    sections.append({"start_bar": q + 1, "end_bar": q * 2, "type": "BUILD_UP", "description": "Rhythm Build-up"})
    sections.append({"start_bar": q * 2 + 1, "end_bar": q * 3, "type": "BREAK_DROP", "description": "Main Drop"})
    sections.append({"start_bar": q * 3 + 1, "end_bar": total_bars, "type": "SLOW", "description": "Outro Breakdown"})
    return {"total_bars": total_bars, "bpm": bpm, "sections": sections}

def llm_pattern_reconstruction(midi1_data, midi2_data, instrument_type="Drums", user_feedback=None):
    """
    LLM Pattern Recognition & Reconstruction Engine:
    Processes the song in 16-bar chunks with rate-limit delays so all chunks succeed.
    """
    total_bars = max(midi1_data['total_bars'], midi2_data['total_bars'])
    bpm = midi1_data.get('bpm', 120)
    
    map1 = {}
    for b in midi1_data['bars']:
        map1[b['bar']] = b['notes']
        
    map2 = {}
    for b in midi2_data['bars']:
        map2[b['bar']] = b['notes']

    chunk_size = 16
    all_reconstructed_notes = []
    
    for chunk_start in range(1, total_bars + 1, chunk_size):
        chunk_end = min(total_bars, chunk_start + chunk_size - 1)
        
        # Pacing delay between chunk API calls to respect rate limits
        if chunk_start > 1:
            time.sleep(3.0)
            
        notes1_chunk = []
        for bar in range(chunk_start, chunk_end + 1):
            for n in map1.get(bar, []):
                notes1_chunk.append({'bar': bar, 'beat': n['beat'], 'pitch': n['pitch'], 'vel': n['vel'], 'dur': n['dur']})
                
        notes2_chunk = []
        for bar in range(chunk_start, chunk_end + 1):
            for n in map2.get(bar, []):
                notes2_chunk.append({'bar': bar, 'beat': n['beat'], 'pitch': n['pitch'], 'vel': n['vel'], 'dur': n['dur']})

        feedback_text = f"\nUser Feedback: {user_feedback}" if user_feedback else ""

        prompt = f"""
You are an expert AI MIDI producer and pattern recognition engine.
Reconstruct authentic '{instrument_type}' MIDI notes for Bars {chunk_start} to {chunk_end} (Total Bars in Song: {total_bars}, BPM: {bpm}).
{feedback_text}

MIDI 1 NOTES (Bars {chunk_start}-{chunk_end}):
{json.dumps(notes1_chunk)}

MIDI 2 NOTES (Bars {chunk_start}-{chunk_end}):
{json.dumps(notes2_chunk)}

INSTRUCTIONS FOR BARS {chunk_start} TO {chunk_end}:
1. PATTERN RECOGNITION: Recognize repeating groove/rhythmic patterns in these bars.
2. FILL MISSING HITS: Fill notes missing in one file but required by the repeating pattern.
3. REMOVE GHOST HITS: Remove spurious pitch 81 / low velocity < 25 artifacts.
4. MAPPING FOR DRUMS:
   - Kick: Pitch 36 (C3)
   - Snare: Pitch 38 (D3), Rim: Pitch 37
   - Closed Hat: Pitch 42 (F#3), Open Hat: Pitch 46 (A#3)
   - Crash: Pitch 49 (C#4), Ride: Pitch 51
   - Toms: Pitches 45, 47, 48, 50
5. QUANTIZE: Snap beats to exact 16th grid positions (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 3.75). Velocity range 75-120.

Return strictly a JSON array of note objects for Bars {chunk_start} to {chunk_end}:
[
  {{"bar": {chunk_start}, "beat": 0.0, "pitch": 36, "vel": 105, "dur": 0.25}},
  {{"bar": {chunk_start}, "beat": 0.0, "pitch": 49, "vel": 110, "dur": 0.5}},
  {{"bar": {chunk_start}, "beat": 1.0, "pitch": 38, "vel": 98, "dur": 0.25}},
  {{"bar": {chunk_start}, "beat": 2.0, "pitch": 36, "vel": 102, "dur": 0.25}},
  {{"bar": {chunk_start}, "beat": 3.0, "pitch": 38, "vel": 95, "dur": 0.25}}
]
"""
        try:
            response_text = call_gemini_with_failover(prompt)
            res = extract_json_block(response_text)
            chunk_notes = res.get('notes', res.get('drums', []))
            if not chunk_notes and isinstance(res, list):
                chunk_notes = res
                
            if not chunk_notes:
                raise ValueError(f"Empty chunk response for bars {chunk_start}-{chunk_end}")
            all_reconstructed_notes.extend(chunk_notes)
        except Exception as e:
            print(f"Chunk fallback for bars {chunk_start}-{chunk_end}: {e}")
            fallback_chunk = fallback_pattern_merge(notes1_chunk, notes2_chunk, chunk_start, chunk_end)
            all_reconstructed_notes.extend(fallback_chunk)

    if instrument_type.lower() == 'drums':
        stems_data = {'drums': all_reconstructed_notes, 'piano': [], 'guitar': []}
    elif 'piano' in instrument_type.lower() or 'keyboard' in instrument_type.lower():
        stems_data = {'drums': [], 'piano': all_reconstructed_notes, 'guitar': []}
    else:
        stems_data = {'drums': [], 'piano': [], 'guitar': all_reconstructed_notes}
        
    return stems_data

def fallback_pattern_merge(notes1, notes2, start_bar, end_bar):
    merged = []
    for n in notes1 + notes2:
        if not (start_bar <= n['bar'] <= end_bar):
            continue
        p = n['pitch']
        v = n['vel']
        if p == 81 and v < 30: continue
        if p == 81: p = 42
        if p == 37: p = 36
        
        q_beat = round(n['beat'] * 4) / 4.0
        
        merged.append({
            'bar': n['bar'],
            'beat': min(3.75, max(0.0, q_beat)),
            'pitch': p,
            'vel': max(70, min(120, v if v > 51 else random.randint(85, 112))),
            'dur': n['dur']
        })
        
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
