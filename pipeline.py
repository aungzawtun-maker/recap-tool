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


def _tts_elevenlabs(text, out_path, api_key, voice_id, model_id="eleven_v3"):
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


def _tts_edgetts(text, out_path, voice="my-MM-ThihaNeural"):
    """Microsoft Edge TTS — မြန်မာ မိခင်ဘာသာအသံတွေ (Thiha ♂ / Nilar ♀), အခမဲ့, key မလို။
    မှတ်ချက်: Muse ရဲ့ VM ကနေ Microsoft endpoint ပိတ်ထားပေမဲ့ Streamlit Cloud ကနေ ရနိုင်တယ်။"""
    import asyncio, edge_tts
    async def _run():
        await edge_tts.Communicate(text, voice).save(out_path)
    asyncio.run(_run())


def tts_all(script, engine, workdir, api_key="", voice_id="", log=print):
    """script = [(start_sec, text), ...] -> [(mp3_path, start, duration), ...]"""
    lines_dir = os.path.join(workdir, "lines")
    os.makedirs(lines_dir, exist_ok=True)
    files = []
    for i, (target, text) in enumerate(script):
        p = os.path.join(lines_dir, f"line_{i:02d}.mp3")
        if engine == "elevenlabs":
            _tts_elevenlabs(text, p, api_key, voice_id)
        elif engine == "edgetts":
            _tts_edgetts(text, p, voice_id or "my-MM-ThihaNeural")
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


# ---------------- Auto script (LLM, multi-provider + auto-fallback) ----------------

SCRIPT_PROMPT = """သင်က မြန်မာဟာသ movie recap စာရေးဆရာပါ။
အောက်က ဗီဒီယို transcript (timestamp နဲ့ပါ) ကို ဖတ်ပြီး ရယ်ရတဲ့ မြန်မာ နောက်ခံစကားပြော script ရေးပါ။

စည်းကမ်းတွေ:
- စာကြောင်းတစ်ကြောင်းချင်းကို ဒီပုံစံနဲ့ပဲ ထုတ်ပါ: စစက္ကန့် | စာသား
  ဥပမာ: 0 | ကြိုးဖြေနေတယ်။ ဘာလုပ်မလို့လဲ?
- Transcript ထဲက [0s] လို ကွင်းခတ်ပုံစံကို လုံး၀ မသုံးပါနဲ့ — ဂဏန်း နဲ့ | ပဲ သုံးပါ
- ဇာတ်ကောင် ကိုယ်တိုင် ပြောသလို (ကျွန်တော်/ကျွန်မ) မရေးပါနဲ့ — ပြင်ပက ကြည့်ပြီး ပြန်ပြောပြတဲ့ narrator အဖြစ် ရေးပါ (ဥပမာ: "ဒီကောင်လေး ကူညီဖို့ ငြင်းဆန်နေတယ်")
- စစက္ကန့်တွေကို transcript ရဲ့ အချိန်တွေနဲ့ ကိုက်ညီအောင် ထားပါ
- တစ်ကြောင်းကို မြန်မာစကားလုံး ၈-၁၂ လုံးခန့်ပဲ ထားပါ (TTS က တစ်စက္ကန့် ၂ လုံးနှုန်းပဲ ပြောနိုင်တယ်)
- ဟာသဖြစ်အောင် ရေးပါ၊ ဒါပေမဲ့ ဇာတ်လမ်းအစစ်ကို မပျက်စီးစေပါနဲ့
- ရှင်းလင်းချက် မရေးပါနဲ့ — script စာကြောင်းတွေပဲ ထုတ်ပါ

Transcript:
{transcript}
"""


# provider -> (API base URL, [model အစဉ် — ပထမဟာ မရရင် နောက်တစ်ခု စမ်းမယ်])
# အကုန်လုံး OpenAI-compatible chat/completions ပုံစံ သုံးကြတယ်။
LLM_PROVIDERS = {
    "openrouter": (
        "https://openrouter.ai/api/v1",
        ["google/gemma-4-31b-it:free",
         "google/gemma-4-26b-a4b-it:free",
         "openrouter/free"],
    ),
    "groq": (
        "https://api.groq.com/openai/v1",
        ["llama-3.3-70b-versatile",
         "openai/gpt-oss-120b",
         "llama-3.1-8b-instant"],
    ),
    "nvidia": (
        "https://integrate.api.nvidia.com/v1",
        ["nvidia/nemotron-3-super-120b-a12b",
         "google/gemma-4-31b-it",
         "meta/llama-3.3-70b-instruct"],
    ),
}


