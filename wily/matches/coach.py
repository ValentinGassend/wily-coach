"""Fetch recent matches from Valve, download each demo, analyze it, keep the JSON results.

Usage: python -m wily.matches.coach [--no-fetch] [--keep-demos]
Steam must be running and CS2 closed for the match list fetch.
"""
import bz2
import json
import os
import shutil
import sys
import traceback
import urllib.request

from wily.demos import analyze
from wily.demos import map_analysis
from wily.matches import matchlist
from demoparser2 import DemoParser

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the root
CACHE = os.path.join(HERE, "cache")
MATCHES = os.path.join(HERE, "out", "matches")
from wily.core import config
ME = config.logged_in_account()[0]
RANK_TYPES = {11: "Premier", 12: "Competitive", 7: "Wingman", 10: "Wingman"}


def log(*a):
    print(*a, flush=True)


class DemoGone(IOError):
    """Valve no longer has this demo (it keeps them about a month)."""


class _Unbz2:
    """A .bz2 unpacked as its bytes come, into <dest>.part (16/10: the archive downloaded, then read again whole to
    unpack it: 9.6 s more for a 235 MB demo, one after the other). Several streams one after the other, as bz2.open."""

    def __init__(self, dest):
        import queue
        import threading
        self.dest, self.part = dest, dest + ".part"
        self.out = open(self.part, "wb")
        self.d = bz2.BZ2Decompressor()
        self.err = None
        # in a thread of its own (bz2 lets the other threads run meanwhile): the download goes on while a piece unpacks
        self.q = queue.Queue(maxsize=64)
        self.t = threading.Thread(target=self._run, daemon=True, name="unbz2")
        self.t.start()

    def _run(self):
        while True:
            b = self.q.get()
            if b is None:
                return
            if self.err is None:
                try:
                    self._unpack(b)
                except Exception as e:
                    self.err = e

    def feed(self, data):
        if self.err is not None:
            raise ValueError(f"unpacking: {self.err}")
        self.q.put(data)

    def _unpack(self, data):
        while data:
            if self.d.eof:   # the next stream
                self.d = bz2.BZ2Decompressor()
            out = self.d.decompress(data)
            if out:
                self.out.write(out)
            data = self.d.unused_data if self.d.eof else b""

    def feed_file(self, path):
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                self.feed(b)

    def _stop(self):
        if self.t.is_alive():
            self.q.put(None)
            self.t.join()

    def finish(self):
        """True when the archive ended complete: the demo is in place."""
        self._stop()
        self.out.close()
        if self.err is None and self.d.eof:
            os.replace(self.part, self.dest)
            return True
        self.drop()
        return False

    def drop(self):
        self._stop()
        try:
            self.out.close()
            os.remove(self.part)
        except OSError:
            pass


def download(url, dest, tries=8, gone_tries=None, unpack=None):
    """Valve's replay servers sometimes drop the connection in the middle of a demo, and Python does not notice it
    (the file just ends early): check the size announced by the server and resume where it stopped.
    gone_tries: for an old match, an error before the first byte means the demo is gone after that many tries
    (it used to wait 8 tries, about 2 minutes, for each expired demo).
    unpack: a .bz2 also unpacked to that path as it arrives; True when it was (else unpack it afterwards)."""
    import time
    import urllib.error
    tmp = dest + ".part"
    total, err = None, None
    un = None   # the unpacking, fed every byte written to tmp; None once it failed or isn't asked
    if unpack:
        try:
            un = _Unbz2(unpack)
            if os.path.exists(tmp):   # a download cut before this run: what it has first
                un.feed_file(tmp)
        except (OSError, ValueError, EOFError):
            un = un.drop() if un else None
    for attempt in range(tries):
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status == 206:
                    t = r.headers.get("Content-Range", "").rsplit("/", 1)[-1]
                    total = int(t) if t.isdigit() else total
                    mode = "ab"
                else:  # a whole file (first try, or the server does not resume): start over
                    cl = r.headers.get("Content-Length")
                    total = int(cl) if cl and cl.isdigit() else None
                    mode = "wb"
                if mode == "wb" and un is not None:   # the file from its start again: so is the unpacking
                    un.drop()
                    un = _Unbz2(unpack)
                with open(tmp, mode) as f:
                    for b in iter(lambda: r.read(1 << 20), b""):
                        f.write(b)
                        if un is not None:
                            try:
                                un.feed(b)
                            except (OSError, ValueError, EOFError):   # unpacked afterwards, as before
                                un = un.drop()
            err = None
        except urllib.error.HTTPError as e:
            if e.code == 416 and have and total and have >= total:  # already complete
                err = None
            elif e.code in (404, 410):
                raise DemoGone(f"HTTP {e.code}") from None
            elif gone_tries and not have and attempt + 1 >= gone_tries:
                raise DemoGone(f"HTTP {e.code} {e.reason}") from None
            else:
                err = e
        except OSError as e:  # connection reset, timeout...
            err = e
        size = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        if err is None and (total is None or size >= total):
            os.replace(tmp, dest)
            return bool(un is not None and un.finish())
        time.sleep(min(30, 2 ** attempt))
    if un is not None:
        un.drop()
    raise IOError(f"incomplete download after {tries} tries ({size // 1_000_000} / {(total or 0) // 1_000_000} MB){f': {err}' if err else ''}")


