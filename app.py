#!/usr/bin/env python3
"""Movie Recap Tool - Streamlit web app
ဖွင့်နည်း:  streamlit run app.py
ပြီးရင် browser မှာ http://localhost:8501 ပွင့်လာမယ်။
"""
import os
import streamlit as st

import pipeline

st.set_page_config(page_title="Movie Recap Tool", page_icon="🎬")
st.title("🎬 Movie Recap Tool")
st.caption("ဗီဒီယိုတင် → transcript → script ပြင် → အသံထည့် → ဗီဒီယိုအပြီး ဒေါင်းလုပ်")

WORKDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_output")
os.makedirs(WORKDIR, exist_ok=True)


def _secret(name):
    """Streamlit Secrets (Cloud -> Settings -> Secrets) ထဲက key ကို ယူ။
    Secrets မရှိရင် / local မှာ run ရင် အလွတ် ပြန်ပေးတယ် — app ပျက်မသွားဘူး။"""
    try:
        return str(st.secrets[name])
    except Exception:
        return ""

# ---------- Sidebar: TTS ရွေးချယ်မှု ----------
st.sidebar.header("🔊 အသံ (TTS) ရွေးမယ်")
engine = st.sidebar.selectbox(
    "TTS engine",
    ["gtts", "edgetts", "elevenlabs"],
    index=1,
    format_func=lambda e: {
        "gtts": "gTTS (အခမဲ့၊ အသံစက်ဆန်)",
        "edgetts": "Edge TTS (မြန်မာ + English၊ အခမဲ့)",
        "elevenlabs": "ElevenLabs (API key လို၊ အသံကောင်း)",
    }[e],
)
api_key, voice_id = "", ""
if engine == "edgetts":
    voice_id = st.sidebar.selectbox(
        "အသံ ရွေးပါ",
        ["my-MM-ThihaNeural", "my-MM-NilarNeural",
         "en-US-AriaNeural", "en-US-GuyNeural"],
        format_func=lambda v: {
            "my-MM-ThihaNeural": "Thiha (မြန်မာ, အမျိုးသား)",
            "my-MM-NilarNeural": "Nilar (မြန်မာ, အမျိုးသမီး)",
            "en-US-AriaNeural": "Aria (English, အမျိုးသမီး)",
            "en-US-GuyNeural": "Guy (English, အမျိုးသား)",
        }[v],
    )
if engine == "elevenlabs":
    api_key = st.sidebar.text_input("ElevenLabs API key", type="password",
                                    value=_secret("elevenlabs_api_key"),
                                    help="elevenlabs.io → Profile → API Keys")
    voice_id = st.sidebar.text_input(
        "Voice ID", value="21m00Tcm4TlvDq8ikWAM",
        help="ElevenLabs Voices ထဲက ကြိုက်တဲ့ အသံရဲ့ ID")

# ---------- Sidebar: Script AI (provider ရွေးနိုင်, auto-fallback) ----------
st.sidebar.header("🤖 Script AI")
st.sidebar.caption("Transcript ကနေ ဟာသ script အလိုအလျောက် ရေးဖို့ — "
                   "provider/model တစ်ခု မရရင် နောက်တစ်ခု အလိုအလျောက် ပြောင်းစမ်းပေးမယ်")
ai_provider = st.sidebar.selectbox(
    "AI provider",
    ["gemini", "openrouter", "groq", "nvidia"],
    format_func=lambda p: {
        "gemini": "Gemini (မြန်မာအကောင်း)",
        "openrouter": "OpenRouter (အခမဲ့ model အများ)",
        "groq": "Groq (မြန်၊ အခမဲ့)",
        "nvidia": "NVIDIA (အခမဲ့)",
    }[p],
)
ai_keys = {
    "gemini": st.sidebar.text_input(
        "Gemini API key", type="password", value=_secret("gemini_api_key"),
        help="aistudio.google.com → Get API Key"),
    "openrouter": st.sidebar.text_input(
        "OpenRouter API key", type="password", value=_secret("openrouter_api_key"),
        help="openrouter.ai → Keys → Create Key"),
    "groq": st.sidebar.text_input(
        "Groq API key", type="password", value=_secret("groq_api_key"),
        help="groq.com → Sign in → API Keys → Create API Key"),
    "nvidia": st.sidebar.text_input(
        "NVIDIA API key", type="password", value=_secret("nvidia_api_key"),
        help="build.nvidia.com → model တစ်ခုခု → Get API Key"),
}
if any(_secret(k) for k in ("gemini_api_key", "openrouter_api_key", "groq_api_key",
                            "nvidia_api_key", "elevenlabs_api_key")):
    st.sidebar.caption("🔑 Secrets ထဲက key တွေ့ပြီ — reboot/sleep ဖြစ်လည်း ပြန်ထည့်စရာ မလိုတော့ဘူး")
