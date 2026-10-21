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
    ["gtts", "elevenlabs"],
    format_func=lambda e: "gTTS (အခမဲ့၊ အသံစက်ဆန်)" if e == "gtts"
    else "ElevenLabs (API key လို၊ အသံကောင်း)",
)
api_key, voice_id = "", ""
if engine == "elevenlabs":
    api_key = st.sidebar.text_input("ElevenLabs API key", type="password",
                                    help="elevenlabs.io → Profile → API Keys")
    voice_id = st.sidebar.text_input(
        "Voice ID", value="21m00Tcm4TlvDq8ikWAM",
        help="ElevenLabs Voices ထဲက ကြိုက်တဲ့ အသံရဲ့ ID")

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

# ---------- အဆင့် ၃: Script ပြင်ရေး ----------
st.subheader("✍️ Recap Script")
st.caption("တစ်ကြောင်းကို `စမယ့်စက္ကန့် | စာသား` ပုံစံနဲ့ ရေးပါ။ "
           "စာတိုတိုထားမှ အသံက ဗီဒီယိုနဲ့ ကိုက်မယ် (၁ စက္ကန့် ≈ မြန်မာစကားလုံး ၂ လုံးနှုန်း)")
default_script = """0 | ကြိုးဖြေနေတယ်။ ဘာလုပ်မလို့လဲ?
8 | ကားခေါင်းပေါ် ခုန်တက်! လျှောကျသွားပြီ!
17 | ကားအောက်မှာ လူပိတ်မိ! ဆွဲထုတ်ကြ! ရှင်တယ်!
34 | ကားဆီ သွားပြီ! တိုင်တွေ လဲကုန်ပြီ! ဘုန်း!
47 | ဘမ်း! ရထားနဲ့ တွေ့ပြီ! မင်းက မုန်တိုင်းလား?"""
script_text = st.text_area("Script", value=default_script, height=180)


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
