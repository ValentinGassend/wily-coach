"""CS2 coach: fetch matches, analyze them for one or more players, build the app.

Examples
  python -m wily.app.pipeline                         # your own account (detected from Steam), last matches
  python -m wily.app.pipeline --steamid 7656119...    # any player: uses every cached demo they appear in
  python -m wily.app.pipeline --steamid 7656119... --sharecode CSGO-xxxxx-...   # add specific matches
  python -m wily.app.pipeline --steamid 7656119... --authcode XXXX-XXXXX-XXXX --knowncode CSGO-...  # full history
                                             # (needs "steam_api_key" in out/settings.json)
  python -m wily.app.pipeline --build-only            # just rebuild out/app.html
Steam must be running (and CS2 closed) to fetch match info from Valve.
"""
import argparse
import json
import os
import sys
import traceback

from wily.core import config
from wily.core import i18n
from wily.matches import matchlist
from wily.matches.coach import DemoGone, decompress, download, game_mode

REGISTRY = os.path.join(config.CACHE, "matches.json")


LOG_HOOK = None  # set by the local server to stream progress to the page
STAGE_HOOK = None   # set by the local server: the steps the page draws (16/10, the user: "beaucoup plus visuel et ux")


ANALYZING = os.path.join(config.OUT, "ledgers", "analyzing")   # its date: an analysis's last step (tools/archive_demos.py waits)


def stage(key, i=None, n=None, note=None):
    """The analysis enters a step (history, lookup, download, extract, matches, profile, plan, page) or moves on in
    it (i of n; note: a few numbers for the page, {"new": 5}): the page's progress, not words."""
    try:
        with open(ANALYZING, "a"):
            pass
        os.utime(ANALYZING, None)
    except OSError:
        pass
    if STAGE_HOOK:
        try:
            STAGE_HOOK(key, i, n, note)
        except Exception:
            pass


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    if LOG_HOOK:
        LOG_HOOK(msg)


def registry():
    if not os.path.exists(REGISTRY):
        return {}
    with open(REGISTRY) as f:
        return json.load(f)


_REG = {"stamp": None, "reg": {}}


def registry_view():
    """registry() for a reader that changes nothing: kept while the file stays the same (16/10: read 8 times a plan)."""
    try:
        st = os.stat(REGISTRY)
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _REG["stamp"] != stamp:
        _REG.update(stamp=stamp, reg=registry())
    return _REG["reg"]


def save_registry(r):
    """Merged into the file as it is now, then replaced in one go: the base-growing loop (grow.py, its own process)
    writes it too, and a reader never gets half a file."""
    import time
    cur = registry()
    cur.update(r)
    tmp = f"{REGISTRY}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(cur, f, indent=1)
    for _ in range(50):
        try:
            os.replace(tmp, REGISTRY)
            return
        except PermissionError:   # the other process is reading it this very moment
            time.sleep(0.1)
    os.replace(tmp, REGISTRY)


def collect(args, own_id):
    reg = registry()
    new = []
    if not args.no_fetch and (args.steamid in (None, own_id) or args.own):
        try:
            for m in matchlist.fetch():
                new.append(m)
        except Exception as e:
            log("Valve match list unavailable (Steam closed or CS2 open?):", e)
    codes = list(args.sharecode or [])
    if args.steamid and args.steamid != own_id and not args.no_fetch:
        codes += leetify_codes(args.steamid)
    s = config.settings()
    if args.authcode and args.knowncode:
        key = s.get("steam_api_key")
        if not key:
            log("steam_api_key is missing from out/settings.json to browse the history from the command line.")
        else:
            codes += [args.knowncode] + matchlist.history_codes(key, args.steamid, args.authcode, args.knowncode)
            s.setdefault("players", {}).setdefault(str(args.steamid), {}).update(
                {"authcode": args.authcode, "last_code": codes[-1]})
            config.save_settings(s)
    for c in codes:
        try:
            mid, oc, tok = matchlist.decode_sharecode(c)
            if str(mid) in reg and reg[str(mid)].get("url"):
                continue
            new += matchlist.fetch_one(mid, oc, tok)
        except Exception as e:
            log(f"Code {c}: failed ({e})")
    by_url = {r["url"]: k for k, r in reg.items() if r.get("url")}
    for m in new:
        if m.get("url"):
            # a match read from Steam's history page (steamhist.py) is kept under its demo's number: the same match
            # given here by its match id joins that entry (its demo is already under that name)
            k = by_url.get(m["url"], m["match_id"])
            reg.setdefault(k, {}).update({**m, "match_id": k})
    save_registry(reg)
    return reg


def leetify_codes(steamid, days=35, limit=15):
    """Share codes of the player's recent matchmaking games, from Leetify (demos older than ~1 month are gone)."""
    import datetime as dt
    from wily.matches import leetify
    ms = leetify.matches(steamid)
    json.dump(ms, open(os.path.join(config.CACHE, f"leetify_{steamid}.json"), "w", encoding="utf-8"))
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    recent = sorted((m for m in ms if str(m.get("data_source_match_id", "")).startswith("CSGO-")
                     and dt.datetime.fromisoformat(m["finished_at"][:19]) >= since), key=lambda m: m["finished_at"], reverse=True)
    codes = [m["data_source_match_id"] for m in recent[:limit]]
    fc = sum(1 for m in ms if m.get("data_source") == "faceit")
    log(f"Leetify: {len(ms)} recent matches, {len(codes)} matchmaking ones from the last {days} days, {fc} FACEIT")
    return codes


def _fetch_demo(mid, url, gone_tries=None):
    dem = os.path.join(config.CACHE, f"{mid}.dem")
    arc = dem + ".bz2"
    if os.path.exists(arc) and not os.path.exists(arc + ".part"):  # left by an earlier, cut download: resume it
        os.replace(arc, arc + ".part")
    if not download(url, arc, gone_tries=gone_tries, unpack=dem):   # unpacked as it came (16/10), else now
        try:
            decompress(arc, dem)
        except Exception:
            os.remove(arc)  # complete but damaged: download it again next time
            raise
    os.remove(arc)


DEMO_DAYS = 28  # Valve keeps matchmaking demos about a month


def _recent(m, days=DEMO_DAYS):
    import datetime as dt
    try:
        return dt.datetime.now() - dt.datetime.fromisoformat(str(m.get("time"))[:16]) < dt.timedelta(days=days)
    except ValueError:
        return False


def out_of_reach(mid):
    """Its demo is surely in an archive this PC cannot reach now (Drive closed): it was read here once (its extraction
    is here). Not fetched again from Valve meanwhile (29/10, the user: "j'aimerais bien que ça ne télécharge pas pour
    rien": Drive closed, 128 of his demos were being downloaded again)."""
    return bool(config.archives_missing()) and os.path.isdir(os.path.join(config.DEEP, str(mid)))


def pending_demos(reg):
    """Your own matches known to Valve whose demo is not here yet: it goes online a few minutes after the match,
    so a download tried too early is tried again at the next analysis."""
    return {mid for mid, m in reg.items() if m.get("url") and m.get("me") and (not m.get("expired") or _recent(m))
            and not config.has_demo(mid) and not out_of_reach(mid)}


