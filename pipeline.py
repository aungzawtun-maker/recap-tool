#!/usr/bin/env python3
"""Movie Recap Tool - pipeline module
recap.py / recap_build.py ထဲက logic ကို parameter နဲ့ သုံးလို့ရအောင် ပြန်ဖွဲ့ထားတာ။
Streamlit app (app.py) က ဒီ module ကို import လုပ်ပြီး သုံးတယ်။

အဆင့်တွေ:
  extract_audio()  -> ဗီဒီယိုကနေ အသံထုတ်
  transcribe()     -> Whisper နဲ့ transcript
  tts_all()        -> script စာကြောင်းတွေ အသံပြောင်း (gTTS / ElevenLabs)
  build_video()    -> narration စီ + ဗီဒီယိုနဲ့ ပြန်ဆက်
  write_srt()      -> script ကို .srt စာတန်းဖိုင် ထုတ်
  burn_subtitles() -> SRT စာတန်းကို ဗီဒီယိုထဲ အပြီးထည့် (မြန်မာဖောင့်ပါ)
"""
import subprocess, os, json

# မြန်မာစာတန်းအတွက် ဖောင့် — Google Fonts (OFL license), ပထမအကြိမ်မှာ auto-download
MYANMAR_FONT_URL = ("https://raw.githubusercontent.com/google/fonts/main/"
                    "ofl/notosansmyanmar/NotoSansMyanmar%5Bwdth%2Cwght%5D.ttf")
MYANMAR_FONT_NAME = "Noto Sans Myanmar"


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def probe_dimensions(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


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


def transcribe(audio_path, model_size="base"):
    # base က tiny ထက် စာသား အများကြီး ပိုမှန်တယ် (script အရည်အသွေးက transcript ပေါ် မူတည်လို့)။
    # Streamlit free RAM ~1GB မှာ base (int8) က အေးဆေး ဝင်တယ်။
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(_load_audio_array(audio_path))
    return [(s.start, s.end, s.text.strip()) for s in segments], info.language


def transcribe_groq(audio_path, api_key, model="whisper-large-v3"):
    """Groq cloud ပေါ်က Whisper large-v3 — local ထက် အများကြီး ပိုမှန်, မြန်, RAM မစား။
    Groq key ရှိရင်ရ (Script AI အတွက် ထည့်ထားတဲ့ key အတူတူပဲ)။
    verbose_json က အပိုဒ်လိုက် timestamp ပြန်ပေးတယ်။
    မှတ်ချက်: Groq ရဲ့ file limit 25MB — 16kHz mono WAV က ၁ မိနစ်ကို ~2MB ပဲ ရှိလို့
    clip အတိုတွေမှာ ပြဿနာ မရှိဘူး။"""
    import requests, os
    with open(audio_path, "rb") as f:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (os.path.basename(audio_path), f, "audio/wav")},
            data={"model": model, "response_format": "verbose_json"},
            timeout=300,
        )
    if r.status_code != 200:
        raise RuntimeError(f"Groq Whisper error {r.status_code}: {r.text[:200]}")
    data = r.json()
    segs = [(s["start"], s["end"], s["text"].strip())
            for s in data.get("segments", [])]
    return segs, data.get("language", "?")


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

def place_timings(files):
    """[(path, target_sec, dur_sec)] -> [(path, start_sec, dur_sec)]
    စာကြောင်းတွေ ထပ်မနေအောင် timestamp အလိုက် စီ (build_video နဲ့ SRT အတူတူ သုံးတယ်)"""
    placed, prev_end = [], 0.0
    for path, target, dur in files:
        start = max(float(target), prev_end + 0.25)
        placed.append((path, start, float(dur)))
        prev_end = start + float(dur)
    return placed


def build_video(video_path, files, workdir, log=print, keep_orig=False):
    video_dur = probe_duration(video_path)
    placed = place_timings(files)
    total = placed[-1][1] + placed[-1][2] if placed else 0.0
    log(f"Narration {total:.1f}s / Video {video_dur:.1f}s")

    inputs, filters = [], []
    for i, (path, start, dur) in enumerate(placed):
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
    if keep_orig:
        # မူရင်းအသံ 12% နဲ့ ရော (အရင်အတိုင်း)
        fc = "[0:a]volume=0.12[orig];[orig][1:a]amix=inputs=2:normalize=0[aout]"
    else:
        # narration သီးသန့် — မူရင်းဗီဒီယိုထဲက လူပြောသံ/အသံတွေ လုံးဝ မပါ
        # (apad က narration တိုနေရင် တိတ်ဆိတ်နဲ့ ဖြည့်ပေးလို့ ဗီဒီယို အပြည့်ထွက်တယ်)
        fc = "[1:a]apad[aout]"
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-i", narr,
                    "-filter_complex", fc, "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-shortest", final],
                   check=True, capture_output=True)
    return final


# ---------------- Subtitles (SRT + burn-in) ----------------

def _srt_time(sec):
    sec = max(0.0, float(sec))
    h, rem = divmod(sec, 3600)
    m, rem = divmod(rem, 60)
    s = int(rem)
    ms = int(round((rem - s) * 1000))
    return f"{int(h):02d}:{int(m):02d}:{s:02d},{ms:03d}"


