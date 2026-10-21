# Movie Recap Tool

ဗီဒီယိုတင် → transcript → script → အသံ → recap ဗီဒီယိုအပြီး အလိုအလျောက်ထုတ်ပေးတဲ့ tool

## Streamlit Cloud မှာ ဖွင့်နည်း
1. ဒီ repo ကို share.streamlit.io မှာ Deploy လုပ်ပါ
2. Main file path: `app.py`

## ဖိုင်တွေ
- `app.py` — Streamlit website
- `pipeline.py` — အသံထုတ် / Whisper / TTS / ဗီဒီယိုဆက် logic
- `requirements.txt` — Python packages
- `packages.txt` — ffmpeg (system package)

## TTS
- gTTS: အခမဲ့ (အသံ စက်ဆန်တယ်)
- ElevenLabs: ကိုယ်ပိုင် API key ကို app ရဲ့ sidebar မှာ ထည့်သုံးပါ — key ကို repo ထဲ လုံးဝ မထည့်ပါနဲ့
