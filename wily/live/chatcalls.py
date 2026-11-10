"""Your team's plan with one key (06/10, the user: "un bind pour A, un bind pour mid, un bind pour B, un bind pour rush,
un bind pour slow, un bind pour contrôle map"): numpad 1, 2, 3 say the direction (A, mid, B), 4, 5, 6 the tempo (rush,
slow, map control) in the team chat, only what you pressed ("Rush A", 07/10: "si la touche veut dire A tu ne peux pas
écrire A from Ramp"), and tell Wily: Live then shows the way in that wins most, its odds and its grenades, with a ping. On CT the same keys only tell Wily (1-2-3 where you play, 4-5-6 what the
Ts do): nothing in the chat.
One line for the two keys (09/10, the user: "attends 6 secondes savoir si j'ai appuyé sur 4, 5 ou 6 avant d'écrire, comme
ça si je mets B Rush ça met Rush B et ça ne met pas juste B"; "Map control mid", not "Map control, then mid"): CS2 only
writes when a key is pressed, so the first key of the pair says nothing (Wily hears it) and the second says both
("Rush B", whichever came first); a key left alone 6 s is said alone on its next press.

CS2 runs a config file each time a key bound to `exec` is pressed, and reads it from the disk again: the app rewrites
small files in CS2's cfg folder (coach_path1.cfg to coach_path3.cfg for the ways, kept from the time they said three
paths, coach_rush.cfg, coach_slow.cfg, coach_ctrl.cfg) whenever the page's plan changes, and the keys run them. Nothing is sent by the app itself: you press the key. One time only, in CS2's
console: `exec wily_bind` (the binds then stay in your CS2 settings; `exec coach_binds`, its name until 20/10, still runs it).

The text written is cleaned (no quote, semicolon or line break, plain characters, 120 at most): a file can only ever
say one line in the team chat (10/10: no more chat wheel "Go A" after it, two lines a key was spam), and define CS2
aliases that only say such a line. Never another command.

Hostage maps (cs_*, 10/10): the keys follow the role, not the side. The CTs attack: as the T of a bomb map, numpad 1, 2,
3 are the ways toward the hostages (left, middle, right from the CT spawn, named by hostage.way_names: "Rush Side Hall")
with the same two-key line; the Ts defend: as the CT of a bomb map, Wily only. Numpad 7 / 9 = the 1st / 2nd hostage
taken (Wily only, both sides: gsi.set_site_key)."""
import os
import re
import time

from wily.live import gsi

KEYS = {1: "KP_1", 2: "KP_2", 3: "KP_3"}   # numpad 1, 2, 3: CS2's names (the physical key, num lock on or off); KP_END etc. were CS:GO's
WAYS = {1: "A", 2: "MID", 3: "B"}          # what numpad 1, 2, 3 say since 06/10 (they were paths 1, 2, 3 of the page)
TEMPO = {"rush": "KP_4", "slow": "KP_5", "ctrl": "KP_6"}   # numpad 4, 5, 6: rush, slow, map control
TEMPO_STATE = {"rush": "rush", "slow": "slow", "ctrl": "control"}
FOCUS_OFF = "KP_MINUS"   # numpad minus: drop the focus on a path
EXTRA = {"eco": "KP_DEL", "sit": "KP_0"}   # numpad ".": the economy plan; numpad 0: the situation, recent and global
SITE_KEYS = {"A": "KP_7", "B": "KP_9"}   # numpad 7 / 9: A / B (CT: the site you play; once planted, both sides: the bomb's site)
TEAM_KEY = "KP_SLASH"   # numpad /: your team agreed to be recorded (what you hear, for this match: 04/10)
# keys the coach no longer uses, unbound by exec wily_bind while they still run the coach's file: numpad *, the team
# key of 04/10 21:40 (already used for something else of yours); numpad +, the lineup photo session's (06/10, gone 16/10)
OLD_KEYS = {"KP_MULTIPLY": "exec coach_team", "KP_PLUS": "exec coach_lineup"}
BINDS = "wily_bind.cfg"   # 20/10, the user: "change exec coach_binds en exec wily_bind"
OLD_BINDS = "coach_binds.cfg"   # its name before: only runs it (a launch option pasted before 20/10, "+exec coach_binds")
_LAST = {}
SAY_DIR = {"A": "A", "MID": "mid", "B": "B"}
SAY_TEMPO = {"rush": "Rush", "slow": "Slow", "control": "Map control"}
ALONE = 6.0   # s: a way without its tempo (or the reverse) is said alone on its next press after this


