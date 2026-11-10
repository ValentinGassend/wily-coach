"""The base grows by itself (04/10, the user: "fait le en boucle pour avoir 5000 matches analysés"): crawl.py's
rebound, but as a loop that never stops on its own. The players of the matches already here, their recent
matchmaking games (Leetify's public API gives their share codes, for the players who use Leetify; all of their
last month, as far as Valve keeps the demos: the user's choice on 04/10, "tous leurs matchs du mois"), each one fetched from Valve through this PC's Steam session like a pasted code, its
demo downloaded and extracted with the per-player numbers of the base; then the players of that match in turn.
- one request to Valve every 30 s at most, slower when it refuses (Steam closed, too many requests);
- paused while you play or the app works: CS2 open (a match, the training server), an analysis of the app, a
  recording or a transcription; the lowest priority otherwise;
- the demos stay (the practice part uses them, and the base only counts matches with their demo): it stops at the
  target, or when the disk has 50 GB left (out/grow_ctl.json "min_free_gb" changes it);
- its state in out/grow.json (codes waiting, players looked up, counts): started again, it goes on where it was.
The app starts and stops it (Settings, out/grow_ctl.json); python -m wily.base.grow --once does a single match."""
import datetime as dt
import json
import os
import shutil
import sys
import time
import urllib.request

from wily.core import config
from wily.app import pipeline
from wily.matches import matchlist
from wily.matches.coach import DemoGone

STATE = os.path.join(config.OUT, "grow.json")
CTL = os.path.join(config.OUT, "grow_ctl.json")
LOG_F = os.path.join(config.OUT, "grow.log")
PER_PLAYER = 0            # matches taken per player, 0: every matchmaking game of the last DAYS days (5 until 04/10)
GAP, MAX_GAP = 30, 600    # s between two requests to Valve's game coordinator, and the most it backs off to
MIN_FREE_GB = 50          # the loop stops when the disk has that much left (150 until 10/10: the user wants the 5,000)
DAYS = 27                 # the last month, as far as Valve keeps a demo (about 28 days)
RELOOK_DAYS = 7           # a player looked up again a week later (their new matches)
PORT = int(os.environ.get("COACH_PORT", 8765))
ID0 = 76561197960265728   # SteamID64 of account id 0


def log(msg):
    line = f"{dt.datetime.now():%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_F, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(st):
    st["updated"] = int(time.time())
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    for _ in range(50):
        try:
            os.replace(tmp, STATE)
            return
        except PermissionError:   # the app is reading it this very moment
            time.sleep(0.1)


def refresh_everything(mine=False):
    """The app updated with the base as it is now (Settings' "Update the app with the base": refresh_all.py; mine: the
    base's references, your profile and your team's only, else every profile): through the app, whose page follows it;
    started here when the app doesn't answer."""
    import subprocess
    what = "the base, your profile and your team's" if mine else "every profile"
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/refresh/start", data=json.dumps({"mine": bool(mine)}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=30).read()
        log(f"target reached: the app's update with the base started ({what})")
        return
    except Exception as e:
        log(f"target reached, the app doesn't answer ({type(e).__name__}): its update started from here ({what})")
    config.write_json(os.path.join(config.OUT, "refresh_ctl.json"), {"stop": False})
    subprocess.Popen([sys.executable, "-m", "wily.base.refresh_all"] + (["--mine"] if mine else []), cwd=config.HERE,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))


def status(st, text):
    if st.get("status") != text:
        log(text)
    st["status"] = text
    save(st)


def analyzed():
    return sum(1 for d in os.listdir(config.DEEP) if os.path.exists(os.path.join(config.DEEP, d, "meta.json")))


def free_gb():
    return shutil.disk_usage(config.CACHE).free / 2 ** 30


