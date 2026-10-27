"""Makes the glow masks for the blueprint editor (blocks like Glowing armor, Neon, lights...).

Run it once, next to editor.html (after the models/ folder exists):   python make_glow.py
For every material used by the models/ files it finds the game's "_add" texture (green channel = emissive),
and writes textures/<same path>.glow.png when that texture really contains glow. Nothing else is touched.
"""
import argparse
import glob
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steam", default=r"C:\Program Files (x86)\Steam\steamapps")
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="textures")
    ap.add_argument("--max", type=int, default=1024)
    a = ap.parse_args()
    content = os.path.join(a.steam, "common", "SpaceEngineers", "Content")
    roots = [content]
    ws = os.path.join(a.steam, "workshop", "content", "244850")
    if os.path.isdir(ws):
        roots += [os.path.join(ws, d) for d in os.listdir(ws) if os.path.isdir(os.path.join(ws, d))]
    print(f"{len(roots)} folders to search (game + mods)")

    paths = set()
    for f in glob.glob(os.path.join(a.models, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for m in d.get("materials", []) if isinstance(d, dict) else []:
            if m.get("AddMapsTexture"):
                paths.add(m["AddMapsTexture"])
    print(f"{len(paths)} add maps used by your models")

    made = skipped = missing = 0
    for p in sorted(paths):
        rel = p.replace("\\", "/").lstrip("/")
        dst = os.path.join(a.out, rel.lower() + ".glow.png")        # the editor looks for textures/<path lowercase>.glow.png
        if os.path.isfile(dst):
            continue
        src = next((os.path.join(r, *rel.split("/")) for r in roots if os.path.isfile(os.path.join(r, *rel.split("/")))), None)
        if not src:
            missing += 1
            continue
        try:
            im = Image.open(src).convert("RGBA")
            im.thumbnail((a.max, a.max))
            g = im.getchannel("G")
            if g.getextrema()[1] < 12:                               # no glow in this map
                skipped += 1
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            Image.merge("RGBA", (g, g, g, Image.new("L", g.size, 255))).save(dst)
            made += 1
            print("glow:", rel)
        except Exception as ex:
            print("cannot read", src, ex)
    print(f"DONE: {made} glow masks written, {skipped} maps without glow, {missing} files not found")


if __name__ == "__main__":
    main()
    if sys.stdin and sys.stdin.isatty():
        input("Press Enter to close.")
