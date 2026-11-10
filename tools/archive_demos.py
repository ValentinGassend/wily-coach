"""The base's older demos moved to an archive (16/10, the user: "mettre les 5000 matchs sur Google Drive pour faire de la
place"; 959 GB of demos on the 2 TB hard disk). The analyses (out/deep, the tables) stay here: only the .dem files go,
read again from the archive when needed (config.demo: the cache, then cache_archive/, then the settings' "demo_archives",
the Google Drive folder streamed by Drive for desktop: a demo there is downloaded when read).

Kept here (the working set): the matches of the players with a history code (you), the 200 most recent of each map
(Crossfire and Momentum read them), the ones not extracted yet, the ones fetched in the last 3 days.

    python tools/archive_demos.py plan                          what stays, what goes
    python tools/archive_demos.py copy --to "G:\\Mon Drive\\wily-demos" [--gb 50]
                                                                 the next demos copied there (sizes checked)
    python tools/archive_demos.py free --to "G:\\Mon Drive\\wily-demos"
                                                                 the local copies of what Drive has in its cloud deleted
    python tools/archive_demos.py cycle --to "G:\\Mon Drive\\wily-demos" [--gb 20]
                                                                 both, batch by batch, until all are there
    ... --all                                                    every analyzed demo goes, the working set too (20/10,
                                                                 the user: "libérer E des 1 965 démos"): read from Drive
    python tools/archive_demos.py lan --to "G:\\Mon Drive\\wily-lan-demos" [--gb 20]
                                                                 the LAN archives (cache/lan_demos) analyzed into the pro
                                                                 base, sent the same way (wily/base/fetch_lan.py reads
                                                                 them from there afterwards)

copy also adds the folder to the settings' "demo_archives" (the app reads the archived demos from it). free deletes a
local copy only when Drive for desktop's own database has the file in the cloud with the same size and nothing left to
upload; cycle keeps 40 GB free on the disk (Drive frees its own cache as it uploads) and waits during a match."""
import argparse
import collections
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # run as a script: the root, for wily

from wily.core import config
from wily.core import ledger

PER_MAP = 200   # crossfire.DEMOS (200) and momentum.DEMOS (120) read the most recent ones of each map
RECENT_DAYS = 3
EVERYTHING = False   # --all: only the demos not analyzed yet stay


def working_set():
    """{match: (size, date)} of the cache's demos, and the set kept here."""
    with os.scandir(config.CACHE) as it:
        dems = {e.name[:-4]: (e.stat().st_size, e.stat().st_mtime) for e in it if e.name.endswith(".dem")}
    facts = ledger.match_facts()
    if EVERYTHING:   # 20/10, the user: "libérer E des 1 965 démos": every analyzed one goes, read from Drive when needed
        return dems, {m for m in dems if m not in facts}
    from wily.app import pipeline
    s = config.settings()
    yours = {int(s.get("own_steamid") or 0)} | {int(k) for k, v in (s.get("players") or {}).items()
                                                 if k.isdigit() and isinstance(v, dict) and v.get("authcode")}
    keep = set()
    for sid in yours:
        keep |= set(pipeline.player_matches(sid)) & set(dems)
    by_map = collections.defaultdict(list)
    for m in dems:
        if m in facts:
            by_map[facts[m]["map"]].append(m)
        else:
            keep.add(m)   # not extracted yet
    for ms in by_map.values():
        keep |= set(sorted(ms, reverse=True)[:PER_MAP])   # match ids grow with time: the most recent
    keep |= {m for m, (_, t) in dems.items() if time.time() - t < RECENT_DAYS * 86400}
    return dems, keep


def _gb(dems, ms):
    return sum(dems[m][0] for m in ms) / 2**30


def plan():
    dems, keep = working_set()
    out = sorted(set(dems) - keep)
    print(f"{len(dems)} demos ({_gb(dems, dems):.0f} GB): {len(keep)} stay ({_gb(dems, keep):.0f} GB), "
          f"{len(out)} can go ({_gb(dems, out):.0f} GB)")
    return dems, out


def _analysis_running():
    """An analysis is running: the app's (its page's /api/job), or one whose last step began less than 3 min ago
    (pipeline.ANALYZING: the base loop's, a script's)."""
    import json
    import urllib.request
    try:
        if time.time() - os.path.getmtime(os.path.join(config.OUT, "ledgers", "analyzing")) < 180:
            return True
    except OSError:
        pass
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{os.environ.get('COACH_PORT', 8765)}/api/job", timeout=2) as r:
            return bool(json.loads(r.read()).get("running"))
    except Exception:
        return False


def _disk_free():
    """Before each copy: the end of a match (CS2 reads its maps from this disk) and of the app's analysis (16/10: the
    copies took the hard disk from the sync's analysis; it reads the same disk)."""
    config.wait_for_match_end(print, "demo archiving")
    said = False
    while _analysis_running() or _server_loading():
        if not said:
            print("the app is analyzing or the training server loads its map: copies paused until it's done", flush=True)
            said = True
        time.sleep(5)