def combo(d, tempo, mp):
    """The team chat's line for a way and a tempo: "Rush B", "Slow mid", "Map control A" (Nuke's mid: outside)."""
    w = ""
    if str(mp or "").startswith("cs_") and d in WAYS.values():   # hostage maps: the way's name (key 1, 2, 3)
        try:
            from wily.insights import hostage
            w = hostage.way_names(mp).get({v: k for k, v in WAYS.items()}[d], "")
        except Exception:
            w = ""
        w = w or {"A": "left", "MID": "middle", "B": "right"}[d]
    elif d == "MID":
        try:
            from wily.insights import tdirs
            w = (tdirs.mid_name(mp) or "Mid").lower()
        except Exception:
            w = "mid"
    elif d:
        w = SAY_DIR.get(d, "")
    if not tempo:
        return w[:1].upper() + w[1:]
    return f"{SAY_TEMPO.get(tempo, '')} {w}".strip()


def t_lines(now=None):
    """The attack (T on a bomb map, CT on a hostage map): the round's plan as the keys' files need it (gsi: the way and
    the tempo pressed this round), or None for the defense (Wily only)."""
    with gsi.LOCK:   # read 10 times a second: only what it needs
        s = {k: gsi.STATE.get(k) for k in ("map", "side", "round", "round_phase", "tdir")}
    mp, rnd = s.get("map") or "", s.get("round")
    if not mp or not rnd or s.get("side") != ("CT" if mp.startswith("cs_") else "T"):
        return None
    kr = rnd + 1 if s.get("round_phase") == "over" else rnd   # a key after the round's end counts for the next one
    t = s.get("tdir") or {}
    if t.get("round") != kr:
        t = {}
    alone = (now or time.time()) - (t.get("t") or 0) >= ALONE
    return {"map": mp, "round": kr, "dir": t.get("dir"), "tempo": t.get("tempo"), "alone": alone,
            "dir_key": t.get("dir_src", t.get("src")) == "key", "tempo_key": t.get("tempo_src", t.get("src")) == "key"}


# The pair is put together by CS2 itself (10/10, the user: two keys pressed fast wrote nothing: the second key's file was
# read before the app had seen the first in the console): each way key defines what the three tempo keys say this round
# ("Rush A"...), each tempo key what the three way keys say, as CS2 aliases named after the round (an older round's never
# answer), and calls the one the other key defined: the first key of the pair says nothing, the second says both, however
# fast. A part said to Wily (not a key) is not in CS2: the other key's file then says the line itself.
TK = {"rush": "rush", "slow": "slow", "ctrl": "control"}


def _alias(name, line):
    return f'alias {name} "say_team {line}"' if line else f'alias {name} ""'


NL = chr(10)


