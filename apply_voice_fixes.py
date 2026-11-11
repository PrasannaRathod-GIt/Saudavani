r"""Apply the SaudaVani voice fixes to the two files, safely.  Run from C:\saudavani

    python apply_voice_fixes.py            # DRY RUN: checks every edit, writes nothing
    python apply_voice_fixes.py --apply    # writes the files (backups: *.bak_voicefix)

What changes (and nothing else):
  backend/main.py   - Gnani TTS speed (GNANI_TTS_SPEED, default 0.95), same loudness for every reply, soft start;
                      buyer confirmation no longer returns text or audio (buyer page is silent).
  frontend/app/page.tsx - one reusable audio player unlocked by a tap (no more fallback to the phone's own voice);
                      buyer notices are not spoken with the phone voice (SPEAK_NOTICES = false).
Every edit must match EXACTLY once, otherwise nothing is written.
"""
import argparse
import ast
import re
import shutil
import sys
from pathlib import Path

HELPER = '''import array
import io
import math
import sys
import wave

try:
    TTS_SPEED = min(1.2, max(0.7, float(os.getenv("GNANI_TTS_SPEED", "0.95"))))
except ValueError:
    TTS_SPEED = 0.95

_TTS_TARGET_RMS = 3700.0   # about -19 dBFS: the same speech level for every reply
_TTS_PEAK_LIMIT = 29000.0  # never push a peak above about -1 dBFS
_TTS_GATE = 400            # ignore samples quieter than this when measuring the speech level
_TTS_MIN_GAIN, _TTS_MAX_GAIN = 0.25, 4.0
_TTS_LEAD_MS, _TTS_TAIL_MS = 200, 120  # silence so phone audio routes wake up before the first word


def _prepare_tts_wav(audio_bytes: bytes) -> bytes:
    """Give every spoken reply the same loudness and add a short silent lead-in/out.
    Returns the input unchanged on any problem (never breaks voice output)."""
    try:
        if not audio_bytes.startswith(b"RIFF"):
            return audio_bytes
        with wave.open(io.BytesIO(audio_bytes), "rb") as src:
            channels, width, rate = src.getnchannels(), src.getsampwidth(), src.getframerate()
            raw = src.readframes(src.getnframes())
        if width != 2 or not raw or channels < 1 or rate < 8000:
            return audio_bytes
        samples = array.array("h")
        samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
        if sys.byteorder == "big":
            samples.byteswap()
        voiced = [abs(v) for v in samples if abs(v) > _TTS_GATE]
        gain = 1.0
        if len(voiced) >= rate // 10:  # almost silent audio is never amplified
            rms = math.sqrt(sum(v * v for v in voiced) / len(voiced))
            gain = min(_TTS_TARGET_RMS / rms, _TTS_PEAK_LIMIT / max(voiced))
            gain = max(_TTS_MIN_GAIN, min(_TTS_MAX_GAIN, gain))
        if abs(gain - 1.0) > 0.02:
            samples = array.array("h", (max(-32768, min(32767, int(v * gain))) for v in samples))
        lead = array.array("h", [0]) * (int(rate * _TTS_LEAD_MS / 1000) * channels)
        tail = array.array("h", [0]) * (int(rate * _TTS_TAIL_MS / 1000) * channels)
        combined = lead + samples + tail
        if sys.byteorder == "big":
            combined.byteswap()
        out = io.BytesIO()
        with wave.open(out, "wb") as dst:
            dst.setnchannels(channels)
            dst.setsampwidth(2)
            dst.setframerate(rate)
            dst.writeframes(combined.tobytes())
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return audio_bytes


'''

SILENT_WAV = "data:audio/wav;base64,UklGRnQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YVAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="

