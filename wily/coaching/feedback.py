"""How it went, asked at the right moment (07/10, the user: "pour encourager les feedback, à chaque fin d'entraînement
et à chaque fin de session live avec Wily, engage une popup de feedback en expliquant que c'est une alpha fermée"), and
!report in the training server's chat ("fais une commande report sur le serveur d'entraînement aussi").

- pending(): the last warm-up that ended (the plugin's "end" line in coach/results.jsonl) or the last match played with
  the In game page open (out/live/<day>.jsonl: its lines while the page shows a match), once each, never during a match;
- send(): a player's answer goes to the author like a bug report (bugreport.send, kind "feedback"); on the author's own
  PC it is filed with the players' reports (out/reports, Settings > Bug reports);
- watch(): the training server's !report notes (coach/reports.jsonl), sent the same way with the drill and the spot.
"""
import glob
import json
import os
import secrets
import time

from wily.core import config
from wily.core.i18n import num, tr, trn

STATE_F = os.path.join(config.OUT, "feedback_state.json")
FRESH = 3 * 3600   # a warm-up or a match older than that: not asked any more


def enabled():
    return config.settings().get("feedback_prompts", True) is not False


def _state():
    return config.read_json(STATE_F, {}) or {}


def _mark(key):
    s = _state()
    s["asked"] = (s.get("asked") or [])[-300:] + [key]
    config.write_json(STATE_F, s)


def _tail(path, n=400):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.readlines()[-n:]
    except OSError:
        return []


def last_training():
    """The last warm-up that ended: its id, points, drills done and passed, when."""
    from wily.training import replay
    for ln in reversed(_tail(os.path.join(replay.COACH, "results.jsonl"))):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("end") and r.get("session"):
            return {"id": f"training:{r['session']}", "session": r["session"], "points": int(r.get("points") or 0),
                    "drills": int(r.get("drills") or 0), "ok": int(r.get("ok") or 0), "t": float(r.get("t") or 0), "early": bool(r.get("early"))}
    return None


def last_live():
    """The last match the In game page showed (its lines without a 10 min gap, one map): map, rounds, score, when."""
    rows = []
    for f in sorted(glob.glob(os.path.join(config.OUT, "live", "*.jsonl")))[-2:]:
        for ln in _tail(f, 3000):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("ts") and r.get("map"):
                rows.append(r)
    if not rows:
        return None
    rows.sort(key=lambda r: r["ts"])
    run = [rows[-1]]
    for r in reversed(rows[:-1]):
        if r["map"] != run[-1]["map"] or run[-1]["ts"] - r["ts"] > 600:
            break
        run.append(r)
    run.reverse()
    rounds = max(int(r.get("round") or 0) for r in run)
    sc = next((r.get("score") for r in reversed(run) if r.get("score")), None)
    return {"id": f"live:{run[0]['map']}:{int(run[0]['ts'])}", "map": run[0]["map"], "first": run[0]["ts"], "last": run[-1]["ts"],
            "rounds": rounds, "score": sc, "side": run[-1].get("side")}


def _mapname(m):
    return " ".join(w.capitalize() for w in str(m or "").replace("de_", "").replace("cs_", "").split("_"))


def pending():
    """What to ask now: {} or {kind, id, title, summary}. A match only once it is over (no news for 2 min, no match now)."""
    if not enabled():
        return {}
    asked = set(_state().get("asked") or [])
    now = time.time()
    lt = last_training()
    if lt and lt["id"] not in asked and now - lt["t"] < FRESH and lt["drills"] >= 3:
        return {"kind": "training", "id": lt["id"], "title": tr("How was this warm-up?"),
                "summary": tr("{a}/{b} drills passed · {p} pts", a=lt["ok"], b=lt["drills"], p=num(lt['points']))}
    lv = last_live()
    if lv and lv["id"] not in asked and lv["rounds"] >= 8 and FRESH > now - lv["last"] > 120 and not config.in_match():
        tr_on = lt and abs(lt["t"] - lv["last"]) < 600   # the training server's own rounds (a warm-up shows in game too)
        if not tr_on:
            sc = f" · {lv['score'][0]}–{lv['score'][1]}" if isinstance(lv.get("score"), list) and len(lv["score"]) == 2 else ""
            return {"kind": "live", "id": lv["id"], "title": tr("How was Wily during this match?"),
                    "summary": f"{_mapname(lv['map'])}{sc} · " + tr("{n} rounds with the In game page", n=lv['rounds'])}
    return {}


def dismiss(key):
    if key:
        _mark(str(key)[:120])
    return {"ok": True}


def _file_here(kind, text, page, rating=None, tags=None):
    """The author's own PC: filed with the players' reports (Settings > Bug reports), no round trip to the site."""
    from wily.sharing import contributions
    os.makedirs(contributions.REPORTS, exist_ok=True)
    rid = time.strftime("%Y%m%d%H%M%S", time.gmtime()) + "-" + secrets.token_hex(6)
    v = config.read_json(os.path.join(config.HERE, "VERSION.json"), {}) or {}
    config.write_json(os.path.join(contributions.REPORTS, rid + ".json"),
                      {"id": rid, "at": int(time.time()), "kind": kind, "install": "this PC", "app": v.get("app") or "", "text": text,
                       "expected": "", "email": "", "page": page[:120], "diag": None, "rating": rating, "tags": tags or []})
    return {"ok": True, "id": rid}


