"""The matches players share, into the base (05/10): pulled from wily.valentingassend.com (api/pull.php, with the
coach's token), checked again here before anything joins the base, kept once (anon.fingerprint: the same match shared
by two players, or already in the base), then processed like a match of the base loop (grow.follow_ups).

    python -m wily.sharing.contributions init     the coach's token: raw in out/settings.json ("contrib_token"), its hash in
                                     web/api/config.php (published with the site; the token never leaves this PC)
    python -m wily.sharing.contributions pull     downloads the waiting zips into out/contrib_in, then deletes them on the site
    python -m wily.sharing.contributions ingest   checks them and adds their matches to the base
    python -m wily.sharing.contributions          both (the base loop does it every hour while it runs)
    python -m wily.sharing.contributions release  the held uploads (below) into the base after all

Held, not in the base (12/10): an upload whose manifest does not say its player saw the notice that speaks of the
matches (usage.NOTICE_V 3). The builds of 10/10 showed an older notice, about the usage statistics only, and shared
the matches all the same; the site's privacy page says they leave "once you have seen that notice". They wait in
out/contrib_in/held until the coach decides: release, or delete the folder.

A match is refused when: its id is not a shared one (8 + 18 digits), a file is not one of the app's tables, a table
has a column the app does not write, a real SteamID or a name is left in it, its map is unknown, or its numbers are not
those of a match (rounds, players, positions)."""
import io
import json
import os
import secrets
import shutil
import sys
import time
import urllib.request
import zipfile

import pyarrow.parquet as pq

from wily.core import anon
from wily.core import config

