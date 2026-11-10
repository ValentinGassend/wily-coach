"""Build the Coach CS2 site in out/site/:
  index.html            app shell + player index (embedded)
  players/<steamid>.json one file per analyzed player (loaded on demand)
  radars/<map>.json      radar images + viewbox per map (loaded on demand)
Also writes out/app.html (same shell) for backward compatibility.
"""
import datetime as dt
import json
import os
import shutil
import sys

from PIL import Image

from wily.core import config
from wily.core import mapdata
from wily.app.build_report import _names, radar_uri, summary

MODE_EN = {"Compétitif": "Competitive", "Compétitif / Premier": "Competitive / Premier"}  # older analyses
TEMPLATE = os.environ.get("COACH_TEMPLATE") or os.path.join(config.HERE, "templates", "app_template.html")  # a test copy can point elsewhere
SITE = os.path.join(config.OUT, "site")


def jload(p, default=None):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def _story(mid):
    """Round by round from the demo: where the Ts went and how fast, who died where and when."""
    try:
        from wily.insights import tside
        return tside.match_story(mid)
    except Exception as e:
        print(f"[{mid}] round story: {e}")
        return None


def _reads(sid, mid, st):
    """The analyst's reads of the match (re-peek, deaths without impact, flashes used, pulled by a fake, clutches)."""
    try:
        from wily.coaching import review
        return review.match_reads(sid, mid, st)
    except Exception as e:
        print(f"[{mid}] reads: {e}")
        return None


def player_data(sid):
    pdir = config.player_dir(sid)
    adv = jload(os.path.join(pdir, "advice.json"))
    if not adv:
        return None
    notes = jload(os.path.join(pdir, "notes.json"), {})
    cross = jload(os.path.join(pdir, "cross.json"), {})
    matches, name, names = [], None, []
    mdir = os.path.join(pdir, "matches")
    for mid in os.listdir(mdir) if os.path.exists(mdir) else []:
        st = jload(os.path.join(mdir, mid, "stats.json"))
        mp = jload(os.path.join(mdir, mid, "map.json"))
        if not st or st.get("error") or not mp:
            continue
        name = name or st["player"]["name"]
        names.append((st["match"].get("time"), st["player"]["name"]))
        manual = notes.get("matches", {}).get(mid)
        matches.append({
            "id": mid, "time": st["match"].get("time"), "map": st["map"], "mode": MODE_EN.get(st["mode"], st["mode"]),
            "hostage": st["map"].startswith("cs_"), "score": st["final_score"], "result": st["result"],
            "rounds": st["rounds"], "sum": summary(st),
            "per_round": [{k: r[k] for k in ("round", "side", "won", "kills", "deaths", "my_buy", "team_buy")} for r in st["per_round"]],
            "map_data": _names(mp) and {k: mp[k] for k in ("zones", "general", "me", "my_deaths", "my_kills", "heat", "levels", "zone_mode")}
                        | {"openings": [k for k in mp["all_kills"] if k["opening"]]},
            "notes": manual or adv["match_notes"].get(mid), "notes_manual": bool(manual),
            "story": _story(mid),
            "reads": _reads(sid, mid, st),
        })
    matches.sort(key=lambda m: m["time"] or "", reverse=True)
    if names:
        name = max(names, key=lambda x: x[0] or "")[1]
    meta = config.settings().get("players", {}).get(str(sid), {})
    if adv.get("light"):
        name = name or (adv.get("leetify") or {}).get("name")
    deep = jload(os.path.join(pdir, "deepdive.json"))
    return {"steamid": str(sid), "vanity": meta.get("vanity"), "light": bool(adv.get("light")), "deep": deep,
            "name": name or meta.get("name") or str(sid),
            "matches": matches, "overall": notes.get("overall"), "advice": adv, "cross": cross,
            "cross_notes": jload(os.path.join(pdir, "cross_notes.json"), {})}


def index_entry(p):
    ms = p["matches"]
    maps = {}
    for m in ms:
        maps[m["map"]] = maps.get(m["map"], 0) + 1
    for m in (p.get("cross") or {}).get("maps", []):
        maps.setdefault(m["map"], m["matches"])
    if not maps and p["advice"].get("leetify"):
        maps = {k: v["n"] for k, v in p["advice"]["leetify"].get("by_map", {}).items()}
    if not maps and p["advice"].get("csstats"):
        maps = {m["map"]: m["wins"] for m in p["advice"]["csstats"].get("maps", [])}
    k = sum(m["sum"]["kills"] for m in ms)
    d = sum(m["sum"]["deaths"] for m in ms)
    rec = {"win": 0, "draw": 0, "loss": 0}
    for m in ms:
        rec[m["result"]] += 1
    bench = p["advice"].get("bench") or {}
    return {"steamid": p["steamid"], "name": p["name"], "vanity": p.get("vanity"), "light": p["light"],
            "avatar": (p["advice"].get("steam") or {}).get("avatar"),   # the bar's account (05/10)
            "minimal": bool(p["advice"].get("minimal")), "n": len(ms),
            "maps": maps, "last": ms[0]["time"] if ms else None, "kd": round(k / d, 2) if d else None,
            "adr": round(sum(m["sum"]["adr"] * m["rounds"] for m in ms) / max(sum(m["rounds"] for m in ms), 1), 1) if ms else None,
            "record": rec, "rank": bench.get("my_rank"),
            "archetype": (p["advice"].get("archetype") or {}).get("name"), "top_rule": (p["advice"]["rules"][0]["short"] if p["advice"]["rules"] else None)}


