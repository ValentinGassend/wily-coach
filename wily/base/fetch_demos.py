"""Pro demos for the pro base: the latest top-tier matches on HLTV (its results, 2 stars and more by default) that the
base does not have yet, downloaded and analyzed by pro.py like your matches, kept apart from the pub base (out/deep_pro;
their match, teams and event in out/pro/matches.json), each archive deleted once analyzed. Politely: pauses between
HLTV pages, two downloads at a time. It waits while CS2 is open or the app analyzes, records or transcribes, and stops
when the disk has 150 GB left (the base's own rules, grow.py); then the pro references are computed again (the
mid-round numbers of the pros, the lineups found in their throws).

Usage: python -m wily.base.fetch_demos [matches=20] [--stars 2]     the latest top-tier matches
       python -m wily.base.fetch_demos --teams [--per-team 4]        the latest matches of the current top teams
       python -m wily.base.fetch_demos --import [folder or file]     demos you downloaded yourself from HLTV (default: Downloads)
       python -m wily.base.fetch_demos --import <folder> --remove    the same, each file deleted once in (Settings' inbox)
       python -m wily.base.fetch_demos --matchlist                    the demos of your cached match list (its first job)

04/10: Antigravity's version tried HLTV demo numbers one by one down from 88000, up to 5,000 demos (about 2 TB from
HLTV), and put them in the pub base (out/deep) among the players of your rank; its 36 folders (matches of February
2025) are kept apart in out/deep_hltv_antigravity."""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from wily.core import config

WAIT = 60   # seconds between two checks while CS2 is open or the app is busy


def _go(on_wait=None):
    """Before each download: wait while CS2 is open or the app is busy; False when the disk is too full to go on.
    on_wait(why): told each time it waits."""
    from wily.base import grow
    while True:
        if grow.free_gb() < grow.MIN_FREE_GB:
            print(f"stopped: {grow.free_gb():.0f} GB left on the disk (the base keeps {grow.MIN_FREE_GB} GB)", flush=True)
            return False
        why = grow.busy()
        if not why:
            return True
        print(f"waiting: {why}", flush=True)
        if on_wait:
            on_wait(why)
        time.sleep(WAIT)


def _pro():
    """The pro demos' downloader: a local module of this PC, not in the repository (10/10)."""
    try:
        from wily.base import pro
        return pro
    except ImportError:
        raise SystemExit("the pro demo tools (pro.py) are a local module, absent from this copy")


def pro_demos(n=20, stars=2, teams=False, per_team=4):
    pro = _pro()
    if not _go():
        return
    before = sum(len(v.get("demos") or []) for v in _registry().values())
    if teams:
        from wily.base import pro_directory
        pro.main(teams=list(pro_directory.CURRENT), per_team=per_team, workers=2, wait=_go)
    else:
        pro.main(n, stars, workers=2, wait=_go)
    added = sum(len(v.get("demos") or []) for v in _registry().values()) - before
    print(f"{added} pro map(s) added", flush=True)
    if added:
        _refresh()


def _refresh():
    """The pros' references again: their mid-round numbers, the catalog's lineups found in their throws."""
    from wily.insights import midround
    from wily.insights import nades_catalog
    midround.run_all(workers=1, log=print)
    nades_catalog.run_all(log=print)


STATUS = os.path.join(config.OUT, "pro", "import_status.json")   # an import's progress, followed by Settings' page


def _fingerprint(folder):
    """A map's first duels (their tick, killer, victim) as one string: the same demo analyzed twice gives the same one."""
    import pandas as pd
    try:
        D = pd.read_parquet(os.path.join(folder, "duels.parquet"), columns=["tick", "killer", "victim"]).head(12)
    except Exception:
        return None
    return "|".join(f"{int(t)}:{int(k)}:{int(v)}" for t, k, v in zip(D.tick, D.killer, D.victim)) or None


def _fingerprints(deep_pro):
    """{map folder: fingerprint} of the pro base, each read again only when its folder changes (out/ledgers)."""
    from wily.core import ledger
    return ledger.per_match("pro_fingerprints", ledger.folders(deep_pro), lambda mid: _fingerprint(os.path.join(deep_pro, mid)))


