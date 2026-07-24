import mido
import os
import zipfile

def create_midi_track(note_events, bpm=120, ticks_per_beat=480, channel=0):
    """
    Creates a mido MidiFile object from a list of note events.
    note_events format: [
        {'bar': 1, 'beat': 0.0, 'pitch': 36, 'vel': 100, 'dur': 0.25},
        ...
    ]
    """
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    
    # Add tempo message
    tempo = mido.bpm2tempo(bpm)
    track.append(mido.MetaMessage('set_tempo', tempo=tempo, time=0))
    track.append(mido.MetaMessage('time_signature', numerator=4, denominator=4, time=0))
    
    ticks_per_bar = ticks_per_beat * 4
    
    # Build absolute tick events (note_on and note_off)
    raw_events = []
    for note in note_events:
        bar = note.get('bar', 1)
        beat = note.get('beat', 0.0)
        pitch = int(note['pitch'])
        vel = int(note.get('vel', 90))
        dur_beats = float(note.get('dur', 0.25))
        
        start_tick = int((bar - 1) * ticks_per_bar + beat * ticks_per_beat)
        duration_ticks = max(1, int(dur_beats * ticks_per_beat))
        end_tick = start_tick + duration_ticks
        
        raw_events.append({
            'tick': start_tick,
            'type': 'note_on',
            'pitch': pitch,
            'vel': vel,
            'channel': channel
        })
        raw_events.append({
            'tick': end_tick,
            'type': 'note_off',
            'pitch': pitch,
            'vel': 0,
            'channel': channel
        })
        
    # Sort events chronologically. For equal ticks, process note_off before note_on
    raw_events.sort(key=lambda x: (x['tick'], 0 if x['type'] == 'note_off' else 1))
    
    # Convert absolute ticks to delta ticks for mido
    last_tick = 0
    for ev in raw_events:
        delta = max(0, ev['tick'] - last_tick)
        last_tick = ev['tick']
        track.append(mido.Message(
            ev['type'],
            note=ev['pitch'],
            velocity=ev['vel'],
            channel=ev['channel'],
            time=delta
        ))
        
    return mid

def build_split_midi_files(generated_data, output_dir, bpm=120):
    """
    Takes generated stem note structures and saves split MIDI files:
    - kick.mid
    - snare.mid
    - hihat.mid
    - cymbals.mid
    - full_drums.mid
    - piano.mid
    - guitar.mid
    Returns dict of output file paths and a ZIP archive.
    """
    os.makedirs(output_dir, exist_ok=True)
    created_files = {}
    
    # 1. Drums split
    drums_data = generated_data.get('drums', [])
    kick_notes = [n for n in drums_data if n.get('pitch') in (35, 36)]
    snare_notes = [n for n in drums_data if n.get('pitch') in (38, 40, 37)] # Snare, Electric Snare, Side Stick / Rim
    hihat_notes = [n for n in drums_data if n.get('pitch') in (42, 44, 46)] # Closed HH, Pedal HH, Open HH
    cymbal_notes = [n for n in drums_data if n.get('pitch') not in (35, 36, 37, 38, 40, 42, 44, 46)]
    
    # Drums use MIDI channel 9 (0-indexed channel 9 = MIDI Channel 10)
    drum_channel = 9
    
    splits = {
        'kick.mid': (kick_notes, drum_channel),
        'snare.mid': (snare_notes, drum_channel),
        'hihat.mid': (hihat_notes, drum_channel),
        'cymbals.mid': (cymbal_notes, drum_channel),
        'full_drums.mid': (drums_data, drum_channel),
        'piano.mid': (generated_data.get('piano', []), 0),
        'guitar.mid': (generated_data.get('guitar', []), 1)
    }
    
    file_paths = []
    for filename, (notes, chan) in splits.items():
        filepath = os.path.join(output_dir, filename)
        mid = create_midi_track(notes, bpm=bpm, channel=chan)
        mid.save(filepath)
        created_files[filename] = filepath
        file_paths.append(filepath)
        
    # Create ZIP bundle
    zip_path = os.path.join(output_dir, 'authentic_stems_midi.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for fname, fpath in created_files.items():
            zipf.write(fpath, arcname=fname)
            
    created_files['zip'] = zip_path
    return created_files
