"""The app in the player's language (13/10, the user: "traduis l'app en russe, pour l'Amérique du Sud et l'Asie, et
améliore les traductions", then "fait la traduction allemande également"). English is the source: every sentence a player reads goes through tr() / trn() here or
tl() / tln() in the page, with the English text as its key, and i18n/<lang>.json gives it in another language (a missing
one stays English, so a new sentence never breaks a page).

- Placeholders: {name}, filled after the translation (a translation may move them).
- Fixed tables (knowledge.py's routines, drills...): N_("...") marks a sentence without translating it, and tr_static()
  translates such sentences where an analysis is saved (advice.json), in the language of that moment.
- Plurals: trn(n, one, other) keys on `other`; the catalog holds the forms the language has, named as Intl.PluralRules
  names them (en, de, es: one / other; fr, pt: one for 0 and 1; ru: one / few / many; zh: other only).
- The language: Settings ("ui_lang"), else the browser's (the page's Accept-Language, remembered in "ui_lang_seen" so
  the analyses write in it too), else English.

python tools/i18n_extract.py lists every key of the code (i18n/_source.json) and what each catalog still misses."""
import json
import os
import re
import threading
import time

from wily.core import config

LANGS = {"en": "English", "fr": "Français", "de": "Deutsch", "ru": "Русский", "pt": "Português (Brasil)", "es": "Español", "zh": "简体中文"}
LOCALES = {"en": "en-US", "fr": "fr-FR", "de": "de-DE", "ru": "ru-RU", "pt": "pt-BR", "es": "es-419", "zh": "zh-CN"}
DIR = os.path.join(config.HERE, "resources", "i18n")
_CACHE = {}
_LANG = {"m": None, "v": "en", "t": None}
FRESH = 1.0   # s: the language and its catalog checked again at most once a second (16/10: two file dates read at each
              # of the 15,000 tr() of an analysis, a second of it)
_LOCK = threading.Lock()
_PH = re.compile(r"\{(\w+)\}")


def catalog(lang):
    """{English: translation} of a language ({} for English or a language without its file); re-read when it changes."""
    if lang not in LANGS or lang == "en":
        return {}
    c = _CACHE.get(lang)
    now = time.monotonic()
    if c and now - c[2] < FRESH:
        return c[1]
    p = os.path.join(DIR, f"{lang}.json")
    try:
        m = os.path.getmtime(p)
    except OSError:
        return {}
    with _LOCK:
        c = _CACHE.get(lang)
        if c and c[0] == m:
            c = _CACHE[lang] = (m, c[1], now)
        else:
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
            c = _CACHE[lang] = (m, {k: v for k, v in data.items() if not k.startswith("_") and v}, now)
    return c[1]


def from_header(h):
    """Accept-Language -> the first language the app speaks ("pt-BR,pt;q=0.9,en;q=0.8" -> "pt"), else English."""
    for part in (h or "").split(","):
        code = part.split(";")[0].strip().lower()
        if code[:2] in LANGS:
            return code[:2]
    return "en"


def current():
    """The language the analyses write in: the player's choice, else the browser's last seen, else English (read
    again only when settings.json changes: tr() runs thousands of times in an analysis)."""
    now = time.monotonic()
    if _LANG["t"] is not None and now - _LANG["t"] < FRESH:
        return _LANG["v"]
    _LANG["t"] = now
    try:
        m = os.path.getmtime(config.SETTINGS)
    except OSError:
        m = None
    if m != _LANG["m"]:
        s = config.settings()
        v = s.get("ui_lang") if s.get("ui_lang") in LANGS else s.get("ui_lang_seen")
        _LANG.update(m=m, v=v if v in LANGS else "en")
    return _LANG["v"]


def page_lang(header):
    """The page's language for a request: the choice in Settings, else the browser's (remembered for the analyses)."""
    s = config.settings()
    if s.get("ui_lang") in LANGS:
        return s["ui_lang"]
    v = from_header(header)
    if s.get("ui_lang_seen") != v:
        s["ui_lang_seen"] = v
        config.save_settings(s)
    return v


def plural(lang, n):
    """The plural form of n in a language, as Intl.PluralRules names it."""
    try:
        f = float(n)
    except (TypeError, ValueError):
        return "other"
    if not f.is_integer():
        return "other"
    i = abs(int(f))
    if lang == "ru":
        if i % 10 == 1 and i % 100 != 11:
            return "one"
        if 2 <= i % 10 <= 4 and not 12 <= i % 100 <= 14:
            return "few"
        return "many"
    if lang in ("fr", "pt"):
        return "one" if i in (0, 1) else "other"
    if lang == "zh":
        return "other"
    return "one" if i == 1 else "other"


def day_month(t, lang=None):
    """A day and month as the language writes them (en, zh: 10/13; de: 13.10.; the others: 13/10); t: a timestamp or a
    date."""
    import time
    lt = time.localtime(t) if isinstance(t, (int, float)) else t.timetuple()
    lang = lang or current()
    d, m = lt.tm_mday, lt.tm_mon
    return f"{m:02d}/{d:02d}" if lang in ("en", "zh") else f"{d:02d}.{m:02d}." if lang == "de" else f"{d:02d}/{m:02d}"


