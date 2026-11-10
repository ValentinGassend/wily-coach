"""Local Coach CS2 app with live analysis: python serve.py  (opens http://127.0.0.1:8765)

The search bar of the page sends any Steam link / SteamID here; the full pipeline runs on this PC
(Steam open, CS2 closed for Valve match info) and the new player appears in the page when done.
"""
import json
import re
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import os

from wily.app import build_app
from wily.core import config
from wily.core import i18n
from wily.app import pipeline

PORT = int(os.environ.get("COACH_PORT", 8765))
JOB = {"running": False, "log": [], "done": False, "error": None, "steamid": None, "query": None, "partial": None, "players": None}
LOCK = threading.Lock()
LOCAL_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}


# the base grows by itself (grow.py, its own process at the lowest priority): started and stopped in Settings, back
# on after a restart of the app; its state in out/grow.json, its switch in out/grow_ctl.json
GROW_STATE = os.path.join(config.OUT, "grow.json")
GROW_CTL = os.path.join(config.OUT, "grow_ctl.json")


def grow_alive():
    pid = (config.read_json(GROW_STATE, {}) or {}).get("pid")
    try:
        import psutil
        return bool(pid) and config.runs(psutil.Process(pid).cmdline(), "wily.base.grow")
    except Exception:
        return False


# "Pull now" of the shared matches (12/10): it runs in the background (download, checks, the base's tables after), the
# page follows it until the end to say what it did, or why it failed
PULL = {"running": False, "error": None}

# 22/10, the coach: "rajoute un bouton pour ajouter les démos ... à l'analyse pour s'en servir aussi pour trouver des
# stuffs": pro demos he downloaded himself (a match's GOTV Demo on HLTV, a LAN's archive), sent by Settings into this
# inbox, analyzed into the pro base by fetch_demos --import --remove in a process of its own at idle priority (its
# progress in out/pro/import_status.json), each copy deleted once in; one run at a time, a file sent meanwhile taken
# by the next one
PRO_INBOX = os.path.join(config.CACHE, "pro_inbox")
PRO_STATUS = os.path.join(config.OUT, "pro", "import_status.json")
PRO_EXTS = (".dem", ".rar", ".zip", ".7z")
PRODEMOS = {"proc": None, "again": False, "lock": threading.Lock()}


def prodemos_alive():
    p = PRODEMOS["proc"]
    if p is not None and p.poll() is None:
        return True
    pid = (config.read_json(PRO_STATUS, {}) or {}).get("pid")   # one started before the app's last start
    try:
        import psutil
        return bool(pid) and config.runs(psutil.Process(pid).cmdline(), "wily.base.fetch_demos")
    except Exception:
        return False


def prodemos_start():
    """The inbox analyzed now, or by the next run when one is on it (its end starts it)."""
    import subprocess
    with PRODEMOS["lock"]:
        if prodemos_alive():
            PRODEMOS["again"] = True
            if PRODEMOS["proc"] is None or PRODEMOS["proc"].poll() is not None:   # an older app's run: its end watched
                threading.Thread(target=_prodemos_after, args=(None,), daemon=True).start()
            return
        os.makedirs(os.path.join(config.OUT, "logs"), exist_ok=True)
        log = open(os.path.join(config.OUT, "logs", "prodemos.log"), "a", encoding="utf-8")
        p = subprocess.Popen([sys.executable, "-m", "wily.base.fetch_demos", "--import", PRO_INBOX, "--remove"], cwd=config.HERE,
                             stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                             creationflags=config.NO_WINDOW | getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))
        log.close()   # the child keeps its own copy of the handle
        PRODEMOS.update(proc=p, again=False)
    threading.Thread(target=_prodemos_after, args=(p,), daemon=True).start()


def _prodemos_after(p):
    if p is not None:
        p.wait()
    else:
        while prodemos_alive():
            time.sleep(10)
    if PRODEMOS["again"]:
        prodemos_start()


def prodemos_files():
    try:
        return sorted(f for f in os.listdir(PRO_INBOX) if f.lower().endswith(PRO_EXTS) and os.path.isfile(os.path.join(PRO_INBOX, f)))
    except OSError:
        return []


def prodemos_status():
    """What Settings shows: the run (its file, its step), the files waiting, the last run's maps added or not, and how
    many maps the pro base holds."""
    st = config.read_json(PRO_STATUS, {}) or {}
    reg = config.read_json(os.path.join(config.OUT, "pro", "matches.json"), {}) or {}
    waiting = []
    for f in prodemos_files():
        try:
            waiting.append({"name": f, "mb": round(os.path.getsize(os.path.join(PRO_INBOX, f)) / 2**20)})
        except OSError:
            pass
    run = prodemos_alive()
    p = PRODEMOS["proc"]
    if run and p is not None and p.poll() is None and st.get("pid") != p.pid:   # the run starting: the last one's status
        st = {}
    return {"running": run, "waiting": waiting, "maps": sum(len(m.get("demos") or []) for m in reg.values()),
            "last": {k: st.get(k) for k in ("started", "ended", "files", "file", "step", "why", "i", "n", "done", "failed", "added")} if st else {}}


def grow_start():
    if grow_alive():
        return
    import subprocess
    subprocess.Popen([sys.executable, "-m", "wily.base.grow"], cwd=config.HERE,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "IDLE_PRIORITY_CLASS", 0))


def grow_status():
    st = config.read_json(GROW_STATE, {}) or {}
    c = config.read_json(GROW_CTL, {}) or {}
    tail = []
    try:
        with open(os.path.join(config.OUT, "grow.log"), encoding="utf-8") as f:
            tail = [x.rstrip() for x in f.readlines()[-6:]]
    except OSError:
        pass
    import shutil
    return {"on": bool(c.get("on")), "target": int(c.get("target") or 5000), "alive": grow_alive(), "status": st.get("status"),
            "n": st.get("n"), "codes": len(st.get("codes") or []), "players": len(st.get("players") or []),
            "looked": len(st.get("looked") or {}), "counts": st.get("counts") or {}, "updated": st.get("updated"),
            "free_gb": round(shutil.disk_usage(config.CACHE).free / 2 ** 30), "log": tail,
            "client": config.role() == "client", "pack": config.read_json(os.path.join(config.OUT, "base_pack.json"), None),
            "min_free_gb": c.get("min_free_gb") or 50}   # grow.MIN_FREE_GB: the disk floor the loop stops at


REFRESH = os.path.join(config.OUT, "refresh.json")
REFRESH_CTL = os.path.join(config.OUT, "refresh_ctl.json")


def refresh_alive():
    st = config.read_json(REFRESH, {}) or {}
    pid = st.get("pid")
    try:
        import psutil
        return bool(st.get("running") and pid and psutil.pid_exists(pid) and config.runs(psutil.Process(pid).cmdline(), "wily.base.refresh_all"))
    except Exception:
        return False


def refresh_status():
    st = dict(config.read_json(REFRESH, {}) or {})
    st["alive"] = refresh_alive()
    if not st["alive"]:
        st["running"] = False
    st["client"] = config.role() == "client"
    return st


def grow_wait():
    """A match the base-growing loop is extracting: the app's analysis waits for its end (they write the same files)."""
    t = time.time()
    while time.time() - t < 300:
        st = config.read_json(GROW_STATE, {}) or {}
        if not st.get("step") or not grow_alive():
            return
        if time.time() - t < 2.5:
            pipeline.log("The base-growing loop finishes its current match first…")
        time.sleep(2)


def _stage(key, i=None, n=None, note=None):
    """A step of the running analysis, for the page's progress: the step before it done when a new one starts."""
    st, now = JOB.setdefault("steps", []), time.time()
    if not st or st[-1]["key"] != key:
        if st and not st[-1].get("t1"):
            st[-1]["t1"] = now
        st.append({"key": key, "t0": now})
    s = st[-1]
    s.update({k: v for k, v in (("i", i), ("n", n), ("note", note)) if v is not None})