def ensure_demos(reg, workers=2, only=None):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    os.makedirs(config.CACHE, exist_ok=True)
    todo = {mid: m["url"] for mid, m in reg.items()
            if (only is None or mid in only) and m.get("url") and (not m.get("expired") or _recent(m))
            and not config.has_demo(mid)}
    away = {mid for mid in todo if out_of_reach(mid)}
    if away:
        log(f"{len(away)} demo(s) not downloaded again: they are in {', '.join(config.archives_missing())}, out of reach now (Google Drive closed?)")
        todo = {mid: u for mid, u in todo.items() if mid not in away}
    if todo:
        config.wait_for_match_end(log, "demo downloads")
        log(f"Downloading {len(todo)} demo(s) from Valve…")
        stage("download", 0, len(todo))
    with ThreadPoolExecutor(workers) as ex:
        # an old match (past Valve's month): 2 tries before calling it gone; a recent one: patience (network hiccups)
        futs = {ex.submit(lambda a, b, g: (config.wait_for_match_end(), _fetch_demo(a, b, g))[1], mid, url,
                          None if _recent(reg[mid]) else 2): mid for mid, url in todo.items()}
        for i, f in enumerate(as_completed(futs), 1):
            mid = futs[f]
            try:
                f.result()
                reg[mid].pop("expired", None)
                log(f"  demo {i}/{len(todo)} ready")
                stage("download", i, len(todo))
            except Exception as e:
                if _recent(reg[mid]):  # not online yet (a few minutes after the match), or a network hiccup
                    reg[mid].pop("expired", None)
                    log(f"  [{mid}] demo not available from Valve yet ({e}): it arrives a few minutes after the match ends. Trying again at the next analysis.")
                elif isinstance(e, DemoGone):
                    reg[mid]["expired"] = True
                    log(f"  [{mid}] demo unavailable ({e}): Valve only keeps it for about a month")
                else:   # cut in the middle: not gone, tried again at the next analysis
                    log(f"  [{mid}] download failed ({e}): tried again at the next analysis")
    save_registry(reg)


def ensure_deep():
    from wily.demos import deep
    from wily.demos import rounds
    from wily.insights import midround
    stage("extract")
    _ensure_deep(deep)
    rounds.run_all(config.CACHE, config.DEEP, log=log)
    midround.run_all(log=log)
    from wily.insights import buys
    buys.run_all(log=log)
    from wily.insights import tside
    tside.run_all(log=log)


def _extract(src, out):
    """deep.extract in a worker: the demo parser's panics (not an Exception) come back as a plain error."""
    from wily.demos import deep
    try:
        deep.extract(src, out)
    except BaseException as e:   # pyo3 PanicException derives from BaseException
        raise RuntimeError(f"{type(e).__name__}: {str(e)[:200]}") from None


def _deep_job(kind, src, out):
    """A demo's detailed extraction, or its round context: it reads the demo only, so it runs beside the extraction
    (16/10: after it, 2 s more per match). rounds.run_all() then finds it done."""
    if kind == "deep":
        return _extract(src, out)
    from wily.demos import rounds
    os.makedirs(out, exist_ok=True)
    try:
        return rounds.extract(src, out)
    except BaseException as e:   # the parser's panics, as _extract: rounds.run_all() tries it again on its own
        raise RuntimeError(f"round context: {type(e).__name__}: {str(e)[:200]}") from None


def _in_workers(fn, jobs, workers, done, batch=0, wait=None):
    """fn(*args) for each (key, args) of jobs, in `workers` processes at the lowest priority: done(key, result, error)
    as each one ends; with batch, `batch` jobs at a time and wait() before each batch. A worker that dies (memory
    exhausted, a crash inside the demo parser) breaks the whole pool and every job still in it fails with it: those
    run again one at a time in their own process, then the rest goes on in a new pool. A job that stops its process
    even alone fails; the others go on."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from concurrent.futures.process import BrokenProcessPool
    jobs = list(jobs)
    while jobs:
        lost = []
        with ProcessPoolExecutor(workers, initializer=config.low_priority) as ex:
            while jobs and not lost:
                if wait:
                    wait()
                n = batch or len(jobs)
                part, jobs = jobs[:n], jobs[n:]
                futs = {}
                for key, args in part:
                    try:
                        futs[ex.submit(fn, *args)] = (key, args)
                    except BrokenProcessPool:
                        lost.append((key, args))
                for fu in as_completed(futs):
                    try:
                        done(futs[fu][0], fu.result(), None)
                    except BrokenProcessPool:
                        lost.append(futs[fu])
                    except Exception as e:
                        done(futs[fu][0], None, e)
        for key, args in lost:
            log(f"[{key}] its process stopped abruptly (out of memory?): again, alone")
            if wait:
                wait()
            with ProcessPoolExecutor(1, initializer=config.low_priority) as ex:
                try:
                    done(key, ex.submit(fn, *args).result(), None)
                except BrokenProcessPool:
                    done(key, None, RuntimeError("its process stops abruptly even alone (memory, or a demo the parser "
                                                 "cannot read): skipped"))
                except Exception as e:
                    done(key, None, e)


def _deep_todo():
    """The cache's demos not extracted yet (the ones done before not checked again: ledger.py)."""
    from wily.core import ledger
    led = ledger.Ledger("deep")   # 15/10: the matches extracted before are not checked again (ledger.py)
    dirs = ledger.folders(config.DEEP)
    todo = []
    for f in sorted(os.listdir(config.CACHE)):
        if not f.endswith(".dem"):
            continue
        mid = f[:-4]
        if mid in dirs and led.settled(mid, dirs[mid]):
            continue
        if mid in dirs and os.path.exists(os.path.join(config.DEEP, mid, "meta.json")):
            led.mark(mid, dirs[mid])
        else:
            todo.append(mid)
    led.save()
    return todo


def _ensure_deep(deep):
    """Detailed extraction of the new demos: in separate processes at the lowest priority (the game and the
    app's page keep the CPU), two at a time, waiting for the end of a match between demos."""
    import multiprocessing
    todo = _deep_todo()
    if not todo:
        return
    stage("extract", 0, len(todo))
    got = [0]

    def one_done(key, _, err):
        mid, kind = key
        if kind != "deep":   # the round context beside it: only its failure said (rounds.run_all() does it again)
            if err:
                log(f"[{mid}] round context beside the extraction: {err}")
            return
        got[0] += 1
        stage("extract", got[0], len(todo))
        log(f"[{mid}] extraction ERROR: {err}" if err else f"[{mid}] detailed extraction")

    if multiprocessing.current_process().name != "MainProcess":   # already a worker: stay in it
        for mid in todo:
            config.wait_for_match_end(log, "demo extraction")
            log(f"[{mid}] detailed extraction")
            try:
                _extract(config.demo(mid), os.path.join(config.DEEP, mid))
            except Exception as e:
                log(f"[{mid}] extraction ERROR: {e}")
        return
    from wily.demos import rounds
    jobs = []
    for mid in todo:   # each demo's extraction, and its round context when it has none yet, side by side
        out = os.path.join(config.DEEP, mid)
        jobs.append(((mid, "deep"), ("deep", config.demo(mid), out)))
        if not rounds.done(out):
            jobs.append(((mid, "rounds"), ("rounds", config.demo(mid), out)))
    _in_workers(_deep_job, jobs, 2, one_done, batch=2, wait=lambda: config.wait_for_match_end(log, "demo extraction"))


