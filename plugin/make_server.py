"""A separate CS2 dedicated server for the coach's replays, next to the game, without touching it.

The game's files are hard-linked (no copy, no space; read-only for the server), except the ones a server could write:
the cfg folder and gameinfo.gi are real copies, console.log, logs and replays are left out. Metamod:Source and
CounterStrikeSharp go into the copy only (addons), and the copy's gameinfo.gi loads Metamod. The game itself never sees
any of it. Run again after a CS2 update: new files are linked, the rest stays. The coach's replay plugin goes in too
(plugin/CoachReplay/bin/out: built by plugin/build.py, shipped built to the players who don't build it).

Any PC (05/10, the beta): the game is found through Steam's libraries, the server goes next to it on its drive (hard
links only work on one NTFS drive), or where COACH_CS2SERVER or the settings' "cs2server" say.

Linux (10/10, experimental): the same, with Metamod:Source and CounterStrikeSharp's Linux builds, the same versions as
Windows' (LINUX_ADDONS: downloaded once from their official pages, checked by SHA-256, not shipped in every update),
the links on the game's file system, and the files' modes kept."""
import os
import re
import shutil
import sys
import threading
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from wily.core import config  # noqa: E402

SRC = os.environ.get("COACH_CS2") or config.cs2_dir()
DST = config.cs2server_dir()
# mmsource.zip (Metamod:Source 2.0) and css-runtime.zip (CounterStrikeSharp with runtime): next to this file in the
# players' copy, in E:\dev\tools on the coach's PC
ZIPS = [d for d in (os.environ.get("COACH_SERVER_ZIPS"), HERE, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools")) if d]
PLUGIN = os.path.join(HERE, "CoachReplay", "bin", "out")
SKIP_DIRS = {os.path.normcase(os.path.join("game", "csgo", d)) for d in ("replays", "logs", "addons", "demoheaders")}
COPY_DIRS = {os.path.normcase(os.path.join("game", "csgo", "cfg"))}
COPY_FILES = {os.path.normcase(os.path.join("game", "csgo", "gameinfo.gi"))}
SKIP_FILES = {os.path.normcase(os.path.join("game", "csgo", "console.log"))}
LINUX = os.name != "nt"
ADDONS = ((("mmsource-linux.tar.gz", "metamod"), ("css-runtime-linux.zip", "counterstrikesharp")) if LINUX
          else (("mmsource.zip", "metamod"), ("css-runtime.zip", "counterstrikesharp")))
LINUX_ADDONS = {   # Metamod:Source 2.0 build 1473 and CounterStrikeSharp 1.0.376: the Windows server's own versions
    "mmsource-linux.tar.gz": ("https://mms.alliedmods.net/mmsdrop/2.0/mmsource-2.0.0-git1473-linux.tar.gz",
                              "da3f612bdf53dda8876dd82cc5ea99858b34c9dc15bc130b65caa39f43630b1c"),
    "css-runtime-linux.zip": ("https://github.com/roflmuffin/CounterStrikeSharp/releases/download/v1.0.376/"
                              "counterstrikesharp-with-runtime-linux-1.0.376.zip",
                              "8d50a25a467fe9c7ebbbc7032028d402cd428e118308f1c4d627a0a5ddf36783"),
}


def _fetch_linux(name, log=print):
    """A Linux add-on downloaded next to this file once, from its official page; refused unless its SHA-256 matches."""
    import hashlib
    import urllib.request
    url, sha = LINUX_ADDONS[name]
    dest = os.path.join(HERE, name)
    log(f"Downloading {name.split('-')[0]} for Linux…")
    data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Wily"}), timeout=300).read()
    if hashlib.sha256(data).hexdigest() != sha:
        raise RuntimeError(f"{name}: the download does not match its expected SHA-256, nothing installed")
    with open(dest, "wb") as fh:
        fh.write(data)
    return dest


def _extract(path, dest):
    """An add-on's archive into dest (a zip, or Metamod's Linux tar.gz); on Linux each file keeps its mode."""
    root = os.path.realpath(dest)
    if path.endswith(".tar.gz"):
        import tarfile
        with tarfile.open(path) as t:
            for m in t.getmembers():
                if not os.path.realpath(os.path.join(root, m.name)).startswith(root + os.sep) or m.issym() or m.islnk():
                    continue
                t.extract(m, dest, set_attrs=True)
        return
    with zipfile.ZipFile(path) as z:
        for m in z.infolist():
            if not os.path.realpath(os.path.join(root, m.filename)).startswith(root + os.sep):
                continue
            out = z.extract(m, dest)
            mode = (m.external_attr >> 16) & 0o777
            if LINUX and mode and not m.is_dir():
                os.chmod(out, mode)


def _same_place(a, b):
    """The server can link the game's files: the same drive (Windows) or the same file system (Linux)."""
    if not LINUX:
        return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()
    os.makedirs(b, exist_ok=True)
    return os.stat(a).st_dev == os.stat(b).st_dev


def current():
    """The server copy has the game's version (an update replaces the game's files: the links then point to the old ones)."""
    if not SRC:
        return False
    try:
        return os.path.samefile(os.path.join(SRC, "game", "csgo", "steam.inf"), os.path.join(DST, "game", "csgo", "steam.inf"))
    except OSError:
        return False


def _zip(name, log=print):
    for d in ZIPS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    if name in LINUX_ADDONS:
        return _fetch_linux(name, log)
    raise RuntimeError(f"{name} is missing (Metamod:Source and CounterStrikeSharp go next to plugin/make_server.py)")


def plugin():
    """The coach's plugin in the server, when it is missing or an older build. -> True when copied."""
    src = os.path.join(PLUGIN, "CoachReplay.dll")
    dst = os.path.join(DST, "game", "csgo", "addons", "counterstrikesharp", "plugins", "CoachReplay")
    if not os.path.exists(src):
        return False
    if os.path.exists(os.path.join(dst, "CoachReplay.dll")) and os.path.getmtime(os.path.join(dst, "CoachReplay.dll")) >= os.path.getmtime(src):
        return False
    os.makedirs(dst, exist_ok=True)
    for f in ("CoachReplay.dll", "CoachReplay.pdb"):
        if os.path.exists(os.path.join(PLUGIN, f)):
            shutil.copy2(os.path.join(PLUGIN, f), dst)
    return True


_MAIN = threading.Lock()   # the app's watch (serve.server_copy_watch) and a warm-up's start: one at a time


def main(log=print):
    with _MAIN:
        return _main(log)


def _main(log=print):
    if not SRC or not os.path.isdir(os.path.join(SRC, "game", "csgo")):
        raise RuntimeError("CS2 was not found in Steam's libraries: install it, then try again")
    if not _same_place(SRC, DST):
        raise RuntimeError(f"The training server must be on CS2's {'file system' if LINUX else 'drive'} ({SRC}): its files are links to the game's, not copies")
    linked = copied = 0
    for root, dirs, files in os.walk(SRC):
        rel = os.path.relpath(root, SRC)
        nrel = os.path.normcase(rel)
        if any(nrel == d or nrel.startswith(d + os.sep) for d in SKIP_DIRS):
            dirs[:] = []
            continue
        os.makedirs(os.path.join(DST, rel), exist_ok=True)
        copy_here = any(nrel == d or nrel.startswith(d + os.sep) for d in COPY_DIRS)
        for f in files:
            r = os.path.normcase(os.path.join(rel, f))
            if r in SKIP_FILES or f.lower().endswith((".log", ".dmp", ".mdmp")):
                continue
            s, d = os.path.join(root, f), os.path.join(DST, rel, f)
            if os.path.exists(d):
                if copy_here or r in COPY_FILES:
                    if r in COPY_FILES and os.path.getmtime(s) > os.path.getmtime(d) + 1:   # gameinfo.gi of an update: patched again below
                        shutil.copy2(s, d)
                        copied += 1
                    continue
                try:
                    if os.path.samefile(s, d):
                        continue
                except OSError:
                    pass
                os.remove(d)   # replaced by a game update: link the new file
            if copy_here or r in COPY_FILES:
                shutil.copy2(s, d)
                copied += 1
            else:
                try:
                    os.link(s, d)
                except OSError as e:
                    raise RuntimeError(f"The game's files can't be linked there ({e.strerror}): the training server needs CS2's "
                                       f"{'file system' if LINUX else 'drive, in NTFS'}") from e
                linked += 1
            if (linked + copied) % 2000 == 0:
                log(f"Linking the game's files: {linked + copied}…")
    csgo = os.path.join(DST, "game", "csgo")
    for z, sub_dir in ADDONS:
        if not os.path.isdir(os.path.join(csgo, "addons", sub_dir)):
            log(f"Adding {'Metamod:Source' if sub_dir == 'metamod' else 'CounterStrikeSharp'}…")
            _extract(_zip(z, log), csgo)
    gi = os.path.join(csgo, "gameinfo.gi")
    t = open(gi, encoding="utf-8").read()
    if "csgo/addons/metamod" not in t:
        t = re.sub(r"(\n(\s*)Game\s+csgo\s*\n)", r"\n\2Game\tcsgo/addons/metamod\1", t, count=1)
        open(gi, "w", encoding="utf-8").write(t)
    new_plugin = plugin()
    log(f"linked {linked}, copied {copied}; metamod in gameinfo: {'csgo/addons/metamod' in open(gi, encoding='utf-8').read()}"
        f"{'; the coach plugin added' if new_plugin else ''}")
    return {"linked": linked, "copied": copied, "plugin": new_plugin}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