def _server_loading():
    """The training server loading a map (wily/training/replay.py's LOADING, 3 min at most): CS2 reads it from this disk
    (17/10: three starts past 120 s while the copies ran)."""
    try:
        return time.time() - os.path.getmtime(os.path.join(config.OUT, "training_loading")) < 180
    except OSError:
        return False


def copy(to, gb):
    dems, out = plan()
    os.makedirs(to, exist_ok=True)
    s = config.settings()
    arch = s.setdefault("demo_archives", [])
    if to not in arch:
        arch.append(to)
        config.save_settings(s)
        print(f"the app reads the archived demos from {to}")
    done = n = 0
    for m in out:   # the oldest first
        dst = os.path.join(to, f"{m}.dem")
        if os.path.exists(dst) and os.path.getsize(dst) == dems[m][0]:
            continue
        if done + dems[m][0] > gb * 2**30:
            break
        tmp = dst + ".part"
        _disk_free()
        shutil.copyfile(os.path.join(config.CACHE, f"{m}.dem"), tmp)
        for _ in range(30):   # Drive for desktop may give the size a moment after the copy (a folder it just made)
            if os.path.getsize(tmp) == dems[m][0]:
                break
            time.sleep(0.5)
        else:
            os.remove(tmp)
            sys.exit(f"{m}: copy incomplete, stopped")
        os.replace(tmp, dst)
        done += dems[m][0]
        n += 1
        print(f"  {n}: {m} ({dems[m][0] >> 20} MB)", flush=True)
    left = sum(1 for m in out if not (os.path.exists(os.path.join(to, f"{m}.dem"))
                                      and os.path.getsize(os.path.join(to, f"{m}.dem")) == dems[m][0]))
    print(f"{n} copied ({done / 2**30:.1f} GB), {left} still to copy")


def drive_uploaded(ext=".dem"):
    """{file name: size} of the files Google Drive for desktop has in the cloud (an id from Drive, not in the trash),
    and whether it still has uploads waiting: from a copy of its own database (read only, Drive keeps running)."""
    import glob
    import sqlite3
    import tempfile
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "DriveFS")
    accts = [d for d in glob.glob(os.path.join(base, "*")) if os.path.exists(os.path.join(d, "metadata_sqlite_db"))]
    if not accts:
        return {}, True
    tmp = tempfile.mkdtemp()
    for db in ("metadata_sqlite_db", "mirror_sqlite.db"):
        for suf in ("", "-wal"):   # never "ext": the kind asked for (20/10: shadowed, it looked for "-wal" files, saw no upload)
            src = os.path.join(accts[0], db + suf)
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(tmp, db + suf))
    m = sqlite3.connect(os.path.join(tmp, "metadata_sqlite_db"))
    up = {t: s_ for t, s_ in m.execute("select local_title, file_size from items where id is not null and id != '' "
                                       "and trashed = 0 and is_tombstone = 0 and local_title like ?", (f"%{ext}",))}
    m.close()
    mi = sqlite3.connect(os.path.join(tmp, "mirror_sqlite.db"))
    waiting = sum(mi.execute(f"select count(*) from {t}").fetchone()[0] for t in ("pending_uploads", "queued_uploads"))
    mi.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return up, waiting > 0


def free(to):
    """The local copies of the archived demos Drive has in the cloud, deleted: each one in the archive folder, in
    Drive's cloud with the same size, nothing left to upload. The app reads them from the archive afterwards."""
    dems, keep = working_set()
    up, waiting = drive_uploaded()
    if waiting:
        print("Drive still has uploads waiting: nothing deleted this time")
        return 0
    n, size = 0, 0
    for m in sorted(set(dems) - keep):
        src, dst = os.path.join(config.CACHE, f"{m}.dem"), os.path.join(to, f"{m}.dem")
        if up.get(f"{m}.dem") == dems[m][0] and os.path.exists(dst) and os.path.getsize(dst) == dems[m][0]:
            os.remove(src)
            n += 1
            size += dems[m][0]
    print(f"{n} local copies deleted ({size / 2**30:.1f} GB freed), each one checked in Drive's cloud", flush=True)
    return n


