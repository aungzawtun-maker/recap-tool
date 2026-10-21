#!/usr/bin/env python3
"""Movie Recap Tool - pipeline module
recap.py / recap_build.py ထဲက logic ကို parameter နဲ့ သုံးလို့ရအောင် ပြန်ဖွဲ့ထားတာ။
Streamlit app (app.py) က ဒီ module ကို import လုပ်ပြီး သုံးတယ်။

အဆင့်တွေ:
  extract_audio()  -> ဗီဒီယိုကနေ အသံထုတ်
  transcribe()     -> Whisper နဲ့ transcript
  tts_all()        -> script စာကြောင်းတွေ အသံပြောင်း (gTTS / ElevenLabs)
  build_video()    -> narration စီ + ဗီဒီယိုနဲ့ ပြန်ဆက်
"""
import subprocess, os, json


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def extract_audio(video_path, out_path):
    cmd = ["ffmpeg", "-y", "-i", video_path,
           "-vn", "-ac", "1", "-ar", "16000", out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _load_audio_array(audio_path):
    import numpy as np
    cmd = ["ffmpeg", "-v", "error", "-i", audio_path,
           "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def transcribe(audio_path, model_size="tiny"):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(_load_audio_array(audio_path))
    return [(s.start, s.end, s.text.strip()) for s in segments], info.language


# ---------------- TTS engines ----------------

def _tts_gtts(text, out_path):
    from gtts import gTTS
    gTTS(text=text, lang="my").save(out_path)


def _tts_elevenlabs(text, out_path, api_key, voice_id, model_id="eleven_multilingual_v2"):
    """ElevenLabs API - ကိုယ်ပိုင် API key လိုတယ် (elevenlabs.io မှာ အခမဲ့ စမ်းလို့ရ)"""
    import requests
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    r = requests.post(
        url,
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": model_id,
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs error {r.status_code}: {r.text[:200]}")
    with open(out_path, "wb") as f:
        f.write(r.content)


def tts_all(script, engine, workdir, api_key="", voice_id="", log=print):
    """script = [(start_sec, text), ...] -> [(mp3_path, start, duration), ...]"""
    lines_dir = os.path.join(workdir, "lines")
    os.makedirs(lines_dir, exist_ok=True)
    files = []
    for i, (target, text) in enumerate(script):
        p = os.path.join(lines_dir, f"line_{i:02d}.mp3")
        if engine == "elevenlabs":
            _tts_elevenlabs(text, p, api_key, voice_id)
        else:
            _tts_gtts(text, p)
        dur = probe_duration(p)
        files.append((p, float(target), dur))
        log(f"TTS {i+1}/{len(script)}: {dur:.1f}s")
    return files


# ---------------- Assembly ----------------

def build_video(video_path, files, workdir, log=print):
    video_dur = probe_duration(video_path)
    # စာကြောင်းတွေ ထပ်မနေအောင် timestamp အလိုက် စီ
    placed, prev_end = [], 0.0
    for path, target, dur in files:
        start = max(target, prev_end + 0.25)
        placed.append((path, start))
        prev_end = start + dur
    total = prev_end
    log(f"Narration {total:.1f}s / Video {video_dur:.1f}s")

    inputs, filters = [], []
    for i, (path, start) in enumerate(placed):
        inputs += ["-i", path]
        ms = int(start * 1000)
        filters.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(placed)))
    filters.append(f"{mix}amix=inputs={len(placed)}:normalize=0[narr]")
    narr = os.path.join(workdir, "narration.wav")
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex",
                    ";".join(filters), "-map", "[narr]", narr],
                   check=True, capture_output=True)
    if total > video_dur:  # ရှည်လွန်းရင် အနည်းငယ် အမြန်တင်
        rate = total / video_dur
        fixed = os.path.join(workdir, "narration_fit.wav")
        subprocess.run(["ffmpeg", "-y", "-i", narr, "-filter:a",
                        f"atempo={rate:.3f}", fixed],
                       check=True, capture_output=True)
        narr = fixed
        log(f"atempo x{rate:.2f}")

    final = os.path.join(workdir, "final_recap.mp4")
    fc = "[0:a]volume=0.12[orig];[orig][1:a]amix=inputs=2:normalize=0[aout]"
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-i", narr,
                    "-filter_complex", fc, "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-shortest", final],
                   check=True, capture_output=True)
    return final