def import_demos(path, remove=False):
    """Pro demos you downloaded yourself (the GOTV demo button of a match page on HLTV): every .rar, .zip, .7z or .dem
    of that folder (or that file) goes to the pro base like a fetched one. Your files stay where they are; their teams
    are read from the demos, the date is the file's. remove (22/10, Settings' "Add demos": the copies the app received
    in its inbox): each file deleted once its maps are in the pro base; one that could not be read stays, with why.
    Its progress in out/pro/import_status.json (the file, the step: waiting and why, extracting, its map i of n)."""
    import re
    import shutil
    import subprocess
    from wily.demos import deep
    from wily.demos import style
    pro = _pro()
    files = [path] if os.path.isfile(path) else sorted(os.path.join(path, f) for f in os.listdir(path)
                                                       if f.lower().endswith((".rar", ".zip", ".7z", ".dem")))
    if not files:   # nothing there (a run started for a file another run took): the last run's result stays shown
        print("no demo to import", flush=True)
        return 0
    st = {"pid": os.getpid(), "started": time.time(), "files": [os.path.basename(f) for f in files], "done": [], "failed": []}

    def say(**kw):
        st.update(kw, t=time.time())
        config.write_json(STATUS, st)

    def gone(f):
        if remove:
            try:
                os.remove(f)
            except OSError:
                pass
    say(file=None, step=None)
    reg = _registry()
    added = 0
    for f in files:
        name = os.path.basename(f)
        stem = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(name)[0].lower()).strip("-")[:60]
        key = f"dl:{stem}"
        if key in reg and reg[key].get("demos"):
            print(f"{name}: already in the pro base", flush=True)
            st["done"].append({"file": name, "teams": reg[key].get("teams") or [], "maps": reg[key].get("maps") or [], "already": True})
            gone(f)
            say(file=None, step=None)
            continue
        if not _go(lambda why: say(file=name, step="wait", why=why)):
            say(file=None, step="disk")
            break
        say(file=name, step="extract")
        tmp = os.path.join(pro.RAW, f"import_{stem}")
        if f.lower().endswith(".dem"):
            dems = [f]
        else:
            r = subprocess.run([pro.SEVENZIP, "e", "-y", f"-o{tmp}", f, "*.dem", "-r"], capture_output=True, timeout=1800,
                               creationflags=config.NO_WINDOW)
            dems = sorted(os.path.join(tmp, x) for x in os.listdir(tmp) if x.endswith(".dem")) if r.returncode == 0 and os.path.exists(tmp) else []
            if not dems:
                print(f"{os.path.basename(f)}: no demo inside (or 7-Zip could not open it)", flush=True)
        done, errs, twice = [], [], []
        for i, dem in enumerate(dems):
            pid = f"pro_dl_{stem}_{i}"
            say(file=name, step="map", i=i + 1, n=len(dems))
            try:
                if not os.path.exists(os.path.join(pro.DEEP_PRO, pid, "meta.json")):
                    deep.extract(dem, os.path.join(pro.DEEP_PRO, pid))
                # a map the pro base has already (22/10: the same match under another file name, a LAN's demo already
                # fetched): its throws would count twice in the stuffs, its new folder dropped
                fp = _fingerprint(os.path.join(pro.DEEP_PRO, pid))
                same = next((m for m, x in _fingerprints(pro.DEEP_PRO).items() if fp and x == fp and m != pid), None)
                if same:
                    shutil.rmtree(os.path.join(pro.DEEP_PRO, pid), ignore_errors=True)
                    twice.append(same)
                    print(f"  {os.path.basename(dem)}: already in the pro base ({same})", flush=True)
                    continue
                style.extract(pid, deep_dir=pro.DEEP_PRO, out_dir=pro.STYLE_PRO)
                done.append({"id": pid, "file": os.path.basename(dem), "teams": pro.clan_names(dem)})
            except Exception as e:
                print(f"  {os.path.basename(dem)}: {e}", flush=True)
                errs.append(f"{type(e).__name__}: {e}"[:160])
        shutil.rmtree(tmp, ignore_errors=True)
        if not done and twice and not errs:   # every map of it there already
            st["done"].append({"file": name, "teams": [], "maps": [], "already": True})
            gone(f)
            say(file=None, step=None)
        elif not done:
            st["failed"].append({"file": name, "why": "; ".join(errs[:2]) if errs else "no demo"})
            say(file=None, step=None)
        if done:
            names = [t for d in done for t in d["teams"].values()]
            maps = []
            for d in done:
                try:
                    with open(os.path.join(pro.DEEP_PRO, d["id"], "meta.json"), encoding="utf-8") as fh:
                        maps.append(json.load(fh)["map"])
                except (OSError, ValueError, KeyError):
                    pass
            reg[key] = {"match_id": key, "slug": stem, "demo_id": None, "teams": sorted(set(names), key=names.count, reverse=True)[:2],
                        "event": None, "date": time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(f))), "maps": maps,
                        "demos": done, "source": "downloaded"}
            with open(os.path.join(pro.PRO, "matches.json"), "w", encoding="utf-8") as fh:
                json.dump(reg, fh, ensure_ascii=False, indent=1)
            added += len(done)
            print(f"{os.path.basename(f)}: {' vs '.join(reg[key]['teams']) or 'teams not in the demo'}, {len(done)} map(s)", flush=True)
            st["done"].append({"file": name, "teams": reg[key]["teams"], "maps": maps})
            gone(f)
            say(file=None, step=None)
    print(f"{added} pro map(s) added", flush=True)
    if added:
        say(file=None, step="refresh")
        _refresh()
    say(file=None, step=None, ended=time.time(), added=added)
    return added


def _registry():
    try:
        with open(os.path.join(config.OUT, "pro", "matches.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def matchlist():
    """The demos of the cached match list (coach.py), 3 at a time, kept."""
    from wily.matches.coach import CACHE, decompress, download

    def get(m):
        dem = os.path.join(CACHE, f"{m['match_id']}.dem")
        if config.has_demo(m["match_id"]):   # in the cache or archived
            return f"{m['match_id']} already there"
        bz = dem + ".bz2"
        download(m["url"], bz)
        decompress(bz, dem)
        os.remove(bz)
        return f"{m['match_id']} OK"

    ms = [m for m in json.load(open(os.path.join(CACHE, "matchlist.json"))) if m.get("url")]
    with ThreadPoolExecutor(3) as ex:
        for f in [ex.submit(get, m) for m in ms]:
            try:
                print(f.result(), flush=True)
            except Exception as e:
                print("ERROR", e, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    opt = lambda k, d: int(a[a.index(k) + 1]) if k in a and a.index(k) + 1 < len(a) else d
    # the number of matches: a number that is not an option's value ("--stars 1" is not 1 match)
    n = next((int(x) for i, x in enumerate(a) if x.isdigit() and (i == 0 or a[i - 1] not in ("--stars", "--per-team"))), 20)
    if "--matchlist" in a:
        matchlist()
    elif "--import" in a:
        i = a.index("--import")
        where = a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith("--") else os.path.join(os.path.expanduser("~"), "Downloads")
        import_demos(where, remove="--remove" in a)
    else:
        pro_demos(n=n, stars=opt("--stars", 2), teams="--teams" in a, per_team=opt("--per-team", 4))
    print("DONE", flush=True)
