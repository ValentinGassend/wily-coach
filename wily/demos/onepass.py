"""A demo's events read in one pass (15/10, the user: "optimiser l'analyse de match pour que ça soit vraiment plus
vite"). Each parse_event of demoparser2 reads the whole demo again (160 MB): the detailed extraction read it 10 times
for its events, your analysis 28 times. Parser(path, events) is demoparser2's DemoParser whose parse_event gives the
declared events from a single parse_events of them all (the union of their properties), each table cut back to the
columns a parse_event of its own gives: the same tables, one read. Anything not declared is the parser's own call."""
from demoparser2 import DemoParser


class Parser:
    def __init__(self, path, events=None):
        """events: {name: (player properties, other properties)} read together at the first parse_event of one."""
        self._p = DemoParser(path)
        self._want = {n: (set(v[0] or ()), set(v[1] or ())) for n, v in (events or {}).items()}
        self._got = None
        self._names = None

    def __getattr__(self, name):
        return getattr(self._p, name)

    def list_game_events(self):
        if self._names is None:
            self._names = self._p.list_game_events()
        return self._names

    def _all(self):
        if self._got is None:
            pl = sorted({x for p, _ in self._want.values() for x in p})
            ot = sorted({x for _, o in self._want.values() for x in o})
            here = set(self.list_game_events())
            names = [n for n in self._want if n in here]
            got = self._p.parse_events(names, player=pl or None, other=ot or None) if names else []
            self._got = {n: df for n, df in got}
            self._pl, self._ot = set(pl), set(ot)
        return self._got

    def parse_event(self, name, player=None, other=None):
        want = self._want.get(name)
        if want is None or not set(player or ()) <= want[0] or not set(other or ()) <= want[1]:
            return self._p.parse_event(name, player=player, other=other)
        got = self._all()
        if name not in got:   # not in this demo: what the parser's own call gives
            return self._p.parse_event(name, player=player, other=other)
        df = got[name]
        extra_p = self._pl - set(player or ())
        pfx = {c[:-len("_steamid")] for c in df.columns if c.endswith("_steamid")}
        drop = {f"{a}_{q}" for a in pfx for q in extra_p} | (self._ot - set(other or ()))
        return df[[c for c in df.columns if c not in drop]].copy()
