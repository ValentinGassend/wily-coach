"""The app for any player's PC (05/10: "any player gets the same as me, the training server, the live advice,
everything, like any client"): one folder to unzip, with Python and its libraries inside, the code, the base's
references, and for a known player their own matches from the base.

    python tools/make_beta.py --generic                        a first install for any player (no history: their PC
                                                         downloads and analyzes their matches)
    python tools/make_beta.py --player <steamid64> [--update]  a player's package with their matches from the base (the
                                                         beta); --update leaves their settings and profile alone
    python tools/make_beta.py --release <version> [--notes "…"] the website's release (wily.valentingassend.com/releases):
                                                         the code, the runtime, the base and the full install as
                                                         zips, and latest.json signed with the coach's release key
    options: --with-dailycsnades (once Daily CS Nades agreed), --no-python, --no-zip

What never leaves this PC: the settings (keys, codes, tokens), the voice, the other players' profiles, the raw demos,
the logs, the base loop's state, the keys (out/pack_key.txt, out/release_key.pem). The base's tables are pseudonymized
(anon.py): the players of its matches get a stable made-up SteamID and no name, except in a known player's own
matches (theirs, as in their own demos) and in the pro matches (public). A last check refuses the package when a real
SteamID or a name is left anywhere else.

Third-party content: Daily CS Nades' lineup catalog has no license (05/10): out of the package until they agree
(--with-dailycsnades). The Fachwerk lineup book (gronnmann on GitHub, no license) is downloaded by the player's own
app from its author's repository. The licenses of what the package carries are in LICENSES/."""
import base64
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # run as a script: the root, for wily

import numpy as np
import pyarrow.parquet as pq

from wily.core import anon
from wily.core import config

DIST = os.path.join(config.HERE, "dist")
DL = os.path.join(DIST, "cache")
SITE = os.path.join(DIST, "site_wily")
RELEASES = os.path.join(SITE, "releases")
PY_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
# the versions this app runs with here: the players' copy behaves the same (cryptography: the updates' signature)
REQS = {"demoparser2": "0.42.0", "pandas": "2.3.3", "numpy": "2.3.4", "pyarrow": "25.0.1", "pillow": "12.0.0", "psutil": "7.2.2",
        "scikit-learn": "1.7.2", "soundfile": "0.13.1", "sounddevice": "0.5.6", "soundcard": "0.4.6", "faster-whisper": "1.2.1",
        "cryptography": "50.0.1"}
# a library the ones above pull in, held back because its next version breaks them (12/10): PyAV 19 removed av.open's
# metadata_errors, which faster-whisper 1.2.1 passes, so no recording could be transcribed. It needs Python 3.12+: the
# Windows runtime (3.11) already holds 18.1.0, but a Linux install on Python 3.12/3.13 got 19 (PR #2, a Fedora tester).
# Kept out of runtime_key: a new key rebuilds the Windows runtime with fresh indirect libraries (untested) and makes
# every player download it again (234 MB) for a version it already has. Pinned in requirements.txt (Linux) and in any
# future runtime build.
PINS = {"av": "18.1.0"}
# the code (14/10, the new tree): the app's package, its launcher, its page, its resources, its match-list tool. The
# install's root keeps serve.py (the shortcuts start it), wily.sh and wily.png (the Linux menu entry names them there)
FILES = {"serve.py": "serve.py", "wily.sh": "wily.sh", os.path.join("installer", "wily.png"): "wily.png"}
DIRS = ["wily", "templates", "resources", "vendor"]
SERVER_ZIPS = ["mmsource.zip", "css-runtime.zip"]   # Metamod:Source and CounterStrikeSharp for the training server
KEY_F = os.path.join(config.OUT, "release_key.pem")   # Ed25519: signs latest.json; its public half ships in the code
RELEASES_URL = "https://wily.valentingassend.com/releases/"   # where the installer downloads the parts from

PER_MATCH = [os.path.join("population"), os.path.join("population", "buys"), os.path.join("population", "midround"),
             os.path.join("population", "routes"), os.path.join("population", "tside"), "style"]
# the pro matches (public, from HLTV): as they are; the pro references of a profile read their positions (proref)
PUBLIC = [os.path.join("population", "midround_pro"), os.path.join("population", "routes_pro"), "style_pro", "deep_pro"]
BASE_FILES = ["train_sites.json", "train_spots.json", "train_zones.json", "hostage.json", "cross.json", "cross_notes.json",
              os.path.join("pro", "matches.json")]