_PM = {"key": None, "index": {}}
PLAYERS_IN = os.path.join(config.OUT, "ledgers", "players_in.json")


def _match_index():
    """steamid -> match ids of the cached demos, read once per process while the demo folder keeps its matches
    (05/10: each profile read the positions file of every match, 2,000 files per profile). 15/10: the players of
    each match kept on disk with its folder's date, so a new match reads its own file only (the 5,000 positions
    files of the hard disk took 2 to 4 minutes at each sync)."""
    import pandas as pd
    from wily.core import ledger
    dirs = ledger.folders(config.DEEP)
    key = (len(dirs), max(dirs.values(), default=0))
    if _PM["key"] != key:
        try:
            known = config.read_json(PLAYERS_IN, {}) or {}
        except (OSError, ValueError):
            known = {}
        per, changed = {}, False
        for mid, stamp in dirs.items():
            k = known.get(mid)
            if k and k[0] == stamp:
                per[mid] = k
                continue
            p = os.path.join(config.DEEP, mid, "samples.parquet")
            if not os.path.exists(p):
                continue
            try:
                ids = set(pd.read_parquet(p, columns=["steamid"]).steamid)
            except Exception:   # a file the base loop is writing (it failed a profile's plan, 05/10): left out this time
                continue
            ok = []
            for s in ids:
                try:
                    ok.append(int(s))
                except (TypeError, ValueError):
                    pass
            per[mid] = [stamp, ok]
            changed = True
        if changed or len(per) != len(known):
            try:
                config.write_json(PLAYERS_IN, per, separators=(",", ":"))
            except OSError:
                pass
        idx = {}
        for mid, (_, ids) in per.items():
            for s in ids:
                idx.setdefault(s, []).append(mid)
        _PM.update(key=key, index=idx)
    return _PM["index"]


def player_matches(steamid):
    """Match ids of cached demos where this player appears."""
    try:
        return list(_match_index().get(int(steamid), []))
    except (TypeError, ValueError):
        return []


def _analyze_match(steamid, mid, m, facts=False):
    """One match for one player (runs in a worker process). facts: its match facts too (blocks, flashes, the
    enemies' odd kills: matchfacts.py) when the plan will read them, here beside the rest (16/10, the user: "c'est méga
    long": the plan read them one match after the other at its very end, 30 s to a minute each, the page still)."""
    from wily.demos import analyze
    from wily.demos import map_analysis
    config.wait_for_match_end()   # a match started meanwhile: this worker waits for its end
    folder = os.path.join(config.player_dir(steamid), "matches", mid)
    dem = config.demo(mid)
    try:
        st = analyze.analyze(dem, steamid)
        if st.get("error"):
            return f"[{mid}] player not found"
        os.makedirs(folder, exist_ok=True)
        st["match"] = {"match_id": mid, "time": m.get("time"), "team_scores": m.get("team_scores"), "duration_s": m.get("duration_s")}
        st["mode"] = "FACEIT" if m.get("source") == "faceit" else game_mode(dem, m.get("players", 10))
        mp = map_analysis.analyze(dem, steamid)
        enc = lambda o: o.item() if hasattr(o, "item") else str(o)
        json.dump(mp, open(os.path.join(folder, "map.json"), "w", encoding="utf-8"), ensure_ascii=False, default=enc)
        json.dump(st, open(os.path.join(folder, "stats.json"), "w", encoding="utf-8"), ensure_ascii=False, default=enc)
        if facts:
            from wily.demos import matchfacts
            try:
                if not os.path.exists(os.path.join(matchfacts.fdir(steamid), f"{mid}.json")):
                    matchfacts.analyze(mid, steamid)
            except Exception as e:   # the plan tries again
                print(mid, "facts impossible:", e, flush=True)
        return f"[{mid}] {st['map']} {st['final_score']['me']}-{st['final_score']['them']}"
    except Exception as e:
        return f"[{mid}] ERROR: {e}"


def _prewarm():
    """The base's tables the advice and the plan read next (none depends on the player): loaded now, kept by their
    modules for the rest of this analysis."""
    try:
        from wily.insights import tside
        tside.load()
        from wily.coaching import archetype
        archetype.reference()
        from wily.base import proref
        proref.load()
        from wily.insights import nades
        nades.load_all()
        from wily.insights import buys
        buys.load()
    except Exception as e:   # the plan loads them itself
        log(f"tables not preloaded: {type(e).__name__}: {e}")


