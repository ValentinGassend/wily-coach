"""The defense module's measures (specs/001-defense-module, 03/11): from a day's server log and the defense driver logs,
per map, what the success criteria read:

- SC-002: the player's deaths in a 2-on-1 at contact (two attackers of one wave seeing him within 0.3 s, his death within
  3 s of the second);
- SC-003: his deaths by a headshot within 0.6 s of an attacker first seeing him (the owner, 03/11: "une fois que le temps
  de réaction est passé, ils mettent un headshot instantanément"), and all his deaths by a headshot;
- SC-004: his follow-up pistol taps' height under the head (median, semi-automatic pistols, shots with no settle);
- R2: blind spells over 3 s in a defense (the driver at [0, 0, 0]).

    python tools/defense_report.py [YYYYMMDD] [--since HH:MM] [--me NAME]

The log lines it reads are the contract in specs/001-defense-module/contracts/log-lines.md."""
import collections
import glob
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = r"E:\CS2Server\game\csgo\addons\counterstrikesharp\logs"
DRIVER = os.path.join(HERE, "out", "realtest")
SEMI = ("hkp2000", "usp_silencer", "glock", "p250", "fiveseven", "tec9", "deagle", "elite")

LINE = re.compile(r"^\d{4}-\d\d-\d\d (\d\d):(\d\d):(\d\d)\.(\d{3}) .*?plugin:CoachReplay (.*)$")
DEATH = re.compile(r"death \d+/(defend:(de_\w+):\S+): (.+?) by (.+?) \((\w+)\)(?: (\d+) u)?( HS)?$")
CONTACT = re.compile(r"contact (.+?) at \d+$")
WAVE = re.compile(r"wave \d+: \d+ attackers$")


def arg(k, d=None):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv and sys.argv.index(k) + 1 < len(sys.argv) else d


def server(day, since):
    """Per map: [deaths of the player, 2-on-1 deaths, his deaths by HS, by an instant HS] from the day's log, from since
    (seconds of the day)."""
    fn = os.path.join(LOGS, f"log-all{day}.txt")
    rows = []
    with open(fn, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = LINE.match(line.rstrip("\n"))
            if not m:
                continue
            t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
            if t >= since:
                rows.append((t, m.group(5)))
    kills = collections.Counter(d.group(4) for _, x in rows if (d := DEATH.search(x)) and d.group(5) != "world")
    me = arg("--me") or (kills.most_common(1)[0][0] if kills else None)
    out = collections.defaultdict(lambda: [0, 0, 0, 0])
    contacts = []   # this wave's (t, attacker)
    for t, x in rows:
        if WAVE.search(x):
            contacts = []
            continue
        c = CONTACT.search(x)
        if c:
            contacts.append((t, c.group(1)))   # one line a bot (two of a wave may walk ways of one name)
            continue
        d = DEATH.search(x)
        if not d or d.group(3) != me or d.group(5) == "world":
            continue
        mp = d.group(2)
        out[mp][0] += 1
        out[mp][2] += 1 if d.group(7) else 0
        near = sorted(t0 for t0, _ in contacts if t - t0 <= 3.0)
        if any(b - a <= 0.3 for a, b in zip(near, near[1:])):
            out[mp][1] += 1
        if d.group(7) and near and t - near[0] <= 0.6:
            out[mp][3] += 1
    return me, out


def driver():
    """Per map: [follow-up pistol taps' up offsets], blind spells over 3 s, from the defense driver logs."""
    shot = re.compile(r"shot at .*?bullet ([+-][\d.]+) right ([+-][\d.]+) up.*?\[(\w+) [\w]+\].*?settle ([\d.]+)\)")
    taps, blind = collections.defaultdict(list), collections.Counter()
    for f in glob.glob(os.path.join(DRIVER, "rt_bat_*_defend.log")):
        mp = "de_" + os.path.basename(f)[len("rt_bat_"):-len("_defend.log")]
        run = 0
        for line in open(f, encoding="utf-8", errors="replace"):
            m = shot.search(line)
            if m and m.group(3) in SEMI and float(m.group(4)) < 0.02:
                taps[mp].append(float(m.group(2)))
            if re.search(r"at \d+ s: \[0, 0, 0\]", line):
                run += 1
                if run == 2:   # two reads 2 s apart: over 3 s
                    blind[mp] += 1
            elif "at " in line and " s: [" in line:
                run = 0
    return taps, blind


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    day = next((a for a in sys.argv[1:] if re.fullmatch(r"\d{8}", a)), time.strftime("%Y%m%d"))
    hh = arg("--since", "00:00").split(":")
    me, srv = server(day, int(hh[0]) * 3600 + int(hh[1]) * 60)
    taps, blind = driver()
    print(f"defense measures, {day} from {arg('--since', '00:00')}, the player: {me}")
    print(f"{'map':12} {'deaths':>6} {'2-on-1':>7} {'HS %':>5} {'instant HS':>10} {'pistol up':>10} {'blind':>6}")
    tot = [0, 0, 0, 0]
    pct = lambda a, b: f"{(100 * a / b if b else 0):4.0f}%"
    for mp in sorted(set(srv) | set(taps) | set(blind)):
        d, two, hs, ihs = srv.get(mp, [0, 0, 0, 0])
        tot = [tot[0] + d, tot[1] + two, tot[2] + hs, tot[3] + ihs]
        up = f"{statistics.median(taps[mp]):+.1f} u" if taps.get(mp) else "-"
        print(f"{mp:12} {d:6} {two:7} {pct(hs, d)} {pct(ihs, d):>10} {up:>10} {blind.get(mp, 0):6}")
    allt = [u for v in taps.values() for u in v]
    print(f"{'all':12} {tot[0]:6} {tot[1]:7} {pct(tot[2], tot[0])} {pct(tot[3], tot[0]):>10} "
          f"{(f'{statistics.median(allt):+.1f} u' if allt else '-'):>10} {sum(blind.values()):6}")
    print("SC-002: 2-on-1 deaths 0 · SC-003: instant HS under 15 % of his deaths · SC-004: pistol up within 8 u · R2: blind 0")


if __name__ == "__main__":
    main()