def session_recap(session):
    """A warm-up's drills as the game's end-of-session recap numbers them (13/10, a tester: "22 boost didn't work",
    which nobody could find): each drill once, in the order played, with its last try; its title and weapons from the
    session file. [{n, id, title, ok, outcome, detail, tries, points, weapons}]"""
    from wily.training import replay
    rows = []
    for ln in _tail(os.path.join(replay.COACH, "results.jsonl"), 4000):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("session") != session or r.get("end") or not r.get("drill"):
            continue
        last = {"ok": bool(r.get("ok")), "outcome": r.get("outcome") or "", "detail": r.get("detail") or "",
                "tries": int(r.get("try") or 1), "points": int(r.get("points") or 0)}
        if rows and rows[-1]["id"] == r["drill"] and last["tries"] > 1:   # a try again of the same drill
            rows[-1].update(last)
        else:
            rows.append(dict(n=len(rows) + 1, id=r["drill"], title="", weapons=[], **last))
    try:
        S = json.load(open(os.path.join(replay.COACH, "sessions", f"{session}.json"), encoding="utf-8"))
        D = {d.get("id"): d for b in S.get("blocks") or [] for d in b.get("drills") or []}
    except (OSError, ValueError):
        D = {}
    for x in rows:
        d = D.get(x["id"]) or {}
        x["title"] = str(d.get("title") or "")
        x["weapons"] = [str(w).replace("weapon_", "") for w in d.get("weapons") or [] if "knife" not in str(w)]
    return rows


def _recap_text(session):
    """The recap in a report (English, for the developer; the titles as the player saw them)."""
    rows = session_recap(session)
    if not rows:
        return ""
    out = ["Drills, numbered as in the game's end-of-session recap:"]
    for x in rows:
        out.append(f"{x['n']}. {'OK' if x['ok'] else 'X '} {x['title'] or '?'} · {x['id']} · {x['outcome']}"
                   + (f" ({x['detail']})" if x["detail"] else "") + (f" · try {x['tries']}" if x["tries"] > 1 else "")
                   + (f" · {'/'.join(x['weapons'])}" if x["weapons"] else ""))
    s = "\n".join(out)
    return s if len(s) <= 7000 else s[:6990] + "\n…"


def send(kind, key, rating=None, tags=None, text="", summary=""):
    """A popup's answer. -> {"ok": True, ...} or {"ok": False, "queued": True} (kept, sent later)."""
    text = (text or "").strip()[:6000]
    tags = [str(t)[:40] for t in (tags or [])][:12]
    rating = int(rating) if str(rating or "").isdigit() and 1 <= int(rating) <= 5 else None
    if not text and not rating and not tags:
        raise ValueError(tr("A rating, a tag or a few words first."))
    what = {"training": "warm-up", "live": "match with the In game page"}.get(kind, kind)
    recap = ""
    if kind == "training" and str(key).startswith("training:"):   # the session's drills, and its numbers in English
        session = str(key).split(":", 1)[1]
        lt = last_training()
        if lt and lt["session"] == session:
            summary = f"{lt['ok']}/{lt['drills']} drills passed · {lt['points']:,} pts"
        try:
            recap = _recap_text(session)
        except Exception as e:
            recap = f"(drill list unavailable: {e})"
    head = f"[feedback · {what}" + (f" · {rating}/5" if rating else "") + "]" + (f" {summary}" if summary else "")
    body = head + (f"\nTags: {', '.join(tags)}" if tags else "") + (f"\n{text}" if text else "") + (f"\n\n{recap}" if recap else "")
    page = f"feedback · {kind} · {key}"
    if config.role() == "client":
        from wily.sharing import bugreport
        res = bugreport.send(body, "", "", False, page, None, "feedback")
    else:
        res = _file_here("feedback", body, page, rating, tags)
    _mark(str(key)[:120])
    return res


# ---------------------------------------------------------------- !report in the training server's chat

def _report_file():
    from wily.training import replay
    return os.path.join(replay.COACH, "reports.jsonl")


def send_training_reports():
    """The !report notes written since last time: sent (a player's) or filed here (the author's). -> how many."""
    f = _report_file()
    s = _state()
    try:
        size = os.path.getsize(f)
    except OSError:
        return 0
    if "report_off" not in s:   # a new installation (13/10: four reinstalls on one PC each sent the training server's
        s["report_off"] = size  # old notes again, the server being the same): only the notes written from now on
        config.write_json(STATE_F, s)
        return 0
    off = int(s.get("report_off") or 0)
    if size < off:   # the file started over
        off = 0
    if size == off:
        return 0
    with open(f, "rb") as fh:
        fh.seek(off)
        chunk = fh.read()
    end = chunk.rfind(b"\n") + 1
    n = 0
    for ln in chunk[:end].decode("utf-8", "replace").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        text = str(r.get("text") or "").strip()
        if not text:
            continue
        where = " · ".join(str(x) for x in (_mapname(r.get("map")), r.get("drill_title") or r.get("drill"), r.get("phase")) if x)
        pos = r.get("pos")
        body = f"[in-game !report · training] {where}\n{text}" + (f"\n(at setpos {' '.join(str(round(float(v), 1)) for v in pos[:3])})" if pos else "")
        page = f"training !report · {r.get('session') or '?'} · {r.get('drill') or '?'}"
        try:
            if config.role() == "client":
                from wily.sharing import bugreport
                bugreport.send(body, "", "", False, page, None, "bug")
            else:
                _file_here("bug", body, page)
            n += 1
        except Exception as e:
            print("training !report:", e, flush=True)
    s = _state()
    s["report_off"] = off + end
    config.write_json(STATE_F, s)
    return n


def watch(every=20):
    """The training server's !report notes, sent within half a minute (a thread of the app)."""
    while True:
        try:
            send_training_reports()
        except Exception as e:
            print("feedback watch:", e, flush=True)
        time.sleep(every)
