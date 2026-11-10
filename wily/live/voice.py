"""Your own calls: records YOUR microphone during CS2 matches (opt-in, in the settings), transcribes it on this PC
(Whisper, nothing leaves the PC), aligns the calls on the rounds of the match and measures how you communicate:
information given before dying, "where + how many" calls, grenades announced, talking during a teammate's clutch,
tilt words.

Recording starts and stops with the match (CS2 Game State Integration) or by hand. Only your microphone is recorded:
with a headset, your teammates' voices do not reach it. Files stay in out/voice (not versioned). Recording other
people's words without their consent is forbidden in France (article 226-1 of the Code pénal): record your own
voice, or teammates who agreed.

Usage: python -m wily.live.voice transcribe <recording id>
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time

from wily.core import config
from wily.core.i18n import N_, tr, trn

DIR = os.path.join(config.OUT, "voice")
SR = 16000
MODEL = "large-v2"
HEARD_V = 1   # heard.py's analysis: up it when it changes


def settings():
    return config.settings().get("voice") or {}


def save_settings(**kw):
    s = config.settings()
    v = s.setdefault("voice", {})
    v.update(kw)
    config.save_settings(s)
    return v


def cs2_voice_device():
    """The microphone CS2 uses for voice chat (voice_device_override in CS2's settings), if one is set."""
    try:
        own = config.logged_in_account()[0]
        f = os.path.join(config.steam_path(), "userdata", str(int(own) - 76561197960265728), "730", "local", "cfg", "cs2_machine_convars.vcfg")
        m = re.search(r'"voice_device_override"\s*"([^"]+)"', open(f, encoding="utf-8", errors="replace").read())
        return m.group(1) if m else None
    except Exception:
        return None


def chosen_device():
    return settings().get("device") or cs2_voice_device()


# ---------- sound libraries ----------
# Windows: sounddevice, whose wheel carries PortAudio with it. Linux: soundcard, which talks to PulseAudio/PipeWire
# and needs nothing installed by hand - sounddevice's Linux wheel bundles no PortAudio, so without one it raises
# OSError("PortAudio library not found") and not a single call is ever recorded (10/10, a tester on Fedora).
BACKENDS = ("sd", "sc") if os.name == "nt" else ("sc", "sd")
_NAMES = {"sd": "sounddevice", "sc": "soundcard"}


def _why_not(b):
    """-> None when that library can be used here, else what it answered."""
    # soundcard names itself to PulseAudio from sys.argv[1] when argv[0] is "-c" or "-m", without checking that there
    # is one: probed from a "python -c" one-liner it raises IndexError and this PC would look unable to record.
    argv = sys.argv
    if len(argv) < 2:
        sys.argv = [*argv, "wily"]
    try:
        __import__(_NAMES[b])
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    finally:
        sys.argv = argv


def backend():
    """The library the recording goes through: 'sc' (PulseAudio/PipeWire) or 'sd' (PortAudio). None: neither works."""
    return next((b for b in BACKENDS if _why_not(b) is None), None)


def available():
    """(your calls can be recorded, why they cannot). The Settings page says it instead of offering a microphone
    that will fail on the first click."""
    if backend():
        return True, ""
    why = ", ".join(f"{_NAMES[b]} ({_why_not(b)})" for b in BACKENDS)
    how = "" if os.name == "nt" else (" PortAudio gives one: Debian/Ubuntu: sudo apt install libportaudio2 ; "
                                      "Fedora: sudo dnf install portaudio ; Arch: sudo pacman -S portaudio.")
    return False, f"no sound library usable on this PC: {why}.{how}"


def _same_device(name, want):
    """A name as the library gives it against the one asked for (PortAudio shortens names to 31 characters)."""
    return bool(name and want) and (name == want or name.startswith(want[:31]) or want.startswith(name[:31]))


def _cut_copy(a, b):
    """Two names of one device: the same, or one of them PortAudio's 31 first characters of the other."""
    return a == b or (len(a) == 31 and b.startswith(a)) or (len(b) == 31 and a.startswith(b))


def devices():
    """The microphones to choose from, each once (16/10: 24 entries for 5 microphones in Settings: PortAudio lists a
    device once per Windows sound API, MME's names cut to 31 characters, with the MME "Sound Mapper" and the
    DirectSound "Primary Sound Capture Driver" that only mean the default, and WDM-KS's raw inputs, one per jack).
    The longest of a device's names is kept: the recording still opens the first device matching it, as before.
    chosen: the one the settings name."""
    cs2, want = cs2_voice_device(), settings().get("device")
    out = []

    def add(name, default):
        for d in out:
            if _cut_copy(d["name"], name):
                d["name"] = max(d["name"], name, key=len)
                d["default"] = d["default"] or default
                return
        out.append({"name": name, "default": default})
    if backend() == "sc":
        import soundcard as sc
        try:
            default = sc.default_microphone().name
        except Exception:
            default = None
        for m in sc.all_microphones(include_loopback=False):   # the monitors are the team sound, not your voice
            add(m.name, m.name == default)
    else:
        import sounddevice as sd
        apis, devs = sd.query_hostapis(), sd.query_devices()
        default = sd.query_devices(kind="input")["name"]
        alias = set()   # each of these two APIs lists "the default" first, under a name in Windows' language
        for a in apis:
            if a["name"] in ("MME", "Windows DirectSound"):
                alias |= {next((i for i in a["devices"] if devs[i]["max_input_channels"] > 0), None)}
        for i, d in enumerate(devs):
            if d["max_input_channels"] > 0 and i not in alias and apis[d["hostapi"]]["name"] != "Windows WDM-KS":
                add(d["name"], _same_device(d["name"], default))
    for d in out:
        d["cs2"], d["chosen"] = _same_device(d["name"], cs2), _same_device(d["name"], want)
    return out


# ---------- recording ----------
def _target(b, name):
    """(soundcard's microphone, sounddevice's index, its name, the rate to record at): the microphone named, else the
    default one."""
    mic = dev = None
    rate = SR
    if b == "sc":
        import soundcard as sc
        if name:
            mic = next((m for m in sc.all_microphones(include_loopback=False) if _same_device(m.name, name)), None)
        mic = mic or sc.default_microphone()
        label = mic.name   # PulseAudio resamples to the rate asked for, so SR is always fine
    else:
        import sounddevice as sd
        if name:
            dev = next((i for i, d in enumerate(sd.query_devices())
                        if d["max_input_channels"] > 0 and _same_device(d["name"], name)), None)
        info = sd.query_devices(dev, kind="input")
        label = info["name"]
        try:
            sd.check_input_settings(device=dev, samplerate=SR, channels=1)
        except Exception:
            rate = int(info["default_samplerate"])  # Whisper resamples on reading
    return mic, dev, label, rate


def test(seconds=3.0):
    """The chosen microphone's loudest sample over a few seconds, nothing written (16/10: 10 of 14 recordings at exactly
    0 and nothing said it outside the recordings' table). During a recording: its level of the last seconds, the
    microphone not opened a second time."""
    if REC.recording():
        return {"device": (REC.meta or {}).get("device"), "peak": round(REC.level(), 4), "recording": True}
    b = backend()
    if b is None:
        raise RuntimeError(available()[1])
    mic, dev, label, rate = _target(b, chosen_device())
    if b == "sc":
        data = mic.record(numframes=int(rate * seconds), samplerate=rate, channels=1)
    else:
        import sounddevice as sd
        data = sd.rec(int(rate * seconds), samplerate=rate, channels=1, dtype="float32", device=dev, blocking=True)
    import numpy as np
    a = abs(np.asarray(data, dtype="float32").reshape(-1))
    return {"device": label, "peak": round(float(a.max()) if a.size else 0.0, 4), "recording": False}


class _ScStream:
    """soundcard records through blocking calls: a thread makes them and hands each block over, behind the same
    start/stop/close a sounddevice stream has. The device opens inside that thread, so start() waits for it: a
    microphone that cannot open is an error of the button you pressed, not a recording that turns out empty."""

    def __init__(self, mic, rate, on_block, blocksize=1024):
        self.mic, self.rate, self.on_block, self.blocksize = mic, rate, on_block, blocksize
        self.stop_ev, self.ready, self.error = threading.Event(), threading.Event(), None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            with self.mic.recorder(samplerate=self.rate, channels=1, blocksize=self.blocksize) as r:
                self.ready.set()
                while not self.stop_ev.is_set():
                    d = r.record(numframes=self.rate // 10)
                    self.on_block(d[:, 0] if getattr(d, "ndim", 1) > 1 else d)
        except Exception as e:
            self.error = e
            if self.ready.is_set():   # it was recording and the sound card went away: the file keeps what it had
                print("microphone:", e, flush=True)
        finally:
            self.ready.set()

    def start(self, timeout=10):
        self.thread.start()
        self.ready.wait(timeout)
        if self.error:
            raise self.error

    def stop(self):
        self.stop_ev.set()
        self.thread.join(timeout=5)

    def close(self):
        pass


class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.stream = self.file = self.meta = None
        self.peak = 0.0          # loudest sample of the recording (silence = wrong microphone)
        self.win = [0.0, 0.0, 0.0]   # the level now: [this second's start, its loudest sample, the second before's]

    def recording(self):
        return self.stream is not None

    def level(self):
        """The loudest sample of the last second or two (Settings' microphone test, during a recording)."""
        w = self.win
        return max(w[1], w[2]) if time.time() - w[0] < 2 else 0.0

    def start(self, map_name=None, steamid=None, source="auto"):
        import soundfile as sf
        b = backend()
        if b is None:
            raise RuntimeError(available()[1])
        with self.lock:
            if self.stream:
                return self.meta
            os.makedirs(DIR, exist_ok=True)
            now = dt.datetime.now()
            rid = f"{now:%Y%m%d_%H%M%S}_{(map_name or 'match').replace('de_', '').replace('cs_', '')}"
            self.peak = 0.0
            self.win = [0.0, 0.0, 0.0]
            mic, dev, label, rate = _target(b, chosen_device())
            path = os.path.join(DIR, rid + ".flac")
            self.file = sf.SoundFile(path, mode="w", samplerate=rate, channels=1, format="FLAC")
            self.meta = {"id": rid, "file": rid + ".flac", "start": time.time(), "start_iso": now.isoformat(timespec="seconds"),
                         "map": map_name, "steamid": str(steamid or ""), "device": label, "rate": rate, "source": source,
                         "backend": b, "rounds": []}

            seg = _Segmenter(rate, LIVE.push) if settings().get("live", True) else None

            def block(data):
                try:
                    self.file.write(data)
                    if seg is not None:
                        seg.feed(data, time.time())
                    p = float(abs(data).max()) if len(data) else 0.0
                    if p > self.peak:
                        self.peak = p
                    w, now = self.win, time.time()
                    if now - w[0] >= 1:
                        w[0], w[1], w[2] = now, p, w[1]
                    elif p > w[1]:
                        w[1] = p
                except Exception:
                    pass

            if b == "sc":
                self.stream = _ScStream(mic, rate, block)
            else:
                import sounddevice as sd
                self.stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32", device=dev,
                                             callback=lambda indata, frames, tinfo, status: block(indata[:, 0].copy()))
            try:
                self.stream.start()
            except Exception:   # the microphone refused: nothing half-open, and the button says why
                self.stream = None
                self.file.close()
                self.file = self.meta = None
                try:
                    os.remove(path)
                except OSError:
                    pass
                raise
            self._save()
            return self.meta

    def mark(self, **event):
        with self.lock:
            if self.meta is not None:
                event["t"] = round(time.time() - self.meta["start"], 2)
                self.meta["rounds"].append(event)
                if event.get("map") and not self.meta.get("map"):
                    self.meta["map"] = event["map"]
                self._save()

    def stop(self):
        off = TEAM.stop()   # your team's sound ends with the match
        with self.lock:
            if not self.stream:
                return None
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None
                self.file.close()
                self.file = None
                self.meta["end"] = time.time()
                self.meta["duration"] = round(self.meta["end"] - self.meta["start"], 1)
                self.meta["peak"] = round(self.peak, 4)
                self.meta["silent"] = self.peak < 0.01  # nothing above -40 dB: the microphone was not the one in use
                if off is not None and self.meta.get("team"):
                    self.meta["team"]["off"] = off
                self._save()
                m, self.meta = self.meta, None
            return m

    def _save(self):
        json.dump(self.meta, open(os.path.join(DIR, self.meta["id"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


REC = Recorder()
LAST = {"key": None, "gameover": None}

TEAM_SR = 48000   # the PC's sound as the sound card mixes it


class TeamRecorder:
    """What you hear (the PC's sound: your teammates' voices and the game), recorded beside your microphone from the
    moment you confirm that your team agreed, for the rest of this match only: nobody's voice without their consent
    (France, art. 226-1; 04/10: Catharsis agreed, the others are asked at the start of the match). <id>.team.flac; the
    consent, how and when it was given, are in the recording's .json."""

    def __init__(self):
        self.thread = None
        self.stop_ev = threading.Event()
        self.pending = None   # agreed before the match recording started (warm-up): starts with it, same map only

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, how, map_name=None):
        """how: the consent, said as it was given ("your team agreed: the In game page's button").
        -> True (recording), "pending" (no match recording yet: it starts with it, on this map), False (already on)."""
        if self.running():
            return False
        if not REC.recording():
            self.pending = {"how": how, "at": time.time(), "map": map_name}
            return "pending"
        self.pending = None
        import soundcard as sc
        import soundfile as sf
        sp = sc.default_speaker()
        mic = sc.get_microphone(id=str(sp.name), include_loopback=True)
        with REC.lock:
            meta = REC.meta
            if meta is None:
                return False
            rid = meta["id"]
            meta["team"] = {"on": round(time.time() - meta["start"], 2), "device": sp.name, "consent": how,
                            "at": dt.datetime.now().isoformat(timespec="seconds"), "file": rid + ".team.flac"}
            REC._save()
        f = sf.SoundFile(os.path.join(DIR, rid + ".team.flac"), mode="w", samplerate=TEAM_SR, channels=1, format="FLAC")
        self.stop_ev.clear()

        def run():
            import numpy as np
            try:
                with mic.recorder(samplerate=TEAM_SR, channels=1, blocksize=1024) as r:
                    t0, n = time.time(), 0
                    while not self.stop_ev.is_set():
                        d = r.record(numframes=TEAM_SR // 10)
                        d = d[:, 0] if d.ndim > 1 else d
                        f.write(d)
                        n += len(d)
                        late = int((time.time() - t0) * TEAM_SR) - n   # a gap of the sound card: silence, so that
                        if late > TEAM_SR // 2:                        # the file's time stays the match's time
                            f.write(np.zeros(late, dtype="float32"))
                            n += late
            except Exception as e:
                print("team sound:", e, flush=True)
            finally:
                f.close()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return True

    def resume(self, map_name=None):
        """The match recording just started: the team sound too when your team agreed during the warm-up."""
        p = self.pending
        if p and time.time() - p["at"] < 30 * 60 and (not p.get("map") or not map_name or p["map"] == map_name):
            return self.start(p["how"], map_name)
        self.pending = None
        return False

    def stop(self):
        """-> when it stopped, in seconds of the recording (None: it was not on)."""
        self.pending = None
        if not self.running():
            return None
        self.stop_ev.set()
        self.thread.join(timeout=5)
        return round(time.time() - ((REC.meta or {}).get("start") or time.time()), 2)


TEAM = TeamRecorder()


def on_gsi(g):
    """Called for every message of the game: start with the match (automatic mode), mark the rounds of any
    recording, stop at the end (automatic mode)."""
    if not g:
        return
    auto = bool(settings().get("auto"))
    phase = g.get("map_phase")
    if TEAM.pending and (g.get("map") is None or (TEAM.pending.get("map") and g.get("map") != TEAM.pending["map"])):
        TEAM.pending = None   # agreed for a match that never started: not carried over to the next one
    if auto and g.get("practice"):   # practice or custom server: nothing to line up with a match, no automatic recording
        if REC.recording() and (REC.meta or {}).get("source") == "auto":
            REC.meta["practice"] = True   # stopped without transcription; kept (Settings lists it, delete it there)
            REC.stop()
            LAST.update(key=None, gameover=None)
        return
    if auto and phase == "live" and g.get("map") and not REC.recording():
        try:
            pause_transcription()  # all the power for the game
            REC.start(g.get("map"), g.get("steamid"), "auto")
            LIVE.start(g.get("map"))
            TEAM.resume(g.get("map"))
        except Exception as e:
            print("microphone unavailable:", e, flush=True)
            return
    if REC.recording():
        key = (g.get("round"), g.get("round_phase"), g.get("side"))
        if key != LAST["key"]:
            LAST["key"] = key
            REC.mark(round=g.get("round"), phase=g.get("round_phase"), side=g.get("side"), map=g.get("map"),
                     score=[g.get("score_ct"), g.get("score_t")])
        if not auto:
            return
        if phase == "gameover":
            LAST["gameover"] = LAST["gameover"] or time.time()
            if time.time() - LAST["gameover"] > 20:  # keep the last words
                finish()
        elif phase is None and g.get("map") is None:  # back to the menu
            finish()
        else:
            LAST["gameover"] = None


def watchdog(g):
    """No message from the game for 2 minutes while recording automatically: the game was closed."""
    if REC.recording() and (REC.meta or {}).get("source") == "auto":
        if not g or g.get("age", 999) > 120:
            finish()


def finish():
    LIVE.stop()
    m = REC.stop()
    LAST.update(key=None, gameover=None)
    if m and m.get("duration", 0) >= 60 and not m.get("silent"):
        start_transcription(m["id"])
    return m


# ---------- transcription (separate low-priority process) ----------
JOB = {"proc": None, "id": None}


def start_transcription(rid):
    if JOB["proc"] and JOB["proc"].poll() is None:
        return False
    flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log = open(os.path.join(DIR, rid + ".log"), "w", encoding="utf-8")
    JOB["proc"] = subprocess.Popen([sys.executable, "-m", "wily.live.voice", "transcribe", rid], cwd=config.HERE,
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    JOB["id"] = rid
    return True


def transcribing():
    return JOB["id"] if JOB["proc"] and JOB["proc"].poll() is None else None


def pending(max_days=14):
    """The recordings not transcribed yet (a match stopped their transcription), the newest first: the matches of the
    last two weeks, at least a minute long, neither silent nor on the training server or a workshop map."""
    out = []
    for f in sorted(os.listdir(DIR), reverse=True) if os.path.exists(DIR) else []:
        if not f.endswith(".json") or f.endswith((".transcript.json", ".analysis.json")) or not f[:8].isdigit():
            continue
        rid = f[:-5]
        if os.path.exists(os.path.join(DIR, rid + ".transcript.json")) and not _team_left(rid):
            continue
        try:
            with open(os.path.join(DIR, f), encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            continue
        if m.get("practice") or m.get("silent") or (m.get("duration") or 0) < 60 or time.time() - (m.get("start") or 0) > max_days * 86400                 or not str(m.get("map") or "").startswith(("de_", "cs_")):   # a workshop or training map: no match to line up with
            continue
        out.append(rid)
    return out


def resume_pending(skip=()):
    """Nothing records nor transcribes: the newest recording a match stopped is transcribed now (the next match stops
    it again). -> its id, or None."""
    if REC.recording() or transcribing():
        return None
    for rid in pending():
        if rid not in skip:
            return rid if start_transcription(rid) else None
    return None


def pause_transcription():
    """A new match starts: stop the transcription (resume_pending does it again later) to keep all the power for the game."""
    if JOB["proc"] and JOB["proc"].poll() is None:
        JOB["proc"].terminate()
        JOB.update(proc=None, id=None)


HALLUCINATIONS = re.compile(r"merci d'avoir regard|sous-titr|abonnez|à bientôt pour|merci de votre attention|n'oubliez pas de|amara\.org", re.I)


def _prompt(map_name, lang="fr"):
    words = ["Counter-Strike", "coach", "flash", "smoke", "molotov", "HE", "lurk", "rotate", "retake", "site A", "site B", "mid", "full buy", "éco", "force",
             "drop", "AWP", "heaven", "ramp", "long", "short", "one shot", "il est à 80"]
    words += ["site clear", "good job", "nice try", "last one", "one more", "low HP"] if lang == "en" else ["bien joué", "perdu", "énervé", "confiant", "bloqué"]
    try:
        from wily.coaching import plan
        z = (plan.zone_refs().get(map_name or "") or {}).get("zones", [])
        words += [x["name"] for x in z][:40]
    except Exception:
        pass
    return ("Counter-Strike calls: " if lang == "en" else "Calls de Counter-Strike : ") + ", ".join(words) + "."


def _words(model, path, lang, map_name):
    segs, _ = model.transcribe(path, language=lang, vad_filter=True, word_timestamps=True, condition_on_previous_text=False,
                               initial_prompt=_prompt(map_name, lang))
    return [(w.start, w.end, w.word, w.probability) for s_ in segs if not HALLUCINATIONS.search(s_.text or "") for w in (s_.words or [])]


def _spans(words, gap=0.9):
    out, cur = [], None
    for w in words:
        if cur and w[0] - cur[1] <= gap:
            cur[1] = max(cur[1], w[1])
        else:
            if cur:
                out.append(cur)
            cur = [w[0], w[1]]
    if cur:
        out.append(cur)
    return out


def transcribe(rid):
    """Your microphone, then your team's sound when your team agreed to it (<id>.team.transcript.json). Only the team's
    part when your microphone's is done (a match stopped the job between the two)."""
    team = os.path.exists(os.path.join(DIR, rid + ".team.flac"))
    n = None
    if not (team and _team_left(rid) and os.path.exists(os.path.join(DIR, rid + ".transcript.json"))):
        n = transcribe_file(rid)
    if team:
        transcribe_file(rid, team=True)
    return n


def _team_left(rid):
    """Your team's sound recorded and not transcribed yet."""
    return os.path.exists(os.path.join(DIR, rid + ".team.flac")) and not os.path.exists(os.path.join(DIR, rid + ".team.transcript.json"))


def transcribe_file(rid, team=False):
    """Two passes over the recording, one in French and one in English (Whisper translates what isn't in the language
    it is told: "site clear" became "cité claire"). The phrases of both passes are lined up, and each keeps the pass
    whose words the model is surest of (mean log-probability): your English calls stay English, your French stays
    French. team: the team's sound (their times start when it was switched on: meta["team"]["on"])."""
    import math
    meta = json.load(open(os.path.join(DIR, rid + ".json"), encoding="utf-8"))
    from faster_whisper import WhisperModel
    threads = int(os.environ.get("COACH_TX_THREADS") or min(8, os.cpu_count() or 4))   # fewer when it runs next to a match
    model = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=threads)
    path = os.path.join(DIR, rid + ".team.flac" if team else meta["file"])
    W = {lang: _words(model, path, lang, meta.get("map")) for lang in ("fr", "en")}
    spans = sorted(_spans(W["fr"]) + _spans(W["en"]))
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 0.3:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        best = None
        for lang, ws in W.items():
            sel = [w for w in ws if w[0] >= a - 0.05 and w[1] <= b + 0.05]
            if not sel:
                continue
            score = sum(math.log(max(w[3], 1e-4)) for w in sel) / len(sel)
            if best is None or score > best[0]:
                best = (score, lang, sel)
        if not best:
            continue
        text = "".join(w[2] for w in best[2]).strip()
        if text and not HALLUCINATIONS.search(text):
            out.append({"start": round(best[2][0][0], 2), "end": round(best[2][-1][1], 2), "text": text, "lang": best[1],
                        "p": round(best[0], 2)})
    json.dump({"id": rid, "model": MODEL, "bilingual": True, "time": dt.datetime.now().isoformat(timespec="minutes"), "utterances": out,
               **({"team": True, "offset": (meta.get("team") or {}).get("on", 0)} if team else {})},
              open(os.path.join(DIR, rid + (".team.transcript.json" if team else ".transcript.json")), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(out)


def transcribe_mono(rid):
    meta = json.load(open(os.path.join(DIR, rid + ".json"), encoding="utf-8"))
    from faster_whisper import WhisperModel
    model = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=min(8, os.cpu_count() or 4))
    segs, info = model.transcribe(os.path.join(DIR, meta["file"]), language="fr", vad_filter=True, word_timestamps=True,
                                  condition_on_previous_text=False, initial_prompt=_prompt(meta.get("map")))
    words = [(w.start, w.end, w.word) for s in segs if not HALLUCINATIONS.search(s.text or "") for w in (s.words or [])]
    utts, cur = [], []
    for w in words:
        if cur and w[0] - cur[-1][1] > 0.9:
            utts.append(cur)
            cur = []
        cur.append(w)
    if cur:
        utts.append(cur)
    out = [{"start": round(u[0][0], 2), "end": round(u[-1][1], 2), "text": "".join(x[2] for x in u).strip()} for u in utts]
    out = [o for o in out if o["text"] and not HALLUCINATIONS.search(o["text"])]
    json.dump({"id": rid, "model": MODEL, "time": dt.datetime.now().isoformat(timespec="minutes"), "utterances": out},
              open(os.path.join(DIR, rid + ".transcript.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(out)


_REC = {"sig": None, "out": []}


def recordings():
    """The recordings, newest first: read again only when a file of the folder changed (16/10: read twice per plan)."""
    if not os.path.exists(DIR):
        return []
    with os.scandir(DIR) as it:
        sig = frozenset((e.name, e.stat().st_mtime_ns, e.stat().st_size) for e in it)
    if sig != _REC["sig"]:
        _REC.update(sig=sig, out=_recordings())
    return [dict(r) for r in _REC["out"]]


def _recordings():
    out = []
    here = set(os.listdir(DIR))   # 15/10: the folder read once (each file checked one by one on the hard disk: 27 s)
    for f in sorted(here, reverse=True):
        if f.endswith(".json") and f.count(".") == 1:   # a recording's own file (not its transcripts or analyses)
            m = json.load(open(os.path.join(DIR, f), encoding="utf-8"))
            rid = m["id"]
            a = os.path.join(DIR, rid + ".analysis.json")
            out.append({"id": rid, "start": m.get("start_iso"), "map": m.get("map"), "duration": m.get("duration"), "device": m.get("device"),
                        "rounds_marked": len({r.get("round") for r in m.get("rounds", [])}), "source": m.get("source"), "practice": bool(m.get("practice")),
                        "transcribed": rid + ".transcript.json" in here,
                        "silent": bool(m.get("silent")) or (m.get("peak") is not None and m["peak"] < 0.01), "peak": m.get("peak"),
                        "match": json.load(open(a, encoding="utf-8")).get("match") if rid + ".analysis.json" in here else None,
                        "audio": m["file"] in here,
                        "team": (m.get("team") or {}).get("consent")})
    return out


def delete(rid):
    for ext in (".flac", ".json", ".transcript.json", ".analysis.json", ".log", ".team.flac", ".team.transcript.json", ".team.analysis.json",
                ".heard.analysis.json"):
        f = os.path.join(DIR, rid + ext)
        if os.path.exists(f):
            os.remove(f)


# ---------- analysis ----------
# how many, in French and in English (04/10: "two short", "three mid" did not count as complete calls in English lobbies).
# 07/10 (the Nuke match of 00:28, "pas dingue": its "best calls" were "je me suis réveillé à 9h", "j'ai refait une nuit,
# ça m'a dégoûté"): a count is one only next to a place ("un B", "3 outside": "une nuit" is an article), a damage only
# in its call forms ("il est à 20", "80 HP": never a time, "à 9h")
NUM = r"\b(un|une|deux|trois|quatre|cinq|[1-5]|tous|toute l'équipe|full|personne|seul|one|two|three|four|five|both|nobody|alone|everyone)\b"
NUM_STRONG = re.compile(r"^(deux|trois|quatre|cinq|[2-5]|two|three|four|five|full|stack|tous|both|everyone)$")
NUM_WEAK = re.compile(r"^(un|une|one|1|seul|personne|nobody|alone|aucun|last|dernier|dernière)$")
DMG = (r"(?<!pas )\btouch[ée]e?s?\b|\btagged\b|\bone ?shot\b|\b(?:he'?s|is|il est|very|one|more) low\b|\blow hp\b|"
       r"\b(?:il est|elle est|est|reste|il lui reste|lui reste)\s+(?:à\s+)?\d{1,3}\b(?!\s*(?:h\b|heures?|min|sec|s\b|%|ans?\b))|"
       r"\b\d{1,3}\s*(?:hp|pv)\b|\bmoins\s+\d{2,3}\b")
UTIL = r"\b(flash|flashe|flashes|smoke|smokes|smok|molo|molotov|incendiaire|grenade|stuff|nade|decoy|une he|la he|ma he|he grenade)\b"
PLAN = r"\b(on (va|part|joue|fait|rush|push|exec|tourne|save|sauve|reste)|rush|push|exec|default|split|fake|save|sauve|éco|eco|force|full ?buy|drop|stack|retake|rotate|tourne|rotation|attends|go)\b"
TILT = r"\b(putain|bordel|merde|nuls?|c'est pas possible|sérieux|fdp|ta gueule|ff|abusé|n'importe quoi)\b"
GENERIC_POS = ["a", "b", "mid", "milieu", "site", "long", "short", "court", "banane", "banana", "apps", "pit", "arch", "connector", "palace", "jungle",
               "window", "fenêtre", "ramp", "rampe", "heaven", "hell", "outside", "lobby", "silo", "hut", "squeaky", "secret", "vent", "vents", "mini",
               "garage", "rafters", "catwalk", "tunnel", "tunnels", "canal", "bridge", "pont", "ruins", "alley", "spawn", "ct", "t", "boîte", "box",
               "car", "voiture", "truck", "camion", "tree", "arbre", "sun", "stairs", "escalier", "back", "fond", "top", "bas", "haut", "upper", "lower"]


# places only in their call forms: alone they are French words ("il a", "t'as", "car" = because, "en bas", "c'est long")
AMBIG = {"a", "b", "t", "car", "court", "fond", "bas", "haut", "long", "top", "back", "site", "main"}
CALL_FORMS = [
    (re.compile(r"\b(?:en|d'en|par en) (haut|bas)\b"), r"en\1"),
    (re.compile(r"\b(?:(?:le|en|sur|au|du|de|vers|par) long|long (?:sitea|siteb|doors?|corner|coin|a|b))\b"), "long_"),
    (re.compile(r"\b(?:(?:le|en|sur|au|du|de) court|court (?:sitea|siteb|a|b))\b"), "court_"),
    (re.compile(r"\b(?:(?:le|sur|en|du|au|on|dans le) site|site (?:sitea|siteb|a|b)|(?:sitea|siteb) site)\b"), "site_"),
    (re.compile(r"\btop (?:main|mid|milieu|ramp|rampe|site|of \w+)\b"), "top_"),
    (re.compile(r"\b(?:back (?:site|sitea|siteb|a|b|plat|plateau))\b"), "back_"),
    (re.compile(r"\b(?:au|le) fond (?:du site|de site|site|sitea|siteb)\b"), "fond_"),
    (re.compile(r"\b(?:t spawn|spawn t|côté t|t side)\b"), "tspawn_"),
    (re.compile(r"\b(?:(?:a|b) main|main (?:a|b))\b"), "main_"),
]
SITE_LOWER = re.compile(r"\b(?:site|rush|go|push|exec|full|stack|côté|cote|sur|vers|long|short)\s+([ab])\b|\b([ab])\s+(?:site|long|short|main|ramp|rampe)\b|\ben b\b")


def _call_text(text):
    """The phrase as the call analysis reads it: the sites A and B marked when the transcription wrote them as sites
    (capital letters, "site A", "rush B", "on part à"), the places that are French words kept in their call forms only."""
    t = re.sub(r"(?<![\w'’])([AB])(?![\w'’])", lambda m: f" site{m.group(1).lower()} ", text)   # "rush B", "Last B", "un B"
    t = normalize(t)
    t = re.sub(r"\b(part|va|joue|fait|rush|push|exec|tourne|sur|en)\s+à(?=\s*(?:[,.!?;]|$|\s+(?:long|short|site|main|direct|rush|go)\b))", r"\1 sitea", t)
    t = SITE_LOWER.sub(lambda m: m.group(0).replace(" a", " sitea").replace(" b", " siteb").replace("a ", "sitea ", 1) if m.group(2) else
                       m.group(0)[:-1] + "site" + m.group(0)[-1], t)
    for rx, rep in CALL_FORMS:
        t = rx.sub(lambda m: " " + re.sub(r"\W+", "_", m.group(0)) + "_ ", t) if rep.endswith("_") else rx.sub(rep, t)
    return t


def _pos_re(map_name):
    words = set(GENERIC_POS)
    try:
        from wily.coaching import plan
        for z in (plan.zone_refs().get(map_name or "") or {}).get("zones", []):
            for w in re.findall(r"[a-zà-ÿ]+", z["name"].lower()):
                if len(w) >= 3 or w in ("a", "b"):
                    words.add(w)
    except Exception:
        pass
    words = {w for w in words if w not in AMBIG} | {"sitea", "siteb", "enhaut", "enbas"}
    # a call form ("long_a_", "top_main_", "site_b_") is one token: any word that ends with "_"
    return re.compile(r"\b(" + "|".join(sorted(map(re.escape, words), key=len, reverse=True)) + r"|\w+_)(?![\w])", re.I)


def normalize(text):
    t = text.lower()
    t = re.sub(r"(\d)([a-z])", r"\1 \2", t)
    t = re.sub(r"([a-z])(\d)", r"\1 \2", t)
    t = re.sub(r"\b(part|va|joue|fait|rush|push|exec|tourne|site|sur|en)\s+à\b", r"\1 a", t)  # "on part à" = site A
    return t


def classify(text, pos_re):
    """info: a place or a damage; complete: where AND how many (the count next to the place: "deux B", "3 outside",
    "un silo, un rampe") or the damage; util: a grenade named."""
    t = _call_text(text)
    toks = re.findall(r"[\w']+", t)
    at = [i for i, w in enumerate(toks) if pos_re.fullmatch(w)]
    dmg = bool(re.search(DMG, t))
    near = lambda i, k: any(abs(i - j) <= k for j in at)
    counted = any((NUM_STRONG.match(w) and near(i, 4)) or (NUM_WEAK.match(w) and near(i, 2)) for i, w in enumerate(toks))
    tn = normalize(text)
    return {"info": bool(at) or dmg, "complete": (bool(at) and counted) or dmg, "util": bool(re.search(UTIL, tn)) or bool(re.search(r"(?<![\w'])HE(?![\w'])", text)),
            "plan": bool(re.search(PLAN, tn)), "tilt": bool(re.search(TILT, tn))}


def _examples(utts, n=4):
    """The best calls of a match: complete and short (a call is a few words; a long phrase is talk), the shortest
    first, each once."""
    seen, out = set(), []
    for u in sorted((u for u in utts if u["complete"] and 1 <= len(u["text"].split()) <= 12), key=lambda u: (len(u["text"].split()), u["start"])):
        k = re.sub(r"\W+", " ", u["text"].lower()).strip()
        if k and k not in seen:
            seen.add(k)
            out.append(u["text"].strip())
        if len(out) >= n:
            break
    return out


# what a phrase says about how you feel. Said on purpose: "coach" then one word ("coach, perdu", "coach confiant");
# otherwise read from the words: frustration (with the team, with yourself, or plain), doubt, suspicion, positive
COACH_RE = re.compile(r"^\W*(?:coach|coache|coatch|couch|koch|kosh|coch|coche)\b[\s,.:;!-]*(.*)$", re.I)
COACH_ANY = re.compile(r"\b(?:coach|coache|coatch)\b", re.I)   # anywhere: "round coach plutôt satisfait", "coach premier round ok, coach deuxième mitigé"
# an order to Wily (06/10, "Wily exec B stuff", "Jarvis contre rush B 5 stack"): wily.WAKE, read again in French with
# the orders' words so "post-plant B" doesn't come out "post plain blade"
WILY_ANY = re.compile(r"\b(?:wh?[iy]l+(?:y|ie|i|ey|ier|is|ee)|wylie|wiley|wili|wall?(?:y|i|ie|ey)|woll?(?:y|ie)|woody|jarv[iy]s|jerv[iy]s|jarvi)", re.I)
WILY_PROMPT = ("Wily, rush A. Wily, exec B stuff. Wily, post-plant B. Wily, fake A go B. Wily, force-buy A. Wily, anti-éco B. "
               "Wily, pistol round. Wily, contre rush B five stack. Wily, fake défense A. Wily, reprise jungle. "
               "Wily, j'ai vu trois rounds en B. Wily, tendance à fake. Wily, trois A sans bombe. Wily, cover mid. Wily, contrôle map.")
COACH_WORDS = {
    "frustration": ["énervé", "énervée", "enervé", "tilt", "tilté", "frustré", "rage", "saoulé", "soûlé", "agacé", "dégoûté", "nul", "bloqué",
                    "déçu", "mauvais", "raté", "pas content", "pas satisfait",
                    "seul", "lâché", "bait", "baité", "angry", "tilted", "frustrated", "blocked", "alone", "mad", "annoyed"],
    "doubt": ["perdu", "paumé", "doute", "hésite", "hésitant", "confus", "stressé", "stress", "tendu", "fatigué", "crevé", "lent", "lost",
              "mitigé", "moyen", "bof", "pas sûr", "incertain",
              "confused", "stressed", "tired", "unsure", "nervous"],
    "positive": ["confiant", "chaud", "bien", "serein", "calme", "facile", "fort", "à l'aise", "focus", "concentré", "en forme", "confident",
                 "satisfait", "content", "ok", "propre", "réussi", "solide", "bon round",
                 "good", "calm", "easy", "focused", "great", "comfortable"],
    "suspicion": ["cheat", "cheater", "cheateur", "triche", "tricheur", "wallhack", "suspect", "aimbot"],
}
MOOD_RE = [
    ("suspicion", None, r"\b(cheat\w*|wall ?hack|aimbot|spinbot|trich\w+|utilisateur suspect|suspect)\b"),
    ("frustration", "team", r"(\bbloqu\w+|\bm'a bloqu|\bme bloqu|\bbait\w*|pique après|peek après|t'es mute|tu parles pas|arrête de (peek|regarder)|"
                            r"pourquoi tu|ta smoke|smoke (est |qui )?(mal|pue)|fake info|stop peek)"),
    ("frustration", "self", r"(j'ai pas touché|pas touché (un|une|de)|mourir trop tôt|c'est moi qui ai pris|je suis (nul|la salope|éclaté)|"
                            r"\bmy bad\b|ma faute|j'ai raté)"),
    ("frustration", None, TILT[:-3] + r"|j'en peux plus|ferme ta gueule|ta mère|\bpute\b|fils de|stupide|\bfuck\w*|\bshit\b|\bwtf\b|"
                          r"dans mes veines|ça me met bien|ah vas-y)\b"),
    ("doubt", None, r"(qu'est-ce qu'on fait|on fait quoi|je sais pas|j'sais pas|aucune idée|je comprends (pas|rien)|j'comprends pas|"
                    r"c'est quoi ce|\bpourquoi\b|\bbizarre\b|\bétrange\b|"
                    r"what do we do|\bperdu\b|\bpaumé\b)"),
    ("positive", None, r"\b(nickel|facile|easy|let'?s go|on les a|trop fort|parfait|good job|gg|bien joué|bien fait|nice|bon travail)\b"),
]
MOOD_RE = [(k, sb, re.compile(rx, re.I)) for k, sb, rx in MOOD_RE]
MOODS = ("frustration", "doubt", "suspicion", "positive")


def _coach_word(rest):
    """The feeling in what follows "coach": the first word of the lists found in it (a "pas" just before a positive
    word makes it a frustration: "pas content"); nothing known: a note, kept as said."""
    best = None
    for kind, words in COACH_WORDS.items():
        for w in words:
            m = re.search(r"(?<![a-zà-ÿ])" + re.escape(w) + r"(?![a-zà-ÿ])", rest)
            if m and (best is None or m.start() < best[0]):
                k = kind
                if kind == "positive" and re.search(r"\bpas (très |trop |vraiment )?$", rest[:m.start()]):
                    k = "frustration"
                best = (m.start(), k, w)
    if not best:
        return {"kind": "note", "sub": None, "word": rest.strip(" ,.")[:40], "coach": True} if rest.strip(" ,.") else None
    sb = "team" if best[2] in ("bloqué", "seul", "lâché", "bait", "baité", "blocked", "alone") else None
    return {"kind": best[1], "sub": sb, "word": best[2], "coach": True}


def mood_all(text):
    """Every feeling of a phrase: each "coach …" part on its own (one phrase can say two), else the one read from the
    words."""
    t = (text or "").strip()
    parts = COACH_ANY.split(t)
    if len(parts) > 1:
        return [m for m in (_coach_word(normalize(p_)) for p_ in parts[1:]) if m]
    m = mood_of(t)
    return [m] if m else []


ANALYSIS_V = 5   # bump when the analysis changes: mood_stats analyzes the older ones again (5: real calls only, 07/10)


def mood_of(text):
    """-> {"kind", "sub", "word", "coach"} or None (the first feeling of the phrase)."""
    t = (text or "").strip()
    if COACH_ANY.search(t):
        for p_ in COACH_ANY.split(t)[1:]:
            m = _coach_word(normalize(p_))
            if m:
                return m
        return None
    tl = normalize(t)
    for kind, sb, rx in MOOD_RE:
        mm = rx.search(tl)
        if mm:
            return {"kind": kind, "sub": sb, "word": mm.group(0)[:30], "coach": False}
    return None


def _match_for(meta, sid):
    """The analyzed match played during this recording (same map, start time inside the recording)."""
    from wily.app import pipeline
    from wily.core import ledger
    reg = pipeline.registry_view()   # read only
    facts = ledger.match_facts()   # 16/10: each match's map without its meta.json (119 opened per recording)
    start, end = meta["start"], meta.get("end") or meta["start"] + 3600
    first = min([e.get("round") for e in meta.get("rounds") or [] if e.get("round")] or [1])
    back = 15 * 60 + max(0, first - 1) * 120   # a recording that starts mid-match (the server restarted, a reconnect): its match began earlier
    best = None
    for mid in pipeline.player_matches(int(sid)):
        r = reg.get(mid) or {}
        mp = (facts.get(mid) or {}).get("map")
        if not r.get("time") or (meta.get("map") and mp and mp != meta["map"]):
            continue
        t = dt.datetime.fromisoformat(r["time"]).timestamp()
        if start - back <= t <= end:
            d = abs(t - start)
            if best is None or d < best[0]:
                best = (d, mid)
    return best[1] if best else None


def analyze(rid, sid):
    """Calls of one recording, aligned on the rounds of its match."""
    import pandas as pd
    meta = json.load(open(os.path.join(DIR, rid + ".json"), encoding="utf-8"))
    tf = os.path.join(DIR, rid + ".transcript.json")
    if not os.path.exists(tf):
        return None
    utts = json.load(open(tf, encoding="utf-8"))["utterances"]
    pos_re = _pos_re(meta.get("map"))
    for u in utts:
        u.update(classify(u["text"], pos_re))
        u["moods"] = mood_all(u["text"])
        u["mood"] = u["moods"][0] if u["moods"] else None
    mid = _match_for(meta, sid)
    # round windows from the game's marks: live start of each round, in seconds of recording
    marks = meta.get("rounds") or []
    if not any(e.get("phase") == "live" for e in marks):  # manual recording: take the rounds from the game's timeline
        from wily.live import gsi
        marks = [dict(e, t=round(e["t"] - meta["start"], 2)) for e in gsi.timeline(meta["start"] - 5, meta.get("end") or meta["start"] + 4 * 3600)]
        if marks and not meta.get("map"):
            meta["map"] = next((e.get("map") for e in marks if e.get("map")), None)
    live = {}
    for e in marks:
        if e.get("phase") == "live" and e.get("round") and e["round"] not in live:
            live[e["round"]] = e["t"]
    starts = sorted(live.items())
    rounds = []
    died, clutch_windows, throws = {}, {}, []
    L = None
    if mid and starts:
        d = os.path.join(config.DEEP, mid)
        L = pd.read_parquet(os.path.join(d, "loadout.parquet")) if os.path.exists(os.path.join(d, "loadout.parquet")) else None
        D = pd.read_parquet(os.path.join(d, "duels.parquet")) if os.path.exists(os.path.join(d, "duels.parquet")) else None
        G = pd.read_parquet(os.path.join(d, "grenades.parquet")) if os.path.exists(os.path.join(d, "grenades.parquet")) else None
        S = pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["steamid", "side", "round"]) if os.path.exists(os.path.join(d, "samples.parquet")) else None
        me = int(sid)
        if L is not None:
            for _, x in L[L.steamid == me].iterrows():
                if pd.notna(x.died_t):
                    died[int(x["round"])] = float(x.died_t)
        if D is not None and S is not None:
            for r, g in D.sort_values("tick").groupby("round"):
                r = int(r)
                side_of = S[S["round"] == r].drop_duplicates("steamid").set_index("steamid")["side"].to_dict()
                my_side = side_of.get(me)
                if my_side is None or r not in died:
                    continue
                mates = [p for p, sd in side_of.items() if sd == my_side]
                alive = set(mates)
                for _, k in g.iterrows():
                    alive.discard(int(k.victim))
                    if len(alive) == 1 and me not in alive and k.t >= died[r]:
                        clutch_windows[r] = float(k.t)  # a teammate is alone from this moment
                        break
        if G is not None:
            throws = [(int(x["round"]), float(x.t), x["type"]) for _, x in G[G.thrower == int(sid)].iterrows()]
    for i, (r, t0) in enumerate(starts):
        t1 = starts[i + 1][1] - 16 if i + 1 < len(starts) else (meta.get("duration") or t0 + 115)
        us = [u for u in utts if t0 - 16 <= u["start"] < t1]
        dt_ = died.get(r)
        alive_us = [u for u in us if u["start"] >= t0 and (dt_ is None or u["start"] <= t0 + dt_)]
        before_death = [u for u in us if dt_ is not None and t0 + dt_ - 10 <= u["start"] <= t0 + dt_ + 1.5]
        dead_us = [u for u in us if dt_ is not None and u["start"] > t0 + dt_ + 1.5]
        cl = clutch_windows.get(r)
        clutch_talk = [u for u in dead_us if cl is not None and u["start"] >= t0 + cl]
        buy_us = [u for u in us if u["start"] < t0]
        announced = sum(1 for (rr, tt, typ) in throws if rr == r and any(u["util"] and t0 + tt - 6 <= u["start"] <= t0 + tt + 0.5 for u in us))
        n_throws = sum(1 for (rr, _, _) in throws if rr == r)
        xr = L[(L.steamid == int(sid)) & (L["round"] == r)] if L is not None else None
        xr = xr.iloc[0] if xr is not None and len(xr) else None
        rounds.append({"round": r, "side": xr.side if xr is not None else None, "won": bool(xr.won) if xr is not None else None,
                       "dmg": int(xr.damage) if xr is not None else None, "kills": int(xr.kills) if xr is not None else None,
                       "moods": [{"t": round(u["start"] - t0, 1), **mo} for u in us for mo in u.get("moods") or []],
                       "died_t": dt_, "calls": len(us), "alive_calls": len(alive_us), "info_before_death": any(u["info"] for u in before_death),
                       "dead_calls": len(dead_us), "clutch_talk": len(clutch_talk), "buy_calls": len(buy_us), "throws": n_throws, "announced": announced,
                       "texts": [{"t": round(u["start"] - t0, 1), "text": u["text"], "kind": "tilt" if u["tilt"] else "info" if u["info"] else "util" if u["util"] else "plan" if u["plan"] else ""} for u in us]})
    n = len(utts)
    tot = lambda k: sum(1 for u in utts if u[k])
    rr = [r for r in rounds]
    deaths = [r for r in rr if r["died_t"] is not None]
    thr = sum(r["throws"] for r in rr)
    res = {"id": rid, "match": mid, "map": meta.get("map"), "start": meta.get("start_iso"), "duration": meta.get("duration"),
           "aligned": bool(rounds), "utterances": n, "speech_s": round(sum(u["end"] - u["start"] for u in utts)),
           "info": tot("info"), "complete": tot("complete"), "util": tot("util"), "plan": tot("plan"), "tilt": tot("tilt"),
           "complete_share": round(100 * tot("complete") / max(tot("info"), 1)),
           "rounds": rr, "rounds_n": len(rr),
           "silent_rounds": sum(1 for r in rr if r["alive_calls"] == 0),
           "silent_deaths": sum(1 for r in deaths if not r["info_before_death"]), "deaths": len(deaths),
           "clutch_talk_rounds": sum(1 for r in rr if r["clutch_talk"]), "clutch_rounds": sum(1 for r in rr if r["round"] in clutch_windows),
           "throws": thr, "announced": sum(r["announced"] for r in rr),
           "examples": _examples(utts),
           "tilt_rounds": [r["round"] for r in rr if any(x["kind"] == "tilt" for x in r["texts"])][:6],
           "moods": {k: sum(1 for u in utts for mo in u.get("moods") or [] if mo["kind"] == k) for k in MOODS + ("note",)}}
    if mid and live:
        res.update(_heard(rid, meta, mid, sid, live, utts))
    res["tip_k"], res["tips"] = tips(res)   # tip_k: each tip's English (the page picks its own by it)
    res["v"] = ANALYSIS_V
    json.dump(res, open(os.path.join(DIR, rid + ".analysis.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res


def _heard(rid, meta, mid, sid, live, utts):
    """What your team could hear in the match (its demo) and what you did with it; after your team's calls, where you
    went (when your team agreed to the team sound). Kept in <id>.heard.analysis.json until the transcripts change."""
    from wily.live import heard
    tt = os.path.join(DIR, rid + ".team.transcript.json")
    key = [mid, str(sid), os.path.getmtime(os.path.join(DIR, rid + ".transcript.json")),
           os.path.getmtime(tt) if os.path.exists(tt) else None, HEARD_V]
    cf = os.path.join(DIR, rid + ".heard.analysis.json")
    try:
        c = json.load(open(cf, encoding="utf-8"))
        if c.get("key") == key:
            return c["res"]
    except Exception:
        pass
    out = {}
    try:
        team_u = json.load(open(tt, encoding="utf-8"))["utterances"] if os.path.exists(tt) else None
        off = float((meta.get("team") or {}).get("on") or 0.0)
        out["heard"] = heard.analyze(mid, sid, live, utts, team_u, off, meta.get("map"))
        if team_u:
            out["team_calls"] = heard.after_calls(mid, sid, live, team_u, off, meta.get("map"))
    except Exception as e:
        print("what you heard: analysis impossible:", e, flush=True)
        return {}
    json.dump({"key": key, "res": out}, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
    return out


# tips(): their keys, for tools/i18n_extract.py
_TIPS = [N_("{n} deaths out of {m} without any info in the 10 s before: call what you see before taking the duel, not after."),
         N_("Only {p}% of your calls say where AND how many (or the damage): 'two B, one tagged for 80' rather than 'they're B'."),
         N_("{n} grenades called out of {m}: say 'flash' before throwing it, your teammates turn away."),
         N_("You talked during {n} teammate clutch(es): one useful piece of info, then silence."),
         N_("{n} frustrated phrases: after a mistake, one breath, then one useful piece of info for the team."),
         N_("No call in {n} rounds out of {m}: even when lurking, call what you hear (rotations, steps)."),
         N_("Your calls are clean: keep saying where, how many and what you are going to do.")]


def tips(a):
    """-> (the tips in English, the tips in the player's language): the page finds its own by their English."""
    T = []

    def add(key, **kw):
        T.append((key.format(**kw), tr(key, **kw)))
    if a["aligned"] and a["deaths"] and a["silent_deaths"] / a["deaths"] >= 0.4:
        add("{n} deaths out of {m} without any info in the 10 s before: call what you see before taking the duel, not after.", n=a['silent_deaths'], m=a['deaths'])
    if a["info"] >= 5 and a["complete_share"] < 50:
        add("Only {p}% of your calls say where AND how many (or the damage): 'two B, one tagged for 80' rather than 'they're B'.", p=a['complete_share'])
    if a["throws"] >= 4 and a["announced"] / a["throws"] < 0.5:
        add("{n} grenades called out of {m}: say 'flash' before throwing it, your teammates turn away.", n=a['announced'], m=a['throws'])
    if a["clutch_talk_rounds"]:
        add("You talked during {n} teammate clutch(es): one useful piece of info, then silence.", n=a['clutch_talk_rounds'])
    if a["tilt"] >= 3:
        add("{n} frustrated phrases: after a mistake, one breath, then one useful piece of info for the team.", n=a['tilt'])
    if a["aligned"] and a["rounds_n"] and a["silent_rounds"] / a["rounds_n"] >= 0.4:
        add("No call in {n} rounds out of {m}: even when lurking, call what you hear (rotations, steps).", n=a['silent_rounds'], m=a['rounds_n'])
    if not T:
        add("Your calls are clean: keep saying where, how many and what you are going to do.")
    return [k for k, _ in T], [t for _, t in T]


def mood_stats(sid):
    """Every aligned recording of the player: the rounds after a frustrated moment (the 3 next rounds) against the
    others, damage per round and rounds won. None under 10 such rounds."""
    rows = []
    for r in recordings():
        if not r["transcribed"] or r.get("practice"):
            continue
        try:
            m = json.load(open(os.path.join(DIR, r["id"] + ".json"), encoding="utf-8"))
            if m.get("steamid") and str(m["steamid"]) != str(sid):
                continue
            f = os.path.join(DIR, r["id"] + ".analysis.json")
            a = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None
            if a is None or a.get("v") != ANALYSIS_V:
                a = analyze(r["id"], sid)
        except Exception:
            a = None
        if not a or not a.get("match") or not a.get("aligned"):
            continue
        rs = [x for x in a["rounds"] if x.get("dmg") is not None]
        frus = {x["round"] for x in rs if any(mo["kind"] == "frustration" for mo in x.get("moods", []))}
        for x in rs:
            rows.append((any(x["round"] - k in frus for k in (1, 2, 3)), x["dmg"], bool(x["won"])))
    A, O = [r for r in rows if r[0]], [r for r in rows if not r[0]]
    if len(A) < 10 or len(O) < 10:
        return None
    f_ = lambda R: {"n": len(R), "adr": round(sum(r[1] for r in R) / len(R)), "won": round(100 * sum(r[2] for r in R) / len(R))}
    return {"after": f_(A), "other": f_(O)}


def summary(sid, limit=6):
    """Latest analyzed recordings of a player, for the plan."""
    out = []
    for r in recordings():
        m = json.load(open(os.path.join(DIR, r["id"] + ".json"), encoding="utf-8"))
        if m.get("steamid") and str(m["steamid"]) != str(sid):
            continue
        if r["transcribed"] and not r.get("silent"):
            try:
                a = analyze(r["id"], sid)
            except Exception as e:
                print("call analysis impossible:", e)
                a = None
            if a:
                out.append(a)
        if len(out) >= limit:
            break
    return out


# ---------- your calls, live ----------
# The calls you already make ("3 B", "rush A", "bombe B", "un Banana") count like a tap on the T read, without a click.
# Only short utterances (a call, not a sentence: dictation is long), transcribed by a low-priority child process on
# the CPU (the graphics card stays for the game). Measured on your own calls: large-v2 takes 10-25 s for a 3 s call on
# 4 cores, small about 1.6 s on 6, base 0.6 s but it gets the words wrong. It listens in English: your callouts are
# English words, and French gets written the English way ("trois" -> "three", "en bas" -> "down").
LIVE_MODEL = "small"
LIVE_THREADS = 6
LIVE_MAX_S, LIVE_MIN_S = 4.5, 0.25
LIVE_FLOOR = 0.003   # speech of a desk microphone can peak at 0.01 RMS


class _Segmenter:
    """Cuts the microphone into utterances (speech, then half a second of silence). A sentence longer than 4.5 s is
    not a call: skipped up to the next silence."""
    def __init__(self, rate, on_utt):
        self.rate, self.on_utt = rate, on_utt
        self.noise, self.buf, self.voiced, self.sil, self.t0, self.skip, self.e = 0.0008, [], 0.0, 0.0, None, False, 0.0

    def feed(self, block, now):
        import numpy as np
        if not len(block):
            return
        dur = len(block) / self.rate
        rms = float(np.sqrt(np.mean(block * block)))
        if rms > max(LIVE_FLOOR, self.noise * 4):
            if not self.buf and not self.skip:
                self.t0 = now - dur
            if not self.skip:
                self.buf.append(block)
            self.voiced += dur
            self.e += rms * rms * dur
            self.sil = 0.0
        else:
            if not self.buf and not self.skip:
                self.noise = 0.98 * self.noise + 0.02 * rms
                return
            self.sil += dur
            if not self.skip:
                self.buf.append(block)
            if self.sil >= 0.5:
                self._flush()
                return
        if not self.skip and sum(len(b) for b in self.buf) / self.rate > LIVE_MAX_S + 0.5:
            self.buf, self.skip = [], True   # a sentence: not a call

    def _flush(self):
        import numpy as np
        buf, voiced, t0, skip, e = self.buf, self.voiced, self.t0, self.skip, self.e
        self.buf, self.voiced, self.sil, self.skip, self.e = [], 0.0, 0.0, False, 0.0
        if skip or not buf or voiced < LIVE_MIN_S:
            return
        a = np.concatenate(buf)
        if self.rate != SR:
            x = np.linspace(0, len(a) - 1, int(len(a) * SR / self.rate))
            a = np.interp(x, np.arange(len(a)), a)
        try:
            self.on_utt(a.astype("float32"), t0, (e / voiced) ** 0.5 if voiced else 0.0)
        except Exception:
            pass


class LiveCalls:
    def __init__(self):
        import queue
        self.q = queue.Queue(maxsize=3)
        self.proc, self.map, self.pending, self.n, self.last, self.levels = None, None, 0, 0, None, []

    def running(self):
        return bool(self.proc and self.proc.poll() is None)

    def start(self, map_name):
        if not settings().get("live", True):
            return
        self.map = map_name
        if self.running():
            return
        try:
            flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            os.makedirs(DIR, exist_ok=True)
            self.proc = subprocess.Popen([sys.executable, "-m", "wily.live.voice", "live"], cwd=config.HERE,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=open(os.path.join(DIR, "live.log"), "w", encoding="utf-8"), creationflags=flags)
            self.pending = 0
            threading.Thread(target=self._send, args=(self.proc,), daemon=True).start()
            threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        except Exception as e:
            print("live calls unavailable:", e, flush=True)
            self.proc = None

    def stop(self):
        if self.running():
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None

    def push(self, audio, t0, rms=0.0):
        """From the microphone thread: never blocks (a call that waits too long is useless anyway). A shout (twice as
        loud as your usual speech, once 8 phrases are known) after your death or a lost round is a frustrated moment."""
        if rms:
            lv = sorted(self.levels)
            if len(lv) >= 8 and rms >= 2.2 * lv[len(lv) // 2]:
                try:
                    from wily.live import gsi
                    gsi.voice_heat(t0)
                except Exception:
                    pass
            self.levels = (self.levels + [rms])[-60:]
        if self.running() and self.pending < 2:
            try:
                self.q.put_nowait((audio, t0))
            except Exception:
                pass

    def _send(self, proc):
        while proc.poll() is None:
            try:
                audio, t0 = self.q.get(timeout=1)
            except Exception:
                continue
            try:
                self.pending += 1
                self.n += 1
                fr = False
                try:   # dead, between rounds or buying: what you say then is more often how you feel than a call
                    from wily.live import gsi
                    fr = (not gsi.STATE.get("_alive", True)) or gsi.STATE.get("round_phase") in ("over", "freezetime")
                except Exception:
                    pass
                proc.stdin.write((json.dumps({"id": self.n, "t": t0, "map": self.map, "n": int(len(audio)), "fr": fr}) + "\n").encode())
                proc.stdin.write(audio.astype("<f4").tobytes())
                proc.stdin.flush()
            except Exception:
                return

    def _read(self, proc):
        for line in proc.stdout:
            self.pending = max(0, self.pending - 1)
            try:
                r = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            orders = []
            follow = time.time() < getattr(self, "wily_until", 0)
            if r.get("wily_text") or (r.get("text") and WILY_ANY.search(r.get("text"))):   # said to Wily (06/10): an order, not a call
                try:
                    from wily.live import commands
                    zones = sorted({n for n, _ in _zone_vocab(r.get("map")).values()})
                    orders = commands.parse(r.get("wily_text") or "", zones) or commands.parse(r.get("text") or "", zones)
                except Exception as e:
                    print("wily:", e, flush=True)
            elif follow and r.get("text"):   # 8 s after an order to Wily: "Slow A", "go A slowly" go on without the name
                try:
                    from wily.live import commands
                    zones = sorted({n for n, _ in _zone_vocab(r.get("map")).values()})
                    orders = [o for o in commands.parse("Wily " + r["text"], zones) if o["k"] in ("dir", "tempo", "buy", "stuff", "exec", "fake", "split")]
                except Exception as e:
                    print("wily:", e, flush=True)
            if orders:
                self.wily_until = time.time() + 8
                self.last = {"text": r.get("wily_text") or r.get("text"), "s": r.get("s"), "parsed": None, "mood": None, "wily": orders}
                try:
                    from wily.live import gsi
                    gsi.wily(orders, r.get("wily_text") or r.get("text"), r.get("t"))
                except Exception as e:
                    print("wily order:", e, flush=True)
                continue
            p = parse_call(r.get("text") or "", r.get("map"))
            mo = mood_of(r.get("mood_text") or "") if r.get("mood_text") else None
            self.last = {"text": r.get("text"), "s": r.get("s"), "parsed": p, "mood": mo}
            if mo and mo["kind"] in MOODS:
                try:
                    from wily.live import gsi
                    gsi.voice_mood(mo, r.get("t"))
                except Exception as e:
                    print("live mood:", e, flush=True)
                continue
            if p:
                try:
                    from wily.live import gsi
                    gsi.voice_call(p, r.get("t"))
                except Exception as e:
                    print("live call:", e, flush=True)


LIVE = LiveCalls()


def _live_prompt(map_name):
    words = ["Wily", "A", "B", "mid", "one", "two", "three", "un", "deux", "trois", "rush", "bomb", "full"]
    try:
        from wily.coaching import plan
        words += [x["name"] for x in (plan.zone_refs().get(map_name or "") or {}).get("zones", [])][:30]
    except Exception:
        pass
    return "Calls: " + ", ".join(words) + "."


def live_loop():
    """Child process: utterances in on stdin (a JSON line, then the 16 kHz samples), their text out on stdout."""
    import numpy as np
    from faster_whisper import WhisperModel
    model = WhisperModel(LIVE_MODEL, device="cpu", compute_type="int8", cpu_threads=LIVE_THREADS)
    inp, prompts = sys.stdin.buffer, {}
    while True:
        line = inp.readline()
        if not line:
            break
        try:
            h = json.loads(line)
            a = np.frombuffer(inp.read(4 * int(h["n"])), dtype="<f4")
        except Exception:
            continue
        mp = h.get("map")
        if mp not in prompts:
            prompts[mp] = _live_prompt(mp)
        t = time.time()
        try:
            segs, _ = model.transcribe(a, language="en", beam_size=1, condition_on_previous_text=False, vad_filter=False,
                                       initial_prompt=prompts[mp], without_timestamps=True, max_new_tokens=20,
                                       temperature=0.0)   # no retries: a late call is useless
            # unsure (noise, a mumble): the model tends to repeat its prompt, dropped
            text = " ".join(x.text for x in segs if (x.no_speech_prob or 0) < 0.6 and (x.avg_logprob or 0) > -1.0).strip()
        except Exception as e:
            text = ""
            print("live transcription:", e, file=sys.stderr, flush=True)
        if HALLUCINATIONS.search(text):
            text = ""
        mood_text, wily_text = None, None
        if WILY_ANY.search(text):   # "Wily, fake défense A": an order to Wily, read again in French with its words (06/10)
            try:
                segs, _ = model.transcribe(a, language="fr", beam_size=1, condition_on_previous_text=False, vad_filter=False,
                                           initial_prompt=WILY_PROMPT, without_timestamps=True, max_new_tokens=32, temperature=0.0)
                wily_text = " ".join(x.text for x in segs).strip()
                if not WILY_ANY.search(wily_text):
                    wily_text = "Wily " + wily_text
            except Exception as e:
                print("live wily transcription:", e, file=sys.stderr, flush=True)
        elif COACH_ANY.search(text):   # "coach, perdu": the word said in French, read again in French
            try:
                segs, _ = model.transcribe(a, language="fr", beam_size=1, condition_on_previous_text=False, vad_filter=False,
                                           initial_prompt="Coach, perdu. Coach, confiant. Coach, énervé. Coach, bloqué. Coach, stressé. Coach, fatigué. Coach, cheat.",
                                           without_timestamps=True, max_new_tokens=12, temperature=0.0)
                fr = " ".join(x.text for x in segs).strip()
                mood_text = fr if COACH_ANY.search(fr) else "coach " + fr
            except Exception as e:
                print("live mood transcription:", e, file=sys.stderr, flush=True)
                mood_text = text
        elif h.get("fr") and len(a) >= SR // 2 and not parse_call(text, mp):   # not a call: read in French for how you feel
            try:
                segs, _ = model.transcribe(a, language="fr", beam_size=1, condition_on_previous_text=False, vad_filter=False,
                                           initial_prompt="Putain. Qu'est-ce qu'on fait ? Je comprends pas. Pourquoi tu peek ? Bien joué. Ah vas-y.",
                                           without_timestamps=True, max_new_tokens=24, temperature=0.0)
                fr_ = " ".join(x.text for x in segs if (x.no_speech_prob or 0) < 0.6 and (x.avg_logprob or 0) > -1.0).strip()
                mood_text = fr_ if fr_ and mood_of(fr_) else None
            except Exception as e:
                print("live mood transcription:", e, file=sys.stderr, flush=True)
        sys.stdout.write(json.dumps({"id": h.get("id"), "t": h.get("t"), "map": mp, "text": text, "mood_text": mood_text, "wily_text": wily_text,
                                     "s": round(time.time() - t, 2)}, ensure_ascii=False) + "\n")
        sys.stdout.flush()


# what a call says: a site, how many, a zone (with its side of the map), a rush, the bomb, one alone
CALL_NUM = {"un": 1, "une": 1, "1": 1, "deux": 2, "2": 2, "trois": 3, "3": 3, "quatre": 4, "4": 4, "cinq": 5, "5": 5, "full": 5, "tous": 5,
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}   # your calls mix French and English
LEVEL_SITE = {"de_nuke": {"bas": "B", "lower": "B", "down": "B", "downstairs": "B", "haut": "A", "upper": "A", "upstairs": "A"}}   # Nuke: B is downstairs
_VOCAB = {}


def _zone_vocab(map_name):
    """Spoken word -> (callout, side of the map) for a map: the words of its callouts, plus the French ones."""
    if map_name in _VOCAB:
        return _VOCAB[map_name]
    v = {}
    try:
        from wily.coaching import team
        from wily.demos.map_analysis import humanize
        for key, reg in ((team.map_meta().get(map_name) or {}).get("regions") or {}).items():
            name = humanize(key, map_name) if key != "?" else None
            if not name or "spawn" in name.lower():
                continue
            ws = re.findall(r"[a-zà-ÿ]+", name.lower())
            for w in ws:   # a one-word callout keeps its word even when it is a common one (Mirage's Short)
                if len(w) >= 4 and (len(ws) == 1 or w not in ("site", "main", "long", "short", "back", "upper", "lower", "middle", "side", "room")):
                    v.setdefault(w, (name, reg))
                if len(w) >= 8:
                    v.setdefault(w[:5], (name, reg))   # "under" for Underpass, "apart" for Apartments
    except Exception:
        pass
    fr = {"banane": "banana", "appart": "apps", "apparts": "apps", "apse": "apps", "appartements": "apartments", "rampe": "ramp", "fenêtre": "window",
          "palais": "palace", "connecteur": "connector", "tunnel": "tunnels", "pont": "bridge"}
    for w_fr, w_en in fr.items():
        if w_en in v and w_fr not in v:
            v[w_fr] = v[w_en]
    _VOCAB[map_name] = v
    return v


A_CTX = (r"(?:\b(?:en|sur|site|vers|bombe|bomb|rush|full|tous|sont|est|c'est|go|là|on|at|in|to|is|are)\s+"
         r"|\b(?:un|une|deux|trois|quatre|cinq|one|two|three|four|five|[1-5])\s+(?:en\s+|on\s+|at\s+)?)a\b"
         r"|\ba\s+(?:site|main|long|short)\b|^a(?:\s+a)*$")


def parse_call(text, map_name):
    """A short call ("3 B", "rush A", "bombe B", "un seul Banana") read for the T read; None for anything else (a
    sentence, small talk)."""
    if not text or HALLUCINATIONS.search(text):
        return None
    t = normalize(text).strip(" .!?,")
    words = [re.sub(r"'s$", "", w) for w in re.findall(r"[a-zà-ÿ0-9']+", t)]
    if not words or len(words) > 8:
        return None
    site = "B" if re.search(r"\b(b|bé|bee)\b", t) else None
    if re.search(A_CTX, t):
        site = "A" if site is None else None   # both letters: unclear
    ns = [CALL_NUM[w] for w in words if w in CALL_NUM]
    n = max(ns) if ns else None   # "2 or 3 mid": 3
    stack = bool(re.search(r"\bstack(?:ed|ing)?\b", t))
    if stack and not n:
        n = 4   # "stack A", "A-stack"
    if n is None and re.search(r"\b(last|dernier)\b", t):
        n = 1   # "last mid": the last one is there
    zone = reg = None
    vocab = _zone_vocab(map_name)
    hits = [vocab.get(w) or vocab.get(w + "s") for w in words]
    hits = [h for h in hits if h]
    if len({h[0] for h in hits}) >= 3:
        return None   # a list of callouts: the model repeating its prompt, not a call
    if hits:
        zone, reg = hits[0]
    if zone is None and re.search(r"\b(mid|mids|milieu|middle)\b", t):
        zone, reg = "Mid", "MID"   # "2 or 3 mid", "4 mids plus"
    if site is None and reg in ("A", "B"):
        site = reg
    if site is None:
        site = next((LEVEL_SITE.get(map_name, {})[w] for w in words if w in LEVEL_SITE.get(map_name, {})), None)
    rush = bool(re.search(r"\b(rush|rushent|rouch|rushs)\b", t))
    bomb = bool(re.search(r"\b(bombe|bomb|plant|plantée?|posée?|planted)\b", t))
    lone = bool(re.search(r"\b(seul|solo|lurk|lurker)\b", t)) or n == 1
    clear = bool(re.search(r"\b(clear|clean|empty|nobody|nothing|none|vide|personne|rien|no one)\b", t))   # "B clear", "personne en B", "nothing B"
    if clear:
        n = None
    me = bool(re.search(r"\b(je suis|j'suis|chui|i'?m|i am|je joue|je reste|je tiens|i play|i'?ll play|i hold|moi je suis)\b", t))   # your own spot
    if not (site or zone or rush or bomb):
        return None
    if len(words) > 5 and not (n or zone or rush or bomb):
        return None   # a sentence with a letter in it, not a call
    regs = [h[1] for h in hits if h[1] in ("A", "B")]   # every zone named, with its side of the map ("1 jungle, 1 connector": A twice)
    return {"site": site, "n": n, "zone": zone, "rush": rush, "bomb": bomb, "lone": lone, "clear": clear, "regs": regs, "me": me, "stack": stack}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "live":
        live_loop()
    elif len(sys.argv) > 2 and sys.argv[1] == "transcribe":
        config.full_speed()   # after a match only (a match stops it): every core at full clock
        print(transcribe(sys.argv[2]), "phrases")