def _normalize_script(text):
    """Model တွေ format လွဲထုတ်တတ်တယ် ([0s] ..., 0:05 ... စသည်) — အားလုံးကို
    'စက္ကန့် | စာသား' ပုံစံတူ ပြောင်းပေး။ မကိုက်တဲ့ စာကြောင်းကို ဒီအတိုင်း ထား
    (app ရဲ့ parse_script က | မပါရင် ကျော်သွားမယ်)။"""
    import re
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = (re.match(r"^\[?(\d+(?:\.\d+)?)\s*s\]?\s*\|\s*(.+)$", line)
             or re.match(r"^\[(\d+(?:\.\d+)?)\s*s?\]\s*(.+)$", line)
             or re.match(r"^(\d+(?:\.\d+)?)s\s*[:\-]\s*(.+)$", line))
        if m:
            sec = float(m.group(1))
            sec = int(sec) if sec == int(sec) else sec
            out.append(f"{sec} | {m.group(2).strip()}")
            continue
        mm = re.match(r"^(\d+):(\d{2})\s*\|?\s*(.+)$", line)
        if mm:
            out.append(f"{int(mm.group(1)) * 60 + int(mm.group(2))} | {mm.group(3).strip()}")
            continue
        out.append(line)
    return "\n".join(out)


def _llm_once(base_url, api_key, provider, model, prompt):
    import requests
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["X-Title"] = "Movie Recap Tool"
    r = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={"model": model,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=90,
    )
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:120]}")
    return r.json()["choices"][0]["message"]["content"].strip()


def write_script(segments, provider="openrouter", keys=None, model=""):
    """Transcript ကို LLM နဲ့ recap script ပြောင်း။
    segments = [(start, end, text), ...]
    keys = {"openrouter": "...", "groq": "...", "nvidia": "..."} (ရှိတဲ့ key ပဲ ထည့်)
    ရွေးထားတဲ့ provider/model ကနေ စ; မရရင် (404/5xx) နောက် model၊
    429 ဆို ၈ စက္ကန့် စောင့် တစ်ခါ ပြန်စမ်း၊ provider ကုန်ရင် key ရှိတဲ့
    နောက် provider ကို ဆက်စမ်း။ အောင်ရင် (script, "provider/model") ပြန်ပေး။
    (Google AI Studio က မြန်မာ region ပိတ်ထားလို့ တိုက်ရိုက် မသုံးပါ)"""
    import time
    keys = {p: k for p, k in (keys or {}).items() if k}
    if not keys:
        raise RuntimeError("AI key တစ်လုံးမှ မထည့်ရသေးပါ — sidebar မှာ key ထည့်ပါ")
    if provider not in keys:
        provider = next(iter(keys))
    transcript = "\n".join(f"[{s:.0f}s] {t}" for s, e, t in segments)
    prompt = SCRIPT_PROMPT.format(transcript=transcript)
    order = [provider] + [p for p in LLM_PROVIDERS if p != provider and p in keys]
    errors = []
    for prov in order:
        base_url, defaults = LLM_PROVIDERS[prov]
        models = (([model] if prov == provider and model else [])
                  + [m for m in defaults if m != model])
        for m in models:
            for attempt in range(2):
                try:
                    text = _llm_once(base_url, keys[prov], prov, m, prompt)
                    return _normalize_script(text), f"{prov}/{m}"
                except RuntimeError as ex:
                    if str(ex).startswith("429") and attempt == 0:
                        time.sleep(8)
                        continue
                    errors.append(f"{prov}/{m} -> {str(ex)[:60]}")
                    break
                except Exception as ex:
                    errors.append(f"{prov}/{m} -> {type(ex).__name__}")
                    break
    raise RuntimeError("AI model တွေ အကုန် မရပါ: " + " | ".join(errors))
