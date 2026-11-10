"""The app's page (app_template.html) is built from these parts: edit them, never the built page.
python ui/assemble.py writes app_template_next.html, checks its scripts parse and runs the In game check on every map;
when it is right:
copy it over app_template.html (the server reads it on each request, no restart).
- fonts/: the three fonts, put in the page itself (fonts_css); p0_base.css, p1_extra.css: the styles (the colors are
  tokens in :root, dark and light);
- p2_shell.html: the bar and the views' containers; p3..p8: the scripts, in that order (core, plan and settings,
  prepare, nav, in game, live panel, visual panel, economy, review, search and routing)."""
import os
import subprocess
import sys

UI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(UI)
PARTS_JS = ("p3_core.js", "p3b_usage.js", "p3c_feedback.js", "p4_plan.js", "p4b_prepare.js", "p5_nav.js", "p6_ingame.js", "p6b_live.js", "p6c_visual.js", "p6d_econ.js", "p6e_dirs.js", "p6f_wily.js", "p7_review.js", "p7b_profile.js", "p8_tail.js")


def read(f):
    with open(os.path.join(UI, f), encoding="utf-8") as fh:
        return fh.read()


FONTS = {"Barlow Condensed": ("barlow-condensed", (500, 600, 700)), "IBM Plex Sans": ("ibm-plex-sans", (400, 500, 600)),
         "JetBrains Mono": ("jetbrains-mono", (400, 600))}
# the Cyrillic letters (13/10, the app in Russian): Plex and JetBrains have their own; Barlow has none, so its
# Cyrillic comes from Roboto Condensed (the closest condensed grotesque), under the same family name
CYRILLIC = {"Barlow Condensed": "roboto-condensed", "IBM Plex Sans": "ibm-plex-sans", "JetBrains Mono": "jetbrains-mono"}
CYR_RANGE = "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"


def fonts_css():
    """@font-face rules with the font files inside (base64): the page needs no font server (05/10: no request to
    Google Fonts from any player's PC, and the page works offline). The fonts are under the SIL Open Font License.
    Chinese uses the system's fonts (p0_base.css, :lang(zh)): a CJK font is megabytes."""
    import base64

    def face(family, w, path, rng=""):
        with open(os.path.join(UI, "fonts", path), "rb") as fh:
            b = base64.b64encode(fh.read()).decode()
        return (f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{w};font-display:swap;"
                f"src:url(data:font/woff2;base64,{b}) format('woff2'){f';unicode-range:{rng}' if rng else ''}}}")
    out = []
    for family, (fid, weights) in FONTS.items():
        for w in weights:
            out.append(face(family, w, f"{fid}-latin-{w}-normal.woff2"))
            out.append(face(family, w, f"{CYRILLIC[family]}-cyrillic-{w}-normal.woff2", CYR_RANGE))
    return "".join(out)


def build():
    css, extra, shell = read("p0_base.css"), read("p1_extra.css"), read("p2_shell.html")
    icons = read("p2b_icons.html")   # the icons' sprite (tools/icons_build.py, 03/11)
    js = "".join(read(f) for f in PARTS_JS)
    return f"<title>Wily</title>\n<style>{fonts_css()}{css}{extra}</style>\n\n{shell}\n{icons}<script>\n{js}</script>\n", js


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    out, js = build()
    dest = os.path.join(ROOT, "templates", "app_template_next.html")
    with open(dest, "w", encoding="utf-8") as fh:   # Windows line ends, as the page always had
        fh.write(out)
    print("written", len(out), "chars")
    # the scripts parse, or nothing else runs (05/10: a comment that swallowed the end of a line reached the app)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "checks", "check_js.py"), dest], capture_output=True, text=True, encoding="utf-8")
    print((r.stdout or r.stderr).strip())
    if r.returncode:
        sys.exit(1)
    # the regression check of the In game page on every map (checks/check_maps.js): a failure is printed, never hidden
    r = subprocess.run(["node", os.path.join(ROOT, "tools", "checks", "check_maps.js"), dest], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    lines = (r.stdout or r.stderr or "check: no output").strip().splitlines()
    print(lines[0])
    for line in lines[1:]:
        if "FAIL" in line:
            print(line)
