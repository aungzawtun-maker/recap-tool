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


def transcribe(audio_path, model_size="base", language=None):
    # base က tiny ထက် စာသား အများကြီး ပိုမှန်တယ် (script အရည်အသွေးက transcript ပေါ် မူတည်လို့)။
    # Streamlit free RAM ~1GB မှာ base (int8) က အေးဆေး ဝင်တယ်။
    # language: None = အလိုအလျောက် သိ; "my" လို့ ပေးရင် မြန်မာလို့ အတင်းပြော
    # (သီချင်းမှာ Whisper က ဘာသာစကား မှားသိပြီး Latin စာနဲ့ ထွက်တတ်လို့)။
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(_load_audio_array(audio_path),
                                      language=language)
    return [(s.start, s.end, s.text.strip()) for s in segments], info.language


def transcribe_groq(audio_path, api_key, model="whisper-large-v3", language=None):
    """Groq cloud ပေါ်က Whisper large-v3 — local ထက် အများကြီး ပိုမှန်, မြန်, RAM မစား။
    Groq key ရှိရင်ရ (Script AI အတွက် ထည့်ထားတဲ့ key အတူတူပဲ)။
    verbose_json က အပိုဒ်လိုက် timestamp ပြန်ပေးတယ်။
    language: None = အလိုအလျောက်; "my" ဆို မြန်မာလို့ အတင်းပြော
    (သီချင်းမှာ ဘာသာစကား မှားသိပြီး Latin စာနဲ့ ထွက်တတ်လို့)။
    မှတ်ချက်: Groq ရဲ့ file limit 25MB — 16kHz mono WAV က ၁ မိနစ်ကို ~2MB ပဲ ရှိလို့
    clip အတိုတွေမှာ ပြဿနာ မရှိဘူး။"""
    import requests, os
    payload = {"model": model, "response_format": "verbose_json"}
    if language:
        payload["language"] = language
    with open(audio_path, "rb") as f:
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (os.path.basename(audio_path), f, "audio/wav")},
            data=payload,
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


