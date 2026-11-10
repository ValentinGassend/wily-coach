"""What the base's steps already did, match by match, and its per-match tables kept as one.

15/10, the user: "optimiser l'analyse de match pour que ça soit vraiment plus vite". The base lives on a hard disk
(5,000 matches): each step of a sync opened every match's files to find the one new match (a file's header, its date:
a disk seek each, ~10 ms), and the advice read the 5,000 per-match tables of the population and the styles again.
Minutes before the first useful second, every sync. Now:
- folders()/names(): a folder read once (os.scandir gives each entry's date without opening it);
- Ledger: the matches a step found complete, with their folder's date: a sync checks only the others (a match
  extracted again changes its folder's date: checked again);
- stacked(): a folder's per-match tables as one, kept on disk with the files it holds and their dates: only the new
  or changed files are read."""
import json
import os

import pandas as pd

from wily.core import config

D = os.path.join(config.OUT, "ledgers")


def folders(base):
    """{name: date (ns)} of the folder's sub-folders, from one read of it."""
    try:
        with os.scandir(base) as it:
            return {e.name: e.stat().st_mtime_ns for e in it if e.is_dir()}
    except OSError:
        return {}


def names(folder, ext=".parquet"):
    """The names (without the extension) of the folder's files of that kind, from one read of it."""
    try:
        return {f[:-len(ext)] for f in os.listdir(folder) if f.endswith(ext)}
    except OSError:
        return set()


def touch(folder):
    """A match's folder rewritten in place (files replaced, none added): its date moved, so the ledgers see it."""
    try:
        os.utime(folder, None)
    except OSError:
        pass


class Ledger:
    """The matches a step found complete, each with its folder's date then. version: what "complete" means (a new
    requirement: every match checked again)."""

    def __init__(self, name, version=1):
        self.path = os.path.join(D, f"done_{name}.json")   # stacked() keeps <name>.json/.parquet: never the same file
        self.version = version if isinstance(version, (int, str)) else json.dumps(version)
        d = None
        try:
            d = config.read_json(self.path)
        except (OSError, ValueError):
            pass
        self.done = d["done"] if isinstance(d, dict) and d.get("v") == self.version else {}
        self.changed = False

    def settled(self, key, stamp):
        return self.done.get(key) == stamp

    def mark(self, key, stamp):
        if self.done.get(key) != stamp:
            self.done[key] = stamp
            self.changed = True

    def save(self):
        if self.changed:
            try:
                config.write_json(self.path, {"v": self.version, "done": self.done}, separators=(",", ":"))
            except OSError as e:   # the next sync checks them again
                print("ledger:", e, flush=True)
            self.changed = False


def stacked(folder, name, prep=None, skip_empty=False, only=None):
    """pd.concat of the folder's .parquet files (in the folder's order; only(file name) when given), each read as
    prep(table, file name) when given, empty ones left out with skip_empty: the same table, read from a consolidated
    copy that only takes in the new or changed files (out/ledgers/<name>.parquet)."""
    try:
        with os.scandir(folder) as it:
            now = {e.name: e.stat().st_mtime_ns for e in it
                   if e.name.endswith(".parquet") and (only is None or only(e.name)) and e.is_file()}
        order = [f for f in os.listdir(folder) if f in now]
    except OSError:
        return pd.DataFrame()
    if not now:
        return pd.DataFrame()
    side, copy = os.path.join(D, f"{name}.json"), os.path.join(D, f"{name}.parquet")
    old, df = {}, None
    try:
        old = config.read_json(side, {}) or {}
        if old:
            df = pd.read_parquet(copy)
    except Exception:   # no copy, or one being replaced: read again
        old, df = {}, None
    if df is not None and old == now:
        return df.drop(columns="_f").reset_index(drop=True)
    parts = []
    if df is not None and len(df):
        parts.append(df[df["_f"].map(lambda f: f in now and old.get(f) == now[f])])
    kept = set(parts[0]["_f"].unique()) if parts else set()
    for f in order:
        if f in kept or (old.get(f) == now[f] and df is not None):   # kept, or read before and empty
            continue
        try:
            x = pd.read_parquet(os.path.join(folder, f))
        except Exception:   # a file being written (the base loop): left out this time, read at the next call
            now.pop(f, None)
            continue
        if prep:
            x = prep(x, f)
        if skip_empty and not len(x):
            continue
        parts.append(x.assign(_f=f))
    parts = [p for p in parts if len(p)] or parts[:1]
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    rank = {f: i for i, f in enumerate(order)}
    out = out.iloc[out["_f"].map(rank).argsort(kind="stable")].reset_index(drop=True)
    try:
        os.makedirs(D, exist_ok=True)
        tmp = f"{copy}.{os.getpid()}.tmp"
        out.to_parquet(tmp)
        os.replace(tmp, copy)
        config.write_json(side, now, separators=(",", ":"))
    except Exception as e:   # a column parquet refuses: the next call reads the files again
        print(f"{name}: no consolidated copy:", e, flush=True)
    return out.drop(columns="_f")