MODEL_LABELS = {
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-flash-latest": "Gemini Flash (နောက်ဆုံး)",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
    "google/gemma-4-31b-it:free": "Gemma 4 31B (အခမဲ့)",
    "google/gemma-4-26b-a4b-it:free": "Gemma 4 26B (အခမဲ့)",
    "openrouter/free": "အခမဲ့ ရတဲ့ model အလိုအလျောက်",
    "llama-3.3-70b-versatile": "Llama 3.3 70B",
    "openai/gpt-oss-120b": "GPT-OSS 120B",
    "llama-3.1-8b-instant": "Llama 3.1 8B (မြန်)",
    "nvidia/nemotron-3-super-120b-a12b": "Nemotron 120B",
    "google/gemma-4-31b-it": "Gemma 4 31B",
    "meta/llama-3.3-70b-instruct": "Llama 3.3 70B",
}
ai_model = st.sidebar.selectbox(
    "AI model",
    pipeline.LLM_PROVIDERS[ai_provider][1],
    format_func=lambda m: MODEL_LABELS.get(m, m),
)
ai_custom = st.sidebar.text_input(
    "Model ID ကိုယ်တိုင်ထည့် (ချန်ထားလို့ရ)",
    help="ဖြည့်ရင် အပေါ်က ရွေးထားတဲ့ model အစား ဒါကို အရင် စမ်းမယ်")
if ai_custom.strip():
    ai_model = ai_custom.strip()

# ---------- Sidebar: Transcript engine ----------
st.sidebar.header("📝 Transcript engine")
stt_engine = st.sidebar.selectbox(
    "Transcript ထုတ်နည်း",
    ["groq", "local"],
    format_func=lambda e: {
        "groq": "Groq Whisper large-v3 (ပိုမှန်၊ မြန်၊ key လို)",
        "local": "Local Whisper base (key မလို၊ နှေးနိုင်)",
    }[e],
    help="Groq မရရင် Local ကို အလိုအလျောက် ပြန်ပြောင်းစမ်းပေးမယ်",
)

# ---------- အဆင့် ၁: ဗီဒီယို upload ----------
uploaded = st.file_uploader("ဗီဒီယို ဖိုင် တင်ပါ (mp4)", type=["mp4", "mov", "mkv"])
video_path = None
if uploaded:
    video_path = os.path.join(WORKDIR, "input.mp4")
    with open(video_path, "wb") as f:
        f.write(uploaded.getbuffer())
    st.video(video_path)
    st.success(f"ဗီဒီယို ရပြီ — အရှည် {pipeline.probe_duration(video_path):.1f} စက္ကန့်")

# ---------- အဆင့် ၂: Transcript ----------
if video_path:
    # ဘာသာ ရွေးတာကို Transcript ခလုတ်နားမှာပဲ ထားတယ် — sidebar ထဲမှာ
    # ဝှက်နေရင် ဖုန်းမှာ သတိမထားမိလို့ (သီချင်းမှာ Whisper က ဘာသာစကား
    # မှားသိပြီး Latin/ကိုရီးယားစာနဲ့ ထွက်တတ်လို့ မြန်မာသီချင်းဆို မြန်မာ ရွေးပါ)
    stt_lang_label = st.selectbox(
        "Transcript ဘာသာ",
        ["အလိုအလျောက်", "မြန်မာ", "English"],
        help="မြန်မာသီချင်းဆို မြန်မာ ကို ရွေးပါ (မှားတဲ့ ဘာသာ ရွေးမိရင် ပိုမှားနိုင်တယ်)",
    )
    stt_lang = {"အလိုအလျောက်": None, "မြန်မာ": "my", "English": "en"}[stt_lang_label]