def _api(path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _match():
    """A match going on: the game detection's flag (out/playing.json, fresh while a map is loaded: bots and the training
    server included), this app's or the installed app's (the one CS2 sends its game state to). Not the menu: the base
    used to wait whenever CS2 was open (09/10: a whole night with the game left open)."""
    paths = [config.PLAYING, os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Wily", "out", "playing.json")]
    for f in paths:
        d = config.read_json(f, {}) or {}
        if d.get("until", 0) > time.time():
            return True
    return False


def busy():
    """Why the loop waits now (None: it can go)."""
    if _match():   # 09/10, the user: "go" to working while CS2 sits in the menu or on the training server
        return "a match is going on"
    j = _api("/api/job")
    if j and j.get("running"):
        return "the app is analyzing"
    v = _api("/api/voice/status")
    if v and (v.get("recording") or v.get("transcribing")):
        return "a recording or a transcription"
    # the app's update with the base (Settings) computing its references: the base stays as it is meanwhile (it then
    # goes on with the profiles while the base grows again)
    r = config.read_json(os.path.join(config.OUT, "refresh.json"), {}) or {}
    if r.get("running") and r.get("phase") == "base" and time.time() - (r.get("updated") or 0) < 3600:
        return "the app is updating its references"
    return None


def players_of(m):
    return [str(ID0 + int(a)) for a in (m.get("accounts") or []) if a]


def seed(st, reg):
    """The players to look up: everyone of the matches here (yours first, the newest first), but you and the
    ones looked up this week."""
    s = config.settings()
    own = str(s.get("own_steamid") or "")
    seen, q = st.setdefault("looked", {}), st.setdefault("players", [])
    if not st.get("seeded"):   # the players crawl.py visited already count as looked up (this week)
        for p in s.get("crawl_visited", []):
            seen.setdefault(str(p), int(time.time()))
        st["seeded"] = True
    fresh = time.time() - RELOOK_DAYS * 86400
    inq = set(q)
    ms = sorted(reg.values(), key=lambda m: str(m.get("time") or ""), reverse=True)
    ms.sort(key=lambda m: 0 if m.get("me") else 1)
    for m in ms:
        for s in players_of(m):
            if s != own and s not in inq and seen.get(s, 0) < fresh:
                q.append(s)
                inq.add(s)


def refill(st, reg):
    """More codes: the recent matchmaking games of the next players (Leetify), the newest first. False: nothing."""
    from wily.matches import leetify
    seen, q = st.setdefault("looked", {}), st.setdefault("players", [])
    codes = st.setdefault("codes", [])
    if not q:
        seed(st, reg)
    known = {c[1] for c in codes}
    since = dt.datetime.utcnow() - dt.timedelta(days=DAYS)
    looked = 0
    while len(codes) < 40 and q and looked < 30:
        sid = q.pop(0)
        if seen.get(sid, 0) > time.time() - RELOOK_DAYS * 86400:
            continue
        seen[sid] = int(time.time())
        looked += 1
        try:
            ms = leetify.matches(int(sid)) or []
        except Exception:
            ms = []
        try:   # their Leetify stats join the reference of the Leetify-only diagnosis (leetify.reference)
            lf = os.path.join(leetify.LDIR, f"{sid}.json")
            if ms and not os.path.exists(lf):
                pr = leetify.profile(int(sid))
                if pr and pr.get("stats"):
                    config.write_json(lf, {"stats": pr["stats"], "ranks": pr.get("ranks"), "total_matches": pr.get("total_matches"),
                                           "t": int(time.time())})
        except Exception:
            pass
        n = 0
        for m in sorted(ms, key=lambda m: str(m.get("finished_at") or ""), reverse=True):
            if PER_PLAYER and n >= PER_PLAYER:
                break
            code = str(m.get("data_source_match_id") or "")
            if not code.startswith("CSGO-") or "wingman" in str(m.get("data_source") or ""):
                continue
            try:
                t = dt.datetime.fromisoformat(str(m.get("finished_at"))[:19])
                mid = str(matchlist.decode_sharecode(code)[0])
            except (ValueError, OverflowError):
                continue
            if t < since or code in known or mid in reg:
                continue
            codes.append([str(m.get("finished_at"))[:19], code, m.get("map_name") or ""])
            known.add(code)
            n += 1
        if n:
            log(f"player {sid}: {n} new match(es) on Leetify")
        save(st)
    codes.sort(reverse=True)   # the newest first: Valve keeps them the longest
    return bool(codes)


def step(st, reg):
    """One match: its demo's address from Valve, the demo, its extraction; its players join the queue."""
    t, code, mp = st["codes"].pop(0)
    try:
        if dt.datetime.utcnow() - dt.datetime.fromisoformat(t) > dt.timedelta(days=27):
            return "old"   # gone from Valve by now
        mid, oc, tok = matchlist.decode_sharecode(code)
    except (ValueError, OverflowError):
        return "bad"
    mid = str(mid)
    m = reg.get(mid)
    if not (m and m.get("url")):
        wait = st.get("gap", GAP) - (time.time() - st.get("gc_at", 0))
        if wait > 0:
            time.sleep(wait)
        st["gc_at"] = time.time()
        err = ""
        try:
            got = [x for x in matchlist.fetch_one(int(mid), oc, tok) if x.get("url")]
        except Exception as e:
            got, err = [], f" ({str(e)[:120]})"
        if not got:
            st["gap"] = min(MAX_GAP, st.get("gap", GAP) * 2)
            fails = st.setdefault("fails", {})
            fails[code] = fails.get(code, 0) + 1
            if fails[code] < 3:
                st["codes"].append([t, code, mp])   # once more later
            log(f"{code}: no answer from Valve{err}; next request in {st['gap']} s")
            return "valve"
        st["gap"] = GAP
        for x in got:
            x.update(sharecode=code, crawled=True)
        pipeline.save_registry({x["match_id"]: {**reg.get(x["match_id"], {}), **x} for x in got})
        m = pipeline.registry().get(mid)
        if not m:
            return "valve"
    dem = config.demo(mid)
    if not os.path.exists(dem):
        try:
            pipeline._fetch_demo(mid, m["url"], gone_tries=2)
        except DemoGone:
            pipeline.save_registry({mid: {**m, "expired": True}})
            return "gone"
        except Exception as e:
            log(f"{mid}: download failed ({str(e)[:120]})")
            return "download"
    out = os.path.join(config.DEEP, mid)
    if not os.path.exists(os.path.join(out, "meta.json")):
        from wily.demos import deep
        try:
            deep.extract(dem, out)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:   # the demo parser's panics are no Exception
            log(f"{mid}: extraction failed ({type(e).__name__}: {str(e)[:120]})")
            return "extract"
    seen, q = st.setdefault("looked", {}), st.setdefault("players", [])
    inq = set(q)
    own = str(config.settings().get("own_steamid") or "")
    q.extend(s for s in players_of(m) if s != own and s not in inq and s not in seen)
    log(f"{mid} {mp or ''} ✔ ({code})")
    return "ok"


def follow_ups():
    """What the app does after an extraction (the rounds, the buys…) and the base's per-player numbers: each one
    skips what is done already."""
    from wily.insights import buys
    from wily.insights import midround
    from wily.insights import nades_catalog
    from wily.demos import population
    from wily.demos import rounds
    from wily.demos import style
    from wily.insights import tside
    rounds.run_all(config.CACHE, config.DEEP, workers=1, log=log)
    midround.run_all(workers=1, log=log)
    buys.run_all(log=log)
    tside.run_all(log=log)
    population.run_all()
    style.run_all(workers=1)
    nades_catalog.run_all(log=log)   # the pro catalog's lineups again once the base grew by a quarter
    from wily.insights import tdirs
    tdirs.run(log=log)   # the T ways in (Live's directions) again once the base grew by 15 %


def _alive(pid):
    try:
        import psutil
        return config.runs(psutil.Process(pid).cmdline(), "wily.base.grow")
    except Exception:
        return False


def main():
    once = "--once" in sys.argv
    config.low_priority()
    st = _read(STATE)
    if st.get("pid") and st["pid"] != os.getpid() and _alive(st["pid"]):
        print("already running", flush=True)
        return
    st["pid"] = os.getpid()
    st.pop("step", None)
    if st.get("per_player", 5) != PER_PLAYER:   # the players looked up for 5 matches: again, for the rest of their month
        st["looked"], st["players"], st["per_player"] = {}, [], PER_PLAYER
    save(st)
    log("loop started" + (" (one match)" if once else ""))
    try:
        while True:
            c = _read(CTL)
            if not c.get("on") and not once:
                status(st, "stopped")
                break
            target = int(c.get("target") or 5000)
            st["n"] = n = analyzed()
            if n >= target:
                status(st, f"done: {n} matches")
                # 07/10, the user: "stop à 3000 matchs et fais la mise à jour complète de l'app à cette étape", then "met à
                # jour Patro et Catharsis, ça suffit": refresh_mine = the base's references, his profile and his team's
                if c.get("then") in ("refresh", "refresh_mine"):
                    config.write_json(CTL, {k: v for k, v in c.items() if k != "then"})   # once
                    refresh_everything(mine=c["then"] == "refresh_mine")
                break
            floor = float(c.get("min_free_gb") or MIN_FREE_GB)   # 10/10, the user: "va jusqu'à 5000 matchs même sous 150 Go"
            if free_gb() < floor:
                status(st, f"stopped: {floor:.0f} GB left on the disk")
                break
            why = busy()
            if why:
                status(st, f"paused: {why}")
                time.sleep(30)
                continue
            if time.time() - st.get("contrib_at", 0) > 3600 and config.settings().get("contrib_token"):
                st["contrib_at"] = time.time()   # the matches players shared (05/10), every hour
                save(st)
                try:
                    from wily.sharing import contributions
                    contributions.pull()
                    contributions.pull_reports()   # the players' bug reports (05/10, the alpha)
                    contributions.pull_usage()   # and their anonymous usage statistics
                    if contributions.ingest(follow=False):
                        st["step"] = int(time.time())
                        save(st)
                        try:
                            follow_ups()
                        finally:
                            st.pop("step", None)
                            save(st)
                except Exception as e:
                    log(f"shared matches: {type(e).__name__}: {str(e)[:160]}")
            reg = pipeline.registry()
            if not st.get("codes") and not refill(st, reg):
                status(st, "waiting: no new match of the players yet (looked up again in 1 h)")
                time.sleep(3600)
                continue
            status(st, f"working: {len(st['codes'])} match(es) waiting, {len(st.get('players') or [])} player(s) to look up")
            st["step"] = int(time.time())   # the app's analyses wait for the end of this match (same files)
            save(st)
            try:
                r = step(st, reg)
            finally:
                st.pop("step", None)
                save(st)
            counts = st.setdefault("counts", {})
            counts[r] = counts.get(r, 0) + 1
            if r == "ok":
                st["step"] = int(time.time())
                save(st)
                try:
                    follow_ups()
                finally:
                    st.pop("step", None)
                    save(st)
                if once:
                    break
    except BaseException as e:   # an interruption too (SystemExit, KeyboardInterrupt): 05/10 02:17 the loop ended mid-step without a word
        import traceback
        log(f"loop error: {type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")
        raise
    finally:
        st["pid"] = None
        save(st)


if __name__ == "__main__":
    if config.role() == "client":   # the base grows on the coach's server only (05/10, the beta)
        sys.exit("a player's copy of the app: the base grows on the coach's server")
    main()