BASE_DIRS = ["train_entries", "train_crossfire", "train_momentum", os.path.join("site", "radars")]
DAILYCSNADES = [os.path.join("site", "nadecat")]   # + out/lineups/*_dailycsnades.json
FRESH = 120   # a file the base loop wrote in the last 2 minutes may be half-written: left for the next package
SITUATIONS = 20   # situations to replay built per map of the player
NEVER = {"settings.json", "pack_key.txt", "release_key.pem", "account.json", "train.json", "train_progress.json",
         "contrib.json", "update.json"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def gentle():
    """Below normal priority: the game keeps the processor (05/10: CS2 open while a release was built)."""
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        config.low_priority()


def pause_for_match(what):
    """A match running: the package waits for its end (the app's own rule: the game first)."""
    config.wait_for_match_end(log=lambda m: log(m), what=what)


def fetch(url):
    os.makedirs(DL, exist_ok=True)
    p = os.path.join(DL, url.rsplit("/", 1)[-1])
    if not os.path.exists(p):
        log("download", url)
        urllib.request.urlretrieve(url, p + ".part")
        os.replace(p + ".part", p)
    return p


def runtime_key():
    return hashlib.sha1(json.dumps([PY_URL, REQS], sort_keys=True).encode()).hexdigest()[:10]


# ---------------------------------------------------------------- Python and its libraries

def runtime(dst):
    """python.org's embeddable Python 3.11 with the app's libraries: made once in dist/cache, copied into the package.
    Its ._pth puts the app's folder on the path (an embedded Python ignores the script's folder)."""
    key = runtime_key()
    built = os.path.join(DL, f"python-{key}")
    py = os.path.join(built, "python.exe")
    # pip sees only the embedded Python: this PC's own libraries (the user site) made it skip packages (05/10)
    env = dict(os.environ, PYTHONNOUSERSITE="1")
    env.pop("PYTHONPATH", None)
    if not os.path.exists(os.path.join(built, ".done")):
        shutil.rmtree(built, ignore_errors=True)
        zipfile.ZipFile(fetch(PY_URL)).extractall(built)
        pth = glob.glob(os.path.join(built, "python3*._pth"))[0]
        zname = os.path.basename(pth).replace("._pth", ".zip")
        open(pth, "w", encoding="utf-8").write(f"{zname}\n.\n..\nimport site\n")
        log("pip into the embedded Python…")
        subprocess.run([py, "-s", fetch(PIP_URL), "--no-warn-script-location"], check=True, env=env)
        log("the libraries…")
        subprocess.run([py, "-s", "-m", "pip", "install", "--no-warn-script-location", "--disable-pip-version-check",
                        *[f"{k}=={v}" for k, v in {**REQS, **PINS}.items()]], check=True, env=env)
        subprocess.run([py, "-s", "-m", "pip", "check"], check=True, env=env)   # every dependency there, in versions that fit
        subprocess.run([py, "-s", "-c", "import pandas, pyarrow, demoparser2, sklearn, scipy, psutil, PIL, soundfile, sounddevice, "
                                        "soundcard, faster_whisper, ctranslate2, av, cryptography; print('libraries ok')"], check=True, env=env)
        open(os.path.join(built, ".done"), "w").write(key)
    if dst:
        # the libraries' own test suites (109 MB) stay out
        shutil.copytree(built, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".done", "__pycache__", "tests"))
        open(os.path.join(dst, ".runtime"), "w").write(key)


# ---------------------------------------------------------------- the release key