def run_job(query, task=None, extra=None):
    """One analysis at a time (search, or Steam history sync when task is given). The caller holds LOCK.
    extra: what the page shows at the end (the view and the match of a re-analysis)."""
    try:   # everything inside: the lock is released whatever happens
        JOB.update({"running": True, "log": [], "done": False, "error": None, "steamid": None, "query": query, "partial": None,
                    "players": None, "view": None, "match": None, "steps": [], "t0": time.time(), **(extra or {})})
        pipeline.LOG_HOOK = lambda m: JOB["log"].append(m)
        pipeline.STAGE_HOOK = _stage
        pipeline.PARTIAL_HOOK = publish_partial
        grow_wait()
        res = task() if task else pipeline.run_for(query)
        ids = [p["steamid"] for p in res["match_players"]] if isinstance(res, dict) else [str(res)]
        _stage("page", 0, len(ids))
        entries = {}
        for k, i in enumerate(ids, 1):
            entries[i] = build_app.write_player(i)
            _stage("page", k, len(ids))
        idx = [x for x in load_index() if x["steamid"] not in entries] + [e for e in entries.values() if e]
        config.write_json(os.path.join(build_app.SITE, "index.json"), idx)
        if isinstance(res, dict):
            JOB["players"] = [p for p in res["match_players"] if entries.get(p["steamid"])]
        else:
            JOB["steamid"] = ids[0]
    except ValueError as e:  # expected situations (nothing public, expired demo...): message only
        JOB["error"] = str(e)
        print(f"  -> {e}")
    except Exception as e:
        JOB["error"] = str(e)
        traceback.print_exc()
    finally:
        pipeline.LOG_HOOK = None
        pipeline.PARTIAL_HOOK = None
        pipeline.STAGE_HOOK = None
        if JOB.get("steps") and not JOB["steps"][-1].get("t1"):
            JOB["steps"][-1]["t1"] = time.time()
        JOB.update(running=False, done=True, t1=time.time())
        _times()
        LOCK.release()