def _cross(steamid, ids):
    """The cross-match analysis, each map in a process of its own, while this one loads the base's tables for the advice
    and the plan (16/10: one after the other before, ~20 s + ~15 s; then the maps one after the other in one process,
    9 to 15 s). Inside a worker already (batch profiling): in turn."""
    import multiprocessing
    from wily.coaching import cross
    if multiprocessing.current_process().name != "MainProcess":
        return cross.run(steamid, set(ids))
    from concurrent.futures.process import BrokenProcessPool
    warm = []
    try:   # a quarter of the processor's cores at most, never more than 6 (each one holds a map's tables)
        return cross.run_parallel(steamid, set(ids), during=lambda: (_prewarm(), warm.append(1)),
                                  workers=max(2, min(6, (os.cpu_count() or 4) // 4)), ex=pool())
    except BrokenProcessPool:   # a process stopped (memory, or no process can start here): here, in turn
        log("cross-match analysis: its processes stopped, done here instead")
        if not warm:
            _prewarm()
        return cross.run(steamid, set(ids))


_POOL = {"ex": None, "used": 0.0}
POOL_SIZE, POOL_IDLE = 6, 300


def pool(start=False):
    """The analyses' worker processes (lowest priority), shared by the steps of an analysis and kept 5 min after their
    last use (16/10: each step started its own, 1 to 2 s each, three times a sync). start: their processes started now
    (while Steam answers and the demo downloads), not at the first job. A broken one (a process that died) is made again."""
    import threading
    import time
    from concurrent.futures import ProcessPoolExecutor
    with _POOL_LOCK:
        ex = _POOL["ex"]
        if ex is None or getattr(ex, "_broken", False) or getattr(ex, "_shutdown_thread", False):
            ex = _POOL["ex"] = ProcessPoolExecutor(POOL_SIZE, initializer=config.low_priority)
            threading.Thread(target=_pool_reaper, args=(ex,), daemon=True, name="pool-reaper").start()
        _POOL["used"] = time.time()
    if start:
        for _ in range(POOL_SIZE):
            ex.submit(int, 0)
    return ex


def _pool_reaper(ex):
    import time
    while True:
        time.sleep(30)
        with _POOL_LOCK:
            if _POOL["ex"] is not ex:
                return
            if time.time() - _POOL["used"] > POOL_IDLE:
                _POOL["ex"] = None
                ex.shutdown(wait=False, cancel_futures=True)
                return


def _latest(steamid, mids, reg):
    """The matches whose facts the plan reads (matchfacts.run: the latest 10 with a demo)."""
    return set([x for x in sorted(mids, key=lambda x: (reg.get(x) or {}).get("time") or "", reverse=True) if config.has_demo(x)][:10])


def early_matches(steamid, mids, reg):
    """Your analysis of these matches started now, each in a worker process (16/10: it reads the demo only, yet waited
    for the detailed extraction, the population and the styles). analyze_player() finds them done; early_done() waits."""
    import multiprocessing
    pdir = config.player_dir(steamid)
    todo = [m for m in mids if config.has_demo(m) and not os.path.exists(os.path.join(pdir, "matches", m, "stats.json"))]
    if not todo or multiprocessing.current_process().name != "MainProcess":
        return None
    latest = _latest(steamid, set(player_matches(steamid)) | set(todo), reg)
    try:
        ex = pool()
        return ex, {ex.submit(_analyze_match, steamid, m, reg.get(m, {}), m in latest): m for m in todo}
    except Exception as e:   # no process can start here: analyze_player() does them, as before
        log(f"matches: not started early ({e})")
        return None


def early_done(early):
    if not early:
        return
    ex, futs = early
    stage("matches", 0, len(futs))
    for k, (f, m) in enumerate(futs.items(), 1):
        try:
            log("  " + f.result())
        except Exception as e:   # its process stopped: analyze_player() does it again
            log(f"  [{m}] ERROR: {e}")
        stage("matches", k, len(futs))


def analyze_player(steamid, reg):
    from wily.demos import analyze
    from wily.demos import map_analysis
    from wily.coaching import cross
    from wily.coaching import advice
    import threading
    from wily.matches import leetify
    lt = {}

    def _leetify():   # Leetify's answers asked from the start, beside the rest (16/10: 2 s of network after it)
        lt["prof"] = leetify.profile(steamid)
        lt["matches"] = leetify.matches(steamid) if lt["prof"] else None
    lth = threading.Thread(target=_leetify, daemon=True, name="leetify")
    lth.start()
    pdir = config.player_dir(steamid)
    ids = player_matches(steamid)
    log(f"Player {steamid}: {len(ids)} match(es) in cache")
    name = None
    todo = [mid for mid in ids if not os.path.exists(os.path.join(pdir, "matches", mid, "stats.json"))
            and config.has_demo(mid)]
    if todo:
        import multiprocessing
        log(f"Analyzing {len(todo)} match(es)…")
        stage("matches", 0, len(todo))
        got = [0]

        def one_done(mid, res, err):
            got[0] += 1
            stage("matches", got[0], len(todo))
            log("  " + (f"[{mid}] ERROR: {err}" if err else res))
        # the matches whose facts the plan reads (matchfacts.run: the latest 10 with a demo): done with the rest
        latest = _latest(steamid, ids, reg)
        if multiprocessing.current_process().name == "MainProcess" and len(todo) > 1:
            config.wait_for_match_end(log, "match analysis")
            _in_workers(_analyze_match, [(mid, (steamid, mid, reg.get(mid, {}), mid in latest)) for mid in todo], min(8, len(todo)), one_done)
        else:  # already inside a worker (batch profiling): stay sequential
            for mid in todo:
                config.wait_for_match_end(log, "match analysis")
                one_done(mid, _analyze_match(steamid, mid, reg.get(mid, {}), mid in latest), None)
    if not ids:
        lth.join()
        prof = lt.get("prof")
        if not prof:
            log("No demo and no public Leetify profile: nothing to analyze.")
            return None
        os.makedirs(pdir, exist_ok=True)
        lm = lt.get("matches")
        adv = leetify.light_advice(prof, lm, steamid)
        adv["light"] = True
        config.write_json(os.path.join(pdir, "advice.json"), _written(adv), separators=(",", ":"))
        log(f"No demo available: light profile built from Leetify ({prof.get('total_matches')} matches)")
        return pdir
    stage("profile")
    res = _cross(steamid, ids)
    enc = lambda o: o.item() if hasattr(o, "item") else str(o)
    config.write_json(os.path.join(pdir, "cross.json"), res, default=enc)   # the same text as json.dump's, in one write
    lang0 = i18n.current()   # the language its sentences are written in (21/10: one changed during it, marked as the other)
    adv = advice.build(pdir)
    lth.join()
    prof = lt.get("prof")
    if prof:
        adv["leetify"] = leetify.light_advice(prof, lt.get("matches"), steamid)["leetify"]
    config.write_json(os.path.join(pdir, "advice.json"), _written(adv, lang0), separators=(",", ":"))
    return pdir


def _written(adv, lang0=None):
    """advice.json as it is saved (13/10): its fixed sentences in the app's language, and that language, so the page
    can have it written again when the app's language changes (serve.relang_if_needed). lang0: the language when its
    sentences were made; the app's language changed meanwhile (21/10: an analysis written in English, marked French,
    never written again): marked with the first, so the page has it written again."""
    adv["written_lang"] = lang0 or i18n.current()
    return i18n.tr_static(adv)


def rebuild_advice(steamid):
    """The advice again from the analyses already done (after a change in how rules are picked): no demo is
    read again. What doesn't come from the demos (Steam, csstats.gg, Leetify) is kept."""
    from wily.coaching import advice
    pdir = config.player_dir(steamid)
    p = os.path.join(pdir, "advice.json")
    if not os.path.exists(os.path.join(pdir, "cross.json")) or not os.path.exists(p):
        return False   # light profile (no demo): nothing to recompute
    old = json.load(open(p, encoding="utf-8"))
    lang0 = i18n.current()
    new = advice.build(pdir)
    new.update({k: v for k, v in old.items() if k not in new and k != "plan"})
    config.write_json(p, _written(new, lang0), separators=(",", ":"))
    return True


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def reanalyze_match(steamid, mid):
    """One match again, from its demo: everything extracted from it (positions, duels, grenades, round context,
    mid-round, buys, T side, reference population, style), then the player's analysis of the match, profile,
    plan and page. For a match analyzed with an older version or interrupted (app closed during the analysis)."""
    import shutil
    sid, mid = int(steamid), str(int(mid))
    dem = config.demo(mid)
    reg = registry()
    if not os.path.exists(dem):
        if out_of_reach(mid):
            raise ValueError(f"The demo of this match is in {', '.join(config.archives_missing())}, out of reach now: open Google Drive, then try again.")
        if not (reg.get(mid) or {}).get("url"):
            raise ValueError("The demo of this match is no longer on this PC, and Valve no longer has it.")
        log("The demo is no longer on this PC: downloading it again…")
        ensure_demos(reg, only={mid})
        if not os.path.exists(dem):
            raise ValueError("Valve no longer has this demo (demos are kept about a month).")
    prefetch(sid)
    pool(start=True)
    log(f"[{mid}] clearing the previous analysis of this match")
    stage("extract")
    shutil.rmtree(os.path.join(config.DEEP, mid), ignore_errors=True)
    for sub in ("midround", "routes", "buys", "tside"):
        _rm(os.path.join(config.OUT, "population", sub, f"{mid}.parquet"))
    _rm(os.path.join(config.OUT, "population", f"{mid}.parquet"))
    _rm(os.path.join(config.OUT, "style", f"{mid}.parquet"))
    pdir = config.player_dir(sid)
    shutil.rmtree(os.path.join(pdir, "matches", mid), ignore_errors=True)
    early = early_matches(sid, [mid], reg)
    ensure_deep()
    if not os.path.exists(os.path.join(config.DEEP, mid, "meta.json")):
        raise ValueError("The demo could not be read again: it may be damaged. Delete it from the cache folder and sync again.")
    from wily.demos import population
    from wily.demos import style
    log(f"[{mid}] reference population and style")
    population.run_all()
    style.run_all(workers=2)
    early_done(early)
    p = os.path.join(pdir, "advice.json")
    old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    log("Updating your profile with this match…")
    if not analyze_player(sid, reg):
        raise ValueError("You are not in this demo.")
    new = json.load(open(p, encoding="utf-8"))
    kept = {k: v for k, v in old.items() if k not in new and k != "plan"}   # Steam, csstats.gg...: not from the demos
    if kept:
        new.update(kept)
        config.write_json(p, new, separators=(",", ":"))
    attach_plan(sid)
    log(f"[{mid}] re-analysis done")
    return sid


def _plan_after(sid):
    """Your teammates' spots and the Live check, in a worker process beside the plan (16/10): (ok, value or error)."""
    out = {}
    for k in ("mates", "livecheck"):
        try:
            if k == "mates":
                from wily.coaching import team
                out[k] = (True, team.mates_regions(sid))
            else:
                from wily.live import livecheck
                out[k] = (True, livecheck.run(sid))
        except Exception as e:
            out[k] = (False, str(e))
    return out


def attach_plan(sid):
    """Coaching plan (routine, mid-round, weapons, context, experiments) from the saved analysis of a player. 16/10
    (the user: "encore beaucoup beaucoup trop long"): its buys, Live check and teammates' spots in the shared worker
    processes meanwhile (pool())."""
    import multiprocessing
    from wily.coaching import plan
    pdir = config.player_dir(sid)
    p = os.path.join(pdir, "advice.json")
    if not os.path.exists(p):
        return
    stage("plan")
    adv = json.load(open(p, encoding="utf-8"))
    load = lambda n: json.load(open(os.path.join(pdir, n), encoding="utf-8")) if os.path.exists(os.path.join(pdir, n)) else None
    ex, bg, after = None, None, None
    if not adv.get("light") and multiprocessing.current_process().name == "MainProcess":
        try:
            ex = pool()
            bg = {"buys": ex.submit(plan.bg_buys, sid, adv.get("archetype"), load("cross.json"))}
            after = ex.submit(_plan_after, sid)
        except Exception as e:   # no process can start here: in turn, as before
            log(f"plan: in one process ({e})")
            ex, bg, after = None, None, None
    try:
        adv["plan"] = plan.build(sid, adv, load("cross.json"), load("deepdive.json"), light=bool(adv.get("light")), bg=bg)
        adv.pop("plan_error", None)
    except Exception as e:
        for f in ((bg or {}).get("buys"), after):   # the shared processes go on with other work
            if f is not None:
                f.cancel()
        log(f"Progress plan unavailable: {e}")
        traceback.print_exc()
        adv["plan_error"] = f"{type(e).__name__}: {e}"[:200]   # the previous plan stays; the page says it is not up to date
        config.write_json(p, _written(adv), separators=(",", ":"), default=str)
        return
    try:   # the focus of the week: the first axis, kept 7 days (Live, Prepare and Review show it)
        from wily.coaching import focus
        adv["plan"]["focus"] = focus.weekly(sid, adv.get("rules"))
    except Exception as e:
        log(f"Focus of the week unavailable: {e}")
    try:
        aft = after.result() if after else _plan_after(sid)
    except Exception as e:   # its process stopped: here, in turn
        log(f"plan: teammates' spots and Live check again here ({type(e).__name__})")
        aft = _plan_after(sid)
    ok, v = aft["mates"]   # your frequent teammates' usual CT spots: dead, the one you watch tells where the fight is
    if ok:
        adv["plan"]["mates"] = v
    else:
        log(f"Teammates' spots unavailable: {v}")
    ok, v = aft["livecheck"]   # what the In game page showed in your matches, against their demos (and its calibration)
    if ok:
        adv["plan"]["livecheck"] = v
    else:
        log(f"Live check unavailable: {v}")
    try:  # coach notes per map and side (zones to change or keep, grenades), from the cross-match analysis
        from wily.coaching import coach_notes
        coach_notes.write(sid, load("cross.json"), adv.get("plan"))
    except Exception as e:
        log(f"Map notes unavailable: {e}")
        adv["plan"].setdefault("unavailable", []).append("map notes")
    config.write_json(p, _written(adv), separators=(",", ":"), default=str)


PARTIAL_HOOK = None  # called with the SteamID once a first profile can be displayed


def quick_profile(sid):
    """Show something within seconds: Leetify stats while demos download (only if no full profile exists yet)."""
    from wily.matches import leetify
    pdir = config.player_dir(sid)
    adv_p = os.path.join(pdir, "advice.json")
    if os.path.exists(adv_p) and not json.load(open(adv_p, encoding="utf-8")).get("light"):
        if PARTIAL_HOOK:
            PARTIAL_HOOK(sid)
        return
    prof = leetify.profile(sid)
    if not prof:
        log("No public Leetify profile: the analysis relies on demos only.")
        return
    os.makedirs(pdir, exist_ok=True)
    adv = leetify.light_advice(prof, leetify.matches(sid), sid)
    adv["light"] = True
    config.write_json(adv_p, _written(adv), separators=(",", ":"))
    log(f"Leetify profile shown ({prof.get('total_matches')} matches tracked): analyzing demos…")
    if PARTIAL_HOOK:
        PARTIAL_HOOK(sid)


SHARECODE_RE = r"CSGO(?:-[A-Za-z0-9]{5}){5}"


def extras(sid):
    """Public info available for anyone: the Steam profile, and the ranks of a local source module when this PC has
    one (csstats, not versioned: 10/10, kept out of the public repository)."""
    from wily.core import steamprofile
    out = {}
    try:
        out["steam"] = steamprofile.steam_profile(sid)
    except Exception:
        pass
    try:
        from wily.matches import csstats
        cs = csstats.fetch(sid)
        if cs:
            out["csstats"] = cs
    except Exception:   # ImportError: no such module here
        pass
    return out


def attach_extras(sid, ex=None):
    p = os.path.join(config.player_dir(sid), "advice.json")
    if not os.path.exists(p):
        return
    adv = json.load(open(p, encoding="utf-8"))
    adv.update(ex if ex is not None else extras(sid))
    config.write_json(p, _written(adv), separators=(",", ":"))


def minimal_profile(sid, ex):
    """No demo, no Leetify: what public sources still tell (ranks per map, Premier history)."""
    cs = ex.get("csstats") or {}
    rules = []
    maps = sorted((m for m in cs.get("maps", []) if m["rank"] > 0), key=lambda m: -m["rank"])  # rank 0 = unranked
    if len(maps) >= 2 and maps[0]["rank"] - maps[-1]["rank"] >= 2:
        b, w = maps[0], maps[-1]
        bn, wn = b['map'].split('_')[-1].capitalize(), w['map'].split('_')[-1].capitalize()
        rules.append({"id": "maps", "score": 20, "short": i18n.tr("Play {map} first", map=bn),
                      "title": i18n.tr("Your best Competitive map: {a} ({ra}), your weakest: {b} ({rb})", a=bn, ra=b['rank_name'], b=wn, rb=w['rank_name']),
                      "why": [i18n.tr("Competitive ranks per map: {list}.", list=", ".join(f"{m['map'].split('_')[-1].capitalize()} {m['rank_name']}" for m in maps[:6]))],
                      "do": [i18n.tr("Pick your best map when you want to win, work on the weakest in Deathmatch and practice mode.")]})
    prem = [x for x in cs.get("premier", []) if x.get("current")]
    if len(prem) >= 2:
        cur, prev = prem[0], prem[1]
        delta = cur["current"] - prev["current"]
        rules.append({"id": "premier", "score": 15, "short": i18n.tr("Premier: improving") if delta > 0 else i18n.tr("Premier: dropping"),
                      "title": i18n.tr("Premier {season}: {cur} (best {best}), vs {prev} in {pseason}", season=cur['season'], cur=i18n.num(cur['current']),
                                       best=i18n.num(cur['best']), prev=i18n.num(prev['current']), pseason=prev['season']),
                      "why": [i18n.tr("{n} wins this season.", n=cur['wins'])], "do": []})
    rules.append({"id": "unlock", "score": 1, "short": i18n.tr("Unlock the full analysis"),
                  "title": i18n.tr("No demo and no Leetify profile: analysis limited to public rankings"),
                  "why": [i18n.tr("Valve doesn't give a player's history from their SteamID alone.")],
                  "do": [i18n.tr("Paste a match share code (CS2 → Watch → Your Matches → share, CSGO-… format) in the search bar, with or without the profile link."),
                         i18n.tr("Or create a free account on leetify.com with this Steam account: its next matches will become analyzable automatically.")]})
    adv = {"rules": rules, "strengths": [], "maps": {}, "match_notes": {}, "light": True, "minimal": True, **ex}
    os.makedirs(config.player_dir(sid), exist_ok=True)
    config.write_json(os.path.join(config.player_dir(sid), "advice.json"), _written(adv), separators=(",", ":"))


def run_for(query, fetch=True):
    """Full pipeline for a search: a SteamID64 / profile URL / vanity name, and/or match share codes.
    Returns a SteamID64, or {"match_players": [...]} when only share codes were given."""
    import re as _re
    from types import SimpleNamespace
    from wily.matches import leetify
    own_id, own_name = config.logged_in_account()
    codes = _re.findall(SHARECODE_RE, str(query))
    rest = _re.sub(SHARECODE_RE, " ", str(query)).replace(",", " ").strip()
    sid = name = None
    if rest:
        sid, name = leetify.resolve_steamid(rest.split()[0])
        if not sid:
            raise ValueError(f"Steam profile not found: {rest}")
    if not sid and not codes:
        raise ValueError("Paste a Steam profile link, a SteamID64, a custom URL name or a CSGO-… share code")
    stage("lookup")
    s = config.settings()
    s.setdefault("own_steamid", own_id)
    if sid:
        log(f"Profile: {name or '?'} ({sid})")
        p = s.setdefault("players", {}).setdefault(str(sid), {})
        if name:
            p["name"] = name
        van = _re.search(r"/id/([^/?#]+)", rest)
        if van:
            p["vanity"] = van.group(1)
    config.save_settings(s)
    ex = {}
    if sid:
        quick_profile(sid)
        ex = extras(sid)
        attach_extras(sid, ex)
    if codes:
        log(f"{len(codes)} share code(s): fetching the matches from Valve…")
    args = SimpleNamespace(steamid=sid, sharecode=codes, authcode=None, knowncode=None, no_fetch=not fetch, own=False)
    before = set(registry())
    reg = collect(args, own_id)
    new = set(reg) - before
    stage("lookup", note={"new": len(new)})
    code_ids = {str(matchlist.decode_sharecode(c)[0]) for c in codes}
    own = bool(sid) and int(sid) == int(own_id or 0)
    ensure_demos(reg, only=new | code_ids | (pending_demos(reg) if own else set()))  # only this search (+ your demos still missing)
    ensure_deep()
    from wily.demos import population
    from wily.demos import style
    population.run_all()
    style.run_all(workers=4)
    if sid and not own and not (s.get("players", {}).get(str(sid)) or {}).get("authcode"):
        log("Only the matches already on this PC (played with you, or added by a share code) can be analyzed for this player. "
            "For a match they played without you: paste its share code (CSGO-…) here, or add their history code in their Analysis tab.")
    if sid:
        if not analyze_player(sid, reg):
            if not ex.get("steam") and not ex.get("csstats"):
                raise ValueError("Nothing public about this player: no demo, no Leetify, no csstats.gg. Try with a share code from one of their matches.")
            minimal_profile(sid, ex)
            log("No demo and no Leetify profile: minimal profile (public csstats.gg rankings and Steam profile).")
        else:
            attach_extras(sid, ex)
        attach_plan(sid)
        log("Analysis done")
        return sid
    # share codes only. Full profiles for you, the players you follow and your teammates in those matches, plus an
    # update of the players already profiled; the others (opponents, strangers) only feed the base: a search builds
    # their profile on demand. A batch of 14 matches used to build ~110 profiles of strangers (hours of CPU).
    import pandas as pd
    players, keep, met = {}, set(), set()
    ps = config.settings().get("players", {})
    anchors = {int(own_id or 0)} | {int(k) for k, v in ps.items() if k.isdigit() and v.get("authcode")}
    profiled = {int(k) for k in (os.listdir(config.PLAYERS) if os.path.exists(config.PLAYERS) else [])
                if k.isdigit() and os.path.exists(os.path.join(config.player_dir(k), "cross.json"))}
    for mid in code_ids:
        f = os.path.join(config.DEEP, mid, "samples.parquet")
        if not os.path.exists(f):
            continue
        S = pd.read_parquet(f, columns=["steamid", "name", "side", "round"])
        side = dict(S[S["round"] == S["round"].min()].drop_duplicates("steamid")[["steamid", "side"]].itertuples(index=False))
        for p_id, nm in S.drop_duplicates("steamid")[["steamid", "name"]].itertuples(index=False):
            if p_id:
                players[int(p_id)] = nm
        ours = {side[a] for a in anchors if a in side}
        met |= {int(p) for p in side if p and int(p) in anchors}
        keep |= {int(p) for p, sd in side.items() if p and (sd in ours or int(p) in profiled)}
    if not players:
        raise ValueError("No match fetched with this code: the demo may have expired at Valve (about 1 month).")
    if not met:   # matches without you or anyone you follow (another team's matches): everyone, as asked
        keep = set(players)
    s = config.settings()
    for p_id, nm in players.items():
        s.setdefault("players", {}).setdefault(str(p_id), {})["name"] = nm
    config.save_settings(s)
    others = len(players) - len(keep)
    log(f"{len(players)} players in this/these match(es): building {len(keep)} profile(s)"
        + (f" (you, your teammates and players already profiled; the {others} others feed the base, search one to see their profile)…" if others else "…"))
    players = {p: nm for p, nm in players.items() if p in keep}
    for i, (p_id, nm) in enumerate(players.items(), 1):
        config.wait_for_match_end(log, "profile building")
        if analyze_player(p_id, reg):
            attach_plan(p_id)
        log(f"  profile {i}/{len(players)}: {nm}")
    log("Analysis done")
    return {"match_players": [{"steamid": str(k), "name": v} for k, v in players.items()]}


_PRE = {"busy": False}
_POOL_LOCK = __import__("threading").Lock()


def prefetch(sid):
    """The files the profile and the plan read next, read once now in the background (16/10, the user: "même sur le
    premier match"): after the PC starts nothing is in memory, and the hard disk seeked ~1,700 times (300 MB, ~20 s)
    while the analysis waited. Started with a sync, while Steam answers and the demo downloads (the disk idle then), and
    by the app a moment after it starts. The thread's disk reads in the background: never ahead of a match's or the
    extraction's."""
    import glob
    import threading
    if _PRE["busy"]:
        return

    def run():
        _PRE["busy"] = True
        try:
            if os.name == "nt":
                import ctypes
                ctypes.windll.kernel32.SetThreadPriority(ctypes.windll.kernel32.GetCurrentThread(), 0x00010000)   # background mode
            pdir = config.player_dir(sid)
            paths = glob.glob(os.path.join(pdir, "matches", "*", "stats.json")) + glob.glob(os.path.join(pdir, "matches", "*", "map.json"))
            for m in player_matches(sid):
                paths += [os.path.join(config.DEEP, m, f) for f in ("loadout.parquet", "deaths_w.parquet", "duels.parquet", "rounds.parquet", "meta.json")]
                paths += [os.path.join(config.OUT, "population", sub, f"{m}.parquet") for sub in ("midround", "tside")]
                paths.append(os.path.join(config.OUT, "population", f"{m}.parquet"))
            paths += glob.glob(os.path.join(config.OUT, "voice", "*.json"))
            paths += glob.glob(os.path.join(config.OUT, "ledgers", "*"))
            paths += [os.path.join(config.OUT, "population", f) for f in ("tside_proc.parquet", "tside_proc.parquet.json", "sites.json")]
            n = 0
            for p in sorted(set(paths)):   # a folder's files one after the other: fewer seeks
                if config.in_match():
                    return
                try:
                    with open(p, "rb") as f:
                        while f.read(1 << 20):
                            pass
                    n += 1
                except OSError:
                    pass
            print(f"prefetch: {n} files of {sid} in memory", flush=True)
        except Exception as e:
            print("prefetch:", e, flush=True)
        finally:
            _PRE["busy"] = False
    threading.Thread(target=run, daemon=True, name="prefetch").start()


def sync_steam(sid=None):
    """Your account: new matches from your Steam history (API key + authentication code) and Valve's last 8,
    then the full analysis. Nothing is recomputed when there is nothing new. Returns the SteamID64."""
    from types import SimpleNamespace
    from wily.matches import steamlink
    own_id, _ = config.logged_in_account()
    s = config.settings()
    sid = int(sid or s.get("own_steamid") or own_id)
    stage("history")
    prefetch(sid)   # your files read while Steam answers and the demo downloads
    pool(start=True)   # and the worker processes started meanwhile
    try:   # demos put in the cache folder by hand (FACEIT's...): listed, then read below like the new ones
        register_local()
    except Exception as e:
        log(f"local demos: {e}")
    try:
        codes = steamlink.new_codes(sid, log=log)
    except steamlink.SteamError as e:
        log(f"Steam history unavailable: {e}")
        codes = []
    key = s.get("steam_api_key")
    try:
        steamlink.friends(key, sid, refresh=True)   # no key of your own: through Wily's site (08/10)
        pt = steamlink.owned_cs2(key, sid) if key else None   # without a key: this PC's Steam says the playtime
        if pt:
            s = config.settings()
            s.setdefault("players", {}).setdefault(str(sid), {})["playtime"] = pt
            config.save_settings(s)
    except steamlink.SteamError as e:
        log(f"Steam: {e}")
    before = registry()
    args = SimpleNamespace(steamid=sid, sharecode=codes, authcode=None, knowncode=None, no_fetch=False, own=(sid == own_id))
    reg = collect(args, own_id)
    try:   # the FACEIT matches of the last month (10/10), when the FACEIT key is set: no demo, the rest counts
        from wily.matches import faceit
        if faceit.key() and faceit.add_matches(sid, log=log):
            reg = registry()
    except Exception as e:
        log(f"FACEIT: {e}")
    got = [c for c in codes if str(matchlist.decode_sharecode(c)[0]) in reg]
    if got:
        steamlink.done_codes(sid, got)
    new = {mid for mid in reg if mid not in before or (reg[mid].get("accounts") and not before[mid].get("accounts"))}
    if len(got) < len(codes):
        log(f"{len(codes) - len(got)} match(es) not fetched yet: Steam must be open and CS2 closed. Trying again at the next sync.")
    fresh = [mid for mid in new if mid not in before]
    pend = pending_demos(reg) if sid == own_id else set()
    log(f"{len(fresh)} new match(es)" + (f", {len(pend)} demo(s) still to fetch" if pend - set(fresh) else ""))
    stage("history", note={"new": len(fresh)})
    if not fresh and not pend and not _deep_todo() and os.path.exists(os.path.join(config.player_dir(sid), "advice.json")):
        attach_plan(sid)  # history-only updates (sessions, friends, playtime) still change the plan
        return sid
    ensure_demos(reg, only=set(fresh) | pend)
    early = early_matches(sid, sorted(set(fresh) | pend), reg)   # your new matches: your analysis of them from now on
    ensure_deep()
    from wily.demos import population
    from wily.demos import style
    population.run_all()
    style.run_all(workers=4)
    early_done(early)
    if analyze_player(sid, reg):
        attach_extras(sid)
        attach_plan(sid)
    log("Sync done")
    return sid


# ---------- demos given by hand (16/10, the user: FACEIT's, while its download API waits for its approval) ----------
FACEIT_NAME = __import__("re").compile(r"^(1-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", __import__("re").I)
SAFE_ID = __import__("re").compile(r"^[A-Za-z0-9_-]{1,80}$")


def _zstd():
    """The zstandard module (FACEIT packs its demos with zstd): installed in this app's Python the first time it is
    needed (a player's copy ships without it: adding it to the runtime would make every player download it again)."""
    try:
        import zstandard
        return zstandard
    except ImportError:
        pass
    import subprocess
    log("FACEIT demo: installing the zstd decompressor (once)…")
    r = subprocess.run([sys.executable, "-s", "-m", "pip", "install", "--disable-pip-version-check", "zstandard"],
                       capture_output=True, text=True, creationflags=config.NO_WINDOW)
    try:
        import importlib
        importlib.invalidate_caches()
        import zstandard
        return zstandard
    except ImportError:
        raise ValueError(i18n.tr("This FACEIT demo is packed with zstd and the decompressor could not be installed "
                                 "(no internet?). Unpack it with 7-Zip or WinRAR and import the .dem.")) from None


def _unpack(src, out):
    """src as a plain demo at out, whatever it was packed with (recognized by its first bytes, not its name)."""
    import shutil
    with open(src, "rb") as f:
        head = f.read(8)
    if head[:7] == b"PBDEMS2":
        shutil.copyfile(src, out)
    elif head[:4] == b"\x28\xb5\x2f\xfd":   # zstd: FACEIT's .dem.zst
        z = _zstd()
        with open(src, "rb") as fi, open(out, "wb") as fo:
            z.ZstdDecompressor().copy_stream(fi, fo)
    elif head[:2] == b"\x1f\x8b":
        import gzip
        with gzip.open(src, "rb") as fi, open(out, "wb") as fo:
            shutil.copyfileobj(fi, fo, 1 << 20)
    elif head[:3] == b"BZh":
        import bz2
        with bz2.open(src, "rb") as fi, open(out, "wb") as fo:
            shutil.copyfileobj(fi, fo, 1 << 20)
    elif head[:6] == b"\xfd7zXZ\x00":
        import lzma
        with lzma.open(src, "rb") as fi, open(out, "wb") as fo:
            shutil.copyfileobj(fi, fo, 1 << 20)
    elif head[:4] == b"PK\x03\x04":
        import zipfile
        with zipfile.ZipFile(src) as zf:
            dems = [n for n in zf.namelist() if n.lower().endswith(".dem")]
            if not dems:
                raise ValueError(i18n.tr("No .dem file in this archive."))
            with zf.open(dems[0]) as fi, open(out, "wb") as fo:
                shutil.copyfileobj(fi, fo, 1 << 20)
    else:
        raise ValueError(i18n.tr("This file is not a CS2 demo."))
    with open(out, "rb") as f:
        if f.read(7) != b"PBDEMS2":
            raise ValueError(i18n.tr("This file is not a CS2 demo."))


def _demo_id(path, name):
    """faceit_<match room> for a FACEIT demo (its file name: <room>-1-1.dem.zst), else import_<its digest>."""
    import hashlib
    m = FACEIT_NAME.match(os.path.basename(name))
    if m:
        return f"faceit_{m.group(1).lower()}", True
    h = hashlib.sha1()
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
    h.update(str(os.path.getsize(path)).encode())
    return f"import_{h.hexdigest()[:16]}", False


def _register(mid, path, name, mtime, faceit):
    """A demo given by hand listed with the matches: its date (the file's), its map, its players; a FACEIT match
    already known from FACEIT's history keeps its entry (scores, date), the demo joins it."""
    import datetime as dt
    from demoparser2 import DemoParser
    try:
        p = DemoParser(path)
        mp = p.parse_header().get("map_name")
        n = int(len(p.parse_player_info()))
    except Exception:
        mp, n = None, 10
    reg = registry()
    e = reg.get(mid) or {}
    entry = {"match_id": mid, "time": dt.datetime.fromtimestamp(mtime or os.path.getmtime(path)).isoformat(timespec="minutes"),
             "players": n or 10, "source": "faceit" if faceit else "import", **e, "file": os.path.basename(name), "map": mp}
    save_registry({mid: entry})
    return mp


def import_demo(src, name, mtime=None):
    """A demo given by the page (Import, drag and drop): .dem or packed (FACEIT's .dem.zst, .gz, .bz2, .xz, .zip),
    unpacked into the cache and listed with the matches. Its analysis: analyze_local(). -> {"id", "map", "new"}"""
    tmp = src + ".dem"
    try:
        _unpack(src, tmp)
        mid, faceit = _demo_id(tmp, name)
        dst = os.path.join(config.CACHE, f"{mid}.dem")
        new = not os.path.exists(config.demo(mid))
        if new:
            os.replace(tmp, dst)
        mp = _register(mid, config.demo(mid), name, mtime, faceit)
        log(f"[{mid}] {'imported' if new else 'already here'}: {os.path.basename(name)} ({mp})")
        return {"id": mid, "map": mp, "new": new}
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def register_local():
    """The demos put in the cache folder by hand (not from Valve, not imported): FACEIT's renamed faceit_<room>, a
    name with other characters renamed import_<digest>, each listed with the matches. -> how many."""
    reg = registry()
    n = 0
    for f in sorted(os.listdir(config.CACHE)) if os.path.isdir(config.CACHE) else []:
        if not f.endswith(".dem") or f[:-4] in reg:
            continue
        path = os.path.join(config.CACHE, f)
        mid, faceit = _demo_id(path, f)
        if FACEIT_NAME.match(f) or not SAFE_ID.match(f[:-4]):
            if os.path.exists(os.path.join(config.CACHE, f"{mid}.dem")):
                continue
            os.replace(path, os.path.join(config.CACHE, f"{mid}.dem"))
            path = os.path.join(config.CACHE, f"{mid}.dem")
        else:
            mid = f[:-4]
        if mid in reg:
            continue
        _register(mid, path, f, os.path.getmtime(path), faceit)
        log(f"[{mid}] a demo put in the cache: {f}")
        n += 1
    return n


def analyze_local(sid=None):
    """The demos given by hand (Import, or put in the cache): read, then your profile, plan and page. -> the SteamID64."""
    own_id, _ = config.logged_in_account()
    sid = int(sid or config.settings().get("own_steamid") or own_id)
    register_local()
    reg = registry()
    ensure_deep()
    from wily.demos import population
    from wily.demos import style
    population.run_all()
    style.run_all(workers=4)
    if analyze_player(sid, reg):
        attach_extras(sid)
        attach_plan(sid)
    log("Import done")
    return sid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steamid", help="SteamID64, Steam profile link or custom URL name")
    ap.add_argument("--sharecode", action="append")
    ap.add_argument("--authcode")
    ap.add_argument("--knowncode")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--own", action="store_true", help="also fetch your own recent matches")
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args()
    own_id, own_name = config.logged_in_account()
    target_name = None
    if args.steamid:
        from wily.matches import leetify
        sid, target_name = leetify.resolve_steamid(args.steamid)
        if not sid:
            log(f"Profile not found: {args.steamid}")
            return
        log(f"Profile: {target_name or '?'} ({sid})")
        args.steamid = sid
    s = config.settings()
    s.setdefault("own_steamid", own_id)
    s.setdefault("players", {}).setdefault(str(own_id), {"name": own_name})
    if args.steamid:
        s["players"].setdefault(str(args.steamid), {})
        if target_name:
            s["players"][str(args.steamid)]["name"] = target_name
    config.save_settings(s)
    if not args.build_only:
        reg = collect(args, own_id)
        ensure_demos(reg)
        ensure_deep()
        from wily.demos import population
        from wily.demos import style
        population.run_all()
        style.run_all(workers=4)
        targets = [args.steamid] if args.steamid else [own_id]
        for sid in targets:
            if analyze_player(sid, reg):
                attach_extras(sid)
                attach_plan(sid)
    from wily.app import build_app
    build_app.main()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