if video_path and st.button("📝 Transcript ထုတ်မယ် (Whisper)"):
    audio = pipeline.extract_audio(video_path, os.path.join(WORKDIR, "audio.wav"))
    segs, lang = None, None
    if stt_engine == "groq":
        gkey = ai_keys["groq"].strip()
        if not gkey:
            st.error("Groq Whisper သုံးမယ်ဆို sidebar မှာ Groq API key အရင် ထည့်ပါ (ဒါမှမဟုတ် Local ကို ရွေးပါ)")
            st.stop()
        try:
            with st.spinner("Groq Whisper နဲ့ စာသားပြောင်းနေတယ်..."):
                segs, lang = pipeline.transcribe_groq(audio, gkey, language=stt_lang)
        except Exception as ex:
            st.warning(f"Groq Whisper မရ ({str(ex)[:100]}) — Local Whisper နဲ့ ပြန်စမ်းနေတယ်")
    if segs is None:
        with st.spinner("Local Whisper နဲ့ စာသားပြောင်းနေတယ်... (base model, ခဏကြာနိုင်)"):
            segs, lang = pipeline.transcribe(audio, language=stt_lang)
    st.session_state["transcript"] = segs
    st.session_state["transcript_lang"] = lang
    st.success(f"ပြီးပြီ — ဘာသာစကား: {lang}, {len(segs)} ပိုဒ်")

if "transcript" in st.session_state:
    st.subheader("Transcript (မူရင်း စကားပြော)")
    for s, e, t in st.session_state["transcript"]:
        st.text(f"[{s:05.1f} - {e:05.1f}] {t}")
    col_my, col_en = st.columns(2)
    with col_my:
        gen_my = st.button("🇲🇲 မြန်မာ Script (AI)")
    with col_en:
        gen_en = st.button("🇬🇧 English Script (AI)")
    if gen_my or gen_en:
        lang = "my" if gen_my else "en"
        lang_name = "မြန်မာ" if gen_my else "English"
        keys = {p: k.strip() for p, k in ai_keys.items() if k.strip()}
        if not keys:
            st.error("Sidebar မှာ AI key တစ်ခု ထည့်ပါ (OpenRouter / Groq / NVIDIA တစ်ခုခု)")
        else:
            try:
                with st.spinner("AI က script ရေးနေတယ်... (model တစ်ခု မရရင် နောက်တစ်ခု စမ်းနေမယ်)"):
                    script_out, used_model = pipeline.write_script(
                        st.session_state["transcript"],
                        provider=ai_provider, keys=keys, model=ai_model,
                        lang=lang)
                    st.session_state["script_box"] = script_out
                st.success(f"Script ရပြီ — {lang_name} (သုံးတဲ့ model: {used_model}) (အောက်မှာ ပြင်လို့ရတယ်)")
            except Exception as ex:
                st.error(f"Script မရပါ: {ex}")
            attempts = getattr(pipeline, "LAST_LLM_ATTEMPTS", [])
            if attempts:
                with st.expander("🔍 Model စမ်းသပ်ချက် (ဘယ် model ဘာဖြစ်လဲ)", expanded=True):
                    for a in attempts:
                        if a["ok"]:
                            st.write(f"✅ {a['model']}")
                        else:
                            st.write(f"❌ {a['model']} — {a['error']}")