def decompress(src, dest):
    """Into a temporary file first: a damaged archive never leaves a half demo behind."""
    tmp = dest + ".part"
    try:
        with bz2.open(src, "rb") as i, open(tmp, "wb") as o:
            shutil.copyfileobj(i, o, 1 << 20)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    os.replace(tmp, dest)


def game_mode(path, n_players):
    p = DemoParser(path)
    try:
        ru = p.parse_event("rank_update")
        types = ru["rank_type_id"].dropna().astype(int).unique().tolist() if "rank_type_id" in ru else []
        for t in types:
            if t in RANK_TYPES:
                return RANK_TYPES[t]
    except Exception:
        pass
    return {4: "Wingman", 6: "3v3"}.get(n_players, "Competitive / Premier")


def process(m, keep=False):
    mid = m["match_id"]
    folder = os.path.join(MATCHES, mid)
    if os.path.exists(os.path.join(folder, "stats.json")):
        log(f"[{mid}] already analyzed")
        return
    os.makedirs(folder, exist_ok=True)
    bz = os.path.join(CACHE, f"{mid}.dem.bz2")
    dem = config.demo(mid)   # an archived demo is not fetched again
    if not os.path.exists(dem):
        log(f"[{mid}] downloading {m['url']}")
        download(m["url"], bz)
        log(f"[{mid}] decompressing")
        decompress(bz, dem)
        os.remove(bz)
    log(f"[{mid}] analyzing")
    stats = analyze.analyze(dem, ME)
    stats["match"] = {k: m[k] for k in ("match_id", "time", "team_scores", "duration_s")}
    stats["mode"] = game_mode(dem, m.get("players", 10))
    mapj = map_analysis.analyze(dem, ME)
    with open(os.path.join(folder, "map.json"), "w", encoding="utf-8") as f:
        json.dump(mapj, f, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    with open(os.path.join(folder, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    if not keep:
        os.remove(dem)
    o = stats["overview"]
    log(f"[{mid}] OK {stats['map']} {stats['mode']} {stats['final_score']} K/D {o['kills']}/{o['deaths']} ADR {o['adr']}")


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(MATCHES, exist_ok=True)
    if "--no-fetch" in sys.argv:
        ms = matchlist.parse(open(matchlist.OUT, "rb").read())
    else:
        ms = matchlist.fetch()
    with open(os.path.join(CACHE, "matchlist.json"), "w") as f:
        json.dump(ms, f, indent=1)
    log(f"{len(ms)} recent matches")
    for m in ms:
        if not m.get("url"):
            log(f"[{m['match_id']}] no demo available")
            continue
        try:
            process(m, keep="--keep-demos" in sys.argv)
        except Exception as e:
            log(f"[{m['match_id']}] ERROR {e}")
            traceback.print_exc()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
