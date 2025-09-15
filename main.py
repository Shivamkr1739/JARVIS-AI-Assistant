import speech_recognition as sr
import webbrowser
import pyttsx3
import musicLibrary
import requests
import wikipedia
import os
from gtts import gTTS
import pygame
import time
import re

# -------------------- API KEYS --------------------
WEATHER_API = "f212bac55c8f1a5d5062681917901a05"   # OpenWeather API key
NEWS_API    = "8a2402fa7e7c4435b964e52bc147e7f0"   # News API key

# -------------------- TTS ENGINES --------------------
engine = pyttsx3.init()
pygame.mixer.init()

# -------------------- SPEAK FUNCTION --------------------
def speak(text, use_gtts=True):
    """Speak text using gTTS (online) with pyttsx3 fallback (offline)."""
    print("Jarvis:", text)
    try:
        if use_gtts:
            filename = "voice.mp3"
            tts = gTTS(text=text, lang="en")
            tts.save(filename)
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            try:
                os.remove(filename)  # cleanup
            except Exception:
                pass
        else:
            engine.say(text)
            engine.runAndWait()
    except Exception as e:
        print("TTS error, fallback:", e)
        engine.say(text)
        engine.runAndWait()

# -------------------- RECOGNITION HELPERS --------------------
recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.6  # small pause between words

def hear_once(timeout=5, phrase_time_limit=6, prompt_log=""):
    """Listen once and return lowercased text or ''."""
    with sr.Microphone() as source:
        if prompt_log:
            print(prompt_log)
        recognizer.adjust_for_ambient_noise(source, duration=0.8)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            text = recognizer.recognize_google(audio)
            text = text.strip()
            print("Heard:", text)
            return text.lower()
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            print("Speech service error:", e)
            return ""
        except Exception as e:
            print("Recognition error:", e)
            return ""

# -------------------- INTENT HELPERS --------------------
def is_weather_cmd(cmd: str) -> bool:
    keys = ["weather", "whether", "climate", "temperature"]
    return any(k in cmd for k in keys)

def is_news_cmd(cmd: str) -> bool:
    keys = ["news", "headlines", "updates"]
    return any(k in cmd for k in keys)

def is_calc_cmd(cmd: str) -> bool:
    keys = ["calculate", "calc", "+", "-", "times", "x", "into", "divide", "divided by", "multiply", "*", "/", "plus", "minus"]
    return any(k in cmd for k in keys)

# -------------------- NEWS --------------------
def get_news(country_pref="in"):
    speak("Fetching the latest headlines, please wait...")
    def fetch(country):
        url = f"https://newsapi.org/v2/top-headlines?country={country}&apiKey={NEWS_API}"
        r = requests.get(url, timeout=10)
        return (r.status_code, r.json() if r.status_code == 200 else {})

    try:
        status, data = fetch(country_pref)
        articles = (data.get("articles") or []) if status == 200 else []
        if not articles:
            # fallback to US (often works on free plan)
            status, data = fetch("us")
            articles = (data.get("articles") or []) if status == 200 else []

        if not articles:
            speak("Sorry, I couldn't find any news right now.")
            return

        for i, article in enumerate(articles[:5], start=1):
            headline = article.get("title") or "No title available"
            print(f"News {i}:", headline)
            speak(f"Headline {i}: {headline}")
            time.sleep(0.4)
    except Exception as e:
        print("News error:", e)
        speak("There was a problem fetching the news.")

# -------------------- WEATHER --------------------
def extract_city_from_text(cmd: str) -> str:
    """
    Tries to extract a city after 'in ' or from phrases like 'weather in bhopal'
    """
    # look for "in <city>"
    m = re.search(r"\bin\s+([a-zA-Z\s]+)$", cmd)
    if m:
        return m.group(1).strip()
    # otherwise remove common words and try what's left
    tmp = cmd
    for w in ["weather", "whether", "climate", "temperature", "in", "of", "at", "for", "jarvis"]:
        tmp = tmp.replace(w, " ")
    tmp = re.sub(r"\s+", " ", tmp).strip()
    # heuristic: if 1-3 words left, treat as city
    if 0 < len(tmp.split()) <= 3:
        return tmp
    return ""

def get_weather_for_city(city: str):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API}&units=metric"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if str(data.get("cod")) == "200":
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"]
            speak(f"The weather in {city} is {desc} with a temperature of {temp} degrees Celsius.")
        else:
            msg = data.get("message", "unknown error")
            print("Weather API response:", data)
            speak(f"Sorry, I couldn't find weather for {city}.")
    except Exception as e:
        print("Weather error:", e)
        speak("Sorry, I couldn't fetch the weather right now.")

def handle_weather(cmd: str):
    # try to parse city from the same utterance: "jarvis weather in bhopal"
    city = extract_city_from_text(cmd)
    if city:
        get_weather_for_city(city)
        return
    # ask for city if not found
    speak("Which city?")
    city = hear_once(timeout=6, phrase_time_limit=6, prompt_log="Listening for city...")
    if not city:
        speak("I didn't catch the city name.")
        return
    get_weather_for_city(city)