# ---------- ဘာသာပြန် စာတန်းထိုး (အသံမပါ) ----------
if "transcript" in st.session_state:
    st.subheader("🌐 ဘာသာပြန် စာတန်းထိုး (အသံမပါ)")
    st.caption("သီချင်း / ဇာတ်ကားအတို ကို မူရင်းအသံအတိုင်း ဘာသာပြန်စာတန်းထိုးမယ်, ဒါမှမဟုတ် မူရင်းဘာသာအတိုင်း စာတန်းထိုးမယ် — နောက်ခံစကားပြော မပါဘူး")
    tr_target_label = st.selectbox(
        "စာတန်း ဘာသာ",
        ["မြန်မာ", "English", "မူရင်းအတိုင်း (ဘာသာမပြန်)"],
        help="မူရင်းဘာသာက transcript မှာ သိပြီးသား — ပြန်မယ့် ဘာသာ, ဒါမှမဟုတ် မူရင်းအတိုင်း (မြန်မာ movie ကို မြန်မာ စာတန်းထိုးတာမျိုး)")
    tr_target = {"မြန်မာ": "my", "English": "en",
                 "မူရင်းအတိုင်း (ဘာသာမပြန်)": "same"}[tr_target_label]
    if tr_target == "same":
        tr_style = "natural"
    else:
        tr_style_label = st.selectbox(
            "ဘာသာပြန်ပုံစံ",
            ["သဘာဝကျ (ဆီလျော်အောင်)", "တိုက်ရိုက်"],
            help="သဘာဝကျ = ဖတ်လို့ကောင်း, သီချင်းဆို ဆိုလို့ကောင်း; တိုက်ရိုက် = မူရင်းစကားလုံး အတိုင်း")
        tr_style = {"သဘာဝကျ (ဆီလျော်အောင်)": "natural", "တိုက်ရိုက်": "literal"}[tr_style_label]
    tr_btn = ("📝 Transcript ကို စာတန်းအဖြစ် ယူမယ်"
              if tr_target == "same" else "🌐 ဘာသာပြန်မယ် (AI)")
    if st.button(tr_btn):
        if tr_target == "same":
            # ဘာသာမပြန် — transcript စာသားအတိုင်း စာတန်းထိုး (AI မလို)
            st.session_state["trans_box"] = pipeline.transcript_to_lines(
                st.session_state["transcript"])
            st.success("Transcript ကို စာတန်းအဖြစ် ယူပြီးပြီ (အောက်မှာ ပြင်လို့ရတယ် — Whisper မှားနေရင် ဒီမှာ ပြင်ပါ)")
        else:
            keys = {p: k.strip() for p, k in ai_keys.items() if k.strip()}
            if not keys:
                st.error("Sidebar မှာ AI key တစ်ခု ထည့်ပါ (OpenRouter / Groq / NVIDIA တစ်ခုခု)")
            else:
                try:
                    with st.spinner("AI က ဘာသာပြန်နေတယ်..."):
                        trans_out, used_model = pipeline.translate_script(
                            st.session_state["transcript"],
                            st.session_state.get("transcript_lang", "?"),
                            provider=ai_provider, keys=keys, model=ai_model,
                            target=tr_target, style=tr_style)
                        st.session_state["trans_box"] = trans_out
                    st.success(f"ဘာသာပြန် ရပြီ (သုံးတဲ့ model: {used_model}) (အောက်မှာ ပြင်လို့ရတယ်)")
                except Exception as ex:
                    st.error(f"ဘာသာပြန် မရပါ: {ex}")

# ---------- အဆင့် ၃: Script ပြင်ရေး ----------
st.subheader("✍️ Recap Script")
st.caption("တစ်ကြောင်းကို `စမယ့်စက္ကန့် | စာသား` ပုံစံနဲ့ ရေးပါ။ "
           "စာတိုတိုထားမှ အသံက ဗီဒီယိုနဲ့ ကိုက်မယ် (၁ စက္ကန့် ≈ မြန်မာစကားလုံး ၂ လုံးနှုန်း)")
if "script_box" not in st.session_state:
    st.session_state["script_box"] = ""
script_text = st.text_area(
    "Script", height=180, key="script_box",
    placeholder="🤖 AI ခလုတ် နှိပ်ရင် ဒီမှာ script ပေါ်လာမယ် — ဒါမှမဟုတ် ကိုယ်တိုင် `0 | စာသား` ပုံစံနဲ့ ရေးထည့်လို့လည်း ရတယ်")
if "trans_box" not in st.session_state:
    st.session_state["trans_box"] = ""
trans_text = st.text_area(
    "ဘာသာပြန် Script", height=180, key="trans_box",
    placeholder="🌐 ဘာသာပြန် ခလုတ် နှိပ်ရင် ဒီမှာ ဘာသာပြန် စာကြောင်းတွေ ပေါ်လာမယ် — `စမယ့်စက္ကန့် | စာသား` ပုံစံ")


