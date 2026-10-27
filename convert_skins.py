"""Converts the game's armor skins for the blueprint editor (color textures and normal/relief maps).

Run it once, next to editor.html:   python convert_skins.py
It reads ArmorModifiers.sbc from the game, converts every skin's color texture (the *_cm.dds files)
to PNG under skins/<Skin>/ and writes skins.json.
"""
import argparse
import json
import os
import re
import traceback
import xml.etree.ElementTree as ET

LOG = None


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()


def find_files(content, name):
    for dp, _, files in os.walk(content):
        for f in files:
            if f.lower() == name.lower():
                yield os.path.join(dp, f)


def pretty(sub):
    s = re.sub(r"_?Armor$", "", sub).replace("_", " ")
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s).strip() or sub


def main():
    from PIL import Image
    ap = argparse.ArgumentParser()
    ap.add_argument("--steam", default=r"C:\Program Files (x86)\Steam\steamapps")
    ap.add_argument("--content", default=None, help="game Content folder (default: <steam>/common/SpaceEngineers/Content)")
    ap.add_argument("--modifiers", default=None, help="a specific ArmorModifiers.sbc (default: every one found in Content)")
    ap.add_argument("--out", default="skins")
    ap.add_argument("--json", default="skins.json")
    ap.add_argument("--max", type=int, default=1024, help="largest texture side, in pixels")
    ap.add_argument("--no-normals", action="store_true", help="skip the normal (relief) maps")
    a = ap.parse_args()
    content = a.content or os.path.join(a.steam, "common", "SpaceEngineers", "Content")
    files = [a.modifiers] if a.modifiers else list(find_files(content, "ArmorModifiers.sbc"))
    if not files:
        log("ArmorModifiers.sbc not found under", content)
        return
    skins, done, bad = {}, 0, 0
    cache = {}                                   # source file -> output file, so shared textures convert once
    for f in files:
        log("reading", f)
        for am in ET.parse(f).getroot().iter("AssetModifier"):
            idn = am.find("Id")
            sub = idn.get("Subtype") if idn is not None else None
            if not sub:
                continue
            sk = skins.setdefault(sub, {"name": pretty(sub), "dlc": am.findtext("DLC") or "", "loc": {}, "nrm": {}, "add": {}})
            for t in am.iter("Texture"):
                kind = t.get("Type")
                if kind not in ("ColorMetal", "NormalGloss", "Extensions") or (kind == "NormalGloss" and a.no_normals):
                    continue
                rel = (t.get("Filepath") or "").replace("\\", "/")
                src = os.path.join(content, *rel.split("/"))
                if not os.path.isfile(src):
                    bad += 1
                    continue
                ck = (kind, src.lower())
                if ck not in cache:
                    stem = os.path.splitext(os.path.basename(src))[0]
                    d = os.path.join(a.out, sub)
                    os.makedirs(d, exist_ok=True)
                    dst = os.path.join(d, stem + {"ColorMetal": ".png", "NormalGloss": "_n.png", "Extensions": "_a.png"}[kind])
                    try:
                        if not os.path.isfile(dst):
                            im = Image.open(src).convert("RGBA" if kind == "Extensions" else "RGB")     # the extension (_add) map keeps all four channels
                            if kind == "NormalGloss":                 # two-channel normal maps come out with an empty blue: rebuild it
                                import math
                                px = im.load()
                                for yy in range(im.size[1]):
                                    for xx in range(im.size[0]):
                                        r, g, b = px[xx, yy]
                                        nx, ny = r / 127.5 - 1, g / 127.5 - 1
                                        nz = math.sqrt(max(0.0, 1 - nx * nx - ny * ny))
                                        px[xx, yy] = (r, g, int((nz + 1) * 127.5))
                            im.thumbnail((a.max, a.max))
                            im.save(dst)
                            done += 1
                        cache[ck] = a.out.replace("\\", "/") + "/" + sub + "/" + os.path.basename(dst)
                    except Exception as ex:
                        log("cannot convert", src, ex)
                        cache[ck] = None
                        bad += 1
                if cache.get(ck):
                    (sk["nrm"] if kind == "NormalGloss" else sk["add"] if kind == "Extensions" else sk["loc"])[t.get("Location")] = cache[ck]
    skins = {k: v for k, v in skins.items() if v["loc"]}
    with open(a.json, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "skins": skins}, fh)
    log(f"DONE: {len(skins)} skins, {done} textures converted, {bad} missing or unreadable -> {a.json}, {a.out}/")


if __name__ == "__main__":
    LOG = open("skins_log.txt", "w", encoding="utf-8")
    try:
        main()
    except Exception:
        log("ERROR:")
        log(traceback.format_exc())
    finally:
        LOG.close()
    try:
        input("Press Enter to close.")
    except EOFError:
        pass