# ------------------------------------------------------------------------------------------ main.py
MAIN_DEF = "async def synthesize_voice(text: str, language: str, voice: Optional[str] = None, hinglish: bool = False) -> dict[str, Any]:"
MAIN_EDITS = [
    ("helper block above synthesize_voice", MAIN_DEF, HELPER + MAIN_DEF),
    ("TTS speed from setting", '        payload["speed"] = 1.05', '        payload["speed"] = TTS_SPEED'),
    ("level + soft start before returning audio",
     '            raise RuntimeError("Gnani TTS returned empty audio")\n        return {"status": "success"',
     '            raise RuntimeError("Gnani TTS returned empty audio")\n'
     '        # Same loudness for every reply + soft start (off the event loop; raw audio is kept on any problem).\n'
     '        audio_bytes = await asyncio.to_thread(_prepare_tts_wav, audio_bytes)\n'
     '        return {"status": "success"'),
]
BUYER_BLOCK = re.compile(r"    # Generate buyer feedback using the exact same Gnani TTS configuration\n.*?(    return response\n)", re.S)

# --------------------------------------------------------------------------------------- page.tsx
PAGE_EDITS = [
    ("constants",
     'const SESSION_STORAGE_KEY = "saudavani_session_id";\n',
     'const SESSION_STORAGE_KEY = "saudavani_session_id";\n'
     'const SPEAK_NOTICES = false; // true = also speak buyer notices with the phone\'s own voice\n'
     'const SILENT_WAV = "' + SILENT_WAV + '";\n'),
    ("refs",
     '  const playerRef = useRef<HTMLAudioElement | null>(null);\n',
     '  const playerRef = useRef<HTMLAudioElement | null>(null);\n'
     '  const audioElRef = useRef<HTMLAudioElement | null>(null);\n'
     '  const audioUnlockedRef = useRef(false);\n'),
    ("stopPlayback + reusable player helpers",
     '  const stopPlayback = useCallback(() => {\n'
     '    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();\n'
     '    const player = playerRef.current;\n'
     '    if (player) {\n'
     '      player.pause();\n'
     '      player.removeAttribute("src");\n'
     '      player.load();\n'
     '      playerRef.current = null;\n'
     '    }\n'
     '  }, []);\n',
     '  const stopPlayback = useCallback(() => {\n'
     '    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();\n'
     '    const player = playerRef.current;\n'
     '    if (player) {\n'
     '      player.onended = null;\n'
     '      player.onerror = null;\n'
     '      player.pause();\n'
     '      player.removeAttribute("src");\n'
     '      player.load();\n'
     '      playerRef.current = null;\n'
     '    }\n'
     '  }, []);\n'
     '\n'
     '  const getPlayer = useCallback(() => {\n'
     '    if (!audioElRef.current) {\n'
     '      const el = new Audio();\n'
     '      el.preload = "auto";\n'
     '      el.setAttribute("playsinline", "");\n'
     '      audioElRef.current = el;\n'
     '    }\n'
     '    return audioElRef.current;\n'
     '  }, []);\n'
     '\n'
     '  // Phones only let an audio element play replies after it was started by a tap, so unlock it once.\n'
     '  const unlockAudio = useCallback(() => {\n'
     '    if (audioUnlockedRef.current) return;\n'
     '    const el = getPlayer();\n'
     '    el.onended = null;\n'
     '    el.onerror = null;\n'
     '    el.src = SILENT_WAV;\n'
     '    el.volume = 1;\n'
     '    const started = el.play();\n'
     '    if (started) {\n'
     '      started.then(() => {\n'
     '        if (!playerRef.current) el.pause();\n'
     '        audioUnlockedRef.current = true;\n'
     '      }).catch(() => { /* tried again on the next tap */ });\n'
     '    }\n'
     '  }, [getPlayer]);\n'),
    ("unlock inside sendTurn",
     '    if (!sessionId || inFlightRef.current) return;\n',
     '    if (!sessionId || inFlightRef.current) return;\n    unlockAudio();\n'),
    ("reuse the unlocked player for replies",
     '        const player = new Audio(`data:${mime};base64,${data.audio_base64}`);\n',
     '        const player = getPlayer();\n'
     '        player.onended = null;\n'
     '        player.onerror = null;\n'
     '        player.pause();\n'
     '        player.src = `data:${mime};base64,${data.audio_base64}`;\n'
     '        player.volume = 1;\n'),
    ("sendTurn dependencies",
     '  }, [language, sessionId, speakInBrowser, stopPlayback, syncSessionState]);\n',
     '  }, [language, sessionId, speakInBrowser, stopPlayback, syncSessionState, getPlayer, unlockAudio]);\n'),
    ("unlock on mic tap",
     '      stopPlayback();\n      void start();\n',
     '      unlockAudio();\n      stopPlayback();\n      void start();\n'),
    ("onMicClick dependencies",
     '  }, [isRecording, phase, recState, start, stop, stopPlayback]);\n',
     '  }, [isRecording, phase, recState, start, stop, stopPlayback, unlockAudio]);\n'),
    ("server notice not spoken with phone voice",
     '            speakInBrowserRef.current(noticeText, languageRef.current);\n',
     '            if (SPEAK_NOTICES) speakInBrowserRef.current(noticeText, languageRef.current);\n'),
    ("buyer response not spoken with phone voice",
     '    speakInBrowserRef.current(text, languageRef.current);\n',
     '    if (SPEAK_NOTICES) speakInBrowserRef.current(text, languageRef.current);\n'),
]