def radar_file(map_name, out_dir):
    path = os.path.join(out_dir, "radars", f"{map_name}.json")
    if os.path.exists(path):
        return True
    try:
        cfg = mapdata.get(map_name)
    except KeyError:
        return False
    levels, boxes = {}, []
    for lv in cfg["levels"]:
        p = lv.get("image_path")
        if p and os.path.exists(p):
            levels[lv["key"]] = radar_uri(p)
            boxes.append(Image.open(p).convert("RGBA").resize((1024, 1024)).getbbox())
    if not boxes:
        return False
    x0, y0 = max(min(b[0] for b in boxes) - 16, 0), max(min(b[1] for b in boxes) - 16, 0)
    x1, y1 = min(max(b[2] for b in boxes) + 16, 1024), min(max(b[3] for b in boxes) + 16, 1024)
    config.write_json(path, {"levels": levels, "viewbox": [x0, y0, x1 - x0, y1 - y0]})
    return True


def write_player(sid, out_dir=SITE):
    p = player_data(str(sid))
    if not p:
        return None
    # atomic: the page may be loading this profile while a job rewrites it
    config.write_json(os.path.join(out_dir, "players", f"{sid}.json"), p, separators=(",", ":"))
    for m in index_entry(p)["maps"]:
        radar_file(m, out_dir)
    rp = os.path.join(config.player_dir(sid), "replays")
    if os.path.exists(rp):  # 2D replays, served next to the profile
        dst = os.path.join(out_dir, "replays", str(sid))
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(rp):
            s, d = os.path.join(rp, f), os.path.join(dst, f)
            try:   # already there (same size and date): not copied again (16/10: 82 replays, 37 MB, at each page write)
                a, b = os.stat(s), os.stat(d)
                if a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime):
                    continue
            except OSError:
                pass
            shutil.copy2(s, d)
    return index_entry(p)


def write_teams(out_dir=SITE):
    """Team plans (out/teams) next to the profiles, with their index."""
    from wily.coaching import team
    dst = os.path.join(out_dir, "teams")
    os.makedirs(dst, exist_ok=True)
    keep = set()
    if os.path.exists(team.TEAMS):
        for f in os.listdir(team.TEAMS):
            if f.endswith(".json"):
                config.write_json(os.path.join(dst, f), config.read_json(os.path.join(team.TEAMS, f)))
                keep.add(f)
    for f in os.listdir(dst):
        if f.endswith(".json") and f != "index.json" and f not in keep:
            os.remove(os.path.join(dst, f))
    config.write_json(os.path.join(dst, "index.json"), team.index())


def _voice_keys():
    """The lines the coach says out loud (tv() in the page), as tools/i18n_extract.py listed them."""
    src = config.read_json(os.path.join(config.HERE, "resources", "i18n", "_source.json"), {}) or {}
    return [k for k, v in src.items() if isinstance(v, dict) and v.get("voice")]


def shell_html(index, local=False, lang=None, relang=False):
    s = config.settings()
    from wily.core import i18n
    lang = lang if lang in i18n.LANGS else i18n.current()
    # a player's first launch (05/10): the Steam account signed in on this PC until they analyze or sign in
    own = str(s.get("own_steamid") or (config.logged_in_account()[0] if config.role() == "client" else None) or "")
    from wily.sharing import usage
    u = usage.settings()
    data = {"index": index, "own": own if own and own != "None" else None, "role": config.role(),
            "setup": bool(s.get("setup_done")) or config.role() != "client",   # the setup guide was done or skipped (08/10)
            "usage": {"on": usage.enabled(), "noticed": usage.noticed()},
            "default": own if any(e["steamid"] == own for e in index) else (index[0]["steamid"] if index else None),
            "local": local, "generated": dt.datetime.now().isoformat(timespec="minutes"),
            # 12/10, a Linux tester could not find the training server's switch (Settings > Game detection): Prepare shows it
            "linux": config.LINUX, "linux_training": bool(s.get("linux_training")),
            "recette": bool(s.get("recette")),   # 29/10: his own recette (every drill the latest tests failed), his setting only
            # 13/10, the app in the player's language: its catalog, the coach's spoken lines in every language, the choice
            "lang": lang, "L": i18n.page_catalog(lang), "LV": i18n.voice_catalogs(_voice_keys()), "langs": i18n.LANGS,
            "ui_lang": s.get("ui_lang") if s.get("ui_lang") in i18n.LANGS else "auto",
            "relang": bool(relang)}   # your analysis is being written again in the page's language (serve.relang_own)
    return open(TEMPLATE, encoding="utf-8").read().replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def build(out_dir=SITE, local=False, players=None):
    os.makedirs(out_dir, exist_ok=True)
    index = []
    ids = players or (os.listdir(config.PLAYERS) if os.path.exists(config.PLAYERS) else [])
    for sid in ids:
        e = write_player(sid, out_dir)
        if e:
            index.append(e)
    index.sort(key=lambda e: (e["steamid"] != str(config.settings().get("own_steamid")), -e["n"], e["name"].lower()))
    config.write_json(os.path.join(out_dir, "index.json"), index)
    try:
        from wily.base import proref
        config.write_json(os.path.join(out_dir, "pros.json"), proref.pro_profiles())
    except Exception as e:
        print("pros.json:", e)
    try:
        write_teams(out_dir)
    except Exception as e:
        print("teams:", e)
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(shell_html(index, local))
    return index


def main(out_path=None):
    index = build()
    shutil.copy(os.path.join(SITE, "index.html"), out_path or os.path.join(config.OUT, "app.html"))
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(SITE) for f in fs)
    print(f"{SITE}: {len(index)} players, {size // 1024 // 1024} MB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