def _clean_script_text(t):
    """Script စာသားထဲက ကွင်းခတ် အချိန်အမှတ်တွေ ([6s] [8s] ...) ကို
    နေရာမရွေး ဖျက် — TTS ဖတ်တာ/စာတန်းထိုးမှာ ပေါ်မလာအောင်။"""
    import re
    t = re.sub(r"\[\d+(?:\.\d+)?s?\]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_script(text):
    lines = []
    for row in text.strip().splitlines():
        row = row.strip()
        if not row:
            continue
        if "|" in row:
            start, body = row.split("|", 1)
            try:
                start = float(start.strip())
            except ValueError:
                continue
            body = _clean_script_text(body)
            if body:
                lines.append((start, body))
            continue
        # | မပါတဲ့ ကွင်းခတ်/mm:ss ပုံစံတွေလည်း လက်ခံ
        # (transcript/AI အထွက်ကို အတိုင်း ကူးထည့်ထားတဲ့ script တွေ အတွက်)
        import re
        m = (re.match(r"^\[(\d+(?:\.\d+)?)\s*s?\]\s*(.+)$", row)
             or re.match(r"^(\d+):(\d{2})\s+(.+)$", row))
        if m:
            if len(m.groups()) == 2:
                body = _clean_script_text(m.group(2))
                if body:
                    lines.append((float(m.group(1)), body))
            else:
                body = _clean_script_text(m.group(3))
                if body:
                    lines.append((int(m.group(1)) * 60 + int(m.group(2)), body))
    # ထပ်နေတဲ့ (အချိန်, စာသား) အတွဲတွေ တစ်ကြောင်းတည်း ချန် (အစဉ်လိုက်) —
    # AI က block လိုက် ထပ်ထုတ်ရင် narration ၂ ခါ ထပ်ပြီး ဗီဒီယိုနဲ့ မကိုက်ဘဲ
    # အသံ အမြန်တင်ရတဲ့ ပြဿနာ မဖြစ်အောင်
    seen = set()
    deduped = []
    for item in lines:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


# ---------- အဆင့် ၄: ဗီဒီယို ထုတ် ----------
mode_label = st.selectbox(
    "ဗီဒီယို မုဒ်",
    ["🎬 Recap (နောက်ခံစကားပြော)", "🌐 ဘာသာပြန် (အသံမပါ, မူရင်းအသံ 100%)"],
    help="Recap = နောက်ခံစကားပြော + စာတန်း; ဘာသာပြန် = မူရင်းအသံအတိုင်း + ဘာသာပြန် စာတန်းထိုး")
mode_translate = mode_label.startswith("🌐")
add_subs = st.checkbox(
    "🔤 စာတန်းထိုး (subtitles) ဗီဒီယိုထဲ ထည့်မယ်",
    value=True,
    help="TikTok/Reels အတွက် အဝါရောင် စာတန်းထိုး — SRT ဖိုင်ကိုတော့ အမြဲ ထုတ်ပေးမယ်")
sub_size_label = st.selectbox(
    "စာတန်းအရွယ်",
    ["အလတ်", "သေး", "ကြီး"],
    help="အလတ် (64) က ပုံမှန် — ဖုန်းကြည့်ရင် သေးနေရင် ကြီး (88) ရွေးပါ")
sub_size = {"သေး": 44, "အလတ်": 64, "ကြီး": 88}[sub_size_label]
orig_label = st.selectbox(
    "🎧 မူရင်းအသံ",
    ["မထည့်", "10%", "25%", "50%", "100%"],
    help="narration နဲ့ ရောမယ့် မူရင်းအသံ အသံအတိုးအကျယ် — မထည့်ရင် narration သီးသန့်ပဲ ထွက်မယ်")
orig_volume = {"မထည့်": 0.0, "10%": 0.10, "25%": 0.25, "50%": 0.50, "100%": 1.0}[orig_label]
sub_pos_label = st.selectbox(
    "စာတန်းနေရာ",
    ["အောက်", "အလယ်", "အပေါ်"],
    help="စာတန်း ဗီဒီယိုရဲ့ ဘယ်နေရာမှာ ပေါ်မလဲ — မူရင်းစာသား blur လုပ်ထားတဲ့နေရာနဲ့ မထပ်အောင် ရွေးပါ")
sub_pos = {"အောက်": "bottom", "အလယ်": "middle", "အပေါ်": "top"}[sub_pos_label]
blur_on = st.checkbox("မူရင်းစာသား ဖျောက် (blur)")
if blur_on:
    blur_y = st.slider(
        "Blur band နေရာ (အပေါ်က %)",
        0, 80, 40, step=5,
        help="Band က အမြင့် 20% ရှိတယ် — 0 = အပေါ်ဆုံး, 40 = အလယ်, 60 = အောက်လယ်, 80 = အောက်ဆုံး. မူရင်း စာတန်းရှိတဲ့နေရာကို ရွှေ့ထားပါ")
    blur_band = blur_y / 100.0
else:
    blur_band = "none"
zoom_label = st.selectbox(
    "🔍 Zoom",
    ["မလုပ်", "အထဲ (zoom in)", "အပြင် (zoom out)"],
    help="အထဲ = 10% ချဲ့ (အနားဖြတ်), အပြင် = 10% သေး + အနက်ကွက်")
zoom = {"မလုပ်": "none", "အထဲ (zoom in)": "in", "အပြင် (zoom out)": "out"}[zoom_label]
pip = st.checkbox(
    "🖼️ Picture-in-picture",
    value=False,
    help="ဗီဒီယိုကို 85% သေးပြီး မှုန်ဝါးထားတဲ့ နောက်ခံပေါ် တင်မယ်")
effect_label = st.selectbox(
    "✨ Effect",
    ["မလုပ်", "မှန်ပြောင်းပြန် (mirror)", "အဖြူအမည်း"],
    help="မူရင်းနဲ့ ပုံစံ ကွဲအောင် — Content ID တိုက်မိတာ လျှော့ဖို့")
effect = {"မလုပ်": "none", "မှန်ပြောင်းပြန် (mirror)": "mirror", "အဖြူအမည်း": "gray"}[effect_label]
logo_file = st.file_uploader(
    "🔖 Logo PNG",
    type=["png"],
    help="ဗီဒီယိုပေါ်မှာ တင်မယ် (အရွယ် 80px) — အကြည် (transparent) PNG ဆို အလှဆုံး, မရှိရင် ကျော်လို့ရတယ်")
logo_pos_label = st.selectbox(
    "🔖 Logo နေရာ",
    ["အပေါ်-ညာ", "အပေါ်-ဘယ်", "အောက်-ညာ", "အောက်-ဘယ်"],
    help="Logo ကို ဗီဒီယိုရဲ့ ဘယ်ထောင့်မှာ ထားမလဲ")
logo_pos = {"အပေါ်-ညာ": "top-right", "အပေါ်-ဘယ်": "top-left",
            "အောက်-ညာ": "bottom-right", "အောက်-ဘယ်": "bottom-left"}[logo_pos_label]
if video_path and st.button("🎬 ဗီဒီယို ထုတ်မယ်", type="primary"):
    timed = None
    if mode_translate:
        trans_script = parse_script(trans_text)
        if not trans_script:
            st.error("ဘာသာပြန် Script မရှိသေးဘူး — အရင် ဘာသာပြန်/စာတန်းယူ ခလုတ် နှိပ်ပါ, ဒါမှမဟုတ် box ထဲ ကိုယ်တိုင် ရေးထည့်ပါ")
            st.stop()
        if "transcript" not in st.session_state:
            st.error("Transcript မရှိသေးဘူး — အရင် Transcript ထုတ်ပါ")
            st.stop()
        timed = pipeline.translation_timings(trans_script, st.session_state["transcript"])
    else:
        if engine == "elevenlabs" and not api_key:
            st.error("ElevenLabs သုံးမယ်ဆို sidebar မှာ API key အရင် ထည့်ပါ")
            st.stop()
        script = parse_script(script_text)
        if not script:
            st.error("Script မရှိသေးဘူး — အရင် AI နဲ့ ရေးခိုင်းပါ, ဒါမှမဟုတ် box ထဲ ကိုယ်တိုင် ရေးထည့်ပါ")
            st.stop()
    logo_path = None
    if logo_file is not None:
        logo_path = os.path.join(WORKDIR, "logo.png")
        with open(logo_path, "wb") as f:
            f.write(logo_file.getbuffer())
    status = st.empty()
    if mode_translate:
        with st.spinner("ဘာသာပြန် ဗီဒီယို ဆက်နေတယ်..."):
            final, fit_rate = pipeline.build_video(video_path, [], WORKDIR,
                                                    log=lambda m: status.write(m),
                                                    orig_volume=1.0,
                                                    blur_band=blur_band,
                                                    zoom=zoom, pip=pip,
                                                    effect=effect,
                                                    logo_path=logo_path,
                                                    logo_pos=logo_pos)
    else:
        with st.spinner("TTS + ဗီဒီယို ဆက်နေတယ်... (မိနစ်ပိုင်း ကြာနိုင်တယ်)"):
            files = pipeline.tts_all(script, engine, WORKDIR,
                                     api_key=api_key, voice_id=voice_id,
                                     log=lambda m: status.write(m))
            final, fit_rate = pipeline.build_video(video_path, files, WORKDIR,
                                                    log=lambda m: status.write(m),
                                                    orig_volume=orig_volume,
                                                    blur_band=blur_band,
                                                    zoom=zoom, pip=pip,
                                                    effect=effect,
                                                    logo_path=logo_path,
                                                    logo_pos=logo_pos)
    st.success("ပြီးပါပြီ! 🎉")
    st.video(final)
    with open(final, "rb") as f:
        st.download_button("⬇️ Final video ဒေါင်းလုပ်", f,
                           file_name="final_recap.mp4", mime="video/mp4")

    # ---------- စာတန်းထိုး: SRT ထုတ် + ဗီဒီယိုထဲ ထည့် ----------
    if timed is None:
        placed = pipeline.place_timings(files)  # [(path, start, dur)]
        timed = [(start, dur, text)
                 for (path, start, dur), (target, text) in zip(placed, script)]
        if fit_rate > 1.0:
            # narration ကို atempo နဲ့ မြန်ထားရင် စာတန်းလည်း အတူတူ မြန်မှ
            # အသံနဲ့ ကိုက်မယ် — မဟုတ်ရင် စာတန်း နောက်ကျကျန်ခဲ့မယ်
            timed = [(s / fit_rate, d / fit_rate, t) for (s, d, t) in timed]
    srt_path = os.path.join(WORKDIR, "recap.srt")
    with st.spinner("SRT စာတန်းဖိုင် ထုတ်နေတယ်..."):
        pipeline.write_srt(timed, srt_path)
    with open(srt_path, "rb") as f:
        st.download_button("⬇️ SRT စာတန်းဖိုင် ဒေါင်းလုပ်", f,
                           file_name="recap.srt", mime="text/plain")
    if add_subs:
        with st.spinner("စာတန်းထိုး ဗီဒီယိုထဲ ထည့်နေတယ်... (ပထမတစ်ခါ ဖောင့် ဒေါင်းလုဒ်မယ်)"):
            font = pipeline.ensure_myanmar_font(
                WORKDIR, log=lambda m: status.write(m))
            if font:
                subbed = os.path.join(WORKDIR, "final_recap_subs.mp4")
                pipeline.burn_subtitles(final, timed, font, subbed,
                                        log=lambda m: status.write(m),
                                        font_size=sub_size,
                                        position=sub_pos)
                st.success("စာတန်းထိုး ထည့်ပြီးပြီ! 🎉")
                st.video(subbed)
                with open(subbed, "rb") as f:
                    st.download_button("⬇️ စာတန်းထိုးဗီဒီယို ဒေါင်းလုပ်", f,
                                       file_name="final_recap_subs.mp4",
                                       mime="video/mp4")
            else:
                st.warning("မြန်မာဖောင့် ဒေါင်းလုဒ် မရလို့ စာတန်းထိုး မထည့်နိုင်ပါ — "
                           "SRT ဖိုင်ကိုတော့ အပေါ်က ဒေါင်းလုဒ်ထားနိုင်ပါတယ်")