def write_srt(timed, out_path):
    """timed = [(start_sec, dur_sec, text), ...] -> .srt စာတန်းဖိုင် ထုတ်။
    အချိန်တွေက TTS အသံအစစ်ရဲ့ နေရာချထားမှုနဲ့ ကိုက်တယ်။"""
    blocks = []
    for i, (start, dur, text) in enumerate(timed):
        end = start + max(0.5, float(dur))
        if i + 1 < len(timed):
            end = min(end, timed[i + 1][0] - 0.05)
        end = max(end, start + 0.5)
        blocks.append(f"{i + 1}\n{_srt_time(start)} --> {_srt_time(end)}\n{text.strip()}\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))
    return out_path


def ensure_myanmar_font(workdir, log=print):
    """မြန်မာဖောင့် (Noto Sans Myanmar) ကို workdir/fonts/ မှာ ရှိမရှိ စစ် —
    မရှိရင် Google Fonts ကနေ ဒေါင်းလုဒ်လုပ်။ ရရင် path ပြန်, မရရင် None။"""
    import requests
    d = os.path.join(workdir, "fonts")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "NotoSansMyanmar.ttf")
    if os.path.exists(p) and os.path.getsize(p) > 100000:
        return p
    try:
        log("မြန်မာဖောင့် ဒေါင်းလုဒ်နေတယ်... (ပထမတစ်ခါတည်း)")
        r = requests.get(MYANMAR_FONT_URL, timeout=120)
        r.raise_for_status()
        if r.content[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            raise RuntimeError("ဖောင့်ဖိုင် မဟုတ်ပါ")
        with open(p, "wb") as f:
            f.write(r.content)
        return p
    except Exception as ex:
        log(f"ဖောင့် ဒေါင်းလုဒ် မရ: {ex}")
        try:
            os.remove(p)
        except OSError:
            pass
        return None


def _vf_escape(path):
    p = os.path.abspath(path)
    for ch in ("\\", "'", ":", ",", "[", "]", ";"):
        p = p.replace(ch, "\\" + ch)
    return p


def _ass_time(sec):
    sec = max(0.0, float(sec))
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_escape(text):
    t = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return t.replace("\n", "\\N")


def burn_subtitles(video_path, timed, font_path, out_path, log=print):
    """Timed subtitle တွေကို ဗီဒီယိုထဲ အပြီးထည့်။
    သတိ: SRT ကို ffmpeg ရဲ့ subtitles filter နဲ့ တိုက်ရိုက်ထည့်ရင်
    ffmpeg က ASS ကို 384x288 PlayRes နဲ့ ထုတ်ပြီး ဗီဒီယို size ကို
    အချိုးမညီဘဲ ဆန့်ထုတ်လို့ — စာလုံး ကြီးလွန်း၊ အပေါ်ရောက်၊
    မြန်မာအက္ခရာ shaping (သရသင်္ကေတ/ရရစ် နေရာလွဲ) ပျက်တယ်။
    ဒါကြောင့် ASS ကို ကိုယ်တိုင် ဗီဒီယိုအရွယ် အတိအကျ
    (PlayRes = video size) နဲ့ ရေးပြီး ass filter နဲ့ ထည့်တယ်။
    timed = [(start_sec, dur_sec, text), ...]
    ပုံစံ: အဝါရောင် bold + အနက်ကွက် outline, အောက်ခြေ, MarginV 120။"""
    w, h = probe_dimensions(video_path)
    events = []
    for start, dur, text in timed:
        end = start + max(0.5, float(dur))
        events.append((start, end, text))
    fixed = []
    for i, (start, end, text) in enumerate(events):
        if i + 1 < len(events):
            end = min(end, events[i + 1][0] - 0.05)
        end = max(end, start + 0.5)
        fixed.append((start, end, text))
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {w}",
        f"PlayResY: {h}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{MYANMAR_FONT_NAME},44,&H0000FFFF,&H000000FF,&H80000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,2,120,120,120,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for start, end, text in fixed:
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{_ass_escape(text.strip())}")
    ass_path = os.path.join(os.path.dirname(out_path), "recap.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    fontsdir = os.path.dirname(os.path.abspath(font_path))
    vf = f"ass='{_vf_escape(ass_path)}':fontsdir='{_vf_escape(fontsdir)}'"
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vf", vf,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "copy", out_path],
                   check=True, capture_output=True)
    log("စာတန်းထိုး ထည့်ပြီးပြီ")
    return out_path


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


def _clean_script_text(t):
    """Script စာသားထဲက ကွင်းခတ် အချိန်အမှတ်တွေ ([6s] [8s] ...) ကို
    နေရာမရွေး ဖျက် — TTS ဖတ်တာ/စာတန်းထိုးမှာ ပေါ်မလာအောင်။"""
    import re
    t = re.sub(r"\[\d+(?:\.\d+)?s?\]", "", t)
    return re.sub(r"\s+", " ", t).strip()


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
            body = _clean_script_text(m.group(2))
            if body:
                out.append(f"{sec} | {body}")
            continue
        mm = re.match(r"^(\d+):(\d{2})\s*\|?\s*(.+)$", line)
        if mm:
            body = _clean_script_text(mm.group(3))
            if body:
                out.append(f"{int(mm.group(1)) * 60 + int(mm.group(2))} | {body}")
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
        json={"model": model, "temperature": 0.7,
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
