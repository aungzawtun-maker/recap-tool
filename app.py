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

# ---------- Sidebar: TTS ရွေးချယ်မှု ----------
st.sidebar.header("🔊 အသံ (TTS) ရွေးမယ်")
engine = st.sidebar.selectbox(
    "TTS engine",
    ["gtts", "edgetts", "elevenlabs"],
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
                                    help="elevenlabs.io → Profile → API Keys")
    voice_id = st.sidebar.text_input(
        "Voice ID", value="21m00Tcm4TlvDq8ikWAM",
        help="ElevenLabs Voices ထဲက ကြိုက်တဲ့ အသံရဲ့ ID")

# ---------- Sidebar: Script AI (OpenRouter) ----------
st.sidebar.header("🤖 Script AI")
st.sidebar.caption("Transcript ကနေ ဟာသ script အလိုအလျောက် ရေးဖို့")
or_key = st.sidebar.text_input("OpenRouter API key", type="password",
                               help="openrouter.ai → Keys → Create Key")
or_model = st.sidebar.selectbox(
    "AI model",
    ["google/gemma-4-31b-it:free",
     "google/gemma-4-26b-a4b-it:free",
     "nvidia/nemotron-3-super-120b-a12b:free"],
    format_func=lambda m: ("Gemma 4 31B (အခမဲ့)" if "31b" in m
                           else "Gemma 4 26B (အခမဲ့)" if "gemma" in m
                           else "Nemotron 120B (အခမဲ့)"),
)
or_custom = st.sidebar.text_input(
    "Model ID ကိုယ်တိုင်ထည့် (ချန်ထားလို့ရ)",
    help="openrouter.ai/models ထဲက ကြိုက်တဲ့ model ရဲ့ ID — ဖြည့်ရင် အပေါ်က ရွေးတာကို ကျော်မယ်")
if or_custom.strip():
    or_model = or_custom.strip()

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
    with st.spinner("အသံထုတ် + စာသားပြောင်းနေတယ်..."):
        audio = pipeline.extract_audio(video_path, os.path.join(WORKDIR, "audio.wav"))
        segs, lang = pipeline.transcribe(audio)
        st.session_state["transcript"] = segs
    st.success(f"ပြီးပြီ — ဘာသာစကား: {lang}, {len(segs)} ပိုဒ်")

if "transcript" in st.session_state:
    st.subheader("Transcript (မူရင်း စကားပြော)")
    for s, e, t in st.session_state["transcript"]:
        st.text(f"[{s:05.1f} - {e:05.1f}] {t}")
    if st.button("🤖 Script အလိုအလျောက် ရေး (AI)"):
        if not or_key:
            st.error("Sidebar မှာ OpenRouter API key အရင် ထည့်ပါ")
        else:
            with st.spinner("AI က script ရေးနေတယ်..."):
                st.session_state["script_box"] = pipeline.write_script(
                    st.session_state["transcript"], or_key, or_model)
            st.success("Script ရပြီ — အောက်မှာ ပြင်လို့ရတယ်")

# ---------- အဆင့် ၃: Script ပြင်ရေး ----------
st.subheader("✍️ Recap Script")
st.caption("တစ်ကြောင်းကို `စမယ့်စက္ကန့် | စာသား` ပုံစံနဲ့ ရေးပါ။ "
           "စာတိုတိုထားမှ အသံက ဗီဒီယိုနဲ့ ကိုက်မယ် (၁ စက္ကန့် ≈ မြန်မာစကားလုံး ၂ လုံးနှုန်း)")
default_script = """0 | ကြိုးဖြေနေတယ်။ ဘာလုပ်မလို့လဲ?
8 | ကားခေါင်းပေါ် ခုန်တက်! လျှောကျသွားပြီ!
17 | ကားအောက်မှာ လူပိတ်မိ! ဆွဲထုတ်ကြ! ရှင်တယ်!
34 | ကားဆီ သွားပြီ! တိုင်တွေ လဲကုန်ပြီ! ဘုန်း!
47 | ဘမ်း! ရထားနဲ့ တွေ့ပြီ! မင်းက မုန်တိုင်းလား?"""
if "script_box" not in st.session_state:
    st.session_state["script_box"] = default_script
script_text = st.text_area("Script", height=180, key="script_box")


def parse_script(text):
    lines = []
    for row in text.strip().splitlines():
        if "|" not in row:
            continue
        start, body = row.split("|", 1)
        lines.append((float(start.strip()), body.strip()))
    return lines


# ---------- အဆင့် ၄: ဗီဒီယို ထုတ် ----------
if video_path and st.button("🎬 ဗီဒီယို ထုတ်မယ်", type="primary"):
    if engine == "elevenlabs" and not api_key:
        st.error("ElevenLabs သုံးမယ်ဆို sidebar မှာ API key အရင် ထည့်ပါ")
        st.stop()
    script = parse_script(script_text)
    status = st.empty()
    with st.spinner("TTS + ဗီဒီယို ဆက်နေတယ်... (မိနစ်ပိုင်း ကြာနိုင်တယ်)"):
        files = pipeline.tts_all(script, engine, WORKDIR,
                                 api_key=api_key, voice_id=voice_id,
                                 log=lambda m: status.write(m))
        final = pipeline.build_video(video_path, files, WORKDIR,
                                      log=lambda m: status.write(m))
    st.success("ပြီးပါပြီ! 🎉")
    st.video(final)
    with open(final, "rb") as f:
        st.download_button("⬇️ Final video ဒေါင်းလုပ်", f,
                           file_name="final_recap.mp4", mime="video/mp4")