def t_bodies(tl):
    """The six files' text for T on a bomb map, and numpad minus's (it forgets the round's pair)."""
    mp, n, d, tempo = tl["map"], tl["round"], tl["dir"], tl["tempo"]
    out = {}
    for i, x in WAYS.items():
        lines = []
        if tempo and not tl["tempo_key"]:
            lines.append(f'say_team "{clean(combo(x, tempo, mp))}"')
        else:
            lines.append(f"coach_t{x}_r{n}")
            if not tempo and d == x and tl["alone"]:   # alone 6 s: said alone on its next press
                lines.append(f'say_team "{clean(combo(x, None, mp))}"')
        lines += [_alias(f"coach_k{k}_r{n}", clean(combo(x, v, mp))) for k, v in TK.items()]
        out[f"coach_path{i}"] = NL.join(lines) + NL
    for k, v in TK.items():
        lines = []
        if d and not tl["dir_key"]:
            lines.append(f'say_team "{clean(combo(d, v, mp))}"')
        else:
            lines.append(f"coach_k{k}_r{n}")
            if not d and tempo == v and tl["alone"]:
                lines.append(f'say_team "{clean(combo(None, v, mp))}"')
        lines += [_alias(f"coach_t{x}_r{n}", clean(combo(x, v, mp))) for x in WAYS.values()]
        out[f"coach_{k}"] = NL.join(lines) + NL
    out["coach_focus0"] = NL.join([_alias(f"coach_k{k}_r{n}", "") for k in TK] + [_alias(f"coach_t{x}_r{n}", "") for x in WAYS.values()]
                                    + ['echo "Coach CS2: focus off"']) + NL
    return out
WHEEL = {"A": 'playerchatwheel CW.GoA "#Chatwheel_aplan"', "B": 'playerchatwheel CW.GoB "#Chatwheel_bplan"'}   # the chat wheel's Go A / Go B


def clean(t):
    t = str(t or "").replace("·", "-").replace("→", ">").replace("’", "'").replace("⚡", "rush ")
    t = re.sub(r'["\\;\r\n\t/]', " ", t)
    t = "".join(ch for ch in t if 32 <= ord(ch) < 127)
    return re.sub(r"\s+", " ", t).strip()[:120]


def _keys_file():
    """Your CS2 key settings (where the binds stay)."""
    from wily.core import config
    own = config.logged_in_account()[0]
    return os.path.join(config.steam_path(), "userdata", str(int(own) - 76561197960265728), "730", "local", "cfg", "cs2_user_keys_0_slot0.vcfg")


def _stale():
    """Keys the coach no longer uses that your CS2 settings still bind to its files."""
    try:
        t = open(_keys_file(), encoding="utf-8", errors="replace").read()
    except Exception:
        return []
    return [k for k, cmd in OLD_KEYS.items() if re.search(rf'"{k}"\s+"{re.escape(cmd)}"', t)]


def binds_text():
    lines = ["// Wily: numpad 1, 2, 3 = A, mid, B; 4, 5, 6 = rush, slow, map control (T: said in the team chat too)"]
    lines += [f'unbind "{k}"' for k in _stale()]
    lines += [f'bind "{k}" "exec coach_path{i}"' for i, k in KEYS.items()]
    lines += [f'bind "{k}" "exec coach_{name}"' for name, k in TEMPO.items()]
    lines += [f'bind "{FOCUS_OFF}" "exec coach_focus0"']
    lines += [f'bind "{k}" "exec coach_{name}"' for name, k in EXTRA.items()]
    lines += [f'bind "{k}" "exec coach_site{site}"' for site, k in SITE_KEYS.items()]
    lines += [f'bind "{TEAM_KEY}" "exec coach_team"']
    # F5 rethrows your last grenade (20/10, the user: "il faudrait que la touche F5 fasse re-throw le dernier stuff envoyé
    # en mode sandbox"): the game's own command where you host the game (your offline practice), the training server's
    # where you join it (it refuses the game's from a player: "not marked FCVAR_CLIENT_CAN_EXECUTE")
    lines += ['bind "F5" "sv_rethrow_last_grenade; css_rt"']
    lines += ['echo "Wily: numpad 1-2-3 = A / mid / B, 4-5-6 = rush / slow / map control, minus drops them, / your team agreed to be recorded"']
    return "\n".join(lines) + "\n"


