"""Grow the reference population: random players seen in demos -> their recent matchmaking games (Leetify share codes)
-> demos from Valve -> deep extraction + per-player metrics.

Usage: python -m wily.base.crawl [max_new_demos=40] [--maps de_anubis,de_vertigo] [--workers 4]
Needs Steam running and CS2 closed (match info comes from Valve's game coordinator).
Phase 1 (sequential): Leetify codes + Valve match info. Phase 2 (parallel): download, decompress, extract.
"""
import datetime as dt
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from wily.core import config
from wily.app import pipeline
from wily.demos import deep
from wily.matches import leetify
from wily.matches import matchlist
from wily.demos import population
from wily.matches.coach import decompress, download


def seen_players():
    ids = set()
    for mid in os.listdir(config.DEEP):
        f = os.path.join(config.DEEP, mid, "samples.parquet")
        if os.path.exists(f):
            ids |= set(pd.read_parquet(f, columns=["steamid"]).steamid)
    ids.discard(0)
    return list(ids)


def own_match_players():
    """Players who shared a match with the app owner (first ring of the rebound)."""
    own = config.settings().get("own_steamid")
    ids = set()
    for mid in os.listdir(config.DEEP):
        f = os.path.join(config.DEEP, mid, "samples.parquet")
        if os.path.exists(f):
            s = set(pd.read_parquet(f, columns=["steamid"]).steamid)
            if own in s:
                ids |= s
    ids.discard(0)
    ids.discard(own)
    return ids


def collect_urls(max_new, prefer_maps, days, per_player=3, own_first=True):
    reg = pipeline.registry()
    s = config.settings()
    visited = {v for v in s.get("crawl_visited", [])}
    ring1 = own_match_players() if own_first else set()
    players = [p for p in seen_players() if str(p) not in visited or (p in ring1 and str(p) not in set(s.get("crawl_deep", [])))]
    random.shuffle(players)
    players.sort(key=lambda p: p not in ring1)
    limit = dt.datetime.utcnow() - dt.timedelta(days=days)
    todo, seen_codes = [], set()
    for pid in players:
        if len(todo) >= max_new:
            break
        visited.add(str(pid))
        ms = leetify.matches(pid)
        cand = [m for m in ms if str(m.get("data_source_match_id", "")).startswith("CSGO-")
                and dt.datetime.fromisoformat(m["finished_at"][:19]) >= limit]
        if prefer_maps:
            cand.sort(key=lambda m: m["map_name"] not in prefer_maps)
        taken = 0
        for m in cand:
            if taken >= per_player or len(todo) >= max_new:
                break
            code = m["data_source_match_id"]
            if code in seen_codes:
                continue
            seen_codes.add(code)
            try:
                mid_, oc, tok = matchlist.decode_sharecode(code)
                if str(mid_) in reg:
                    continue
                info = matchlist.fetch_one(mid_, oc, tok)
                if info and info[0].get("url"):
                    todo.append(info[0] | {"crawled": True, "map_hint": m["map_name"]})
                    reg[info[0]["match_id"]] = todo[-1]
                    taken += 1
                    print(f"  link {len(todo)}/{max_new}: {m['map_name']} (player {pid})", flush=True)
            except Exception as e:
                print(f"  code {code}: {e}", flush=True)
    s = config.settings()
    s["crawl_visited"] = sorted(visited)
    s["crawl_deep"] = sorted(set(s.get("crawl_deep", [])) | {str(p) for p in ring1 if str(p) in visited})
    config.save_settings(s)
    pipeline.save_registry(reg)
    return todo


def process(info):
    mid = info["match_id"]
    dem = config.demo(mid)
    if not os.path.exists(dem):
        download(info["url"], dem + ".bz2")
        decompress(dem + ".bz2", dem)
        os.remove(dem + ".bz2")
    out = os.path.join(config.DEEP, mid)
    if not os.path.exists(os.path.join(out, "meta.json")):
        deep.extract(dem, out)
    population.extract(mid)
    return info.get("map_hint"), mid


def main(max_new=40, prefer_maps=None, days=28, workers=4, per_player=3):
    todo = collect_urls(max_new, prefer_maps, days, per_player)
    print(f"{len(todo)} demos to fetch", flush=True)
    done = 0
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(process, i) for i in todo]
        for f in as_completed(futs):
            try:
                mp, mid = f.result()
                done += 1
                print(f"[{done}/{len(todo)}] {mp} {mid}", flush=True)
            except Exception as e:
                print(f"  failed: {e}", flush=True)
    print(f"DONE: {done} new demos", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    n = int(next((a for a in args if a.isdigit()), 40))
    maps = args[args.index("--maps") + 1] if "--maps" in args else None
    w = int(args[args.index("--workers") + 1]) if "--workers" in args else 4
    pp = int(args[args.index("--per-player") + 1]) if "--per-player" in args else 3
    main(n, set(maps.split(",")) if maps else None, workers=w, per_player=pp)