API = os.environ.get("COACH_CONTRIB_API") or "https://wily.valentingassend.com/api/"
INBOX = os.path.join(config.OUT, "contrib_in")
HELD = os.path.join(INBOX, "held")
NOTICE_MIN = 3   # usage.NOTICE_V since the notice speaks of the matches in every build (12/10)
SEEN_F = os.path.join(config.OUT, "contrib_seen.json")
CONFIG_PHP = os.path.join(config.HERE, "website", "root", "api", "config.php")
TABLES = {"duels", "grenades", "samples", "rounds", "loadout", "deaths_w", "steps", "sounds"}
NEEDED = {"meta.json", "rounds.parquet", "samples.parquet", "duels.parquet", "loadout.parquet"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def init():
    """A new token: the old one stops working once the site has the new config.php."""
    tok = secrets.token_urlsafe(32)
    s = config.settings()
    s["contrib_token"] = tok
    config.save_settings(s)
    import hashlib
    os.makedirs(os.path.dirname(CONFIG_PHP), exist_ok=True)
    open(CONFIG_PHP, "w", encoding="utf-8", newline="\n").write(
        "<?php\n// written by `python -m wily.sharing.contributions init` on the coach's PC: the hash of its token, never the token\n"
        f"return ['token_sha256' => '{hashlib.sha256(tok.encode()).hexdigest()}', 'max_bytes' => 25 * 1024 * 1024, "
        "'per_day' => 40, 'per_ip_day' => 80];\n")
    log(f"token written in out/settings.json, its hash in {CONFIG_PHP}: publish the site (website/deploy.py) for it to work")


def _req(action, f=None, post=False, kind="contrib"):
    tok = config.settings().get("contrib_token")
    if not tok:
        raise SystemExit("no token yet: python -m wily.sharing.contributions init, then publish the site")
    url = API + "pull.php?action=" + action + (f"&f={f}" if f else "") + (f"&kind={kind}" if kind != "contrib" else "")
    req = urllib.request.Request(url, data=b"" if post else None, method="POST" if post else "GET",
                                 headers={"X-Coach-Token": tok, "User-Agent": "CoachCS2-coach"})
    return urllib.request.urlopen(req, timeout=120)


def pull():
    """The waiting zips: downloaded, their sha256 checked, then deleted on the site. -> how many."""
    os.makedirs(INBOX, exist_ok=True)
    files = json.loads(_req("list").read()).get("files") or []
    n = 0
    for x in files:
        dst = os.path.join(INBOX, x["f"])
        data = _req("get", x["f"]).read()
        import hashlib
        if hashlib.sha256(data).hexdigest() != x.get("sha256"):
            log(f"{x['f']}: damaged on the way, left on the site")
            continue
        open(dst, "wb").write(data)
        config.write_json(dst[:-4] + ".json", x.get("meta") or {})
        _req("delete", x["f"], post=True)
        n += 1
    if files:
        log(f"pulled {n} of {len(files)} shared upload(s)")
    return n


def _expected():
    """The columns each table has in the app's own extractions (the newest matches of the base)."""
    cols = {}
    for mid in sorted(os.listdir(config.DEEP), reverse=True)[:30] if os.path.isdir(config.DEEP) else []:
        for f in os.listdir(os.path.join(config.DEEP, mid)):
            if f.endswith(".parquet") and f[:-8] in TABLES:
                try:
                    cols.setdefault(f[:-8], set()).update(pq.read_schema(os.path.join(config.DEEP, mid, f)).names)
                except Exception:
                    pass
    return cols


def _maps():
    return {f[:-5] for f in os.listdir(os.path.join(config.HERE, "resources", "maps")) if f.endswith(".json")}


def check_match(files, expected, maps):
    """One shared match ({file: bytes}): [] when it can join the base, else what is wrong."""
    bad = []
    names = set(files)
    if not NEEDED <= names:
        bad.append(f"missing {sorted(NEEDED - names)}")
    for f in names - {"meta.json"}:
        if not (f.endswith(".parquet") and f[:-8] in TABLES):
            bad.append(f"unexpected {f}")
    try:
        meta = json.loads(files.get("meta.json") or b"{}")
    except ValueError:
        return ["meta.json unreadable"]
    if meta.get("map") not in maps:
        bad.append(f"unknown map {meta.get('map')!r}")
    if anon.SID_RE.search((files.get("meta.json") or b"").decode("utf-8", "replace")):
        bad.append("a SteamID in meta.json")
    for f, b in files.items():
        if not f.endswith(".parquet") or f[:-8] not in TABLES:
            continue
        try:
            tb = pq.read_table(io.BytesIO(b))
        except Exception:
            bad.append(f"{f} unreadable")
            continue
        extra = set(tb.column_names) - expected.get(f[:-8], set(tb.column_names))
        if extra:
            bad.append(f"{f}: columns the app does not write {sorted(extra)[:5]}")
        left = anon.leftovers(tb)
        if left:
            bad.append(f"{f}: {left}")
        if f == "rounds.parquet" and not 1 <= tb.num_rows <= 60:
            bad.append(f"{tb.num_rows} rounds")
        if f == "samples.parquet":
            if not 100 <= tb.num_rows <= 400000:
                bad.append(f"{tb.num_rows} positions")
            elif "steamid" in tb.column_names and len(set(tb.column("steamid").to_pylist())) > 14:
                bad.append("more than 14 players")
    return bad


def _seen():
    """The fingerprints of the base's matches (computed once, then kept) and of the shared ones."""
    s = config.read_json(SEEN_F, {}) or {}
    fps = s.setdefault("fingerprints", {})
    known = set(fps.values())
    for mid in os.listdir(config.DEEP) if os.path.isdir(config.DEEP) else []:
        if mid not in known:
            fp = anon.fingerprint(os.path.join(config.DEEP, mid))
            if fp:
                fps.setdefault(fp, mid)
    config.write_json(SEEN_F, s)
    return s


def held():
    """How many matches wait in out/contrib_in/held (each upload's count, from the site's note of it)."""
    n = 0
    for f in os.listdir(HELD) if os.path.isdir(HELD) else []:
        if f.endswith(".zip"):
            n += int((config.read_json(os.path.join(HELD, f[:-4] + ".json"), {}) or {}).get("matches") or 1)
    return n


def drop_held():
    """The held uploads deleted (15/10, Settings: the coach decides): their zips and notes. -> how many matches."""
    n = held()
    for f in os.listdir(HELD) if os.path.isdir(HELD) else []:
        if f.endswith((".zip", ".json")):
            os.remove(os.path.join(HELD, f))
    log(f"{n} held match(es) deleted")
    return n


def ingest(dest=None, follow=True, release=False):
    """The pulled zips: every match checked, the new ones into out/deep (or dest), then the base's per-match tables;
    an upload sent before its player saw the notice that speaks of the matches: held (release: those, into the base).
    -> how many matches joined."""
    dest = dest or config.DEEP
    src = HELD if release else INBOX
    zips = sorted(f for f in os.listdir(src) if f.endswith(".zip")) if os.path.isdir(src) else []
    if not zips:
        return 0
    expected, maps, s = _expected(), _maps(), _seen()
    fps, added = s["fingerprints"], 0
    stats = s.setdefault("stats", {"joined": 0, "duplicates": 0, "refused": 0})
    for zf in zips:
        p = os.path.join(src, zf)
        try:
            z = zipfile.ZipFile(p)
            groups, man = {}, {}
            for m in z.infolist():
                name = m.filename
                if name == "manifest.json":
                    try:
                        man = json.loads(z.read(m))
                    except ValueError:
                        pass
                    continue
                if name.endswith("/"):
                    continue
                mid, _, f = name.partition("/")
                if not (len(mid) == 19 and mid.startswith("8") and mid.isdigit() and f and "/" not in f) or m.file_size > 300 * 2 ** 20:
                    raise ValueError(f"unexpected {name}")
                groups.setdefault(mid, {})[f] = z.read(m)
        except Exception as e:
            log(f"{zf}: refused ({e})")
            stats["refused"] += 1
            shutil.move(p, p + ".refused")
            continue
        notice = man.get("notice") if isinstance(man, dict) else None
        if not release and not (isinstance(notice, int) and notice >= NOTICE_MIN):
            z.close()
            os.makedirs(HELD, exist_ok=True)
            for a in (zf, zf[:-4] + ".json"):
                if os.path.exists(os.path.join(src, a)):
                    shutil.move(os.path.join(src, a), os.path.join(HELD, a))
            log(f"{zf}: held, {len(groups)} match(es) sent before the notice that speaks of them (python -m wily.sharing.contributions release)")
            continue
        for mid, files in groups.items():
            bad = check_match(files, expected, maps)
            if bad:
                log(f"{zf} {mid}: refused ({'; '.join(bad)[:200]})")
                stats["refused"] += 1
                continue
            tmp = os.path.join(dest, f".{mid}.tmp")
            shutil.rmtree(tmp, ignore_errors=True)
            os.makedirs(tmp)
            for f, b in files.items():
                open(os.path.join(tmp, f), "wb").write(b)
            fp = anon.fingerprint(tmp)
            if not fp or fp in fps or os.path.exists(os.path.join(dest, mid)):
                shutil.rmtree(tmp, ignore_errors=True)
                stats["duplicates"] += 1
                continue
            os.replace(tmp, os.path.join(dest, mid))
            fps[fp] = mid
            stats["joined"] += 1
            added += 1
        z.close()
        os.makedirs(os.path.join(INBOX, "done"), exist_ok=True)
        shutil.move(p, os.path.join(INBOX, "done", zf))
        if os.path.exists(p[:-4] + ".json"):
            shutil.move(p[:-4] + ".json", os.path.join(INBOX, "done", zf[:-4] + ".json"))
    s["last"] = time.time()
    config.write_json(SEEN_F, s)
    log(f"shared matches: {added} joined the base ({stats['joined']} in all, {stats['duplicates']} already there, {stats['refused']} refused)")
    if added and follow and dest == config.DEEP:
        from wily.base import grow
        grow.follow_ups()   # midround, buys, T side, population, style: each skips what is done
    return added


REPORTS = os.path.join(config.OUT, "reports")


def pull_reports():
    """The bug reports players sent (05/10, the alpha): into out/reports/<id>.json, then deleted on the site."""
    import hashlib
    os.makedirs(REPORTS, exist_ok=True)
    files = json.loads(_req("list", kind="reports").read()).get("files") or []
    n = 0
    for x in files:
        data = _req("get", x["f"], kind="reports").read()
        if hashlib.sha256(data).hexdigest() != x.get("sha256"):
            continue
        config.write_json(os.path.join(REPORTS, x["f"]), json.loads(data), indent=1)
        _req("delete", x["f"], post=True, kind="reports")
        n += 1
    if n:
        log(f"{n} bug report(s) pulled into out/reports")
    return n


def pull_usage(days=10):
    """The days' totals of the players' anonymous usage statistics (usage.php): the last days again each time (today's
    still grows), into out/usage_all/<day>.json."""
    import datetime as dt
    from wily.sharing import usage
    os.makedirs(usage.ALL, exist_ok=True)
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    n = 0
    for x in json.loads(_req("list", kind="usage").read()).get("files") or []:
        if x["f"][:10] < since and os.path.exists(os.path.join(usage.ALL, x["f"])):
            continue
        config.write_json(os.path.join(usage.ALL, x["f"]), json.loads(_req("get", x["f"], kind="usage").read()))
        n += 1
    return n


def reports(with_diag=None):
    """The reports here, the newest first; one with its technical details (with_diag: its id)."""
    out = []
    for sub in ("", "done"):
        d = os.path.join(REPORTS, sub)
        for f in os.listdir(d) if os.path.isdir(d) else []:
            if not f.endswith(".json"):
                continue
            r = config.read_json(os.path.join(d, f), {}) or {}
            r["done"] = bool(sub)
            r["has_diag"] = bool(r.get("diag"))
            if r.get("id") != with_diag:
                r.pop("diag", None)
            out.append(r)
    return sorted(out, key=lambda r: -(r.get("at") or 0))


def report_done(rid, done=True):
    import re
    if not re.fullmatch(r"\d{14}-[0-9a-f]{12}", rid or ""):
        raise ValueError("unknown report")
    src, dst = (REPORTS, os.path.join(REPORTS, "done")) if done else (os.path.join(REPORTS, "done"), REPORTS)
    os.makedirs(dst, exist_ok=True)
    os.replace(os.path.join(src, rid + ".json"), os.path.join(dst, rid + ".json"))


def status():
    s = config.read_json(SEEN_F, {}) or {}
    waiting = len([f for f in os.listdir(INBOX) if f.endswith(".zip")]) if os.path.isdir(INBOX) else 0
    new_reports = len([f for f in os.listdir(REPORTS) if f.endswith(".json")]) if os.path.isdir(REPORTS) else 0
    return {"token": bool(config.settings().get("contrib_token")), "stats": s.get("stats") or {}, "last": s.get("last"), "waiting": waiting,
            "held": held(), "reports": new_reports}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "init" in sys.argv:
        init()
    elif "reports" in sys.argv:
        pull_reports()
        for r in reports():
            print(time.strftime("%d/%m %H:%M", time.localtime(r.get("at") or 0)), r.get("app"), "|", (r.get("text") or "")[:100].replace("\n", " "),
                  "| done" if r["done"] else "")
    elif "release" in sys.argv:
        print(f"{ingest(release=True)} match(es) joined the base from the held uploads")
    else:
        if "ingest" not in sys.argv:
            pull()
        if "pull" not in sys.argv:
            ingest()
