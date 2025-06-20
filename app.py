import os, uuid
from flask import Flask, request, send_from_directory
from dotenv import load_dotenv
from pydub import AudioSegment
import pandas as pd
from gtts import gTTS
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client

# Load env vars
load_dotenv()

TESTING_MODE = True
os.makedirs("temp_audio", exist_ok=True)
AudioSegment.converter = "/usr/bin/ffmpeg"

app = Flask(__name__)

# Twilio setup
client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
FROM = os.getenv("TWILIO_NUMBER")
RECIPIENTS = os.getenv("RECIPIENT_NUMBER", "").split(",")

# Translate via Google unofficial API
def translate_to_hausa(text):
    try:
        res = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "ha", "dt": "t", "q": text}
        )
        return res.json()[0][0][0]
    except Exception as e:
        print(f"❌ Translation error: {e}")
        return text

# TTS using gTTS
def tts_generate(text):
    tts = gTTS(text=text, lang="ha")
    mp3_name = f"{uuid.uuid4().hex}.mp3"
    mp3_path = os.path.join("temp_audio", mp3_name)
    tts.save(mp3_path)
    return mp3_name

# Auto-set PUBLIC_URL on first request
@app.before_request
def set_public_url():
    if not os.getenv("PUBLIC_URL"):
        os.environ["PUBLIC_URL"] = request.host_url.rstrip("/")

# Broadcast message
def broadcast():
    try:
        print("🚀 Broadcasting...")
        df = pd.read_csv("messages.csv")
        if "message" not in df.columns:
            raise ValueError("Missing 'message' column in messages.csv")

        # Get index
        if TESTING_MODE:
            index_file = "last_sent.txt"
            idx = (int(open(index_file).read()) + 1 if os.path.exists(index_file) else 0) % len(df)
            open(index_file, "w").write(str(idx))
        else:
            idx = (pd.Timestamp.now().day - 1) % len(df)

        en = df.loc[idx, "message"]
        ha = translate_to_hausa(en)
        audio = tts_generate(ha)
        audio_url = f"{os.getenv('PUBLIC_URL')}/temp_audio/{audio}"

        print(f"📨 EN: {en}\n🌍 HA: {ha}")
        print(f"🔊 Audio: {audio_url}")

        for to in RECIPIENTS:
            # Send Hausa text
            client.messages.create(body=ha, from_=FROM, to=to)

            # Send Hausa audio
            client.messages.create(media_url=[audio_url], from_=FROM, to=to)

    except Exception as e:
        print(f"❌ Broadcast error: {e}")

# Schedule every 2 mins (or daily later)
sched = BackgroundScheduler()
sched.add_job(broadcast, "interval", minutes=2)
sched.start()

@app.route("/")
def home():
    return "✅ WhatsApp Malaria Bot is running!"

@app.route("/temp_audio/<file>")
def serve_audio(file):
    return send_from_directory("temp_audio", file)

@app.route("/twilio", methods=["POST"])
def handle_incoming():
    msg = request.values.get("Body", "")
    sender = request.values.get("From", "")
    print(f"📥 From {sender}: {msg}")
    return "OK", 200

if __name__ == "__main__":
    print("🌍 App starting...")
    broadcast()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