def release_key():
    """The coach's Ed25519 key: created once in out/release_key.pem, never shipped. A player's app installs only what
    it signed (a hosting account broken into could not push code to every player)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if not os.path.exists(KEY_F):
        k = Ed25519PrivateKey.generate()
        open(KEY_F, "wb").write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                serialization.NoEncryption()))
        log(f"release key created: {KEY_F} (keep it: without it no update can reach the players)")
    return serialization.load_pem_private_key(open(KEY_F, "rb").read(), password=None)


def public_key_hex():
    from cryptography.hazmat.primitives import serialization
    return release_key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


# ---------------------------------------------------------------- the code

def modules():
    """The app's modules: the whole wily package (the coach's tools, tools/ and website/, stay out)."""
    out = []
    for r, ds, fs in os.walk(os.path.join(config.HERE, "wily")):
        ds[:] = [d for d in ds if d != "__pycache__"]
        out += [os.path.relpath(os.path.join(r, f), config.HERE) for f in fs if f.endswith(".py")]
    return sorted(out)


def copy_code(dst, version, build=None):
    ms = modules()
    for src, name in FILES.items():
        if os.path.exists(os.path.join(config.HERE, src)):
            shutil.copy2(os.path.join(config.HERE, src), os.path.join(dst, name))
    for d in DIRS:
        if os.path.isdir(os.path.join(config.HERE, d)):
            shutil.copytree(os.path.join(config.HERE, d), os.path.join(dst, d), dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.ts", "bw.zip", "*_next.html"))
    pl = os.path.join(dst, "plugin")
    os.makedirs(os.path.join(pl, "CoachReplay", "bin", "out"), exist_ok=True)
    shutil.copy2(os.path.join(config.HERE, "plugin", "make_server.py"), pl)
    for f in ("CoachReplay.dll", "CoachReplay.pdb"):
        shutil.copy2(os.path.join(config.HERE, "plugin", "CoachReplay", "bin", "out", f), os.path.join(pl, "CoachReplay", "bin", "out"))
    shutil.copy2(os.path.join(config.HERE, "plugin", "CoachReplay", "LICENSE.txt"), os.path.join(pl, "CoachReplay"))
    sys.path.insert(0, os.path.join(config.HERE, "plugin"))
    import make_server
    for z in SERVER_ZIPS:
        shutil.copy2(make_server._zip(z), pl)
    shutil.copytree(os.path.join(config.HERE, "legal", "licenses"), os.path.join(dst, "LICENSES"), dirs_exist_ok=True)
    shutil.copy2(os.path.join(config.HERE, "legal", "THIRD_PARTY_NOTICES.txt"), dst)
    open(os.path.join(dst, "requirements.txt"), "w", encoding="utf-8").write("".join(f"{k}=={v}\n" for k, v in {**REQS, **PINS}.items()))
    open(os.path.join(dst, "release_key.pub"), "w").write(public_key_hex())
    # the build: what tells two publications of one version apart (the version only changes when the coach says so)
    config.write_json(os.path.join(dst, "VERSION.json"), {"app": version, "build": build or time.strftime("%Y%m%d-%H%M"), "runtime": runtime_key(),
                                                          "built": int(time.time())}, indent=1)
    log(f"code {version}: {len(ms)} modules")


# ---------------------------------------------------------------- the base, pseudonymized

def lands(path):
    """Where each throw of the base landed in the world (x, y, z), from its match's demo extraction: the training's
    grenade drills show that very landing (train._land), and a player's PC has only its own matches' extractions."""
    import pandas as pd
    df = pd.read_parquet(path)
    if "land_Z" in df and df.land_Z.notna().any():   # the base's own file carries them since nades v5 (09/10)
        log(f"lineup landings: {int(df.land_X.notna().sum())} of {len(df)} throws (in the base)")
        return
    key = ["match", "round", "type", "_x", "_y"]
    parts = []
    for mid in df["match"].astype(str).unique():
        f = os.path.join(config.DEEP, mid, "grenades.parquet")
        try:
            G = pd.read_parquet(f, columns=["round", "type", "X", "Y", "land_X", "land_Y", "land_Z"])
        except Exception:
            continue
        parts.append(G.assign(match=mid))
    L = pd.concat(parts, ignore_index=True)
    for d in (df, L):
        d["_x"], d["_y"] = d.X.round(0), d.Y.round(0)
    df["match"] = df["match"].astype(str)
    L = L.drop_duplicates(key)[key + ["land_X", "land_Y", "land_Z"]]
    out = df.merge(L, on=key, how="left").drop(columns=["_x", "_y"])
    assert len(out) == len(df)
    out.to_parquet(path, index=False)
    log(f"lineup landings: {int(out.land_X.notna().sum())} of {len(out)} throws")


def _settled(p):
    return time.time() - os.path.getmtime(p) > FRESH


def copy_base(dst, pseudo, mine, dailycsnades=False):
    """The base's references: the summaries as they are (no player in them), the per-match tables pseudonymized
    (a known player's own matches real), the pro tables as they are."""
    out = os.path.join(dst, "out")
    n = {"tables": 0, "skipped": 0}
    for d in PER_MATCH:
        src = os.path.join(config.OUT, d)
        for f in os.listdir(src):
            if not (f.endswith(".parquet") and f[:-8].isdigit()):
                continue
            if n["tables"] % 500 == 0:
                pause_for_match("the package")
            s, t = os.path.join(src, f), os.path.join(out, d, f)
            try:
                if not _settled(s):
                    raise ValueError("being written")
                if f[:-8] in mine or d.endswith("tside"):   # tside: rounds and zones, no player in it
                    pq.read_metadata(s)
                    os.makedirs(os.path.dirname(t), exist_ok=True)
                    shutil.copy2(s, t)
                else:
                    anon.pseudonymize(s, t, pseudo)
                n["tables"] += 1
            except Exception as e:
                n["skipped"] += 1
                print("  skipped", os.path.join(d, f), type(e).__name__, str(e)[:80])
    anon.pseudonymize(os.path.join(config.OUT, "population", "nades.parquet"), os.path.join(out, "population", "nades.parquet"), pseudo, keep_match=mine)
    lands(os.path.join(out, "population", "nades.parquet"))
    for f in glob.glob(os.path.join(config.OUT, "population", "*.json")):
        shutil.copy2(f, os.path.join(out, "population"))
    for d in PUBLIC + BASE_DIRS + (DAILYCSNADES if dailycsnades else []):
        shutil.copytree(os.path.join(config.OUT, d), os.path.join(out, d), dirs_exist_ok=True)
    if dailycsnades:
        os.makedirs(os.path.join(out, "lineups"), exist_ok=True)
        for f in glob.glob(os.path.join(config.OUT, "lineups", "*_dailycsnades.json")):
            shutil.copy2(f, os.path.join(out, "lineups"))
    # 08/10, his warm-up on the installed app: a player's PC has its own matches only, and what the training draws from
    # the base's players came out of those few (Nuke's Tunnels outlined 32 x 96 u, almost no rusher for the anti-rush
    # stuff): made here, shipped with the base
    from wily.training import train
    pause_for_match("the zones")
    train.zones_for_base(log)
    early(out)
    for f in BASE_FILES:
        if os.path.exists(os.path.join(config.OUT, f)):
            os.makedirs(os.path.dirname(os.path.join(out, f)), exist_ok=True)
            shutil.copy2(os.path.join(config.OUT, f), os.path.join(out, f))
    shutil.copy2(os.path.join(config.OUT, "site", "pros.json"), os.path.join(out, "site"))
    matches = len([f for f in os.listdir(os.path.join(out, "population")) if f.endswith(".parquet") and f[:-8].isdigit()])
    info = {"built": int(time.time()), "matches": matches, "players": len(pseudo.memo), "version": time.strftime("%Y%m%d-%H%M"),
            "dailycsnades": bool(dailycsnades)}
    if mine:   # a known player's matches came from the base: never shared back as theirs (contrib.py)
        info["player_matches"] = sorted(mine)
    config.write_json(os.path.join(out, "base_pack.json"), info)
    log(f"base {info['version']}: {n['tables']} tables ({n['skipped']} left for the next package), {matches} matches, "
        f"{len(pseudo.memo)} players pseudonymized")
    return info


def early(out):
    """The Ts' first 40 s of the base's rounds per map (train._early: when a rush gets where), compact and without who
    they were (a number per player in each file, no SteamID)."""
    import pandas as pd
    src = os.path.join(config.OUT, "train_early")
    if not os.path.isdir(src):
        return
    dst = os.path.join(out, "train_early")
    os.makedirs(dst, exist_ok=True)
    total = 0
    for fp in sorted(glob.glob(os.path.join(src, "*.parquet"))):
        E = pd.read_parquet(fp)
        E["sid"] = E["sid"].astype("category").cat.codes.astype(np.int32)
        E["zone"] = E["zone"].astype(str)   # plain text: the package's check reads every column
        for c in ("X", "Y", "Z"):
            E[c] = E[c].round().astype(np.int16)
        t = os.path.join(dst, os.path.basename(fp))
        E.to_parquet(t, compression="zstd", index=False)
        shutil.copy2(fp[:-8] + ".json", dst)
        total += os.path.getsize(t)
    log(f"early rushers: {total / 1048576:.0f} MB for {len(glob.glob(os.path.join(dst, '*.parquet')))} maps")


def copy_player(dst, sid, update):
    """The player's own matches from the base (their demos as extracted here: Valve keeps a demo about a month), their
    profile, their team. -> their match ids."""
    from wily.app import pipeline
    out = os.path.join(dst, "out")
    mine = set(pipeline.player_matches(sid))
    for mid in mine:
        shutil.copytree(os.path.join(config.DEEP, mid), os.path.join(out, "deep", mid), dirs_exist_ok=True)
    if not update:   # their profile: from here the first time, then their PC keeps it up to date
        shutil.copytree(config.player_dir(sid), os.path.join(out, "players", sid), dirs_exist_ok=True)
    for f in glob.glob(os.path.join(config.OUT, "teams", "*.json")):
        t = config.read_json(f, {}) or {}
        if sid in {str(m.get("steamid") if isinstance(m, dict) else m) for m in t.get("members") or []}:
            os.makedirs(os.path.join(out, "teams"), exist_ok=True)
            shutil.copy2(f, os.path.join(out, "teams"))
    log(f"player {config.display_name(sid)}: {len(mine)} matches, their profile")
    return mine


def _situation(a):
    """One situation of the player's matches built from its demo, into the package (a worker process)."""
    from wily.training import replay
    sid, s, out = a
    replay.SCEN = os.path.join(out, s["mid"])
    try:
        replay.build(sid, s["mid"], s["round"], s["kind"], s.get("t") if s["kind"] == "clutch" else None)
        return True
    except Exception as e:
        print("  situation", s["id"], type(e).__name__, str(e)[:100], flush=True)
        return False


def situations(dst, sid, per_map=SITUATIONS):
    """The training replays the situations of a player's matches from their demos, which stay here (200-300 MB each):
    the most important ones of each map are built here (4-6 s each) and go in the package (replay.PREBUILT)."""
    import multiprocessing
    from wily.training import replay
    sc = replay.scenarios(sid, n=1000)   # the worst first
    pick, per = [], {}
    for s in sc:
        if per.get(s["map"], 0) < per_map:
            per[s["map"]] = per.get(s["map"], 0) + 1
            pick.append(s)
    cache = os.path.join(DL, "scenarios", sid)   # built once: the next package only builds the new ones
    todo = [s for s in pick if not os.path.exists(os.path.join(cache, s["mid"], f"{s['id']}.json"))]
    if todo:
        with multiprocessing.Pool(4) as pool:
            pool.map(_situation, [(sid, s, cache) for s in todo], chunksize=1)
    out, n = os.path.join(dst, "out", "scenarios"), 0
    for s in pick:
        f = os.path.join(cache, s["mid"], f"{s['id']}.json")
        if os.path.exists(f):
            os.makedirs(os.path.join(out, s["mid"]), exist_ok=True)
            shutil.copy2(f, os.path.join(out, s["mid"]))
            n += 1
    log(f"situations to replay: {n} of {len(pick)} ({len(todo)} built now; {len(sc)} in their matches, the {per_map} most important of each map)")


# ---------------------------------------------------------------- the last check

def check(dst, mine, sid):
    """No real SteamID or name in the package outside a known player's own matches, profile and team, and the pro
    data; none of the coach's keys, settings or state."""
    out = os.path.join(dst, "out")
    ok_dirs = [os.path.join(out, d) for d in ["deep", "scenarios", "teams"] + PUBLIC + ([os.path.join("players", sid)] if sid else [])]
    ok_files = {os.path.join(out, "site", "pros.json"), os.path.join(out, "pro", "matches.json")}
    bad = []
    for root, _, fs in os.walk(out):
        if any(root == d or root.startswith(d + os.sep) for d in ok_dirs):
            continue
        for f in fs:
            p = os.path.join(root, f)
            if p in ok_files or f[:-8] in mine:
                continue
            if root == out and f in NEVER and f != "settings.json":
                bad.append(f"{f} must stay on the coach's PC")
            elif f.endswith(".parquet"):
                tb = pq.read_table(p)
                keep = (np.isin(np.array([str(x) for x in tb.column("match").to_pylist()]), list(mine))
                        if mine and "match" in tb.column_names else None)   # a table of every match: their own rows
                bad += [f"{p}: {b}" for b in anon.leftovers(tb, keep)]
            elif f.endswith((".json", ".jsonl", ".txt", ".csv")):
                t = open(p, encoding="utf-8", errors="replace").read()
                if p == os.path.join(out, "settings.json"):
                    extra = set(json.loads(t)) - {"role", "own_steamid"}
                    if extra:
                        bad.append(f"settings.json: {sorted(extra)}")
                elif anon.SID_RE.search(t):
                    bad.append(f"{p}: a SteamID")
    for f in glob.glob(os.path.join(dst, "**", "*.pem"), recursive=True):
        bad.append(f"{f}: a private key")
    if bad:
        raise SystemExit("REFUSED, personal data left:\n  " + "\n  ".join(bad[:20]))
    log("check: no real SteamID or name outside a player's own matches and the pro data, no key, no coach settings")


# ---------------------------------------------------------------- the rest

LAUNCHER = r"""@echo off
rem Wily, your CS2 coach, on this PC (http://127.0.0.1:8765). Its window stays hidden; the page opens in your browser.
rem Its own Python only: never the libraries another Python installed on this PC.
cd /d "%~dp0"
set PYTHONNOUSERSITE=1
start "" "%~dp0python\pythonw.exe" -s serve.py
"""
AUTOSTART = r"""@echo off
rem Starts Wily in the background each time you sign in to Windows (Win+R, shell:startup to remove it).
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%STARTUP%\Wily.lnk'); $s.TargetPath='%~dp0python\pythonw.exe'; $s.Arguments='-s serve.py --no-browser'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()"
echo Wily now starts with Windows: http://127.0.0.1:8765
pause
"""
README = """WILY (alpha)
============

Hi, I'm Wily, your CS2 coach. I follow your matches live on your second screen, warm you up before you play (map
sheets, and a training server where bots replay your own situations), and review your matches with you after.
I run on this PC: your matches, your profile and your voice stay here.

I'm an alpha, the first version open to every player: things will break. Tell me with the "alpha · report" tag at
the top of my page, or write to my author (contact@valentingassend.com).
Website, updates, privacy policy and terms: https://wily.valentingassend.com

INSTALL
The simplest: WilySetup.exe from https://wily.valentingassend.com (it installs everything, shortcuts included).
With this zip instead:
1. Unzip this folder where you want to keep it, on a drive with a few GB free (not in Program Files).
2. Double-click "Wily.bat". I open in your browser at http://127.0.0.1:8765
   (Windows may ask to confirm the first time: the app is not signed yet.)
3. My first launch shows three steps: your Steam account (found on this PC), CS2 connected (game detection, and one
   launch option to paste in Steam: CS2 > Properties > Launch options:  -condebug +exec wily_bind ), your match
   history code (from Steam's help page; no Steam Web API key needed: Wily's site asks Steam, keeping nothing).
4. Prepare > Warm-up: the training server installs itself the first time (no extra space: links to the game's files).

DAILY USE
- "Wily.bat" (or "Start with Windows.bat" once, to have me always running).
- Update (top bar): downloads and analyzes your new matches.
- Live during a match on your 2nd screen, Prepare before playing, Review after.
- Settings > App updates: my new versions and my base, checked against my author's signature.
- Something wrong, or an idea? The "alpha · report" tag at the top of the app sends a report from any page
  (you see exactly what is sent first).

PRIVACY
- Your matches, your profile and your voice stay on this PC.
- Recording your teammates' voices needs their agreement, for each match (in France: article 226-1 of the Code penal).
  The app records the team's sound only after you confirm it in game (numpad /).
- The base's matches that come with the app are anonymized (no name, no real SteamID), except your own matches
  (as in your own demos) and the public pro matches.
- Settings > Share my matches (off unless you turn it on): your new matches go to the base anonymized, without any
  SteamID, name or match id. Details: https://wily.valentingassend.com/privacy.html

LICENSES
THIRD_PARTY_NOTICES.txt and the LICENSES folder.
"""


def extras(dst, sid, update):
    open(os.path.join(dst, "Wily.bat"), "w", encoding="utf-8", newline="\r\n").write(LAUNCHER)
    open(os.path.join(dst, "Start with Windows.bat"), "w", encoding="utf-8", newline="\r\n").write(AUTOSTART)
    open(os.path.join(dst, "README.txt"), "w", encoding="utf-8", newline="\r\n").write(README)
    os.makedirs(os.path.join(dst, "cache"), exist_ok=True)
    if not update:   # a first install: a player's copy (an update leaves their settings alone)
        config.write_json(os.path.join(dst, "out", "settings.json"), {"role": "client", **({"own_steamid": sid} if sid else {})}, indent=1)


def zip_dir(src, zpath, top=True, only=None, skip=()):
    """src as a zip: under its own folder name (top), or its content at the root (an update over an install).
    only/skip: first-level names kept or left out."""
    with zipfile.ZipFile(zpath + ".part", "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, dirs, fs in os.walk(src):
            dirs.sort()
            rel_src = os.path.relpath(root, src)
            first = rel_src.split(os.sep)[0]
            if rel_src == ".":
                dirs[:] = [d for d in dirs if (only is None or d in only) and d not in skip]
                fs = [f for f in fs if (only is None or f in only) and f not in skip]
            rel = os.path.relpath(root, os.path.dirname(src)) if top else ("" if rel_src == "." else rel_src)
            if not fs and not dirs and rel:
                z.writestr(rel.replace(os.sep, "/") + "/", "")
            for f in sorted(fs):
                z.write(os.path.join(root, f), os.path.join(rel, f) if rel else f)
    os.replace(zpath + ".part", zpath)


def _entry(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return {"file": os.path.basename(path), "size": os.path.getsize(path), "sha256": h.hexdigest()}


def release(dst, version, base, notes):
    """The website's release folder: the full install, and the parts an installed app updates (code, runtime, base),
    with latest.json signed. A runtime or base already published is not zipped again."""
    os.makedirs(RELEASES, exist_ok=True)
    code_z = os.path.join(RELEASES, f"code-{version}.zip")
    zip_dir(dst, code_z, top=False, skip={"python", "out", "cache"})
    rt = runtime_key()
    rt_z = os.path.join(RELEASES, f"runtime-{rt}.zip")
    if not os.path.exists(rt_z):
        zip_dir(dst, rt_z, top=False, only={"python"})
    base_z = os.path.join(RELEASES, f"base-{base['version']}.zip")
    zip_dir(os.path.join(dst, "out"), base_z, top=False, skip={"settings.json"})
    setup_z = os.path.join(RELEASES, f"Wily-{version}.zip")
    zip_dir(dst, setup_z, top=True)
    build = (config.read_json(os.path.join(dst, "VERSION.json"), {}) or {}).get("build")
    man = {"app": version, "build": build, "released": int(time.time()), "notes": notes,
           "code": dict(_entry(code_z), build=build), "runtime": dict(_entry(rt_z), key=rt),
           "base": dict(_entry(base_z), version=base["version"], matches=base["matches"]), "setup": _entry(setup_z)}
    exe = installer(man)   # WilySetup.exe for these very parts (08/10)
    if exe:
        man["installer"] = _entry(exe)
    lx = linux_installer()   # wily-linux.sh (10/10): the same code and base, with a Python of the player's own
    man["installer_linux"] = _entry(lx)
    raw = json.dumps(man, indent=1).encode()
    open(os.path.join(RELEASES, "latest.json"), "wb").write(raw)
    open(os.path.join(RELEASES, "latest.json.sig"), "w").write(base64.b64encode(release_key().sign(raw)).decode())
    keep = {v["file"] for v in man.values() if isinstance(v, dict) and v.get("file")}
    for f in os.listdir(RELEASES):   # an app only ever fetches what latest.json names: the older zips are not published
        if f.endswith(".zip") and f not in keep:
            os.remove(os.path.join(RELEASES, f))
    log(f"release {version}: " + ", ".join(f"{k} {v['size'] / 2 ** 20:.0f} MB" for k, v in man.items() if isinstance(v, dict)))
    return man


def linux_installer():
    """installer/wily-linux.sh with the release key's public half in it: it checks latest.json's signature itself."""
    s = open(os.path.join(config.HERE, "installer", "wily-linux.sh"), encoding="utf-8").read().replace("@@PUBKEY@@", public_key_hex())
    out = os.path.join(RELEASES, "wily-linux.sh")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s.replace("\r\n", "\n"))
    return out


def iscc():
    """Inno Setup's compiler: installed for this user by winget (JRSoftware.InnoSetup), or for every user."""
    for p in (shutil.which("ISCC"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
              r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"):
        if p and os.path.exists(p):
            return p
    return None


def installer(man, base_url=RELEASES_URL, out_dir=RELEASES):
    """WilySetup.exe (08/10, the user: a much simpler install): installer/wily.iss filled with this release's parts (their
    address and SHA-256, checked by the setup as it downloads them), compiled by Inno Setup. -> its path, or None."""
    exe_c = iscc()
    if not exe_c:
        log("Inno Setup not found (winget install JRSoftware.InnoSetup): no WilySetup.exe")
        return None
    import re as re_
    v = man["app"]
    vals = {"VERSION": v, "VERNUM": ".".join((re_.findall(r"\d+", v) + ["0"] * 4)[:4]), "BUILD": str(man.get("build") or ""),
            "BASEURL": base_url, "RT_FILE": man["runtime"]["file"], "RT_SHA": man["runtime"]["sha256"],
            "CODE_FILE": man["code"]["file"], "CODE_SHA": man["code"]["sha256"], "BASE_FILE": man["base"]["file"],
            "BASE_SHA": man["base"]["sha256"], "OUTDIR": out_dir, "ICON": os.path.join(config.HERE, "installer", "wily.ico"),
            "TOTAL_MB": str(round(sum(man[k]["size"] for k in ("runtime", "code", "base")) / 2 ** 20))}
    tpl = open(os.path.join(config.HERE, "installer", "wily.iss"), encoding="utf-8").read()
    for k, x in vals.items():
        tpl = tpl.replace(f"@{k}@", x)
    left = re_.findall(r"@[A-Z_]+@", tpl)
    if left:
        raise RuntimeError(f"installer template: {left} not filled")
    iss = os.path.join(DIST, "WilySetup.iss")
    open(iss, "w", encoding="utf-8-sig").write(tpl)   # with its BOM: Inno Setup reads the French messages right
    os.makedirs(out_dir, exist_ok=True)
    r = subprocess.run([exe_c, "/Q", iss], capture_output=True, text=True)
    exe = os.path.join(out_dir, "WilySetup.exe")
    if r.returncode or not os.path.exists(exe):
        log(f"WilySetup.exe not built: {(r.stdout + r.stderr)[-800:]}")
        return None
    log(f"installer: {exe} ({os.path.getsize(exe) / 2 ** 20:.1f} MB, downloads {vals['TOTAL_MB']} MB from {base_url})")
    return exe


def page_current():
    """The page ui/ builds is the one shipped: app_template.html is copied as it is, nothing here assembles it (12/10:
    the builds of 10/10 shipped the page of 10/10 00:25, without the first-launch notice that speaks of the shared
    matches nor the Linux switch, both already in ui/). -> nothing, or stops the build with what to do."""
    r = subprocess.run([sys.executable, os.path.join(config.HERE, "ui", "assemble.py")], capture_output=True, text=True,
                       encoding="utf-8", cwd=config.HERE)
    if r.returncode:
        raise SystemExit(f"ui/assemble.py failed, nothing built:\n{(r.stdout or '') + (r.stderr or '')}")
    new, cur = (open(os.path.join(config.HERE, "templates", f), "rb").read().replace(b"\r\n", b"\n") for f in ("app_template_next.html", "app_template.html"))
    if new != cur:
        raise SystemExit("templates/app_template.html is not the page ui/ builds (python ui/assemble.py just wrote"
                         " templates/app_template_next.html): check it, copy it over app_template.html, then build again")
    log("the page: the one ui/ builds")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    arg = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else None
    if "--installer" in sys.argv:   # only WilySetup.exe, for the release already in dist/site_wily/releases (a test: --base-url)
        man = config.read_json(os.path.join(RELEASES, "latest.json"), {}) or {}
        out = arg("--out") or (RELEASES if not arg("--base-url") else os.path.join(DIST, "installer-test"))
        raise SystemExit(0 if installer(man, arg("--base-url") or RELEASES_URL, out) else 1)
    sid, version = arg("--player"), arg("--release")
    generic = "--generic" in sys.argv or bool(version)
    if not sid and not generic:
        raise SystemExit(__doc__)
    if sid and not os.path.exists(os.path.join(config.player_dir(sid), "advice.json")):
        raise SystemExit(f"no profile for {sid} here: analyze them first")
    update = "--update" in sys.argv and not generic
    page_current()
    # a player's package carries the published version it is built with: their app then offers only what is newer
    pub = config.read_json(os.path.join(RELEASES, "latest.json"), {}) or {}
    version = version or pub.get("app") or "dev-" + time.strftime("%Y%m%d-%H%M")
    # a player's package built from the published code carries its build: their app offers no update to the same code
    build = None if arg("--release") else pub.get("build")
    dst = os.path.join(DIST, "Wily")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(os.path.join(dst, "out", "site"))
    t0 = time.time()
    gentle()
    pause_for_match("the package")
    copy_code(dst, version, build)
    mine = set()
    if sid and not generic:
        mine = copy_player(dst, sid, update)
        situations(dst, sid)
    base = copy_base(dst, anon.Pseudo.from_file(os.path.join(config.OUT, "pack_key.txt")), mine, "--with-dailycsnades" in sys.argv)
    extras(dst, None if generic else sid, update)
    check(dst, mine, None if generic else sid)
    if "--no-python" not in sys.argv:
        pause_for_match("the package")
        runtime(os.path.join(dst, "python"))
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(dst) for f in fs)
    log(f"folder: {dst} ({size / 2 ** 20:.0f} MB, {round(time.time() - t0)} s)")
    if arg("--release"):
        pause_for_match("the release")
        release(dst, version, base, arg("--notes") or "")
        from website import pages
        pages.build()
    elif "--no-zip" not in sys.argv:
        who = "any-player" if generic else (re.sub(r"[^\w-]", "", config.display_name(sid)) or sid)
        z = os.path.join(DIST, f"Wily-{time.strftime('%Y%m%d')}-{who}{'-update' if update else ''}.zip")
        zip_dir(dst, z)
        log(f"zip: {z} ({os.path.getsize(z) / 2 ** 20:.0f} MB)")


if __name__ == "__main__":
    main()
