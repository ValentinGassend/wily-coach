"""Build individual profiles for every player with enough demos in the base (parallel).

Usage: python -m wily.base.profile_all [min_demos=3] [--workers N] [--force]
       python -m wily.base.profile_all --plans      # rebuild only the coaching plans of every existing profile
       python -m wily.base.profile_all --existing   # full analysis again for every existing profile (after the base grew)
       python -m wily.base.profile_all --advice     # advice and plans again from the analyses already done (no demo read)
"""
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

from wily.core import config


def candidates(min_demos):
    c, names = Counter(), {}
    for mid in os.listdir(config.DEEP):
        f = os.path.join(config.DEEP, mid, "samples.parquet")
        if not os.path.exists(f) or not config.has_demo(mid):
            continue
        s = pd.read_parquet(f, columns=["steamid", "name"]).drop_duplicates("steamid")
        for sid, n in zip(s.steamid, s.name):
            if sid:
                c[sid] += 1
                names[sid] = n
    return [(sid, names[sid], n) for sid, n in c.most_common() if n >= min_demos]


def work(sid):
    config.wait_for_match_end()   # a match is going on: this profile waits for its end
    import io
    import contextlib
    from wily.app import pipeline
    buf = io.StringIO()
    t = time.time()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        if ADVICE:
            ok = pipeline.rebuild_advice(int(sid))
        else:
            ok = pipeline.analyze_player(int(sid), pipeline.registry()) if not PLANS_ONLY else True
        if ok or os.path.exists(os.path.join(config.player_dir(sid), "advice.json")):   # profiles without demos too
            pipeline.attach_plan(int(sid))
    return sid, bool(ok), round(time.time() - t)


PLANS_ONLY = "--plans" in sys.argv  # only (re)build the coaching plan of existing profiles
EXISTING = "--existing" in sys.argv  # full analysis of every existing profile
ADVICE = "--advice" in sys.argv  # advice and plan again, from the analyses already done


def main(min_demos=3, workers=None, force=False):
    if PLANS_ONLY or EXISTING or ADVICE:
        todo = [(sid, (config.settings().get("players", {}).get(sid) or {}).get("name") or sid, 0) for sid in os.listdir(config.PLAYERS)
                if os.path.exists(os.path.join(config.player_dir(sid), "advice.json"))]
        force = True
        if EXISTING:  # the most played first, and yours before everything
            own = str(config.settings().get("own_steamid") or "")
            n_demos = dict((str(sid), n) for sid, _, n in candidates(1))
            todo = sorted(((sid, name, n_demos.get(str(sid), 0)) for sid, name, _ in todo), key=lambda t: (str(t[0]) != own, -t[2]))
    else:
        todo = candidates(min_demos)
    if not force:
        todo = [t for t in todo if not os.path.exists(os.path.join(config.player_dir(t[0]), "advice.json"))]
    s = config.settings()
    for sid, name, n in todo:
        s.setdefault("players", {}).setdefault(str(sid), {})["name"] = name
    config.save_settings(s)
    workers = workers or max(1, (os.cpu_count() or 4) - 2)
    print(f"{len(todo)} profiles to build ({workers} processes)", flush=True)
    done = 0
    with ProcessPoolExecutor(workers, initializer=config.low_priority) as ex:
        futs = {ex.submit(work, sid): (sid, name, n) for sid, name, n in todo}
        for f in as_completed(futs):
            sid, name, n = futs[f]
            done += 1
            try:
                _, ok, secs = f.result()
                print(f"[{done}/{len(todo)}] {name} ({n} demos) {'OK' if ok else 'nothing'} {secs}s", flush=True)
            except Exception as e:
                print(f"[{done}/{len(todo)}] {name} ERROR {e}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    md = int(next((x for x in a if x.isdigit()), 3))
    w = int(a[a.index("--workers") + 1]) if "--workers" in a else None
    main(md, w, "--force" in a)
