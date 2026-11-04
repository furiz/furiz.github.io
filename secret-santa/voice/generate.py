#!/usr/bin/env python3
"""Genererar uppläsarrösten för Secret Santa med ElevenLabs.

Användning:
    export ELEVENLABS_API_KEY=...            # din nyckel
    python3 secret-santa/voice/generate.py --list-voices   # visa röster att välja bland
    python3 secret-santa/voice/generate.py --voice <voice_id>
    python3 secret-santa/voice/generate.py --voice <voice_id> --only pl --force

Läser script.json, skriver voice/<språk>/<klipp>.mp3 och manifest.json.
Befintliga filer hoppas över om inte --force anges (sparar krediter).
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.elevenlabs.io/v1"
TAG = re.compile(r"\[[^\]]*\]\s*")


def request(method, path, key, body=None, accept="application/json"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "xi-api-key": key, "Content-Type": "application/json", "Accept": accept,
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def clips_for(lines, names):
    """Alla klipp som ska finnas för ett språk: {klipp-id: text}."""
    out = {k: lines[k] for k in ("intro", "hello_any", "build", "drum", "tease", "outro")}
    for slug, name in names.items():
        out["hello_" + slug] = lines.get("hello_" + slug, lines["hello"]).replace("{name}", name)
        out["name_" + slug] = lines.get("name_" + slug, lines["name"]).replace("{name}", name)
    return out


def tts(key, voice, model, text):
    if model == "eleven_v3":
        settings = {"stability": 0.0, "similarity_boost": 0.8}
    else:
        text = TAG.sub("", text)
        settings = {"stability": 0.3, "similarity_boost": 0.8, "style": 0.7, "use_speaker_boost": True}
    return request("POST", "/text-to-speech/%s?output_format=mp3_44100_128" % voice, key,
                   {"text": text, "model_id": model, "voice_settings": settings}, accept="audio/mpeg")


def list_voices(key):
    mine = json.loads(request("GET", "/voices", key))
    print("Dina röster:")
    for v in mine.get("voices", []):
        print("  %-22s %-28s %s" % (v["voice_id"], v["name"], (v.get("labels") or {}).get("description", "")))
    q = urllib.parse.urlencode({"language": "pl", "page_size": 30, "search": "radio"})
    try:
        shared = json.loads(request("GET", "/shared-voices?" + q, key))
        print("\nPolska radioröster i röstbiblioteket (lägg till i 'My voices' först):")
        for v in shared.get("voices", []):
            print("  %-22s %-28s %s" % (v["voice_id"], v["name"], v.get("description", "")[:60]))
    except urllib.error.HTTPError as e:
        print("(kunde inte söka i biblioteket: %s)" % e.code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=os.environ.get("ELEVENLABS_VOICE_ID"))
    ap.add_argument("--model", default=os.environ.get("ELEVENLABS_MODEL", "eleven_v3"))
    ap.add_argument("--only", help="bara detta språk, t.ex. pl")
    ap.add_argument("--force", action="store_true", help="skriv över befintliga filer")
    ap.add_argument("--list-voices", action="store_true")
    a = ap.parse_args()

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("Sätt ELEVENLABS_API_KEY först.")
    if a.list_voices:
        return list_voices(key)
    if not a.voice:
        sys.exit("Ange --voice <voice_id> (se --list-voices).")

    script = json.load(open(os.path.join(HERE, "script.json"), encoding="utf-8"))
    manifest_path = os.path.join(HERE, "manifest.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}

    model = a.model
    for lang, lines in script["lines"].items():
        if a.only and lang != a.only:
            continue
        os.makedirs(os.path.join(HERE, lang), exist_ok=True)
        done = set(manifest.get(lang, []))
        for clip, text in clips_for(lines, script["names"]).items():
            path = os.path.join(HERE, lang, clip + ".mp3")
            if os.path.exists(path) and not a.force:
                done.add(clip)
                continue
            try:
                audio = tts(key, a.voice, model, text)
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:300]
                if model == "eleven_v3":
                    print("eleven_v3 gick inte (%s), byter till eleven_multilingual_v2" % e.code)
                    model = "eleven_multilingual_v2"
                    audio = tts(key, a.voice, model, text)
                else:
                    sys.exit("Fel %s för %s/%s: %s" % (e.code, lang, clip, msg))
            open(path, "wb").write(audio)
            done.add(clip)
            print("✓ %s/%s.mp3 (%d kB)" % (lang, clip, len(audio) // 1024))
        manifest[lang] = sorted(done)

    json.dump(manifest, open(manifest_path, "w"), indent=1)
    print("Klart. manifest.json uppdaterad (modell: %s)." % model)


if __name__ == "__main__":
    main()
