import mido
import os
import shutil
import zipfile

def create_midi_track(note_events, bpm=120, ticks_per_beat=480, channel=0):
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    
    tempo = mido.bpm2tempo(bpm)
    track.append(mido.MetaMessage('set_tempo', tempo=tempo, time=0))
    track.append(mido.MetaMessage('time_signature', numerator=4, denominator=4, time=0))
    
    ticks_per_bar = ticks_per_beat * 4
    
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
        
    raw_events.sort(key=lambda x: (x['tick'], 0 if x['type'] == 'note_off' else 1))
    
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

def build_split_midi_files(generated_data, output_dir, bpm=120, target_downloads_dir=r"C:\Users\ricky\Downloads", original_filename_base="lullaby_of_damsel"):
    os.makedirs(output_dir, exist_ok=True)
    created_files = {}
    
    drums_data = generated_data.get('drums', [])
    piano_data = generated_data.get('piano', [])
    guitar_data = generated_data.get('guitar', [])
    
    # Combined master reconstructed notes
    all_reconstructed_notes = drums_data if drums_data else (piano_data if piano_data else guitar_data)
    
    kick_notes = [n for n in drums_data if n.get('pitch') in (35, 36)]
    snare_notes = [n for n in drums_data if n.get('pitch') in (37, 38, 40)]
    hihat_notes = [n for n in drums_data if n.get('pitch') in (42, 44, 46, 81)]
    cymbal_notes = [n for n in drums_data if n.get('pitch') not in (35, 36, 37, 38, 40, 42, 44, 46, 81)]
    
    drum_channel = 9
    
    splits = {
        'reconstructed_master.mid': (all_reconstructed_notes, drum_channel if drums_data else 0),
        'kick.mid': (kick_notes, drum_channel),
        'snare.mid': (snare_notes, drum_channel),
        'hihat.mid': (hihat_notes, drum_channel),
        'cymbals.mid': (cymbal_notes, drum_channel),
        'full_drums.mid': (drums_data, drum_channel),
        'piano.mid': (piano_data, 0),
        'guitar.mid': (guitar_data, 1)
    }
    
    for filename, (notes, chan) in splits.items():
        filepath = os.path.join(output_dir, filename)
        mid = create_midi_track(notes, bpm=bpm, channel=chan)
        mid.save(filepath)
        created_files[filename] = filepath

    # Export copy to C:\Users\ricky\Downloads\
    if os.path.exists(target_downloads_dir):
        out_name = f"{original_filename_base}_reconstructed.mid"
        downloads_export_path = os.path.join(target_downloads_dir, out_name)
        master_src = created_files['reconstructed_master.mid']
        shutil.copy(master_src, downloads_export_path)
        created_files['downloads_path'] = downloads_export_path
        
    # ZIP Bundle
    zip_path = os.path.join(output_dir, 'authentic_stems_midi.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for fname, fpath in created_files.items():
            if fname != 'downloads_path':
                zipf.write(fpath, arcname=fname)
            
    created_files['zip'] = zip_path
    return created_files