# -------------------- CALCULATOR --------------------
def to_math(expr: str) -> str:
    """Map spoken words to math symbols and keep only safe characters."""
    expr = expr.lower()
    # strip wake/keywords
    for w in ["jarvis", "calculate", "calc", "please", "equals", "equal to"]:
        expr = expr.replace(w, " ")
    # spoken replacements
    expr = (expr.replace("plus", "+")
                .replace("minus", "-")
                .replace("times", "*")
                .replace("into", "*")
                .replace("x", "*")
                .replace("multiplied by", "*")
                .replace("divide by", "/")
                .replace("divided by", "/")
                .replace("over", "/"))
    expr = re.sub(r"[^0-9+\-*/().\s]", " ", expr)  # allow only safe math chars
    expr = re.sub(r"\s+", " ", expr).strip()
    return expr

def safe_eval_math(expr: str):
    """Very small safe eval for + - * / and parentheses."""
    # still uses eval, but after strict filtering of characters
    try:
        return eval(expr, {"__builtins__": {}}, {})
    except Exception:
        return None

def handle_calculate(cmd: str):
    # support one-shot: "jarvis calculate 5 plus 3" or "jarvis 5 plus 3"
    expr = to_math(cmd)
    if not expr or not re.search(r"[0-9]", expr):
        # ask again if no numbers found
        speak("Please say the calculation, for example: 12 plus 7.")
        heard = hear_once(timeout=6, phrase_time_limit=6, prompt_log="Listening for calculation...")
        expr = to_math(heard)

    if not expr:
        speak("Sorry, I didn't understand the calculation.")
        return

    print("Math expr:", expr)
    result = safe_eval_math(expr)
    if result is None:
        speak("Sorry, I couldn't calculate that.")
    else:
        speak(f"The result is {result}")

# -------------------- WEB/OPEN --------------------
def handle_open_sites(cmd: str):
    if "open google" in cmd:
        speak("Opening Google")
        webbrowser.open("https://google.com")
        return True
    if "open facebook" in cmd:
        speak("Opening Facebook")
        webbrowser.open("https://facebook.com")
        return True
    if "open linkedin" in cmd:
        speak("Opening LinkedIn")
        webbrowser.open("https://linkedin.com")
        return True
    if "open youtube" in cmd:
        speak("Opening YouTube")
        webbrowser.open("https://youtube.com")
        return True
    return False

def handle_play(cmd: str):
    if cmd.startswith("play "):
        parts = cmd.split()
        if len(parts) >= 2:
            song = parts[1]
            link = musicLibrary.music.get(song)
            if link:
                speak(f"Playing {song}")
                webbrowser.open(link)
            else:
                speak("Sorry, I couldn't find that song.")
            return True
    return False

# -------------------- WIKIPEDIA --------------------
def handle_wikipedia(cmd: str):
    if "wikipedia" in cmd:
        query = cmd.replace("wikipedia", "").strip()
        if not query:
            speak("What topic should I search on Wikipedia?")
            query = hear_once(timeout=6, phrase_time_limit=6, prompt_log="Listening for topic...")
        if not query:
            speak("I didn't catch the topic.")
            return True
        try:
            speak(f"Searching Wikipedia for {query}.")
            summary = wikipedia.summary(query, sentences=2)
            speak(summary)
        except Exception as e:
            print("Wiki error:", e)
            speak("Sorry, I couldn't fetch information from Wikipedia.")
        return True
    return False

# -------------------- COMMAND ROUTER --------------------
def process_command(cmd: str):
    cmd = cmd.lower().strip()
    print("Command:", cmd)

    # quick exits
    if any(x in cmd for x in ["exit", "quit", "stop", "shutdown"]):
        speak("Goodbye, shutting down Jarvis.")
        raise SystemExit

    # open sites / play
    if handle_open_sites(cmd):
        return
    if handle_play(cmd):
        return

    # intents
    if is_news_cmd(cmd):
        get_news()
        return

    if is_weather_cmd(cmd):
        handle_weather(cmd)
        return

    if is_calc_cmd(cmd):
        handle_calculate(cmd)
        return

    if handle_wikipedia(cmd):
        return

    speak("Sorry, I did not understand that command.")

# -------------------- MAIN LOOP --------------------
if __name__ == "__main__":
    speak("Initializing Jarvis. Say 'Jarvis' followed by your request.")
    while True:
        heard = hear_once(timeout=6, phrase_time_limit=6, prompt_log="Listening...")
        if not heard:
            continue

        # One-shot: "jarvis news", "jarvis weather in bhopal", etc.
        if "jarvis" in heard:
            # strip the wake word
            cmd = heard.replace("jarvis", "").strip()
            if cmd:
                process_command(cmd)
                continue
            # two-step: heard only "jarvis" → ask for next command
            speak("Yes, I'm listening.")
            follow = hear_once(timeout=6, phrase_time_limit=6, prompt_log="Listening for command...")
            if follow:
                process_command(follow)
            else:
                speak("I didn't hear any command.")
        else:
            # ignore phrases without wake word to avoid accidental triggers
            print("Ignored (no wake word):", heard)
