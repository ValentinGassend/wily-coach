"""Whether a stuff spot is one you can find again (19/10, his 21:19 video: "on retient un stuff en identifiant une zone
depuis laquelle l'envoyer ... un angle, le long d'un mur", "des endroits comme en plein milieu de l'allée ne sont pas
des endroits dans lesquels on peut envoyer un stuff"; 20/10: "cette flash est envoyée de nulle part"): where the base's
players stood around it (train._zone_samples), in 16 directions; one nobody ever stood in within 40 u is a wall.

    python tools/spot_walls.py <map> x,y,z [x,y,z ...]      each spot's walls (wily/training/train.py spot_walls)"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.training import train  # noqa: E402

if __name__ == "__main__":
    mp = sys.argv[1]
    for a in sys.argv[2:]:
        p = [float(v) for v in a.split(",")]
        w = train.spot_walls(mp, p)
        print(f"{a:28} {''.join('#' if x else '.' for x in w['dirs'])}  walls {w['walls']}  findable {w['ok']}  ({w['n']} samples)")
