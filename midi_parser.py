import mido
import mido.midifiles.meta as meta
import json
import math

# Monkey patch mido's KeySignature decoder to handle corrupt AI MIDI files (e.g. 12 sharps)
_orig_key_decode = meta.MetaSpec_key_signature.decode

def safe_decode_key_signature(self, msg, data):
    try:
        _orig_key_decode(self, msg, data)
    except Exception:
        msg.key = 'C'  # Default safe key if AI MIDI contains corrupt key meta bytes

meta.MetaSpec_key_signature.decode = safe_decode_key_signature

def parse_midi_file(file_path):
    """
    Parses a MIDI file using mido and converts its contents into a structured,
    bar-by-bar JSON timeline suitable for LLM analysis.
    Safely handles corrupt or non-standard meta messages from AI generators.
    """
    try:
        mid = mido.MidiFile(file_path, clip=True)
    except Exception as e:
        # Fallback with type_checks=False if file header has non-standard values
        mid = mido.MidiFile(file_path, clip=True, type_checks=False)

    ticks_per_beat = mid.ticks_per_beat if mid.ticks_per_beat else 480
    
    # 1. Determine tempo and BPM (default 120 BPM = 500,000 microseconds per beat)
    tempo = 500000
    for track in mid.tracks:
        try:
            for msg in track:
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                    break
        except Exception:
            continue
    bpm = round(mido.tempo2bpm(tempo), 2)
    
    # Time signature default 4/4
    time_num = 4
    time_den = 4
    for track in mid.tracks:
        try:
            for msg in track:
                if msg.type == 'time_signature':
                    time_num = msg.numerator
                    time_den = msg.denominator
                    break
        except Exception:
            continue
                
    ticks_per_bar = int(ticks_per_beat * time_num * (4 / max(1, time_den)))
    
    # 2. Extract note events across all tracks
    all_notes = []
    
    for track_idx, track in enumerate(mid.tracks):
        current_tick = 0
        active_notes = {}  # pitch -> (start_tick, velocity, channel)
        
        try:
            for msg in track:
                if hasattr(msg, 'time'):
                    current_tick += msg.time
                    
                if msg.type == 'note_on' and msg.velocity > 0:
                    active_notes[msg.note] = (current_tick, msg.velocity, getattr(msg, 'channel', 0))
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    if msg.note in active_notes:
                        start_tick, vel, chan = active_notes.pop(msg.note)
                        duration_ticks = current_tick - start_tick
                        all_notes.append({
                            'pitch': msg.note,
                            'velocity': vel,
                            'start_tick': start_tick,
                            'duration_ticks': max(1, duration_ticks),
                            'channel': chan,
                            'track': track_idx
                        })
        except Exception as err:
            print(f"Warning: Ignored corrupt track event in track {track_idx}: {err}")
            continue
                    
    # Sort notes by start tick
    all_notes.sort(key=lambda x: (x['start_tick'], x['pitch']))
    
    # Calculate total length in bars
    max_tick = max([n['start_tick'] + n['duration_ticks'] for n in all_notes]) if all_notes else ticks_per_bar
    total_bars = max(1, math.ceil(max_tick / ticks_per_bar))
    
    # 3. Group notes into bars & calculate bar metrics
    bar_data = []
    for bar_idx in range(total_bars):
        bar_start = bar_idx * ticks_per_bar
        bar_end = (bar_idx + 1) * ticks_per_bar
        
        notes_in_bar = [
            n for n in all_notes
            if bar_start <= n['start_tick'] < bar_end
        ]
        
        pitches = [n['pitch'] for n in notes_in_bar]
        velocities = [n['velocity'] for n in notes_in_bar]
        
        avg_vel = round(sum(velocities) / len(velocities), 1) if velocities else 0
        min_pitch = min(pitches) if pitches else None
        max_pitch = max(pitches) if pitches else None
        note_count = len(notes_in_bar)
        
        # Micro-rhythm density (16th note grid occupancy)
        ticks_per_16th = ticks_per_bar / 16
        occupied_16ths = set()
        for n in notes_in_bar:
            rel_tick = n['start_tick'] - bar_start
            grid_pos = int(rel_tick // ticks_per_16th)
            if 0 <= grid_pos < 16:
                occupied_16ths.add(grid_pos)
                
        rhythmic_density = len(occupied_16ths) / 16.0
        
        simplified_notes = []
        for n in notes_in_bar:
            rel_beat = round((n['start_tick'] - bar_start) / ticks_per_beat, 3)
            dur_beat = round(n['duration_ticks'] / ticks_per_beat, 3)
            simplified_notes.append({
                'beat': rel_beat,
                'pitch': n['pitch'],
                'vel': n['velocity'],
                'dur': dur_beat
            })
            
        bar_data.append({
            'bar': bar_idx + 1,
            'note_count': note_count,
            'avg_velocity': avg_vel,
            'rhythmic_density': round(rhythmic_density, 2),
            'min_pitch': min_pitch,
            'max_pitch': max_pitch,
            'notes': simplified_notes
        })
        
    return {
        'bpm': bpm,
        'time_signature': f"{time_num}/{time_den}",
        'ticks_per_beat': ticks_per_beat,
        'ticks_per_bar': ticks_per_bar,
        'total_bars': total_bars,
        'total_notes': len(all_notes),
        'bars': bar_data
    }

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        res = parse_midi_file(sys.argv[1])
        print(f"Parsed {res['total_bars']} bars, BPM {res['bpm']}, total notes {res['total_notes']}")