def load(path):
    raw = Path(path).read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n"), crlf


def apply_edits(text, edits, label):
    for name, find, repl in edits:
        n = text.count(find)
        if n != 1:
            sys.exit(f"STOP ({label}): edit '{name}' matched {n} times (needs exactly 1). Nothing was written.")
        text = text.replace(find, repl)
    return text


def patch_main(text):
    if "_prepare_tts_wav" in text:
        sys.exit("STOP (main.py): voice fix already applied. Nothing was written.")
    text = apply_edits(text, MAIN_EDITS, "main.py")
    matches = BUYER_BLOCK.findall(text)
    m = BUYER_BLOCK.search(text)
    if len(matches) != 1 or not m or "synthesize_voice(" not in m.group(0) or len(m.group(0)) > 3000:
        sys.exit("STOP (main.py): the buyer voice block was not found exactly once. Nothing was written.")
    text = text[:m.start()] + m.group(1) + text[m.end():]
    try:
        ast.parse(text)
    except SyntaxError as exc:
        sys.exit(f"STOP (main.py): result would not compile ({exc}). Nothing was written.")
    return text


def patch_page(text):
    if "SPEAK_NOTICES" in text:
        sys.exit("STOP (page.tsx): voice fix already applied. Nothing was written.")
    before = text.count("{") - text.count("}")
    text = apply_edits(text, PAGE_EDITS, "page.tsx")
    if text.count("{") - text.count("}") != before:
        sys.exit("STOP (page.tsx): braces no longer balance. Nothing was written.")
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--main", default="backend/main.py")
    ap.add_argument("--page", default="frontend/app/page.tsx")
    args = ap.parse_args()
    for p in (args.main, args.page):
        if not Path(p).exists():
            sys.exit(f"File not found: {p}  (run from C:\\saudavani or pass --main / --page)")
    main_text, main_crlf = load(args.main)
    page_text, page_crlf = load(args.page)
    new_main = patch_main(main_text)
    new_page = patch_page(page_text)
    print(f"OK  {args.main}: {len(MAIN_EDITS) + 1} edits matched exactly once, result compiles")
    print(f"OK  {args.page}: {len(PAGE_EDITS)} edits matched exactly once, braces balanced")
    if not args.apply:
        print("Dry run only. Run again with --apply to write the files.")
        return
    for path, text, crlf in ((args.main, new_main, main_crlf), (args.page, new_page, page_crlf)):
        shutil.copy2(path, path + ".bak_voicefix")
        Path(path).write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
        print(f"WROTE {path}  (backup: {path}.bak_voicefix)")


if __name__ == "__main__":
    main()
