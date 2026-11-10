"""Steam connection for the local app.

- Sign in through Steam (OpenID 2.0): Steam's own page confirms who you are; the app never sees a password.
- Local Steam data of this PC (no login): CS2 playtime of the accounts that used this PC.
- The match-history authentication code (created by the player on Steam's site): every new match is found
  automatically (GetNextMatchSharingCode), even weeks later, and Steam friends help detect who you queue with.
  Steam asks for a Steam Web API key too: the player's own when they gave one, else Wily's site asks Steam with the
  coach's key (web/api/steam.php, 08/10: one code to paste instead of a key to create on a developer page).

Keys and codes stay in out/settings.json (not versioned). They go to Steam's official API, or, without a key of your
own, through Wily's site, which passes the request to Steam and keeps nothing.
"""
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from wily.core import config

OPENID = "https://steamcommunity.com/openid/login"
API = "https://api.steampowered.com"
STEAM64 = 76561197960265728
KEY_URL = "https://steamcommunity.com/dev/apikey"
AUTH_URL = "https://help.steampowered.com/fr/wizard/HelpWithGameIssue/?appid=730&issueid=128"
KEY_RE = re.compile(r"^[0-9A-Fa-f]{32}$")
AUTH_RE = re.compile(r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{5}-[A-Za-z0-9]{4}$")
CODE_RE = re.compile(r"^CSGO(-[A-Za-z0-9]{5}){5}$")
FRIENDS_DIR = os.path.join(config.OUT, "steam")
RELAY = "https://wily.valentingassend.com/api/steam.php"


# ---------- sign in through Steam (OpenID 2.0) ----------
def login_url(return_to, realm):
    q = {"openid.ns": "http://specs.openid.net/auth/2.0", "openid.mode": "checkid_setup",
         "openid.return_to": return_to, "openid.realm": realm,
         "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
         "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select"}
    return OPENID + "?" + urllib.parse.urlencode(q)


def verify(params, return_to):
    """Ask Steam to confirm the signed answer it sent back. -> SteamID64 or None."""
    if params.get("openid.mode") != "id_res" or not str(params.get("openid.return_to", "")).startswith(return_to):
        return None
    m = re.fullmatch(r"https?://steamcommunity\.com/openid/id/(7656\d{13})", params.get("openid.claimed_id", ""))
    if not m:
        return None
    data = dict(params, **{"openid.mode": "check_authentication"})
    req = urllib.request.Request(OPENID, data=urllib.parse.urlencode(data).encode(), headers={"User-Agent": "wily-coach"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    return int(m.group(1)) if "is_valid:true" in body else None


def save_login(sid, name=None):
    s = config.settings()
    s["steam_login"] = {"steamid": str(sid), "name": name, "time": dt.datetime.now().isoformat(timespec="minutes")}
    s["own_steamid"] = int(sid)
    p = s.setdefault("players", {}).setdefault(str(sid), {})
    if name:
        p["name"] = name
    config.save_settings(s)


# ---------- local Steam data (this PC) ----------
def local_playtime(sid):
    """CS2 playtime recorded by the Steam client of this PC for this account (minutes -> hours)."""
    try:
        acc = int(sid) - STEAM64
        f = os.path.join(config.steam_path(), "userdata", str(acc), "config", "localconfig.vdf")
        txt = open(f, encoding="utf-8", errors="replace").read()
    except (OSError, ValueError):
        return None
    for m in re.finditer(r'"730"\s*\{', txt):
        # keep only the keys at the first level of the "730" block (it can contain nested blocks)
        depth, i, top = 1, m.end(), []
        while depth and i < len(txt):
            c = txt[i]
            depth += (c == "{") - (c == "}")
            if depth == 1 and c not in "{}":
                top.append(c)
            i += 1
        vals = dict(re.findall(r'"(LastPlayed|Playtime2wks|Playtime)"\s*"(\d+)"', "".join(top)))
        if "Playtime" in vals:
            last = int(vals.get("LastPlayed", 0) or 0)
            return {"total_h": round(int(vals["Playtime"]) / 60), "two_weeks_h": round(int(vals.get("Playtime2wks", 0)) / 60, 1),
                    "last_played": dt.datetime.fromtimestamp(last).isoformat(timespec="minutes") if last else None, "source": "This PC's Steam"}
    return None


# ---------- Steam Web API ----------
class SteamError(Exception):
    pass


def _api(path, **params):
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "wily-coach"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        raise SteamError(f"Steam is not responding ({e})")


def api_key():
    return config.settings().get("steam_api_key")


def _relay(op, **body):
    """Wily's site asks Steam with its own key (web/api/steam.php): for a player with no key of their own. The body is
    sent by POST (never in an address the host logs); the site keeps nothing. -> (Steam's status, the site's answer)."""
    req = urllib.request.Request(RELAY, data=json.dumps(dict(body, op=op)).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "wily-app"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise SteamError("Enough Steam requests through Wily's site for today: try again tomorrow, or add your own Steam API key in Settings.")
        if e.code == 503:
            raise SteamError("Wily's Steam relay isn't available: add your own Steam API key in Settings.")
        raise SteamError(f"Wily's site answered {e.code} to the Steam request.")
    except Exception as e:
        raise SteamError(f"Wily's site is not responding ({e})")
    return int(j.get("status") or 0), j


def check_key(key, sid):
    code, j = _api("ISteamUser/GetPlayerSummaries/v2/", key=key, steamids=sid)
    if code in (401, 403):
        raise SteamError("API key rejected by Steam: check it on steamcommunity.com/dev/apikey.")
    if code != 200 or not j:
        raise SteamError(f"Steam answered {code} to the key check.")
    ps = (j.get("response") or {}).get("players") or []
    return ps[0] if ps else {}


def next_code(key, sid, auth, known):
    """-> next share code, or None when there is no newer match. No key of your own: through Wily's site."""
    if key:
        code, j = _api("ICSGOPlayers_730/GetNextMatchSharingCode/v1", key=key, steamid=sid, steamidkey=auth, knowncode=known)
    else:
        code, r = _relay("next", steamid=str(sid), auth=auth, known=known)
        j = {"result": {"nextcode": r.get("nextcode")}}
    if code == 403:
        raise SteamError("Authentication code rejected: generate it again on Steam's help page.")
    if code == 412:
        raise SteamError("The starting match code is not recognized for this account.")
    if code == 503 or code == 429:
        raise SteamError("Steam is temporarily unavailable, try again in a few minutes.")
    if code not in (200, 202) or j is None:
        raise SteamError(f"Unexpected answer from Steam ({code}).")
    nxt = (j.get("result") or {}).get("nextcode")
    return None if not nxt or nxt == "n/a" else nxt


def owned_cs2(key, sid):
    code, j = _api("IPlayerService/GetOwnedGames/v1/", key=key, steamid=sid, include_played_free_games=1, **{"appids_filter[0]": 730})
    g = next((x for x in ((j or {}).get("response") or {}).get("games", []) if x.get("appid") == 730), None) if code == 200 else None
    if not g:
        return None
    return {"total_h": round(g.get("playtime_forever", 0) / 60), "two_weeks_h": round(g.get("playtime_2weeks", 0) / 60, 1), "source": "API Steam"}


def friends(key, sid, refresh=False):
    """Steam friends (only if the friend list is public). Cached one day."""
    os.makedirs(FRIENDS_DIR, exist_ok=True)
    f = os.path.join(FRIENDS_DIR, f"{sid}_friends.json")
    if os.path.exists(f) and not refresh:
        c = json.load(open(f, encoding="utf-8"))
        if (dt.datetime.now() - dt.datetime.fromisoformat(c["time"])).total_seconds() < 86400:
            return c["friends"]
    if key:
        code, j = _api("ISteamUser/GetFriendList/v1/", key=key, steamid=sid, relationship="friend")
        ids = [int(x["steamid"]) for x in ((j or {}).get("friendslist") or {}).get("friends", [])] if code == 200 else None
    else:   # no key of your own: through Wily's site
        code, r = _relay("friends", steamid=str(sid))
        ids = [int(x) for x in r.get("friends") or [] if str(x).isdigit()] if code == 200 else None
    json.dump({"time": dt.datetime.now().isoformat(timespec="minutes"), "friends": ids}, open(f, "w", encoding="utf-8"))
    return ids


def names(ids):
    """Persona names of SteamIDs (API key needed), remembered in the settings."""
    s = config.settings()
    key = s.get("steam_api_key")
    known = {i: (s.get("players", {}).get(str(i)) or {}).get("name") for i in ids}
    ask = [str(i) for i, n in known.items() if not n]
    if ask:
        try:
            if key:
                code, j = _api("ISteamUser/GetPlayerSummaries/v2/", key=key, steamids=",".join(ask[:100]))
            else:   # no key of your own: through Wily's site
                code, r = _relay("names", steamids=ask[:100])
                j = {"response": {"players": r.get("players") or []}}
        except SteamError:
            code, j = 0, None
        for p in ((j or {}).get("response") or {}).get("players", []) if code == 200 else []:
            known[p["steamid"]] = p.get("personaname")
            s.setdefault("players", {}).setdefault(p["steamid"], {})["name"] = p.get("personaname")
        config.save_settings(s)
    return {str(i): n for i, n in known.items() if n}


def cached_friends(sid):
    f = os.path.join(FRIENDS_DIR, f"{sid}_friends.json")
    return set(json.load(open(f, encoding="utf-8")).get("friends") or []) if os.path.exists(f) else set()


# ---------- credentials ----------
def set_credentials(sid, key=None, auth=None, known=None):
    """Validate and store what the player pasted. Returns the list of what was saved."""
    sid = str(int(sid))
    s = config.settings()
    saved = []
    key = (key or "").strip()
    auth = (auth or "").strip().upper() if auth else ""
    known = (known or "").strip()
    # 10/10, a tester pasted the whole steam://rungame/730/.../+csgo_download_match%20CSGO-... link: the code inside it
    m = re.search(r"CSGO(?:-[A-Za-z0-9]{5}){5}", known)
    known = m.group(0) if m else known
    if key:
        if not KEY_RE.match(key):
            raise SteamError("A Steam API key is 32 characters long (digits and letters A to F).")
        who = check_key(key, sid)
        s["steam_api_key"] = key
        saved.append("API key")
        if who.get("personaname"):
            s.setdefault("players", {}).setdefault(sid, {})["name"] = who["personaname"]
    if auth:
        if not AUTH_RE.match(auth):
            raise SteamError("The authentication code looks like XXXX-XXXXX-XXXX.")
        if known and not CODE_RE.match(known):
            raise SteamError("The match code looks like CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx.")
        k = s.get("steam_api_key")   # none: Wily's site asks Steam (08/10)
        start = known or (s.get("players", {}).get(sid, {}).get("last_code"))
        if not start:
            start = oldest_recent_code(sid)
        if not start:
            raise SteamError("A starting match code is needed: paste the one shown on Steam's help page, or open Steam (CS2 closed) so the coach finds it.")
        next_code(k, sid, auth, start)  # raises if the code or the pair is refused
        p = s.setdefault("players", {}).setdefault(sid, {})
        p["authcode"] = auth
        p["last_code"] = start
        # the starting match itself is fetched too (the walk only finds the ones after it): with the code of your last
        # match, that match at once rather than nothing until the next one
        pend = list(p.get("pending_codes") or [])
        if start not in pend:
            p["pending_codes"] = pend + [start]
        p.setdefault("auto_sync", False)   # the Update button does it when you want
        saved.append("history code")
    config.save_settings(s)
    return saved


def forget(sid):
    """Remove a player's history code. For your own account, the sign-in and the API key go too (a teammate's
    removal keeps your key: it is the one used for everyone)."""
    s = config.settings()
    p = s.get("players", {}).get(str(sid), {})
    for k in ("authcode", "last_code", "auto_sync", "last_sync", "pending_codes"):
        p.pop(k, None)
    own = str(s.get("own_steamid") or "") == str(sid)
    if s.get("steam_login", {}).get("steamid") == str(sid):
        s.pop("steam_login", None)
    if own:
        s.pop("steam_api_key", None)
    config.save_settings(s)
    f = os.path.join(FRIENDS_DIR, f"{sid}_friends.json")
    if os.path.exists(f):
        os.remove(f)


def oldest_recent_code(sid):
    """Share code of the oldest of the last 8 matches given by Valve (Steam running, CS2 closed)."""
    from wily.matches import matchlist
    try:
        ms = matchlist.fetch()
    except Exception:
        return None
    own = config.logged_in_account()[0]
    if own and int(own) != int(sid):
        return None
    ms = [m for m in ms if m.get("sharecode")]
    return min(ms, key=lambda m: m["time"])["sharecode"] if ms else None


def new_codes(sid, log=print, limit=200):
    """Walk the player's history forward from the last known code.
    -> share codes still to fetch (new ones + those a previous sync could not fetch)."""
    sid = str(int(sid))
    s = config.settings()
    p = s.get("players", {}).get(sid, {})
    key, auth, cur = s.get("steam_api_key"), p.get("authcode"), p.get("last_code")
    if not (auth and cur):   # no key of your own: Wily's site asks Steam
        return list(p.get("pending_codes") or [])
    found = []
    for _ in range(limit):
        nxt = next_code(key, sid, auth, cur)
        if not nxt:
            break
        found.append(nxt)
        cur = nxt
    s = config.settings()
    p = s.setdefault("players", {}).setdefault(sid, {})
    pending = list(dict.fromkeys((p.get("pending_codes") or []) + found))
    p.update(last_code=cur, pending_codes=pending, last_sync=dt.datetime.now().isoformat(timespec="minutes"))
    config.save_settings(s)
    if found:
        log(f"Steam history: {len(found)} new match(es)")
    return pending


def done_codes(sid, codes):
    s = config.settings()
    p = s.setdefault("players", {}).setdefault(str(sid), {})
    p["pending_codes"] = [c for c in p.get("pending_codes") or [] if c not in set(codes)]
    config.save_settings(s)


def status(sid):
    sid = str(int(sid))
    s = config.settings()
    p = s.get("players", {}).get(sid, {})
    own, own_name = config.logged_in_account()
    login = s.get("steam_login") or {}
    reg_n = 0
    rp = os.path.join(config.CACHE, "matches.json")
    if os.path.exists(rp):
        acc = int(sid) - STEAM64
        reg_n = sum(1 for m in json.load(open(rp)).values() if acc in (m.get("accounts") or []) or (m.get("me") and str(own) == sid))
    fr = cached_friends(sid)
    return {"steamid": sid, "name": p.get("name"),
            "login": login if login.get("steamid") == sid else None,
            "pc_account": {"steamid": str(own) if own else None, "name": own_name},
            "playtime": local_playtime(sid),
            "has_key": bool(s.get("steam_api_key")), "has_auth": bool(p.get("authcode")), "relay": True,
            "last_code": p.get("last_code"), "last_sync": p.get("last_sync"), "pending": len(p.get("pending_codes") or []),
            "auto_sync": bool(p.get("auto_sync")), "known_matches": reg_n, "friends": len(fr) if fr else None,
            "links": {"key": KEY_URL, "auth": AUTH_URL}}