def gathered(name, items, prep=None):
    """pd.concat of prep(pd.read_parquet(path), key) for (key, path, date) in items, in that order (prep: the table
    marked with its key, say): read from a copy kept as one (out/ledgers/<name>.parquet with each key's date) that
    only takes in the new or changed keys. The copy also keeps the keys other callers asked (another player's pool):
    the columns a table lacks are empty (NaN) there, read by name only."""
    side, copy = os.path.join(D, f"{name}.json"), os.path.join(D, f"{name}.parquet")
    old, df = {}, None
    try:
        old = config.read_json(side, {}) or {}
        if old:
            df = pd.read_parquet(copy)
    except Exception:   # no copy, or one being replaced: read again
        old, df = {}, None
    want = {k: st for k, _, st in items}
    valid = {k for k, st in old.items() if want.get(k, st) == st}
    parts = [df[df["_k"].isin(valid)]] if df is not None and len(df) else []
    idx, new = {k: old[k] for k in valid}, False
    for k, path, st in items:
        if k in valid:
            continue
        try:
            x = pd.read_parquet(path)
        except Exception:   # no such file (a match without that table), or one being written: left out, asked again next time
            continue
        if prep:
            x = prep(x, k)
        idx[k] = st
        new = True
        if len(x):
            parts.append(x.assign(_k=k))
    allp = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["_k"])
    if new or len(idx) != len(old):
        try:
            os.makedirs(D, exist_ok=True)
            tmp = f"{copy}.{os.getpid()}.tmp"
            allp.to_parquet(tmp)
            os.replace(tmp, copy)
            config.write_json(side, idx, separators=(",", ":"))
        except Exception as e:   # a column parquet refuses: the next call reads the files again
            print(f"{name}: no consolidated copy:", e, flush=True)
    rank = {k: i for i, (k, _, _) in enumerate(items)}
    out = allp[allp["_k"].isin(want)]
    out = out.iloc[out["_k"].map(rank).argsort(kind="stable")]
    return out.drop(columns="_k").reset_index(drop=True)


_PM = {}


def per_match(name, dirs, read, shared=False):
    """{match: read(match)} for the matches of dirs ({match: folder date}), kept in out/ledgers/<name>.json with each
    folder's date: read() only for the new or changed ones (None: left out, asked again next time). shared: callers ask
    different sets (16/10: cross_zone_n, each player's maps): the ones not asked this time are kept, not dropped (the
    analyses of you and a teammate in one sync read the other's 1,365 matches again each time)."""
    path = os.path.join(D, f"{name}.json")
    try:   # kept in memory while the file is the same (16/10: a page build asked for the facts 94 times)
        mt = os.path.getmtime(path)
        known = _PM[name][1] if _PM.get(name, (None,))[0] == mt else (config.read_json(path, {}) or {})
        _PM[name] = (mt, known)
    except (OSError, ValueError):
        known = {}
    out, changed = {}, False
    for mid, stamp in dirs.items():
        k = known.get(mid)
        if k and k[0] == stamp:
            out[mid] = k[1]
            continue
        v = read(mid)
        if v is None:
            continue
        out[mid] = v
        known[mid] = [stamp, v]
        changed = True
    if changed or (not shared and len(known) != len(out)):
        try:
            keep = known if shared else {m: known[m] for m in out}
            config.write_json(path, keep, separators=(",", ":"))
            _PM[name] = (os.path.getmtime(path), keep)
        except OSError:
            _PM.pop(name, None)
    return out


def match_facts():
    """Each extracted match of the base (a meta.json): {"map", "zone_mode", "zones" (how many), and whether its
    "samples", "rounds" and "loadout" files are there}, read again only when its folder changes (15/10: the plan
    opened the 5,000 meta.json twice to sort the matches by map, and counted the files one by one)."""
    def read(mid):
        d = os.path.join(config.DEEP, mid)
        try:
            with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            return None
        has = lambda n: os.path.exists(os.path.join(d, f"{n}.parquet"))
        g = os.path.join(d, "grenades.parquet")
        return {"map": meta.get("map"), "zone_mode": meta.get("zone_mode"), "zones": len(meta.get("zones") or []),
                "samples": has("samples"), "rounds": has("rounds"), "loadout": has("loadout"),
                "grenades": os.path.getmtime(g) if os.path.exists(g) else None}
    return per_match("match_facts2", folders(config.DEEP), read)
