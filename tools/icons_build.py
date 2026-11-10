"""The app's icons (03/11, the interface's review with ui-ux-pro-max: 138 emoji used as icons, drawn by each system's own
emoji font, in colors the page cannot set): Lucide's line icons (ISC license, kept with them), one SVG sprite put in the
page itself (ui/p2b_icons.html, no request anywhere), each one used as <svg class="ic"><use href="#i-NAME"/></svg>
(IC() in ui/p3_core.js), in the text's own color and size.

    python tools/icons_build.py [lucide-react folder]

The icons are read from an installed lucide-react (node_modules/lucide-react/dist/esm/icons/*.mjs): only the ones in
NAMES, so the page grows by a few kilobytes."""
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "ui", "p2b_icons.html")
DEFAULT_SRC = r"E:\dev\calque\app\node_modules\lucide-react"

# the icons the page uses (ui/*.js: IC("name"))
NAMES = ["angry", "frown", "meh", "smile", "laugh", "flask-conical", "shield", "shield-check", "footprints", "crosshair",
         "cloud", "brick-wall", "repeat", "fast-forward", "flame", "eye", "map", "dices", "shuffle", "bot", "triangle-alert",
         "megaphone", "gamepad-2", "lightbulb", "bug", "puzzle", "target", "menu", "lock", "maximize", "swords", "bomb", "mic",
         "users", "arrow-right", "map-pin", "book-open", "key-round", "zap", "star"]

ELEM = re.compile(r'\[\s*"(\w+)"\s*,\s*\{([^}]*)\}\s*\]', re.S)
ATTR = re.compile(r'(\w+)\s*:\s*"([^"]*)"')


def icon(src, name):
    f = name
    for _ in range(3):   # an alias's own file (smile.mjs: export { default } from './face-slightly-smiling.mjs')
        with open(os.path.join(src, "dist", "esm", "icons", f"{f}.mjs"), encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r"export \{ default \} from '\./([\w-]+)\.mjs'", text)
        if "node:" in text or not m:
            break
        f = m.group(1)
    node = text[text.index("node:"):]
    parts = []
    for tag, attrs in ELEM.findall(node):
        a = " ".join(f'{k}="{v}"' for k, v in ATTR.findall(attrs) if k != "key")
        parts.append(f"<{tag} {a}/>")
    if not parts:
        raise ValueError(f"no shape in {name}")
    return f'<symbol id="i-{name}" viewBox="0 0 24 24">{"".join(parts)}</symbol>'


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    with open(os.path.join(src, "package.json"), encoding="utf-8") as fh:
        import json
        version = json.load(fh).get("version")
    with open(os.path.join(src, "LICENSE"), encoding="utf-8") as fh:
        lic = " ".join(fh.read().split())
    syms = [icon(src, n) for n in NAMES]
    out = (f"<!-- Lucide icons {version} (https://lucide.dev), ISC license: {lic} -->\n"
           '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style="position:absolute;width:0;height:0;overflow:hidden" '
           'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
           + "".join(syms) + "</svg>\n")
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    print(f"{len(syms)} icons, {len(out)} bytes -> {OUT}")


if __name__ == "__main__":
    main()
