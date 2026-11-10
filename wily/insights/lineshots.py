"""Photos of the lineups (06/10, the user: "les endroits avec les images de là où je dois viser, de là où je dois me
mettre", like the Fachwerk book), taken in the game on the training server during photo sessions that numpad + drove
(16/10, the user: "enlever '+ photo de lineup suivante' et la commande qui va avec": the session is gone, no page started
it since 07/10). The photos taken stay on Live's ways: out/lineups/shots/<map>/<id>.webp (id: side, type, from and to
zones of the game)."""
import os
import re

from wily.core import config

DIR = os.path.join(config.OUT, "lineups", "shots")
SAFE = re.compile(r"[^A-Za-z0-9_>-]")


def lid(side, u):
    """A lineup's id: its side, type, and the game's zones it's thrown from and lands in (the training's own key)."""
    return SAFE.sub("", f"{side}_{u['type']}_{u.get('from_key') or u.get('from') or ''}_{u.get('to_key') or u.get('to') or ''}").replace(">", "-")


def shots(mp):
    """The photos taken on a map: id -> its address on the app."""
    d = os.path.join(DIR, mp)
    if not os.path.isdir(d):
        return {}
    return {f[:-5]: f"/lineshot/{mp}/{f}" for f in os.listdir(d) if f.endswith(".webp")}
