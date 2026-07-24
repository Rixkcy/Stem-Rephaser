# Stem Rephaser & AI MIDI Generator 🎛️

An AI-powered MIDI visualizer, section blueprint analyzer, and authentic stem generator for FL Studio (FPC / FLEX).

## 🌟 Overview

When AI music generators (like Suno/Udio) generate stems, transcription tools often output robotic, timing-jittered, or ghost-note-filled MIDI files. **Stem Rephaser** takes 2 transcribed MIDI passes of the exact same stem, cross-references them using Gemini 2.5 Flash / 3.5 Flash Lite agentic reasoning, and produces clean, humanized replacement MIDIs.

## 🚀 Key Features

- **Dual-Input Cross-Analysis**: Analyzes 2 MIDI transcriptions of the same track to construct a 100% accurate Master Blueprint of song sections (`CONSTANT_BEAT`, `BUILD_UP`, `BREAK_DROP`, `SLOW`).
- **Interactive Agentic Critic Loop**: Generates authentic replacement drum patterns mapped for FL Studio FPC pads (Kick=C3, Snare=D3, Hats=F#3, Cymbals=Crash/Ride) and instrument tracks (Piano, Guitar).
- **Streamlined Dual View Web UI**: HTML5 Canvas density timelines, color-coded section badges, and built-in Web Audio synthesizers for instant browser preview playback.
- **Multi-Track Export**: Downloads individual split `.mid` files (`kick.mid`, `snare.mid`, `hihat.mid`, `cymbals.mid`, `piano.mid`, `guitar.mid`) and packaged `authentic_stems_midi.zip` bundles.

## 🛠️ Installation & Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Rixkcy/Stem-Rephaser.git
   cd Stem-Rephaser
   ```

2. Install dependencies:
   ```bash
   pip install flask mido google-genai python-dotenv
   ```

3. Configure your Gemini API key in `D:\apps\columbina-bot\.env` (or a local `.env` file):
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

4. Launch the Web Application:
   - Double-click `launch.bat` OR run:
   ```bash
   python app.py
   ```
5. Open `http://127.0.0.1:5000` in your browser.