def _times():
    """Each analysis's steps and how long each took, kept (16/10, the user: "encore beaucoup trop long, même sur le premier
    match": the first one after the PC starts, its files not in memory yet, is the one to measure, and it was lost)."""
    try:
        d = os.path.join(config.OUT, "ledgers")
        os.makedirs(d, exist_ok=True)
        row = {"t0": round(JOB.get("t0") or 0), "s": round((JOB.get("t1") or 0) - (JOB.get("t0") or 0), 1), "query": str(JOB.get("query") or "")[:40],
               "error": bool(JOB.get("error")), "steps": [[x["key"], round((x.get("t1") or 0) - x["t0"], 1), x.get("n")] for x in JOB.get("steps") or []],
               "since_boot": round(time.time() - __import__("psutil").boot_time())}
        with open(os.path.join(d, "job_times.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def publish_partial(sid):
    """A first profile (Leetify, or the existing one) is ready: put it on the site right away."""
    sid = str(sid)
    e = build_app.write_player(sid)
    if e:
        idx = [x for x in load_index() if x["steamid"] != sid] + [e]
        config.write_json(os.path.join(build_app.SITE, "index.json"), idx)
        JOB["partial"] = sid


# the app's addresses (like csrep's): the page is served there, and reads them
# 07/10: the menus' words (/review, /profile/reads, /profile/maps/nuke, /matches/<code>...), another player's under /player/<id>
APP_PAGES = re.compile(r"/(?:player/\d{17}(?:/[A-Za-z0-9_-]{1,40}){0,3}|match/[A-Za-z0-9-]{1,40}|"
                       r"(?:profile|matches|review|prepare|live|settings|team|players|pros)(?:/[A-Za-z0-9_-]{1,40}){0,2})/?")


def match_info(code):
    """/match/<match id or share code>: its id, share code, map, time, whether its demo is analyzed, and the analyzed
    players who played it (you first, full profiles before light ones)."""
    from wily.matches import matchlist
    if re.fullmatch(pipeline.SHARECODE_RE, code):
        try:
            mid, sc = str(matchlist.decode_sharecode(code)[0]), code
        except (ValueError, OverflowError):   # the shape of a share code, not one
            return None
    elif code.isdigit():
        mid, sc = code, None
    else:
        return None
    e = pipeline.registry().get(mid) or {}
    d = os.path.join(config.DEEP, mid)
    ids = [str(76561197960265728 + int(a)) for a in e.get("accounts") or [] if a]
    if not ids and os.path.isfile(os.path.join(d, "samples.parquet")):
        import pandas as pd
        ids = [str(int(x)) for x in pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["steamid"]).steamid.unique() if x]
    idx = {x["steamid"]: x for x in load_index()}
    own = str(config.settings().get("own_steamid") or "")
    ps = sorted((x for x in dict.fromkeys(ids) if x in idx), key=lambda x: (x != own, bool(idx[x].get("light"))))
    return {"id": mid, "code": sc or e.get("sharecode"), "map": (config.read_json(os.path.join(d, "meta.json"), {}) or {}).get("map"),
            "time": e.get("time"), "analyzed": os.path.isdir(d), "players": ps}


def load_index():
    return config.read_json(os.path.join(build_app.SITE, "index.json"), [])


class _Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        """A page that left before its answer (a refresh, a closed tab: 22/10, his "erreur comme ça qui pète"): no
        traceback for it; anything else, as before."""
        if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    def foreign(self, write=False):
        """True for a request coming from another site. Without this, a page you visit could start the microphone,
        change or remove your Steam access, delete data or launch analyses (a form or a fetch sent to 127.0.0.1),
        or read your data through a domain name pointed at 127.0.0.1 (DNS rebinding: the Host is then that name).
        The page of the app, CS2 (Game State Integration) and command-line tools pass."""
        host = self.headers.get("Host")
        if host is not None and host.lower() not in LOCAL_HOSTS:
            return True
        if write:   # a change: the browser says where the request comes from (Origin, else Sec-Fetch-Site)
            origin = self.headers.get("Origin")
            if origin is not None:
                return origin.lower() not in {f"http://{h}" for h in LOCAL_HOSTS}
            return self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none")
        return False

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # the page left before its answer (22/10, his test video: Prepare refreshed while its first answer was made,
            # "j'ai souvent une erreur comme ça qui pète"): nobody to answer, nothing wrong
            self.close_connection = True

    def log_message(self, *a):
        pass

    def do_GET(self):
        PAGE["any"] = time.time()
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if self.foreign(write=u.path == "/api/analyze"):   # the only GET that starts something
            return self.send(403, {"error": i18n.tr("request from another site refused")})
        if u.path in ("/", "/index.html") or APP_PAGES.fullmatch(u.path):
            # standards mode (the claude.ai host adds this wrapper itself when publishing)
            from wily.core import i18n   # 13/10: the page in the player's language (Settings, else the browser's)
            lang = i18n.page_lang(self.headers.get("Accept-Language"))
            relang_if_needed()
            head = f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0">'
            return self.send(200, head + build_app.shell_html(load_index(), local=True, lang=lang, relang=bool(RELANG["t"])) + "</body></html>", "text/html; charset=utf-8")
        if u.path == "/api/voice/status":
            return self.send(200, voice_status())
        if u.path == "/api/coach/status":
            from wily.live import chatcalls
            return self.send(200, chatcalls.status())
        if u.path == "/api/clips":   # the lineups of the clips you sent, found in the base (clips.py)
            from wily.insights import clips
            return self.send(200, clips.by_map())
        if u.path.startswith("/api/tdirs/"):   # the T side's ways in on a map (tdirs.py): Live's directions, odds and grenades
            from wily.insights import tdirs
            mp = u.path.rsplit("/", 1)[-1]
            return self.send(200, tdirs.for_page(mp) or {})
        if u.path.startswith("/lineshot/"):   # a lineup's photo, taken on the training server (lineshots.py)
            m = re.fullmatch(r"/lineshot/((?:de|cs|ar)_\w+)/([A-Za-z0-9_-]+\.webp)", u.path)
            from wily.insights import lineshots
            f = os.path.join(lineshots.DIR, m.group(1), m.group(2)) if m else None
            if not f or not os.path.exists(f):
                return self.send(404, {"error": "not found"})
            data = open(f, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path == "/api/voice/devices":
            try:
                from wily.live import voice
                ok, why = voice.available()
                return self.send(200, voice.devices() if ok else {"error": why})
            except Exception as e:
                return self.send(200, {"error": str(e)})
        if u.path == "/api/account":   # your Steam name and avatar for the bar (05/10)
            return self.send(200, account())
        if u.path == "/api/gsi/state":
            from wily.live import gsi
            if not q.get("peek"):   # the bar's Live button only peeks (07/10): CS2's start still opens Live when no Live page is open
                PAGE["seen"] = time.time()   # the In game page asks a few times a second: a Wily page is open
            s = gsi.state()
            try:
                from wily.live import voice
                s["mic"] = voice.REC.recording()
                s["mic_silent"] = voice.REC.recording() and time.time() - (voice.REC.meta or {}).get("start", time.time()) > 60 and voice.REC.peak < 0.01
                s["mic_auto"] = bool(voice.settings().get("auto"))
                s["team_rec"] = "on" if voice.TEAM.running() else "pending" if voice.TEAM.pending else None   # your team agreed: what you hear
            except Exception:
                pass
            return self.send(200, s)
        if u.path == "/api/gsi/raw":   # what the game really sends (key paths and a few whole messages)
            from wily.live import gsi
            return self.send(200, {"keys": dict(sorted(gsi.RAW["keys"].items())), "samples": gsi.RAW["samples"]})
        if u.path == "/api/gsi/status":
            from wily.live import gsi
            return self.send(200, gsi.status() | {"open_on_cs2": bool(config.settings().get("open_on_cs2", True)),
                                                  "feedback_prompts": config.settings().get("feedback_prompts", True) is not False,
                                                  "linux": config.LINUX, "linux_training": bool(config.settings().get("linux_training"))})
        if u.path == "/api/feedback/pending":   # how it went: after a warm-up, after a match with the In game page (07/10)
            from wily.coaching import feedback
            try:
                return self.send(200, feedback.pending())
            except Exception as e:
                return self.send(200, {"error": f"{type(e).__name__}"})
        if u.path == "/api/train/maps":   # the bomb maps the base covers: Prepare offers the ones you have no demo of (09/10)
            from wily.training import train
            return self.send(200, {"maps": [{"map": m, "n": n} for m, n in train.base_maps().items()]})
        if u.path == "/api/train/status":   # installed, installing, running (Prepare's warm-up asks before offering it)
            from wily.training import replay
            return self.send(200, replay.status())
        if u.path == "/api/train/steps":   # a step-by-step drill's toggles, live (23/10: the Live page shows them too)
            from wily.training import replay
            return self.send(200, replay.steps_live())
        if u.path == "/api/train/preview":   # Prepare's warm-up before it's built: each part's minutes (06/10)
            from wily.training import train
            sid = (q.get("sid") or [""])[0] or str(config.settings().get("own_steamid") or "")
            try:
                mins = max(5, min(90, int((q.get("minutes") or ["20"])[0])))
            except ValueError:
                mins = 20
            where = (q.get("where") or ["random"])[0]
            if not re.fullmatch(r"random|mix|(?:(?:de|cs|ar)_\w+)(?:,(?:de|cs|ar)_\w+){0,2}", where):
                return self.send(400, {"error": "invalid map"})
            focus = (q.get("focus") or [""])[0] or None   # a focus block (13/10): one module, one map
            if focus is not None and focus not in train.FOCUS:
                return self.send(400, {"error": "invalid module"})
            out = {"blocks": train.preview(sid, mins, where, focus)}
            if focus:   # each module's tile: what it has on that map
                out["modules"] = train.modules(sid, where.split(",")[0])
            return self.send(200, out)
        if u.path == "/api/train/execs":   # a Stuff focus block's choices on that map: its site takes and defenses (19/10)
            from wily.training import execs
            sid = (q.get("sid") or [""])[0] or str(config.settings().get("own_steamid") or "")
            mp = (q.get("map") or [""])[0]
            if not re.fullmatch(r"(?:de|cs|ar)_\w+", mp):
                return self.send(400, {"error": "invalid map"})
            return self.send(200, {"map": mp, "execs": execs.offer(sid, mp)})
        if u.path == "/api/train/momentum":   # a Momentum focus block's choices on that map: its jumps, its ways (20/10)
            from wily.training import train
            sid = (q.get("sid") or [""])[0] or str(config.settings().get("own_steamid") or "")
            mp = (q.get("map") or [""])[0]
            if not re.fullmatch(r"(?:de|cs|ar)_\w+", mp):
                return self.send(400, {"error": "invalid map"})
            return self.send(200, {"map": mp, "choices": train.momentum_offer(sid, mp)})
        if u.path == "/api/train/modules":   # a focus block's tiles: each module's drills on that map (13/10)
            from wily.training import train
            sid = (q.get("sid") or [""])[0] or str(config.settings().get("own_steamid") or "")
            mp = (q.get("map") or [""])[0]
            if not re.fullmatch(r"(?:de|cs|ar)_\w+", mp):
                return self.send(400, {"error": "invalid map"})
            return self.send(200, {"map": mp, "counts": train.module_counts(sid, mp), "est": {k: train.EST[k] for k in train.FOCUS if k in train.EST},
                                   "repeat": train.FOCUS_REPEAT})
        if u.path == "/api/train/struggles":   # where you lose rounds lately: what the training puts first (06/10)
            from wily.training import train
            sid = (q.get("sid") or [""])[0] or str(config.settings().get("own_steamid") or "")
            try:
                S = train.struggles(sid)[:4] if sid.isdigit() else []
            except Exception as e:
                return self.send(200, {"struggles": [], "error": str(e)})
            return self.send(200, {"struggles": [{k: x[k] for k in ("map", "side", "site", "kind", "lost", "n", "last", "text")} for x in S]})
        if u.path == "/api/train":   # the training server, your situations to play again, your tries
            from wily.training import replay
            sid = (q.get("sid") or [""])[0] or str(config.settings().get("own_steamid") or "")
            try:
                sc, err = (replay.scenarios(sid)[:40] if sid.isdigit() else []), None
            except Exception as e:
                sc, err = [], str(e)
            try:
                from wily.training import train
                prog, maps_ = train.summary(sid), (train.maps(sid) if sid.isdigit() else {})
            except Exception as e:
                prog, maps_, err = None, {}, err or str(e)
            return self.send(200, {"status": replay.status(), "scenarios": sc, "results": replay.results(), "progress": prog,
                                   "maps": maps_, "error": err})
        if u.path == "/api/team/suggest":
            from wily.coaching import team
            sid = (q.get("sid") or [""])[0]
            return self.send(200, team.suggestions(sid) if sid.isdigit() else [])
        if u.path in ("/index.json", "/pros.json") or u.path.startswith(("/players/", "/radars/", "/replays/", "/teams/", "/nadecat/")):
            f = os.path.normpath(os.path.join(build_app.SITE, u.path.lstrip("/")))
            rm = re.fullmatch(r"/replays/(\d{17})/(\d{6,20})\.json", u.path)
            if rm and not os.path.isfile(f):   # a 2D replay not made yet: from the match's detailed extraction, now
                try:
                    from wily.demos import deepdive
                    import shutil
                    src = deepdive.ensure_replay(rm.group(1), rm.group(2))
                    if src:
                        os.makedirs(os.path.dirname(f), exist_ok=True)
                        shutil.copy(src, f)
                except Exception as e:
                    print("replay:", e, flush=True)
            if f.startswith(os.path.normpath(build_app.SITE) + os.sep) and os.path.isfile(f):
                return self.send(200, config._retry(lambda: open(f, "rb").read(), f))
            if re.fullmatch(r"/nadecat/[a-z0-9_]+\.json", u.path):   # a map without a pros' grenade catalog yet (Fachwerk): none, said quietly (21/10: a 404 in the console)
                return self.send(200, None)
            return self.send(404, {"error": "not found"})
        if u.path == "/api/match":   # an address /match/<match id or share code>
            m = match_info((q.get("code") or [""])[0].strip())
            return self.send(200, m) if m else self.send(404, {"error": i18n.tr("not a match id or share code")})
        if u.path == "/api/relang":   # your analysis being written again in the app's new language (13/10)
            return self.send(200, {"running": RELANG["t"] is not None, "lang": RELANG["lang"]})
        if u.path == "/api/grow":   # the base-growing loop: its state (Settings)
            return self.send(200, grow_status())
        if u.path == "/api/update":   # a player's copy: the app's and the base's new versions (Settings, 05/10)
            from wily.app import updater
            return self.send(200, updater.status())
        if u.path == "/api/usage":   # anonymous usage statistics: a player's switch and today's counters (05/10)
            from wily.sharing import usage
            return self.send(200, usage.status())
        if u.path == "/api/usage/stats":   # the coach's PC: how players use the app
            from wily.sharing import usage
            return self.send(200, usage.stats(max(1, min(90, int((q.get("days") or ["30"])[0] or 30)))))
        if u.path == "/api/reports":   # the coach's PC: the bug reports players sent (Settings, 05/10)
            from wily.sharing import contributions
            return self.send(200, contributions.reports((q.get("id") or [None])[0]))
        if u.path == "/api/contrib":   # the matches shared with the base: a player's switch, or what the coach received
            if config.role() == "client":
                from wily.sharing import contrib
                return self.send(200, dict(contrib.status(), client=True))
            from wily.sharing import contributions
            return self.send(200, dict(contributions.status(), client=False, pulling=PULL["running"], pull_error=PULL["error"]))
        if u.path == "/api/refresh":   # everything the app shows computed again from the base (Settings)
            return self.send(200, refresh_status())
        if u.path == "/api/codes":   # the share code of each match (the addresses /match/<share code>)
            return self.send(200, {k: e["sharecode"] for k, e in pipeline.registry().items() if e.get("sharecode")})
        if u.path == "/api/ping":
            return self.send(200, {"ok": True})
        if u.path == "/api/analyze":
            query = (q.get("q") or [""])[0].strip()
            if not query:
                return self.send(400, {"error": "Empty search"})
            if not LOCK.acquire(blocking=False):
                return self.send(409, {"error": i18n.tr("An analysis is already running"), "query": JOB["query"]})
            threading.Thread(target=run_job, args=(query,), daemon=True).start()
            return self.send(200, {"started": True})
        if u.path == "/api/job":
            return self.send(200, JOB)
        if u.path == "/api/prodemos":   # Settings' pro demos: the run, the files waiting, the last run's result (22/10)
            return self.send(200, prodemos_status())
        if u.path == "/api/steam/status":
            from wily.matches import steamlink
            sid = (q.get("sid") or [""])[0] or str(config.settings().get("own_steamid") or config.logged_in_account()[0] or "")
            if not sid.isdigit():
                return self.send(200, {"steamid": None, "links": {"key": steamlink.KEY_URL, "auth": steamlink.AUTH_URL}})
            return self.send(200, steamlink.status(sid))
        if u.path == "/api/steam/login":  # sign in through Steam: Steam's own page, then back to /api/steam/callback
            from wily.matches import steamlink
            base = f"http://127.0.0.1:{PORT}"
            return self.redirect(steamlink.login_url(base + "/api/steam/callback", base + "/"))
        if u.path == "/api/steam/callback":
            from wily.matches import steamlink
            params = {k: v[0] for k, v in q.items()}
            sid = steamlink.verify(params, f"http://127.0.0.1:{PORT}/api/steam/callback")
            if not sid:
                return self.redirect("/settings?steam=refused")
            name = None
            try:
                if steamlink.api_key():
                    name = steamlink.check_key(steamlink.api_key(), sid).get("personaname")
            except steamlink.SteamError:
                pass
            if not name:
                own, own_name = config.logged_in_account()
                name = own_name if own and int(own) == sid else (config.settings().get("players", {}).get(str(sid)) or {}).get("name")
            steamlink.save_login(sid, name)
            return self.redirect("/settings?steam=ok")
        return self.send(404, {"error": "not found"})

    def redirect(self, url):
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def import_demo(self, u):
        """One demo file sent by the page (16/10: FACEIT's .dem.zst, a .dem, .gz, .bz2, .xz, .zip): received in pieces
        into the cache folder (a demo is 100 to 400 MB), unpacked, checked and listed with the matches."""
        q = parse_qs(u.query)
        name = (q.get("name") or ["demo.dem"])[0][:200]
        try:
            mtime = float((q.get("mtime") or ["0"])[0]) / 1000 or None
        except ValueError:
            mtime = None
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 4 * 2**30:
            return self.send(400, {"error": i18n.tr("The file is empty or too big.")})
        os.makedirs(config.CACHE, exist_ok=True)
        tmp = os.path.join(config.CACHE, f"_upload_{os.getpid()}_{threading.get_ident()}.part")
        try:
            with open(tmp, "wb") as f:
                left = n
                while left:
                    b = self.rfile.read(min(left, 1 << 20))
                    if not b:
                        break
                    f.write(b)
                    left -= len(b)
            if left:
                return self.send(400, {"error": i18n.tr("The file did not arrive whole.")})
            return self.send(200, pipeline.import_demo(tmp, name, mtime))
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self.send(500, {"error": f"{type(e).__name__}: {e}"[:300]})
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def add_prodemo(self, u):
        """A pro demo or its archive sent by Settings (22/10): received in pieces into the pro inbox (an archive of a
        whole match is up to 1.5 GB), then the inbox analyzed. Its date: the file's (when you downloaded it)."""
        if config.role() == "client":
            return self.send(403, {"error": i18n.tr("the coach's PC only")})
        q = parse_qs(u.query)
        name = re.sub(r"[^\w.\- ()]+", "_", os.path.basename((q.get("name") or [""])[0])).strip(" .")[:120]
        if not name.lower().endswith(PRO_EXTS):
            return self.send(400, {"error": i18n.tr("Not a demo or an archive of demos (.dem, .rar, .zip, .7z).")})
        try:
            mtime = float((q.get("mtime") or ["0"])[0]) / 1000 or None
        except ValueError:
            mtime = None
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 8 * 2**30:
            return self.send(400, {"error": i18n.tr("The file is empty or too big.")})
        from wily.base import grow
        if grow.free_gb() - n / 2**30 < grow.MIN_FREE_GB:
            return self.send(507, {"error": i18n.tr("Not enough room on the disk: the base keeps {gb} GB free.", gb=grow.MIN_FREE_GB)})
        os.makedirs(PRO_INBOX, exist_ok=True)
        dest = os.path.join(PRO_INBOX, name)
        if os.path.exists(dest):   # the same download sent twice: once is enough (the run may be reading it)
            return self.send(409, {"error": i18n.tr("{name} is already waiting to be analyzed.", name=name)})
        tmp = dest + f".{os.getpid()}_{threading.get_ident()}.part"
        try:
            with open(tmp, "wb") as f:
                left = n
                while left:
                    b = self.rfile.read(min(left, 1 << 20))
                    if not b:
                        break
                    f.write(b)
                    left -= len(b)
            if left:
                return self.send(400, {"error": i18n.tr("The file did not arrive whole.")})
            os.replace(tmp, dest)
            if mtime:
                os.utime(dest, (mtime, mtime))
        except OSError as e:
            return self.send(500, {"error": f"{type(e).__name__}: {e}"[:300]})
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        prodemos_start()
        return self.send(200, prodemos_status())

    def do_POST(self):
        PAGE["any"] = time.time()
        """Journal check-ins and experiments: saved in out/, then the player's plan and page are rebuilt."""
        u = urlparse(self.path)
        if self.foreign(write=True):
            return self.send(403, {"error": i18n.tr("request from another site refused")})
        if u.path == "/api/import":   # a demo file from the page (Import, drag and drop): streamed to disk, not JSON
            return self.import_demo(u)
        if u.path == "/api/prodemos/add":   # a pro demo or its archive from Settings (22/10): streamed to disk, not JSON
            return self.add_prodemo(u)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self.send(400, {"error": "invalid request"})
        if u.path in ("/api/prodemos/run", "/api/prodemos/drop"):   # Settings' pro demos waiting: analyzed, or one deleted
            if config.role() == "client":
                return self.send(403, {"error": i18n.tr("the coach's PC only")})
            if u.path.endswith("drop"):   # one the run could not read (its archive broken, no demo inside): gone
                name = os.path.basename(str(body.get("name") or ""))
                cur = (config.read_json(PRO_STATUS, {}) or {}).get("file")
                if name in prodemos_files() and not (prodemos_alive() and name == cur):
                    try:
                        os.remove(os.path.join(PRO_INBOX, name))
                    except OSError as e:
                        return self.send(500, {"error": f"{type(e).__name__}: {e}"[:300]})
            elif prodemos_files():
                prodemos_start()
            return self.send(200, prodemos_status())
        if u.path == "/api/import/run":   # the imported demos read, then your profile, plan and page (16/10)
            if not LOCK.acquire(blocking=False):
                return self.send(409, {"error": i18n.tr("An analysis is already running"), "query": JOB["query"]})
            threading.Thread(target=run_job, args=("Demo import", lambda: pipeline.analyze_local()), daemon=True).start()
            return self.send(200, {"started": True})
        if u.path == "/api/gsi":  # CS2 Game State Integration: the game itself, many times per round
            from wily.live import gsi
            ok = gsi.update(body)
            if ok:
                try:
                    from wily.live import voice
                    if voice.settings().get("auto") or voice.REC.recording():
                        voice.on_gsi(gsi.state())
                except Exception as e:
                    print("calls:", e, flush=True)
            return self.send(200 if ok else 403, {})
        if u.path.startswith("/api/voice/"):
            from wily.live import gsi
            from wily.live import voice
            act = u.path.rsplit("/", 1)[-1]
            try:
                if act == "settings":
                    voice.save_settings(**{k: body[k] for k in ("auto", "device", "live") if k in body})
                    if body.get("live") is False:
                        voice.LIVE.stop()
                elif act == "start":
                    g = gsi.state()
                    voice.pause_transcription()
                    voice.REC.start(g.get("map"), body.get("sid") or config.settings().get("own_steamid"), "manual")
                    voice.LIVE.start(g.get("map"))
                    voice.TEAM.resume(g.get("map"))
                elif act == "stop":
                    voice.finish()
                elif act == "team":   # your team agreed: what you hear is recorded too, for this match only (04/10)
                    if body.get("on") is False:
                        voice.TEAM.stop()
                    else:
                        g = gsi.state()
                        if not g.get("map") or g.get("practice"):
                            return self.send(409, {"error": i18n.tr("No match loaded.")})
                        voice.TEAM.start("your team agreed: the In game page's button", g.get("map"))
                elif act == "test":   # Settings: the chosen microphone's level for 3 s (16/10), nothing recorded
                    return self.send(200, voice.test())
                elif act == "transcribe":
                    if not voice.start_transcription(str(body.get("id") or "")):
                        return self.send(409, {"error": i18n.tr("A transcription is already running.")})
                elif act == "delete":
                    rid = str(body.get("id") or "")
                    if re.fullmatch(r"[\w-]+", rid):
                        voice.delete(rid)
                else:
                    return self.send(404, {"error": "not found"})
            except Exception as e:
                return self.send(400, {"error": f"Microphone: {e}"})
            return self.send(200, voice_status())
        if u.path == "/api/coach/paths":   # the page's plan this round: numpad 1-2-3 (A, mid, B) and 4-5-6 (tempo) say it in the team chat
            from wily.live import chatcalls
            return self.send(200 if chatcalls.write(body.get("paths"), body.get("extra"), body.get("tempo")) else 400, {})
        if u.path.startswith("/api/train/"):   # the training server (separate copy of the game, 127.0.0.1 only)
            from wily.training import replay
            act = u.path.rsplit("/", 1)[-1]
            try:
                if act == "play":
                    if config.in_match() and not replay.on_server():
                        return self.send(409, {"error": i18n.tr("A match is running: training after it.")})
                    mid, kind, mode = str(body.get("mid") or ""), body.get("kind") or "death", body.get("mode") or "actor"
                    if not mid.isdigit() or kind not in ("death", "clutch") or mode not in ("actor", "spec"):
                        return self.send(400, {"error": "invalid situation"})
                    sid = str(body.get("sid") or config.settings().get("own_steamid") or "")
                    if not replay.claim("a situation"):
                        return self.send(409, {"error": i18n.tr("{what} is starting on the training server: wait for it", what=replay.busy())})
                    try:
                        return self.send(200, replay.play(sid, mid, int(body.get("round")), kind, mode, int(body["diff"]) if body.get("diff") is not None else 2))
                    finally:
                        replay.release()
                if act == "session":   # one Play: the whole training (server, session, the game sent to it)
                    if config.in_match() and not replay.on_server():
                        return self.send(409, {"error": i18n.tr("A match is running: training after it.")})
                    from wily.training import train
                    sid = str(body.get("sid") or config.settings().get("own_steamid") or "")
                    minutes = max(5, min(90, int(body.get("minutes") or 20)))
                    where = str(body.get("where") or "random")
                    if not re.fullmatch(r"random|mix|(?:(?:de|cs|ar)_\w+)(?:,(?:de|cs|ar)_\w+){0,2}", where):   # Prepare: up to three maps
                        return self.send(400, {"error": "invalid map"})
                    diff = int(body["diff"]) if body.get("diff") is not None else 2
                    focus = body.get("focus") or None   # a focus block (13/10): one module for the whole time, one map
                    if focus is not None and (focus not in train.FOCUS or where in ("random", "mix")):
                        return self.send(400, {"error": "invalid module"})
                    ex = body.get("exec") or None   # a Stuff focus block: a site take or defense instead of a time (19/10)
                    from wily.training import execs as _ex, momentum as _mo   # a Momentum block: its part instead of a time too
                    if ex is not None and not ((focus == "nade" and ex in _ex.KEYS) or (focus == "momentum" and ex in _mo.PICKS)):
                        return self.send(400, {"error": "invalid exec"})
                    try:
                        gun = body.get("weapon") or None   # Prepare's choice of weapon (20/10)
                        if gun is not None and gun not in train.WEAPONS:
                            return self.send(400, {"error": "invalid weapon"})
                        seed = int(body["seed"]) if str(body.get("seed") or "").isdigit() else None   # the tests' fixed set (29/10)
                        return self.send(200, train.play(sid, minutes, where, diff, focus, ex, gun, seed, bool(body.get("every"))))
                    except RuntimeError as e:   # another start on the server meanwhile
                        return self.send(409, {"error": str(e)})
                if act == "recette":   # 29/10: his own (the "recette" setting only): every drill the latest tests failed
                    if not config.settings().get("recette"):
                        return self.send(404, {"error": "not found"})
                    if config.in_match() and not replay.on_server():
                        return self.send(409, {"error": i18n.tr("A match is running: training after it.")})
                    from wily.training import train
                    sid = str(body.get("sid") or config.settings().get("own_steamid") or "")
                    seed = int(body["seed"]) if str(body.get("seed") or "").isdigit() else None
                    try:
                        return self.send(200, train.play_recette(sid, int(body["diff"]) if body.get("diff") is not None else 2, seed))
                    except RuntimeError as e:
                        return self.send(409, {"error": str(e)})
                if act == "install":   # a player's PC: CS2's files linked next to the game, Metamod, CounterStrikeSharp, the plugin
                    if config.in_match():
                        return self.send(409, {"error": i18n.tr("A match is running: install after it.")})
                    return self.send(200, replay.install())
                if act == "stop":
                    return self.send(200, replay.stop())
                if act in ("pause", "resume"):   # 09/10: "il faudrait pouvoir la mettre en pause, et la reprendre"
                    if not replay.status().get("running"):
                        return self.send(409, {"error": i18n.tr("The training server is not running.")})
                    replay.rcon(f"css_{act}")
                    return self.send(200, {"ok": True})
                if act == "join":   # the game back on the session's server (it crashed or was closed meanwhile, 04/10)
                    if not replay.status().get("running"):
                        return self.send(409, {"error": i18n.tr("The training server is not running.")})
                    from wily.training import train   # threading is the module's (a local import made it local to the whole handler: Update failed, 05/10)
                    threading.Thread(target=train._connect, daemon=True).start()
                    return self.send(200, replay.status())
                if act == "cmd":   # the plugin's commands: again, next, previous, spec, difficulty
                    c = str(body.get("cmd") or "")
                    if not re.fullmatch(r"r|n|p|spec|stop|diff [0-3]", c):
                        return self.send(400, {"error": "unknown command"})
                    replay.rcon(f"css_{c}")
                    return self.send(200, replay.status())
            except (OSError, RuntimeError, ValueError, StopIteration) as e:
                return self.send(400, {"error": str(e) or i18n.tr("training server error")})
            return self.send(404, {"error": "not found"})
        if u.path in ("/api/refresh/start", "/api/refresh/stop"):   # the app's update with the base: started or stopped
            if u.path.endswith("stop"):
                config.write_json(REFRESH_CTL, {"stop": True})
                return self.send(200, refresh_status())
            if not refresh_alive():
                import subprocess
                config.write_json(REFRESH_CTL, {"stop": False})
                args = [sys.executable, "-m", "wily.base.refresh_all"] + (["--mine"] if body.get("mine") else [])
                subprocess.Popen(args, cwd=config.HERE,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
                time.sleep(1)
            return self.send(200, refresh_status())
        if u.path == "/api/update/dismiss":   # a player's copy: a message of the coach closed (14/10)
            from wily.app import updater
            return self.send(200, {"notices": updater.dismiss(str(body.get("id") or ""))})
        if u.path in ("/api/update/check", "/api/update/apply"):   # a player's copy: updates signed by the coach (05/10)
            from wily.app import updater
            try:
                if u.path.endswith("check"):
                    return self.send(200, updater.check(force=True))
                parts = body.get("parts")
                return self.send(200, updater.apply([p for p in parts if p in ("code", "base", "runtime")] if isinstance(parts, list) else None))
            except ValueError as e:
                return self.send(409, {"error": str(e)})
        if u.path in ("/api/usage", "/api/usage/set", "/api/usage/pull"):   # anonymous usage statistics (05/10)
            from wily.sharing import usage
            if u.path == "/api/usage":   # the page's counters of the last minute
                usage.add(body)
                return self.send(200, {"ok": True})
            if u.path.endswith("set"):
                return self.send(200, usage.set_options(body.get("on"), body.get("noticed")))
            if config.role() == "client":
                return self.send(403, {"error": i18n.tr("the coach's PC only")})
            from wily.sharing import contributions
            try:
                contributions.pull_usage(days=int(body.get("days") or 10))
            except (OSError, SystemExit, ValueError) as e:
                return self.send(400, {"error": str(e) or "failed"})
            except Exception as e:
                return self.send(502, {"error": f"the site: {type(e).__name__}"})
            return self.send(200, usage.stats(int(body.get("days") or 30)))
        if u.path in ("/api/report/preview", "/api/report/send"):   # a player reports a bug (the alpha, 05/10)
            from wily.sharing import bugreport
            page = str(body.get("page") or "")[:120]
            errors = [str(e)[:500] for e in (body.get("errors") or [])[:20]] if isinstance(body.get("errors"), list) else []
            if u.path.endswith("preview"):
                return self.send(200, bugreport.diagnostics(page, errors))
            try:
                return self.send(200, bugreport.send(body.get("text"), body.get("expected"), body.get("email"), bool(body.get("include", True)),
                                                     page, errors, body.get("kind") or "bug"))
            except ValueError as e:
                return self.send(400, {"error": str(e)})
        if u.path in ("/api/reports/pull", "/api/reports/done"):   # the coach's PC: the bug reports
            if config.role() == "client":
                return self.send(403, {"error": i18n.tr("the coach's PC only")})
            from wily.sharing import contributions
            try:
                if u.path.endswith("pull"):
                    contributions.pull_reports()
                else:
                    contributions.report_done(str(body.get("id") or ""), bool(body.get("done", True)))
            except (ValueError, OSError, SystemExit) as e:
                return self.send(400, {"error": str(e) or "failed"})
            except Exception as e:
                return self.send(502, {"error": f"the site: {type(e).__name__}"})
            return self.send(200, contributions.reports())
        if u.path in ("/api/contrib/release", "/api/contrib/drop"):   # the coach's PC (15/10): the held uploads, his call
            if config.role() == "client":
                return self.send(403, {"error": i18n.tr("the coach's PC only")})
            from wily.sharing import contributions
            if u.path.endswith("drop"):
                contributions.drop_held()
                return self.send(200, dict(contributions.status(), client=False, pulling=PULL["running"]))

            def release_now():
                try:
                    contributions.ingest(release=True)
                except BaseException as e:
                    PULL["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                    print("held matches:", e, flush=True)
                finally:
                    PULL["running"] = False
            if not PULL["running"]:   # one at a time with a pull (both write the base)
                PULL.update(running=True, error=None)
                threading.Thread(target=release_now, daemon=True).start()
            return self.send(200, dict(contributions.status(), client=False, pulling=True))
        if u.path in ("/api/contrib/set", "/api/contrib/send", "/api/contrib/pull"):   # the matches shared with the base
            if u.path.endswith("pull"):   # the coach's PC: what players shared, now
                if config.role() == "client":
                    return self.send(403, {"error": i18n.tr("the coach's PC only")})
                from wily.sharing import contributions

                def pull_now():
                    PULL.update(running=True, error=None)
                    try:
                        contributions.pull()
                        contributions.ingest()
                    except BaseException as e:
                        PULL["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                        print("shared matches:", e, flush=True)
                    finally:
                        PULL["running"] = False
                if not PULL["running"]:   # one pull at a time (a second click while one runs only follows it)
                    PULL.update(running=True, error=None)   # the last pull's error, gone at once
                    threading.Thread(target=pull_now, daemon=True).start()
                return self.send(200, dict(contributions.status(), client=False, pulling=True))
            if config.role() != "client":
                return self.send(403, {"error": i18n.tr("a player's copy only")})
            from wily.sharing import contrib
            if u.path.endswith("set"):
                return self.send(200, dict(contrib.set_on(bool(body.get("on"))), client=True))
            threading.Thread(target=contrib.send, daemon=True).start()
            return self.send(200, dict(contrib.status(), client=True))
        if u.path in ("/api/grow/start", "/api/grow/stop"):   # the base-growing loop: on until the target, or off
            on = u.path.endswith("start")
            try:
                target = max(100, min(20000, int(body.get("target") or 5000)))
            except (TypeError, ValueError):
                return self.send(400, {"error": "invalid target"})
            if on and config.role() == "client":
                return self.send(403, {"error": i18n.tr("My base grows on the developer's PC: it comes to you with my updates.")})
            # then: the app's update once the target is reached (07/10): "refresh" every profile, "refresh_mine" yours and your team's
            then = body.get("then") if on and body.get("then") in ("refresh", "refresh_mine") else None
            keep = {k: v for k, v in (config.read_json(GROW_CTL, {}) or {}).items() if k == "min_free_gb"}   # the disk floor stays
            config.write_json(GROW_CTL, {"on": on, "target": target} | keep | ({"then": then} if then else {}))
            if on:
                grow_start()
            return self.send(200, grow_status())
        if u.path == "/api/live/log":   # what the In game page shows, a few times per round: checked after the match
            from wily.live import livecheck
            return self.send(200 if livecheck.log(body) else 400, {})
        if u.path == "/api/gsi/site":  # the player marks where the T attacked, and what they saw in the round
            from wily.live import gsi
            try:
                rnd = int(body.get("round"))
                ok = gsi.set_site(rnd, body.get("site")) if "site" in body else True
                mark = {k: body[k] for k in ("contact", "alone", "contact_t", "site_t", "dyn", "lone") if k in body}
                ok = ok and (gsi.set_mark(rnd, mark) if mark else True)
            except (TypeError, ValueError):
                return self.send(400, {"error": "invalid round"})
            return self.send(200 if ok else 409, gsi.state())
        if u.path == "/api/reanalyze":  # one match again, from its demo (button of the Matches view)
            sid, mid = str(body.get("sid") or ""), str(body.get("mid") or "")
            if not sid.isdigit() or not mid.isdigit():
                return self.send(400, {"error": "invalid match"})
            if not LOCK.acquire(blocking=False):
                return self.send(409, {"error": i18n.tr("An analysis is already running"), "query": JOB["query"]})
            threading.Thread(target=run_job, args=("re-analysis of the match", lambda: pipeline.reanalyze_match(sid, mid)),
                             kwargs={"extra": {"view": "matches", "match": mid}}, daemon=True).start()
            return self.send(200, {"started": True})
        if u.path in ("/api/feedback/send", "/api/feedback/dismiss"):   # the popup's answer (07/10, the closed alpha)
            from wily.coaching import feedback
            try:
                if u.path.endswith("dismiss"):
                    if body.get("stop"):   # "don't ask after each one": off (Settings turns it back on)
                        s = config.settings()
                        s["feedback_prompts"] = False
                        config.save_settings(s)
                    return self.send(200, feedback.dismiss(body.get("id")))
                return self.send(200, feedback.send(str(body.get("kind") or ""), str(body.get("id") or ""), body.get("rating"),
                                                    body.get("tags") if isinstance(body.get("tags"), list) else [], str(body.get("text") or ""),
                                                    str(body.get("summary") or "")[:200]))
            except ValueError as e:
                return self.send(400, {"error": str(e)})
        if u.path == "/api/app/options":   # Settings' switches of the app itself
            s = config.settings()
            if "open_on_cs2" in body:
                s["open_on_cs2"] = bool(body["open_on_cs2"])
            if "feedback_prompts" in body:
                s["feedback_prompts"] = bool(body["feedback_prompts"])
            lang0 = i18n.current()
            if "ui_lang" in body:   # the app's language (13/10): one of i18n.LANGS, or "auto" (the browser's)
                if body["ui_lang"] in i18n.LANGS:
                    s["ui_lang"] = body["ui_lang"]
                else:
                    s.pop("ui_lang", None)
            if "linux_training" in body:   # Linux (10/10): the training server, experimental there
                s["linux_training"] = bool(body["linux_training"])
            if "setup_done" in body:   # the setup guide, done or skipped (08/10)
                s["setup_done"] = bool(body["setup_done"])
            if "auto_update" in body:   # automatic updates (08/10), on by default
                s["auto_update"] = bool(body["auto_update"])
            config.save_settings(s)
            relang = "ui_lang" in body and i18n.current() != lang0 and relang_own()
            return self.send(200, {"ok": True, "open_on_cs2": bool(s.get("open_on_cs2", True)), "feedback_prompts": s.get("feedback_prompts", True) is not False,
                                   "relang": relang})
        if u.path in ("/api/gsi/install", "/api/gsi/uninstall"):
            from wily.live import gsi
            try:
                return self.send(200, gsi.install(PORT) if u.path.endswith("install") and not u.path.endswith("uninstall") else gsi.uninstall())
            except (ValueError, OSError) as e:
                return self.send(400, {"error": str(e)})
        sid = str(body.get("sid") or "")
        if not sid.isdigit():
            return self.send(400, {"error": "missing player"})
        try:
            if u.path == "/api/checkin":
                from wily.coaching import context
                context.add_checkin(sid, body)
                refresh_plan(sid)
                return self.send(200, {"ok": True, "n": len(context.journal(sid))})
            if u.path == "/api/focus":   # your focus of the week, picked among the coach's axes (05/10)
                from wily.coaching import focus
                adv = config.read_json(os.path.join(config.player_dir(sid), "advice.json"), {}) or {}
                card = focus.choose(sid, str(body.get("id") or ""), adv.get("rules"))
                if not card:
                    return self.send(400, {"error": "Unknown axis."})
                set_focus(sid, card)
                return self.send(200, {"focus": card})
            if u.path == "/api/experiment":
                from wily.coaching import experiments
                if body.get("action") == "start":
                    experiments.start(sid, body.get("template"), body.get("params") or {})
                elif body.get("action") == "stop":
                    experiments.stop(sid, body.get("id"), "done")
                else:
                    return self.send(400, {"error": "unknown action"})
                refresh_plan(sid)
                return self.send(200, {"ok": True})
            if u.path == "/api/team":
                from wily.coaching import team
                ids = [str(i) for i in body.get("ids") or [] if str(i).isdigit()]
                p = team.build(ids, owner=sid)
                build_app.write_teams()
                return self.send(200, {"ok": True, "id": p["id"]})
            if u.path == "/api/team/delete":
                from wily.coaching import team
                tid = str(body.get("id") or "")
                f = os.path.join(team.TEAMS, f"{tid}.json")
                if tid.isalnum() and os.path.exists(f):
                    os.remove(f)
                build_app.write_teams()
                return self.send(200, {"ok": True})
            if u.path.startswith("/api/steam/"):
                from wily.matches import steamlink
                act = u.path.rsplit("/", 1)[-1]
                try:
                    if act == "credentials":
                        saved = steamlink.set_credentials(sid, body.get("api_key"), body.get("auth_code"), body.get("known_code"))
                        return self.send(200, {"ok": True, "saved": saved, "status": steamlink.status(sid)})
                    if act == "options":
                        s = config.settings()
                        s.setdefault("players", {}).setdefault(sid, {})["auto_sync"] = bool(body.get("auto_sync"))
                        config.save_settings(s)
                        return self.send(200, {"ok": True, "status": steamlink.status(sid)})
                    if act == "forget":
                        steamlink.forget(sid)
                        return self.send(200, {"ok": True, "status": steamlink.status(sid)})
                    if act == "sync":
                        if not LOCK.acquire(blocking=False):
                            return self.send(409, {"error": i18n.tr("An analysis is already running"), "query": JOB["query"]})
                        threading.Thread(target=run_job, args=("Steam sync", lambda: pipeline.sync_steam(sid)), daemon=True).start()
                        return self.send(200, {"started": True})
                except steamlink.SteamError as e:
                    return self.send(400, {"error": str(e)})
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self.send(500, {"error": str(e)})
        return self.send(404, {"error": "not found"})


def refresh_plan(sid):
    pipeline.attach_plan(sid)
    build_app.write_player(sid)


RELANG = {"t": None, "lang": None, "tried": None}
_WL = {"key": None, "v": None}


def written_lang(own):
    """The language your advice.json was written in (13/10; English before), read again only when it changes: the
    file is megabytes. None: no analysis yet."""
    p = os.path.join(config.player_dir(own), "advice.json")
    try:
        key = (p, os.path.getmtime(p))
    except OSError:
        return None
    if _WL["key"] != key:
        try:
            with open(p, "rb") as fh:
                m = re.search(rb'"written_lang":\s*"(\w+)"', fh.read())
        except OSError:
            return None
        _WL.update(key=key, v=m.group(1).decode() if m else "en")
    return _WL["v"]


def relang_if_needed():
    """The page opens in a language your analysis isn't written in (13/10: after the update that brought the languages,
    or a new browser language): written again in it once, in the background (relang_own; tried again 10 minutes
    later at most, when a match or a job stopped it)."""
    if os.environ.get("COACH_TEST"):   # a test copy leaves the main app's analysis alone
        return
    try:
        own = str(config.settings().get("own_steamid") or "")
        if not own.isdigit() or RELANG["t"]:
            return
        cur, wl = i18n.current(), written_lang(own)
        if wl is None or wl == cur:
            return
        tried = RELANG["tried"]
        if tried and tried[0] == (own, cur) and time.time() - tried[1] < 600:
            return
        RELANG["tried"] = ((own, cur), time.time())
        relang_own()
    except Exception as e:
        print("relang:", e, flush=True)


def relang_own():
    """The app's language changed (13/10): your own analysis written again in it, in the background, from what is
    already analyzed (no demo read again; a minute or so). Not during a match, not while a job runs: then the next
    update writes it. -> True when it started."""
    own = str(config.settings().get("own_steamid") or "")
    if not own.isdigit() or JOB["running"] or config.in_match() or not os.path.exists(os.path.join(config.player_dir(own), "advice.json")):
        return False
    RELANG.update(t=time.time(), lang=i18n.current())

    def go():
        try:
            pipeline.rebuild_advice(own)
            refresh_plan(own)
        except Exception as e:
            print("relang:", e, flush=True)
        finally:
            RELANG["t"] = None
    threading.Thread(target=go, daemon=True).start()
    return True


def account():
    """Your Steam name and avatar for the bar's account (05/10): the public profile (no key, as the analysis reads
    it), kept a day in out/account.json."""
    own = str(config.settings().get("own_steamid") or "")
    if not own.isdigit():
        return {}
    f = os.path.join(config.OUT, "account.json")
    c = config.read_json(f, {}) or {}
    if c.get("steamid") == own and c.get("avatar") and time.time() - (c.get("at") or 0) < 86400:
        return c
    sp = {}
    try:   # Steam's official API with your key when you gave one (the public profile's avatar can be an old one: 404)
        from wily.matches import steamlink
        if steamlink.api_key():
            x = steamlink.check_key(steamlink.api_key(), own) or {}
            sp = {"name": x.get("personaname"), "avatar": x.get("avatarfull") or x.get("avatarmedium")}
    except Exception:
        sp = {}
    if not sp.get("avatar"):
        from wily.core import steamprofile
        sp = steamprofile.steam_profile(own) or {}
    if sp.get("avatar"):
        c = {"steamid": own, "name": sp.get("name"), "avatar": sp.get("avatar"), "at": time.time()}
        config.write_json(f, c)
    return c if c.get("steamid") == own else {}


def set_focus(sid, card):
    """The focus written into the saved plan and the profile's page as they are (seconds; building the plan again
    takes minutes): the next build keeps it, focus.json holds it."""
    for path, keys, kw in ((os.path.join(config.player_dir(sid), "advice.json"), ("plan",), {"indent": 1, "default": str}),
                           (os.path.join(build_app.SITE, "players", f"{sid}.json"), ("advice", "plan"), {"separators": (",", ":")})):
        d = config.read_json(path, None)
        if not isinstance(d, dict):
            continue
        x = d
        for k in keys:
            x = x.setdefault(k, {})
        x["focus"] = card
        config.write_json(path, d, **kw)


def voice_status():
    try:
        from wily.live import voice
    except Exception as e:
        return {"available": False, "error": str(e)}
    ok, why = voice.available()
    if not ok:   # no sound library: the page says so instead of offering a microphone that fails on the first click
        return {"available": False, "error": why, "settings": voice.settings()}
    m = voice.REC.meta
    return {"available": True, "backend": voice.backend(), "settings": voice.settings(), "device": voice.chosen_device(), "cs2_device": voice.cs2_voice_device(),
            "recording": bool(m), "level": round(voice.REC.peak, 4) if m else None,
            "current": m and {k: m[k] for k in ("id", "map", "start_iso", "device", "source")},
            "transcribing": voice.transcribing(), "recordings": voice.recordings()[:12],
            "live": {"on": voice.settings().get("live", True), "running": voice.LIVE.running(), "last": voice.LIVE.last},
            "team": {**{k: v for k, v in ((m or {}).get("team") or {}).items() if k in ("consent", "at", "device")},
                     "on": voice.TEAM.running(), "pending": bool(voice.TEAM.pending)}}


PAGE = {"seen": 0.0, "any": 0.0}   # the last time a Wily page asked for the game's state; anything at all (an open page peeks every few seconds)


def app_busy():
    """Why the app can't restart now (None: it can): CS2 open (a match, its menu or the training server), an analysis,
    a recording or a transcription, the references being recomputed."""
    try:
        import psutil
        if any(config.is_cs2(p.info.get("name")) for p in psutil.process_iter(["name"])):
            return i18n.tr("CS2 is open")
    except Exception:
        pass
    if LOCK.locked():
        return i18n.tr("an analysis is running")
    try:
        v = voice_status()
        if v.get("recording") or v.get("transcribing"):
            return i18n.tr("a recording or a transcription")
    except Exception:
        pass
    r = config.read_json(os.path.join(config.OUT, "refresh.json"), {}) or {}
    if r.get("running") and time.time() - (r.get("updated") or 0) < 3600:
        return i18n.tr("the references are being updated")
    return None


def server_copy_watch():
    """After a CS2 update the training server's copy links the game's old files: linked again in the background when
    nothing plays (16/10: it was done at the click on Warm-up, 1 min 40 s before the server even started)."""
    time.sleep(90)
    while True:
        try:
            from wily.training import replay
            s = replay._state()
            if replay.installed() and not app_busy() and not replay._pid_alive(s.get("pid")):
                sys.path.insert(0, os.path.join(config.HERE, "plugin"))
                import make_server
                if not make_server.current():
                    print("training server: CS2 was updated, its copy is linked again", flush=True)
                    make_server.main(log=lambda *a: None)
                    make_server.plugin()
        except Exception as e:
            print("training server copy:", e, flush=True)
        time.sleep(1800)


def cs2_page_watch():
    """CS2 starts and no Wily page is open: Wily opens its In game page (07/10, the user: the reminder "lance Wily" at
    CS2's start, "dans le chat du lobby": CS2 lets nothing write in its lobby's chat, neither a config nor a command, and
    Wily already starts with Windows: it opens itself instead). At the game's start, before its window: CS2 comes up over
    the browser, never a window over a game already running. Settings: "open_on_cs2" (on unless turned off)."""
    try:
        import psutil
    except ImportError:
        return
    was = None
    while True:
        try:
            on = any(config.is_cs2(p.info.get("name")) for p in psutil.process_iter(["name"]))
        except Exception:
            on = was
        if on and was is False and time.time() - PAGE["seen"] > 20 and config.settings().get("open_on_cs2", True):
            print("CS2 starts, no Wily page open: the In game page", flush=True)
            webbrowser.open(f"http://127.0.0.1:{PORT}/#ingame")
        was = on
        time.sleep(3)


def voice_watch(every=15):
    """Stops an automatic recording when the game is gone, refreshes the plan once a transcription is done, and
    transcribes again the recordings a match stopped, one by one, while no map is loaded."""
    import time
    seen, failed = set(), {}   # failed: recording -> when; a match stopping it is no failure, a failure is tried again after 30 min
    while True:
        time.sleep(every)
        try:
            from wily.live import gsi
            from wily.live import voice
            voice.watchdog(gsi.state())
            from wily.training import replay
            replay.idle_check()   # the training server stops itself 20 min after you left it
            p = voice.JOB.get("proc")
            if p and p.poll() is not None and p.pid not in seen:
                seen.add(p.pid)
                if p.returncode != 0 and not config.in_match():   # 06/10: two evening recordings stopped by the next match stayed untranscribed
                    failed[voice.JOB["id"]] = time.time()
                sid = config.settings().get("own_steamid")
                if sid and p.returncode == 0 and not LOCK.locked():
                    refresh_plan(sid)
            gs = gsi.state() or {}
            if not gs.get("map") or gs.get("age", 0) > 120:   # the game in its menu or closed: what a match stopped, now
                voice.resume_pending({r for r, t in failed.items() if time.time() - t < 1800})
        except Exception as e:
            print("microphone watch:", e, flush=True)


def auto_sync(every=1800):
    """Only when you turned it on in Settings (off by default: the Update button in the header does it when you want):
    new matches at start-up, then every 30 minutes, never during a match."""
    import time
    time.sleep(20)
    while True:
        while config.in_match():   # never start downloads and analyses during a match: after it
            time.sleep(30)
        s = config.settings()
        sid = str(s.get("own_steamid") or "")
        p = s.get("players", {}).get(sid, {})
        if sid.isdigit() and p.get("authcode") and p.get("auto_sync", False) and LOCK.acquire(blocking=False):
            print("Automatic Steam sync…", flush=True)
            run_job("Steam sync", lambda: pipeline.sync_steam(sid))  # releases LOCK
        # teammates whose history code you added: their matches without you too
        for other, op in list(config.settings().get("players", {}).items()):
            if other != sid and other.isdigit() and op.get("authcode") and op.get("auto_sync", False) and LOCK.acquire(blocking=False):
                print(f"Automatic Steam sync of {op.get('name') or other}…", flush=True)
                run_job(f"Steam sync of {op.get('name') or other}", lambda o=other: pipeline.sync_steam(o))
        time.sleep(every)


def serving(port, timeout=1.0):
    """Something really is listening there, as opposed to a bind refused for another reason."""
    import socket
    with socket.socket() as s:
        s.settimeout(timeout)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


if __name__ == "__main__":
    if sys.stdout is None:  # started with pythonw (no console): keep a log file instead
        sys.stdout = sys.stderr = open(os.path.join(config.CACHE, "serve.log"), "a", encoding="utf-8", buffering=1)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(build_app.SITE, "index.json")):
        print("First build of the site…")
        build_app.build()
    # Windows hands the port to a second socket when SO_REUSEADDR is on, so an instance there must not ask for it.
    # Linux never gives a port to a second listener, with or without it, and without it refuses the bind for a whole
    # minute after a stop while the last answered connections sit in TIME_WAIT (10/10, measured at 60 s on a player's
    # PC): the app then said it was already running while nothing was.
    ThreadingHTTPServer.allow_reuse_address = os.name != "nt"
    try:
        srv = _Server(("127.0.0.1", PORT), Handler)
    except OSError as e:
        if serving(PORT):
            print(f"Wily is already running: open http://127.0.0.1:{PORT}/")
            if "--no-browser" not in sys.argv:
                webbrowser.open(f"http://127.0.0.1:{PORT}/")   # your Review (07/10: Live is for the match)
            sys.exit(0)
        sys.exit(f"Wily cannot listen on port {PORT}: {e}. Nothing answers there: another program may hold it, or the "
                 f"port was just released and the system still keeps it a few seconds.")
    url = f"http://127.0.0.1:{PORT}/"   # your Review first; CS2's start opens Live (cs2_page_watch)
    print(f"Wily: {url}  (Ctrl+C to stop)")
    config.full_speed()   # 16/10: started without a window (Windows' startup), Windows may run it on the slow cores
    if not os.environ.get("COACH_TEST"):
        threading.Thread(target=cs2_page_watch, daemon=True).start()
        threading.Thread(target=server_copy_watch, daemon=True).start()

        def warm():   # your files in memory a moment after the app starts (the PC's start: nothing is there yet)
            # started by hand, the PC up for a while (22/10, his test video: Prepare opened a minute after he started the
            # app, its warm-up still 2 min away): at once; Windows' start: 2 min, the disk busy with the rest
            try:
                import ctypes
                up = ctypes.windll.kernel32.GetTickCount64() / 1000.0
            except Exception:
                up = 0.0
            time.sleep(5 if up > 600 else 120)
            own = config.settings().get("own_steamid")
            if own and not config.in_match():
                pipeline.prefetch(int(own))
            if own and not config.in_match():   # Prepare's answers for your maps, ahead (20/10: "accélérer la préparation")
                from wily.training import train
                try:   # this thread only below the others (the whole app's priority stays: its pages answer)
                    import ctypes
                    ctypes.windll.kernel32.SetThreadPriority(ctypes.windll.kernel32.GetCurrentThread(), -2)
                except Exception:
                    pass
                train.prewarm(str(own))
        threading.Thread(target=warm, daemon=True).start()
    if os.environ.get("COACH_TEST"):  # a test copy: leaves the game's settings, the Steam sync and the microphone alone
        print("test copy: game detection, sync and microphone left to the main app")
    else:
        try:
            from wily.live import gsi
            if gsi.refresh(PORT):
                print("Game detection updated: restart CS2 so it picks it up.")
        except Exception as e:
            print("game detection:", e)
        threading.Thread(target=auto_sync, daemon=True).start()
        threading.Thread(target=voice_watch, daemon=True).start()
        from wily.coaching import feedback
        threading.Thread(target=feedback.watch, daemon=True).start()   # !report in the training server's chat (07/10)
        from wily.live import chatcalls
        threading.Thread(target=chatcalls.watch, daemon=True).start()   # numpad keys of the paths: the focus
        if config.role() != "client" and (config.read_json(GROW_CTL, {}) or {}).get("on"):   # the base was growing: it goes on
            threading.Timer(60, grow_start).start()
        if config.role() == "client":   # a player's copy: updates from the coach, and the matches they chose to share
            from wily.sharing import contrib
            from wily.app import updater
            threading.Thread(target=updater.watch, kwargs={"busy": app_busy, "quiet": lambda: time.time() - PAGE["any"] > 300},
                             daemon=True).start()   # automatic updates: installed when nobody uses the app (08/10)
            threading.Thread(target=contrib.watch, daemon=True).start()
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    srv.serve_forever()