def build_video(video_path, files, workdir, log=print, orig_volume=0.0,
                blur_band="none", zoom="none", pip=False, effect="none",
                logo_path=None, logo_pos="top-right"):
    """Narration စီ + ဗီဒီယိုနဲ့ ပြန်ဆက်။
    ပြန်ပေးတာ: (final_path, fit_rate)။ fit_rate > 1 ဆို narration ကို
    atempo နဲ့ အမြန်တင်ထားတာ — စာတန်းအချိန်တွေကို fit_rate နဲ့
    စားမှ (start/rate, dur/rate) အသံနဲ့ ကိုက်မယ်။
    orig_volume: မူရင်းအသံ အတိုးအကျယ် (0.0 = မထည့်, 0.1/0.25/0.5/1.0)။
    blur_band: မူရင်းစာသား ရှိတဲ့နေရာ မှုန်ဝါးပေး
      (none/top/middle/lower/bottom — အမြင့် 20% ကြောင်း,
      ဒါမှမဟုတ် slider က ဂဏန်း 0.0–0.8 = band အပေါ်ဆုံးနေရာ)။
    zoom: none/in (10% ချဲ့)/out (10% သေး + အနက်ကွက်)။
    pip: မှုန်နောက်ခံ + 85% ဗီဒီယို picture-in-picture။
    effect: none/mirror (မှန်ပြောင်းပြန်)/gray (အဖြူအမည်း)။
    logo_path: ဗီဒီယိုပေါ်မှာ တင်မယ့် PNG (transparent ဆို အလှဆုံး)၊
      အကျယ် 80px; logo_pos: top-right/top-left/bottom-right/bottom-left။
    သတိ: video filter တစ်ခု ပါတာနဲ့ ဗီဒီယို ပြန် encode ရတယ်
    (မပါရင် အရင်အတိုင်း -c:v copy မြန်မြန်)။"""
    video_dur = probe_duration(video_path)
    placed = place_timings(files)
    total = placed[-1][1] + placed[-1][2] if placed else 0.0
    log(f"Narration {total:.1f}s / Video {video_dur:.1f}s")
    rate = 1.0

    narr = None
    if files:
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
            log(f"atempo x{rate:.2f} (စာတန်းလည်း လိုက်မြန်မယ်)")
    else:
        # ဘာသာပြန် မုဒ် — narration မပါ, မူရင်းအသံပဲ သုံးမယ်
        log("ဘာသာပြန် မုဒ် — narration မပါ")

    # ---------- video filter chain (လိုမှ တည်, အထွက် size မပြောင်း) ----------
    vw, vh = probe_dimensions(video_path)
    logo_idx = 2 if narr else 1  # mux inputs: video, [narr], [logo]
    vf = []
    cur = "0:v"
    n = [0]

    def _next():
        n[0] += 1
        return f"v{n[0]}"

    if blur_band != "none":
        if isinstance(blur_band, (int, float)):
            # slider က ဂဏန်း — band အပေါ်ဆုံးနေရာ (0.0 = အပေါ်ဆုံး)
            y = f"ih*{float(blur_band)}"
            yo = f"H*{float(blur_band)}"
        else:
            y = {"top": "0", "middle": "ih*0.4", "lower": "ih*0.6", "bottom": "ih*0.8"}[blur_band]
            yo = {"top": "0", "middle": "H*0.4", "lower": "H*0.6", "bottom": "H*0.8"}[blur_band]
        nxt = _next()
        vf.append(f"[{cur}]split=2[base][band]")
        vf.append(f"[band]crop=iw:ih*0.2:0:{y},boxblur=lr=20:lp=2[bandb]")
        vf.append(f"[base][bandb]overlay=0:{yo}[{nxt}]")
        cur = nxt
    if effect == "mirror":
        nxt = _next()
        vf.append(f"[{cur}]hflip[{nxt}]")
        cur = nxt
    elif effect == "gray":
        nxt = _next()
        vf.append(f"[{cur}]format=gray[{nxt}]")
        cur = nxt
    if zoom == "in":
        nxt = _next()
        vf.append(f"[{cur}]crop=iw*0.9:ih*0.9,scale={vw}:{vh}[{nxt}]")
        cur = nxt
    elif zoom == "out":
        zw, zh = vw * 90 // 100 // 2 * 2, vh * 90 // 100 // 2 * 2  # 90%, စုံကိန်း
        nxt = _next()
        vf.append(f"[{cur}]scale={zw}:{zh},pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2[{nxt}]")
        cur = nxt
    if pip:
        pw, ph = vw * 85 // 100 // 2 * 2, vh * 85 // 100 // 2 * 2  # 85%, စုံကိန်း
        nxt = _next()
        vf.append(f"[{cur}]split=2[bg][fg]")
        vf.append("[bg]boxblur=lr=20:lp=2[bgb]")
        vf.append(f"[fg]scale={pw}:{ph}[fgs]")
        vf.append(f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[{nxt}]")
        cur = nxt
    if logo_path and os.path.exists(logo_path):
        nxt = _next()
        vf.append(f"[{logo_idx}:v]scale=80:-2,format=rgba[logo]")
        ox, oy = {"top-right": ("W-w-10", "10"),
                  "top-left": ("10", "10"),
                  "bottom-right": ("W-w-10", "H-h-10"),
                  "bottom-left": ("10", "H-h-10")}[logo_pos]
        vf.append(f"[{cur}][logo]overlay={ox}:{oy}[{nxt}]")
        cur = nxt

    # ---------- audio chain ----------
    if narr:
        if orig_volume and orig_volume > 0:
            afc = (f"[0:a]volume={orig_volume}[orig];"
                   f"[orig][1:a]amix=inputs=2:normalize=0[aout]")
        else:
            # narration သီးသန့် — မူရင်းဗီဒီယိုထဲက လူပြောသံ/အသံတွေ လုံးဝ မပါ
            # (apad က narration တိုနေရင် တိတ်ဆိတ်နဲ့ ဖြည့်ပေးလို့ ဗီဒီယို အပြည့်ထွက်တယ်)
            afc = "[1:a]apad[aout]"
    else:
        # narration မပါ — မူရင်းအသံ အပြည့် (ဘာသာပြန် မုဒ်မှာ အဓိက အသံ)
        vol = orig_volume if orig_volume and orig_volume > 0 else 1.0
        afc = f"[0:a]volume={vol}[aout]"

    final = os.path.join(workdir, "final_recap.mp4")
    mux_inputs = ["-i", video_path]
    if narr:
        mux_inputs += ["-i", narr]
    if logo_path and os.path.exists(logo_path):
        mux_inputs += ["-i", logo_path]
    if vf:
        fc = ";".join(vf + [afc])
        subprocess.run(["ffmpeg", "-y", *mux_inputs,
                        "-filter_complex", fc, "-map", f"[{cur}]",
                        "-map", "[aout]",
                        "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "20", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", final],
                       check=True, capture_output=True)
    else:
        subprocess.run(["ffmpeg", "-y", *mux_inputs,
                        "-filter_complex", afc, "-map", "0:v",
                        "-map", "[aout]",
                        "-c:v", "copy", "-c:a", "aac",
                        "-shortest", final],
                       check=True, capture_output=True)
    return final, rate


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


def burn_subtitles(video_path, timed, font_path, out_path, log=print, font_size=64, position="bottom"):
    """Timed subtitle တွေကို ဗီဒီယိုထဲ အပြီးထည့်။
    သတိ: SRT ကို ffmpeg ရဲ့ subtitles filter နဲ့ တိုက်ရိုက်ထည့်ရင်
    ffmpeg က ASS ကို 384x288 PlayRes နဲ့ ထုတ်ပြီး ဗီဒီယို size ကို
    အချိုးမညီဘဲ ဆန့်ထုတ်လို့ — စာလုံး ကြီးလွန်း၊ အပေါ်ရောက်၊
    မြန်မာအက္ခရာ shaping (သရသင်္ကေတ/ရရစ် နေရာလွဲ) ပျက်တယ်။
    ဒါကြောင့် ASS ကို ကိုယ်တိုင် ဗီဒီယိုအရွယ် အတိအကျ
    (PlayRes = video size) နဲ့ ရေးပြီး ass filter နဲ့ ထည့်တယ်။
    timed = [(start_sec, dur_sec, text), ...]
    ပုံစံ: အဝါရောင် bold + အနက်ကွက် outline။
    position: bottom (အောက်, MarginV 120) / middle (အလယ်) / top (အပေါ်, MarginV 120)။
    font_size: စာလုံးအရွယ် (default 64 — 1080x1920 မှာ 44 က ဖုန်းကြည့်ရင် သေးလွန်းလို့)။"""
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
    alignment, marginv = {"bottom": (2, 120), "middle": (5, 0), "top": (8, 120)}[position]
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {w}",
        f"PlayResY: {h}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{MYANMAR_FONT_NAME},{font_size},&H0000FFFF,&H000000FF,&H80000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,{alignment},120,120,{marginv},1",
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

SCRIPT_PROMPT_EN = """You are a funny movie recap narrator.
Read the video transcript below (with timestamps) and write a funny English voice-over recap script.

Rules:
- Output ONLY lines in this exact format: start_second | text
  Example: 0 | He's untying the rope. What's he planning?
- Never use bracket timestamps like [0s] from the transcript — only numbers and |
- Write as an outside narrator watching the scene, NOT as a character speaking in first person (for example: "The guy refuses to help")
- Keep the start seconds aligned with the transcript times
- Keep each line short (about 8-12 words) so the narration fits the video (TTS speaks about 2-3 words per second)
- Be funny, but don't distort the real story
- No explanations — output only the script lines

Transcript:
{transcript}
"""


TRANSLATE_PROMPT = """You are a professional subtitle translator.
Translate the transcript below from {source} to {target}.

Rules:
- Output ONE line per transcript segment, in the same order, same count.
- Each line in exactly this format: start_second | translated text
  Example: 0 | Hello, how are you?
- Use the segment's start second (the number in [Ns]) as the line's start.
- {style_line}
- For songs, keep the translation singable and keep the feeling — a
  stiff word-for-word version ruins a song.
- No explanations, no extra lines, no bracket timestamps — only
  "start | text" lines.

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
    "gemini": (
        # Google ရဲ့ OpenAI-compatible endpoint — _llm_once အတိုင်း
        # Bearer key + chat/completions ပုံစံနဲ့ တိုက်ရိုက်ခေါ်လို့ရတယ်
        "https://generativelanguage.googleapis.com/v1beta/openai",
        # သတိ: 2.5-flash / 2.0-flash ကို Google က key အသစ်တွေအတွက်
        # ပိတ်လိုက်ပြီ (404 "no longer available to new users") — 2026-10-26
        # debug run မှာ အတည်ပြုပြီးသား။ အစားထိုးက 3.8-flash (error ကိုယ်တိုင်
        # ညွှန်တဲ့ model, key အသစ်နဲ့ ရတယ်လို့ စမ်းပြီးသား)၊ ပြီးရင်
        # flash-latest (alias, တစ်ခါတစ်ရံ 503 overload ဖြစ်)၊
        # 3.5-flash-lite (ပေါ့ပါးတဲ့ အစားထိုး)။
        ["gemini-3.8-flash",
         "gemini-flash-latest",
         "gemini-3.5-flash-lite"],
    ),
}


# နောက် write_script() ခေါ်တိုင်း ဘယ် model တွေ စမ်းပြီး ဘာဖြစ်လဲ ဆိုတာ
# ဒီမှာ မှတ်ထားတယ် — app.py က 🔍 section မှာ ပြဖို့။
# (အောင်တဲ့ model တစ်ခု ရှိရင် ကျန်တဲ့ အမှားတွေ ပျောက်သွားလို့ ဒီလို မှတ်ရတာ)
LAST_LLM_ATTEMPTS = []


def _clean_script_text(t):
    """Script စာသားထဲက ကွင်းခတ် အချိန်အမှတ်တွေ ([6s] [8s] ...) ကို
    နေရာမရွေး ဖျက် — TTS ဖတ်တာ/စာတန်းထိုးမှာ ပေါ်မလာအောင်။"""
    import re
    t = re.sub(r"\[\d+(?:\.\d+)?s?\]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _normalize_script(text):
    """Model တွေ format လွဲထုတ်တတ်တယ် ([0s] ..., 0:05 ... စသည်) — အားလုံးကို
    'စက္ကန့် | စာသား' ပုံစံတူ ပြောင်းပေး။ မကိုက်တဲ့ စာကြောင်းကို ဒီအတိုင်း ထား
    (app ရဲ့ parse_script က | မပါရင် ကျော်သွားမယ်)။
    Reasoning model တွေ (Nemotron လို) က script block လိုက် ထပ်ထုတ်တာ +
    "I need to stop. Final answer:" လို meta စာကြောင်းတွေ ပါတတ်လို့
    အဲဒါတွေကို ဖျက်ပြီး ထပ်နေတဲ့ စာကြောင်းတွေလည်း တစ်ကြောင်းတည်း ချန်တယ် —
    မဟုတ်ရင် narration ၂ ခါ ထပ်ပြီး ဗီဒီယိုနဲ့ မကိုက်ဘဲ အမြန်တင်ရတယ်။"""
    import re
    META_PREFIXES = ("i need to stop", "final answer", "here is", "here's",
                     "sure, here", "okay, here", "let me", "thinking:")
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith(META_PREFIXES):
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
    # ထပ်နေတဲ့ စာကြောင်းတွေ တစ်ကြောင်းတည်း ချန် (အစဉ်လိုက်)
    seen = set()
    deduped = []
    for line in out:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    return "\n".join(deduped)


def _llm_once(base_url, api_key, provider, model, prompt):
    import requests
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["X-Title"] = "Movie Recap Tool"
    # Gemini 3.x flash တွေ free tier မှာ တန်းစီတတ်တယ် (တိုင်းတာချက်အရ
    # 27-148 စက္ကန့်အထိ ကြာတတ်လို့) — 90s timeout နဲ့ အမှားထင်ပြီး
    # ဖြတ်မချမိအောင် Gemini အတွက် 180s ပေး
    timeout = 180 if provider == "gemini" else 90
    r = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={"model": model, "temperature": 0.7,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:120]}")
    return r.json()["choices"][0]["message"]["content"].strip()


def write_script(segments, provider="openrouter", keys=None, model="", lang="my"):
    """Transcript ကို LLM နဲ့ recap script ပြောင်း။
    lang="my" → မြန်မာ script, lang="en" → English script။
    segments = [(start, end, text), ...]
    keys = {"openrouter": "...", "groq": "...", "nvidia": "..."} (ရှိတဲ့ key ပဲ ထည့်)
    ရွေးထားတဲ့ provider/model ကနေ စ; မရရင် (404/5xx) နောက် model၊
    429 ဆို ၈ စက္ကန့် စောင့် တစ်ခါ ပြန်စမ်း၊ provider ကုန်ရင် key ရှိတဲ့
    နောက် provider ကို ဆက်စမ်း။ အောင်ရင် (script, "provider/model") ပြန်ပေး။
    စမ်းခဲ့တဲ့ model တိုင်းရဲ့ ရလဒ်ကို LAST_LLM_ATTEMPTS မှာ မှတ်ထားတယ်
    (app.py က 🔍 section မှာ ပြဖို့)။"""
    import time
    keys = {p: k for p, k in (keys or {}).items() if k}
    if not keys:
        raise RuntimeError("AI key တစ်လုံးမှ မထည့်ရသေးပါ — sidebar မှာ key ထည့်ပါ")
    if provider not in keys:
        provider = next(iter(keys))
    transcript = "\n".join(f"[{s:.0f}s] {t}" for s, e, t in segments)
    prompt = (SCRIPT_PROMPT_EN if lang == "en" else SCRIPT_PROMPT).format(transcript=transcript)
    order = [provider] + [p for p in LLM_PROVIDERS if p != provider and p in keys]
    errors = []
    LAST_LLM_ATTEMPTS.clear()
    for prov in order:
        base_url, defaults = LLM_PROVIDERS[prov]
        models = (([model] if prov == provider and model else [])
                  + [m for m in defaults if m != model])
        for m in models:
            for attempt in range(2):
                try:
                    text = _llm_once(base_url, keys[prov], prov, m, prompt)
                    LAST_LLM_ATTEMPTS.append(
                        {"model": f"{prov}/{m}", "ok": True, "error": ""})
                    return _normalize_script(text), f"{prov}/{m}"
                except RuntimeError as ex:
                    if str(ex).startswith("429") and attempt == 0:
                        time.sleep(8)
                        continue
                    errors.append(f"{prov}/{m} -> {str(ex)[:60]}")
                    LAST_LLM_ATTEMPTS.append(
                        {"model": f"{prov}/{m}", "ok": False,
                         "error": str(ex)[:200]})
                    break
                except Exception as ex:
                    errors.append(f"{prov}/{m} -> {type(ex).__name__}")
                    LAST_LLM_ATTEMPTS.append(
                        {"model": f"{prov}/{m}", "ok": False,
                         "error": f"{type(ex).__name__}: {str(ex)[:150]}"})
                    break
    raise RuntimeError("AI model တွေ အကုန် မရပါ: " + " | ".join(errors))


def translate_script(segments, source_lang, provider="openrouter", keys=None,
                     model="", target="my", style="natural"):
    """Transcript segments -> ဘာသာပြန် စာတန်းထိုး စာသားတွေ။
    segments = [(start, end, text), ...]; source_lang = Whisper language
    code (ဥပမာ "en", "my")။ target: "my" (မြန်မာ) / "en" (English)။
    style: "natural" (ဆီလျော်အောင်, သဘာဝကျ) / "literal" (တိုက်ရိုက်)။
    write_script ရဲ့ provider/model fallback loop အတိုင်း သုံးတယ်
    (recap လမ်းကြောင်း မထိအောင် သပ်သပ် ရေးထားတာ)။
    ပြန်ပေးတာ: ("start | text" စာကြောင်းတွေ, "provider/model")။
    အရေအတွက်/အစဉ်လိုက်က transcript အတိုင်း ဖြစ်ရမယ် (သီချင်းရဲ့
    ထပ်နေတဲ့ စာကြောင်းတွေလည်း အကုန် ပါရမယ် — dedupe မလုပ်ဘူး)။"""
    import re
    import time
    keys = {p: k for p, k in (keys or {}).items() if k}
    if not keys:
        raise RuntimeError("AI key တစ်လုံးမှ မထည့်ရသေးပါ — sidebar မှာ key ထည့်ပါ")
    if provider not in keys:
        provider = next(iter(keys))
    transcript = "\n".join(f"[{s:.0f}s] {t}" for s, e, t in segments)
    style_line = ("Translate naturally and idiomatically — it should read like it was written in the target language, not like a translation."
                  if style == "natural" else
                  "Translate closely and literally, keeping the original wording and word order as much as the target language allows.")
    source_name = {"my": "Burmese", "en": "English"}.get(
        source_lang, "the transcript's language")
    target_name = "Burmese" if target == "my" else "English"
    prompt = TRANSLATE_PROMPT.format(
        source=source_name, target=target_name,
        style_line=style_line, transcript=transcript)
    order = [provider] + [p for p in LLM_PROVIDERS if p != provider and p in keys]
    errors = []
    LAST_LLM_ATTEMPTS.clear()
    for prov in order:
        base_url, defaults = LLM_PROVIDERS[prov]
        models = (([model] if prov == provider and model else [])
                  + [m for m in defaults if m != model])
        for m in models:
            for attempt in range(2):
                try:
                    text = _llm_once(base_url, keys[prov], prov, m, prompt)
                    LAST_LLM_ATTEMPTS.append(
                        {"model": f"{prov}/{m}", "ok": True, "error": ""})
                    lines = []
                    for row in text.splitlines():
                        mm = re.match(r"^\s*(\d+(?:\.\d+)?)\s*\|\s*(.+)$",
                                      row.strip())
                        if mm:
                            lines.append(f"{mm.group(1)} | {mm.group(2).strip()}")
                    if not lines:
                        raise RuntimeError("ဘာသာပြန် output ထဲမှာ စာကြောင်း မတွေ့ပါ")
                    return "\n".join(lines), f"{prov}/{m}"
                except RuntimeError as ex:
                    if str(ex).startswith("429") and attempt == 0:
                        time.sleep(8)
                        continue
                    errors.append(f"{prov}/{m} -> {str(ex)[:60]}")
                    LAST_LLM_ATTEMPTS.append(
                        {"model": f"{prov}/{m}", "ok": False,
                         "error": str(ex)[:200]})
                    break
                except Exception as ex:
                    errors.append(f"{prov}/{m} -> {type(ex).__name__}")
                    LAST_LLM_ATTEMPTS.append(
                        {"model": f"{prov}/{m}", "ok": False,
                         "error": f"{type(ex).__name__}: {str(ex)[:150]}"})
                    break
    raise RuntimeError("AI model တွေ အကုန် မရပါ: " + " | ".join(errors))


def transcript_to_lines(segments):
    """Transcript segments -> 'start | text' စာကြောင်းတွေ။
    ဘာသာမပြန်ပဲ မူရင်းဘာသာအတိုင်း စာတန်းထိုးချင်တဲ့အခါ သုံးတယ်
    (ဥပမာ မြန်မာစကားပြော movie ကို မြန်မာ စာတန်းထိုးတာ) —
    AI မလို, transcript စာသားအတိုင်း ယူရုံပဲ။"""
    out = []
    for s, e, t in segments:
        sec = int(s) if s == int(s) else s
        out.append(f"{sec} | {t}")
    return "\n".join(out)


def translation_timings(parsed, segments):
    """ဘာသာပြန် script (parsed = [(start, text)]) + မူရင်း transcript
    segments ([(start, end, text)]) -> [(start, dur, text)]။
    စာကြောင်းတိုင်းရဲ့ အချိန်ကို အနီးဆုံး transcript segment က ယူတယ်
    (3 စက္ကန့်အတွင်း ရှာမတွေ့ရင် dur = 3.0)။ စာတန်းထိုးရဲ့
    အချိန်က မူရင်း ပြောဆိုချိန်နဲ့ ကိုက်ရမယ် (narration လို နေရာချတာ မဟုတ်)။"""
    timed = []
    for start, text in parsed:
        best_dur, best_dt = 3.0, 1e9
        for s, e, _t in segments:
            dt = abs(s - float(start))
            if dt < best_dt:
                best_dt = dt
                if dt <= 3.0:
                    best_dur = max(0.5, float(e) - float(s))
        timed.append((float(start), best_dur, text))
    timed.sort(key=lambda x: x[0])
    return timed