def write(paths, extra=None, tempo=None):
    """paths: [{"rank": 1, "text": "...", "site": "A"}, ...] from the page (rank 1, 2, 3: numpad 1, 2, 3: the ways A, mid,
    B since 06/10); a rank without a text only prints a note in the console.
    extra: {"eco": "...", "sit": "..."}, the economy plan and the situation, for numpad "." and 0 (one line each).
    tempo: {"rush": "...", "slow": "...", "ctrl": "..."}, the lines of numpad 4, 5, 6 (empty: Wily only)."""
    d = gsi.cfg_dir()
    if not d:
        return False
    _binds_file(d)
    ff = os.path.join(d, "coach_focus0.cfg")
    if not os.path.exists(ff):
        open(ff, "w", encoding="utf-8").write('echo "Coach CS2: focus off"\n')
    _site_files(d)
    by, site = {}, {}
    for p in paths or []:
        try:
            r = int(p.get("rank"))
        except (TypeError, ValueError, AttributeError):
            continue
        t = clean(p.get("text"))
        if r in KEYS and t:
            by[r] = t
            if p.get("site") in WHEEL:
                site[r] = p["site"]
    tl = t_lines()
    if tl:   # T on a bomb map: the way and the tempo in one line, from the round's plan (09/10)
        _t_files(d, tl)
    for i in KEYS:
        if tl:
            break
        body = f'say_team "{by[i]}"\n' if i in by else f'echo "Wily: {WAYS[i]}"\n'   # one line (10/10: no chat wheel order after it)
        if _LAST.get(i) != body:
            open(os.path.join(d, f"coach_path{i}.cfg"), "w", encoding="utf-8").write(body)
            _LAST[i] = body
    for name in EXTRA:
        t = clean((extra or {}).get(name)) if isinstance(extra, dict) else ""
        body = f'say_team "{t}"\n' if t else f'echo "Coach CS2: nothing to say for this key now"\n'
        if _LAST.get(name) != body:
            open(os.path.join(d, f"coach_{name}.cfg"), "w", encoding="utf-8").write(body)
            _LAST[name] = body
    for name in TEMPO:   # always a file: the key must reach Wily even with nothing to say (its line in the console)
        if tl:
            break
        t = clean((tempo or {}).get(name)) if isinstance(tempo, dict) else ""
        body = f'say_team "{t}"\n' if t else f'echo "Wily: {TEMPO_STATE[name]}"\n'
        f = os.path.join(d, f"coach_{name}.cfg")
        if _LAST.get(name) != body or not os.path.exists(f):
            open(f, "w", encoding="utf-8").write(body)
            _LAST[name] = body
    return True


def _t_files(d, tl):
    """Numpad 1-6's files (and minus's) for T on a bomb map: one line in the team chat for the pair, nothing else (10/10:
    CS2's chat wheel Go A / Go B doubled every line, "ça spam")."""
    for name, body in t_bodies(tl).items():
        f = os.path.join(d, f"{name}.cfg")
        if _LAST.get(name) != body or not os.path.exists(f):
            open(f, "w", encoding="utf-8").write(body)
            _LAST[name] = body


def refresh():
    """Numpad 1-6's lines again from the round's plan (T on a bomb map): right after a key, and as time passes (a key
    alone for 6 s)."""
    d = gsi.cfg_dir()
    tl = t_lines() if d else None
    if tl:
        _t_files(d, tl)


def _site_files(d):
    tf = os.path.join(d, "coach_team.cfg")   # numpad /: only a line in the console, the app reads it
    if not os.path.exists(tf):
        open(tf, "w", encoding="utf-8").write('echo "Coach CS2: team agreed"\n')
    for site in SITE_KEYS:   # only a line in the console: the app reads it (CT: your site; planted: the bomb's site)
        sf = os.path.join(d, f"coach_site{site}.cfg")
        if not os.path.exists(sf):
            open(sf, "w", encoding="utf-8").write(f'echo "Coach CS2: {site}"\n')


def bound():
    """True when numpad 1 runs coach_path1 in your CS2 key settings (the binds were set once)."""
    try:
        f = _keys_file()
        return "exec coach_path1" in open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        return False