# the thousands' separator of each language (French and Russian: a narrow no-break space)
_THOUSANDS = {"en": ",", "fr": "\u202f", "de": ".", "ru": "\u202f", "pt": ".", "es": ".", "zh": ","}


def num(v, lang=None):
    """A whole number as the language writes it (21/10: "4,300 $" in French): 4,300 · 4 300 · 4.300."""
    return f"{int(round(v)):,}".replace(",", _THOUSANDS.get(lang or current(), ","))


def fill(s, kw):
    return _PH.sub(lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), s) if kw else s


def tr(s, lang=None, /, **kw):
    """A sentence in the language (lang, else current()), its {placeholders} filled (positional-only: a placeholder
    may be named s or lang, 13/10: "{s} solo")."""
    v = catalog(lang or current()).get(s)
    if isinstance(v, dict):
        v = v.get("other")
    return fill(v if isinstance(v, str) and v else s, kw)


def trn(n, one, other, lang=None, /, **kw):
    """The form of a sentence that fits n ({n} is filled too): the catalog's forms, else English's."""
    lang = lang or current()
    kw = {"n": n, **kw}
    v = catalog(lang).get(other)
    if isinstance(v, dict):
        return fill(v.get(plural(lang, n)) or v.get("other") or other, kw)
    if isinstance(v, str) and v:
        return fill(v, kw)
    return fill(one if plural("en", n) == "one" else other, kw)


def N_(s):
    """A sentence of a fixed table, marked for tools/i18n_extract.py; tr_static() translates it where it is saved."""
    return s


_SRC = {"m": None, "static": frozenset(), "page": frozenset(), "plugin": frozenset()}


def _source():
    p = os.path.join(DIR, "_source.json")
    try:
        m = os.path.getmtime(p)
    except OSError:
        return _SRC
    if m != _SRC["m"]:
        try:
            with open(p, encoding="utf-8") as f:
                src = json.load(f)
        except (OSError, ValueError):
            src = {}
        st = frozenset(k for k, v in src.items() if isinstance(v, dict) and v.get("static"))
        pg = frozenset(k for k, v in src.items() if isinstance(v, dict)
                       and any(re.match(r"(p\d\w*\.(js|html)):", w) for w in v.get("where", [])))
        pl = frozenset(k for k, v in src.items() if isinstance(v, dict) and any(w.startswith("cs/") for w in v.get("where", [])))
        _SRC.update(m=m, static=st, page=pg, plugin=pl)
    return _SRC


# the values tr_static never touches: callouts and keys the page looks up ("Mid" is a zone of the radar as well as a
# word of the team plan's groups), whatever they say
_KEEP = frozenset(("zone", "name", "from", "to", "key", "gate", "site", "map", "place", "land", "id", "kind", "type", "side", "role",
                   "k", "to_key", "from_key", "zones", "route", "lane", "verdict", "level", "status", "template", "metric", "unit",
                   "result", "dyn", "tags", "src", "url", "icon", "weapon", "steamid", "group_key", "category", "cat", "unit_n"))


def tr_static(obj, lang=None):
    """The N_() sentences of an analysis (dicts and lists, in place) in the language: only the marked ones, so a
    value that happens to be a word of the page ("kevlar", a callout) never changes, and never under a key of _KEEP."""
    lang = lang or current()
    c = catalog(lang)
    if not c:
        return obj
    st = _source()["static"]

    def tx(v):
        if isinstance(v, str):
            if v in st:
                t = c.get(v)
                return t.get("other") if isinstance(t, dict) else (t or v)
            return v
        if isinstance(v, dict):
            for k in v:
                if k not in _KEEP:
                    v[k] = tx(v[k])
            return v
        if isinstance(v, list):
            for i, x in enumerate(v):
                v[i] = tx(x)
            return v
        return v
    return tx(obj)


def page_catalog(lang):
    """What the page gets: the sentences of the page (ui/) in its language, not the analyses' (they come translated)."""
    c, pg = catalog(lang), _source()["page"]
    return {k: v for k, v in c.items() if k in pg} if pg else c


def plugin_catalog(lang=None):
    """What the training server says on its screen and in its chat (plugin/CoachReplay: T(), F(), Tn()), in a language:
    {"lang", "ui": {English: translation or its plural forms}}, written to coach/ui.json by replay.write_ui()."""
    lang = lang or current()
    c, pl = catalog(lang), _source()["plugin"]
    return {"lang": lang, "ui": {k: v for k, v in c.items() if k in pl}}


def voice_catalogs(keys):
    """The coach's spoken lines in every language (the voice may speak another language than the page's)."""
    out = {}
    for lang in LANGS:
        c = catalog(lang)
        sub = {k: c[k] for k in keys if k in c}
        if sub:
            out[lang] = sub
    return out
