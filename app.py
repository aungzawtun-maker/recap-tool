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
        "edgetts": "Edge TTS (မြန်မာ Thiha/Nilar၊ အခမဲ့)",
        "elevenlabs": "ElevenLabs (API key လို၊ အသံကောင်း)",
    }[e],
)
api_key, voice_id = "", ""
if engine == "edgetts":
    voice_id = st.sidebar.selectbox(
        "အသံ ရွေးပါ",
        ["my-MM-ThihaNeural", "my-MM-NilarNeural"],
        format_func=lambda v: "Thiha (အမျိုးသား)" if "Thiha" in v else "Nilar (အမျိုးသမီး)",
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
                segs, lang = pipeline.transcribe_groq(audio, gkey)
        except Exception as ex:
            st.warning(f"Groq Whisper မရ ({str(ex)[:100]}) — Local Whisper နဲ့ ပြန်စမ်းနေတယ်")
    if segs is None:
        with st.spinner("Local Whisper နဲ့ စာသားပြောင်းနေတယ်... (base model, ခဏကြာနိုင်)"):
            segs, lang = pipeline.transcribe(audio)
    st.session_state["transcript"] = segs
    st.success(f"ပြီးပြီ — ဘာသာစကား: {lang}, {len(segs)} ပိုဒ်")

if "transcript" in st.session_state:
    st.subheader("Transcript (မူရင်း စကားပြော)")
    for s, e, t in st.session_state["transcript"]:
        st.text(f"[{s:05.1f} - {e:05.1f}] {t}")
    if st.button("🤖 Script အလိုအလျောက် ရေး (AI)"):
        keys = {p: k.strip() for p, k in ai_keys.items() if k.strip()}
        if not keys:
            st.error("Sidebar မှာ AI key တစ်ခု ထည့်ပါ (OpenRouter / Groq / NVIDIA တစ်ခုခု)")
        else:
            try:
                with st.spinner("AI က script ရေးနေတယ်... (model တစ်ခု မရရင် နောက်တစ်ခု စမ်းနေမယ်)"):
                    script_out, used_model = pipeline.write_script(
                        st.session_state["transcript"],
                        provider=ai_provider, keys=keys, model=ai_model)
                    st.session_state["script_box"] = script_out
                st.success(f"Script ရပြီ — သုံးတဲ့ model: {used_model} (အောက်မှာ ပြင်လို့ရတယ်)")
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

# ---------- အဆင့် ၃: Script ပြင်ရေး ----------
st.subheader("✍️ Recap Script")
st.caption("တစ်ကြောင်းကို `စမယ့်စက္ကန့် | စာသား` ပုံစံနဲ့ ရေးပါ။ "
           "စာတိုတိုထားမှ အသံက ဗီဒီယိုနဲ့ ကိုက်မယ် (၁ စက္ကန့် ≈ မြန်မာစကားလုံး ၂ လုံးနှုန်း)")
if "script_box" not in st.session_state:
    st.session_state["script_box"] = ""
script_text = st.text_area(
    "Script", height=180, key="script_box",
    placeholder="🤖 AI ခလုတ် နှိပ်ရင် ဒီမှာ script ပေါ်လာမယ် — ဒါမှမဟုတ် ကိုယ်တိုင် `0 | စာသား` ပုံစံနဲ့ ရေးထည့်လို့လည်း ရတယ်")


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
add_subs = st.checkbox(
    "🔤 စာတန်းထိုး (subtitles) ဗီဒီယိုထဲ ထည့်မယ်",
    value=True,
    help="TikTok/Reels အတွက် အဝါရောင် စာတန်းထိုး — SRT ဖိုင်ကိုတော့ အမြဲ ထုတ်ပေးမယ်")
sub_size_label = st.selectbox(
    "စာတန်းအရွယ်",
    ["အလတ်", "သေး", "ကြီး"],
    help="အလတ် (64) က ပုံမှန် — ဖုန်းကြည့်ရင် သေးနေရင် ကြီး (88) ရွေးပါ")
sub_size = {"သေး": 44, "အလတ်": 64, "ကြီး": 88}[sub_size_label]
keep_orig = st.checkbox(
    "🎧 မူရင်းအသံ နည်းနည်းထားမယ် (12%)",
    value=False,
    help="မနှိပ်ရင် narration သီးသန့်ပဲ ထွက်မယ် — မူရင်းဗီဒီယိုထဲက လူပြောသံတွေ မပါတော့ဘူး")
if video_path and st.button("🎬 ဗီဒီယို ထုတ်မယ်", type="primary"):
    if engine == "elevenlabs" and not api_key:
        st.error("ElevenLabs သုံးမယ်ဆို sidebar မှာ API key အရင် ထည့်ပါ")
        st.stop()
    script = parse_script(script_text)
    if not script:
        st.error("Script မရှိသေးဘူး — အရင် AI နဲ့ ရေးခိုင်းပါ, ဒါမှမဟုတ် box ထဲ ကိုယ်တိုင် ရေးထည့်ပါ")
        st.stop()
    status = st.empty()
    with st.spinner("TTS + ဗီဒီယို ဆက်နေတယ်... (မိနစ်ပိုင်း ကြာနိုင်တယ်)"):
        files = pipeline.tts_all(script, engine, WORKDIR,
                                 api_key=api_key, voice_id=voice_id,
                                 log=lambda m: status.write(m))
        final = pipeline.build_video(video_path, files, WORKDIR,
                                      log=lambda m: status.write(m),
                                      keep_orig=keep_orig)
    st.success("ပြီးပါပြီ! 🎉")
    st.video(final)
    with open(final, "rb") as f:
        st.download_button("⬇️ Final video ဒေါင်းလုပ်", f,
                           file_name="final_recap.mp4", mime="video/mp4")

    # ---------- စာတန်းထိုး: SRT ထုတ် + ဗီဒီယိုထဲ ထည့် ----------
    placed = pipeline.place_timings(files)  # [(path, start, dur)]
    timed = [(start, dur, text)
             for (path, start, dur), (target, text) in zip(placed, script)]
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
                                        font_size=sub_size)
                st.success("စာတန်းထိုး ထည့်ပြီးပြီ! 🎉")
                st.video(subbed)
                with open(subbed, "rb") as f:
                    st.download_button("⬇️ စာတန်းထိုးဗီဒီယို ဒေါင်းလုပ်", f,
                                       file_name="final_recap_subs.mp4",
                                       mime="video/mp4")
            else:
                st.warning("မြန်မာဖောင့် ဒေါင်းလုဒ် မရလို့ စာတန်းထိုး မထည့်နိုင်ပါ — "
                           "SRT ဖိုင်ကိုတော့ အပေါ်က ဒေါင်းလုဒ်ထားနိုင်ပါတယ်")