def bound_site():
    """True when numpad 7 runs coach_siteA in your CS2 key settings (exec wily_bind once more after this update)."""
    try:
        f = _keys_file()
        return "exec coach_siteA" in open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        return False


def bound_tempo():
    """True when numpad 4 runs coach_rush (exec wily_bind once more after the 06/10 update)."""
    try:
        return "exec coach_rush" in open(_keys_file(), encoding="utf-8", errors="replace").read()
    except Exception:
        return False


def bound_rt():
    """True when F5 runs the training server's rethrow (exec wily_bind once more after the 20/10 update)."""
    try:
        return "css_rt" in open(_keys_file(), encoding="utf-8", errors="replace").read()
    except Exception:
        return False


def bound_focus():
    try:
        f = _keys_file()
        return "exec coach_focus0" in open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        return False


def console_file():
    d = gsi.cfg_dir()
    return os.path.join(os.path.dirname(d), "console.log") if d else None


KEY_RE = re.compile(r"execing coach_(?:path([123])|focus0|site([AB])|(team)|(rush|slow|ctrl))\b")


def watch():
    """Reads the new lines CS2 writes to its console log (from now on, never the past): a numpad key of the paths sets
    the focus on that path, numpad minus drops it. The file starts over with each CS2 session: read from its start."""
    pos, path = None, None
    while True:
        try:
            path = path or console_file()
            if not path or not os.path.exists(path):
                time.sleep(5)
                path = None
                continue
            size = os.path.getsize(path)
            if pos is None or size < pos:
                pos = size if pos is None else 0
            if size > pos:
                with open(path, "rb") as fh:
                    fh.seek(pos)
                    chunk = fh.read(size - pos)
                pos = size
                for line in chunk.decode("utf-8", "replace").splitlines():
                    m = KEY_RE.search(line)
                    if m and m.group(3):   # numpad /: your team agreed, what you hear is recorded too (this match)
                        try:
                            from wily.live import voice
                            voice.TEAM.start("your team agreed: numpad / in game", gsi.state().get("map"))
                        except Exception as e:
                            print("team sound:", e, flush=True)
                    elif m and m.group(2):
                        gsi.set_site_key(m.group(2))
                    elif m and m.group(4):   # numpad 4-5-6: the tempo (pressed again: said again, it stays; minus drops it)
                        gsi.set_tdir(TEMPO_STATE[m.group(4)], toggle=False)
                    elif m and m.group(1):   # numpad 1-2-3: the way (A, mid, B); hostage maps keep their routes 1-2-3
                        if gsi.wily_answer(WAYS[int(m.group(1))]):   # Wily asked "from A or B?": the key answers
                            continue
                        gsi.set_focus(int(m.group(1)))
                        gsi.set_tdir(WAYS[int(m.group(1))])
                    elif m:   # numpad minus: no focus, no plan
                        gsi.set_focus(0)
                        gsi.drop_tdir()
            refresh()   # the two keys' line (09/10): ready before the second key is pressed
        except Exception:
            pass
        time.sleep(0.1)


def _binds_file(d):
    """wily_bind.cfg up to date, and coach_binds.cfg, its old name, running it."""
    for f, text in ((BINDS, binds_text()), (OLD_BINDS, "exec wily_bind\n")):
        p = os.path.join(d, f)
        if not os.path.exists(p) or open(p, encoding="utf-8").read() != text:
            open(p, "w", encoding="utf-8").write(text)


def status():
    d = gsi.cfg_dir()
    if d:
        _binds_file(d)
        _site_files(d)
    cf = console_file()
    fresh = bool(cf and os.path.exists(cf) and time.time() - os.path.getmtime(cf) < 2 * 86400)
    return {"cfg": bool(d), "binds_file": bool(d and os.path.exists(os.path.join(d, BINDS))), "bound": bound(), "focus_bound": bound_focus(),
            "site_bound": bound_site(), "tempo_bound": bound_tempo(), "rt_bound": bound_rt(),
            "console": fresh}