def cycle(to, gb, keep_gb=40):
    """Little by little until every archived demo is in Drive (16/10, the user: "petit à petit... sans perdre l'énorme
    richesse"): a batch copied, its upload waited for, the local copies of what Drive has in the cloud deleted; never
    under keep_gb free on the disk (Drive frees its own cache as it goes), never during a match."""
    while True:
        config.wait_for_match_end(print, "demo archiving")
        free(to)
        dems, out = plan()
        left = [m for m in out if not os.path.exists(os.path.join(to, f"{m}.dem"))]
        if not left:
            print("every archived demo is in Drive", flush=True)
            return
        room = shutil.disk_usage(config.CACHE).free / 2**30 - keep_gb
        if room < 2:
            print(f"{shutil.disk_usage(config.CACHE).free / 2**30:.0f} GB free: waiting for Drive to free its cache", flush=True)
            time.sleep(600)
            continue
        copy(to, min(gb, room))
        for _ in range(360):   # its upload: up to 6 hours, until each file there has its size in Drive's cloud (a file
            time.sleep(60)    # being sent is listed with a size of 0, its queue already empty)
            up, waiting = drive_uploaded()
            sizes = {f: os.path.getsize(os.path.join(to, f)) for f in os.listdir(to) if f.endswith(".dem")}
            if not waiting and all(up.get(f) == n for f, n in sizes.items()):
                break


def _lan_files():
    """{archive name: size} of the LAN archives here analyzed into the pro base (each of their maps done, or given up
    on: a broken archive), the others stay till then (20/10, the user: "analyse tout ... les démos LAN à mettre sur drive
    ensuite")."""
    from wily.base import fetch_lan
    reg = config.read_json(fetch_lan.REG, {}) or {}
    state = {}
    for m in reg.values():
        for x in m.get("maps") or []:
            if x.get("zip"):
                state.setdefault(x["zip"], []).append(bool(x.get("done") or x.get("error")))
    if not os.path.isdir(fetch_lan.KEEP):
        return {}
    return {f: os.path.getsize(os.path.join(fetch_lan.KEEP, f)) for f in os.listdir(fetch_lan.KEEP)
            if f.endswith(".zip") and state.get(f) and all(state[f])}


def lan(to, gb, keep_gb=40):
    """The LAN archives analyzed sent to Drive batch by batch, each local one deleted once Drive has it in its cloud
    with its size; the folder kept in the settings ("lan_archive") for a later analysis to read them from."""
    from wily.base import fetch_lan
    os.makedirs(to, exist_ok=True)
    s = config.settings()
    if s.get("lan_archive") != to:
        s["lan_archive"] = to
        config.save_settings(s)
    while True:
        config.wait_for_match_end(print, "LAN archiving")
        files = _lan_files()
        up, waiting = drive_uploaded(".zip")
        if not waiting:
            n = size = 0
            for f, z in files.items():
                dst = os.path.join(to, f)
                if up.get(f) == z and os.path.exists(dst) and os.path.getsize(dst) == z:
                    os.remove(os.path.join(fetch_lan.KEEP, f))
                    n += 1
                    size += z
            if n:
                print(f"{n} LAN archives deleted here ({size / 2**30:.1f} GB freed), each one checked in Drive's cloud", flush=True)
            files = _lan_files()
        left = {f: z for f, z in files.items() if not (os.path.exists(os.path.join(to, f)) and os.path.getsize(os.path.join(to, f)) == z)}
        if not files:
            print("every analyzed LAN archive is in Drive", flush=True)
            return
        if not left:   # all copied: their upload
            time.sleep(60)
            continue
        room = min(gb, shutil.disk_usage(config.CACHE).free / 2**30 - keep_gb)
        done = 0
        for f, z in sorted(left.items()):
            if done + z > room * 2**30:
                break
            _disk_free()
            dst = os.path.join(to, f)
            shutil.copyfile(os.path.join(fetch_lan.KEEP, f), dst + ".part")
            for _ in range(30):
                if os.path.getsize(dst + ".part") == z:
                    break
                time.sleep(0.5)
            else:
                os.remove(dst + ".part")
                sys.exit(f"{f}: copy incomplete, stopped")
            os.replace(dst + ".part", dst)
            done += z
            print(f"  {f} ({z >> 20} MB)", flush=True)
        for _ in range(360):   # their upload, up to 6 hours
            time.sleep(60)
            up, waiting = drive_uploaded(".zip")
            if not waiting and all(up.get(f) == os.path.getsize(os.path.join(to, f)) for f in left if os.path.exists(os.path.join(to, f))):
                break


def background():
    """This process last on the disk and the CPU (16/10: the copies took the hard disk from the app's sync: its last
    step waited minutes)."""
    config.low_priority()
    try:
        import psutil
        psutil.Process().ionice(psutil.IOPRIO_VERYLOW if os.name == "nt" else psutil.IOPRIO_CLASS_IDLE)
    except Exception:
        pass


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    background()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=["plan", "copy", "free", "cycle", "lan"])
    ap.add_argument("--to")
    ap.add_argument("--gb", type=float, default=50)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    EVERYTHING = a.all
    if a.what != "plan" and not a.to:
        sys.exit("--to: the archive folder")
    {"plan": lambda: plan(), "copy": lambda: copy(a.to, a.gb), "free": lambda: free(a.to), "cycle": lambda: cycle(a.to, a.gb),
     "lan": lambda: lan(a.to, a.gb)}[a.what]()
