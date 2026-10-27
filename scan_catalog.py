import argparse
import io
import json
import os
import re
import traceback
import zipfile
import xml.etree.ElementTree as ET

XSI = "{http://www.w3.org/2001/XMLSchema-instance}type"
POWER_IN = ("RequiredPowerInput", "MaxPowerConsumption", "OperationalPowerConsumption", "PowerConsumption")
LOG = None
IMG_EXT = (".dds", ".png", ".tga", ".jpg", ".jpeg", ".bmp", ".tif")


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()


class Src:
    """A folder, or a .bin archive (zip), holding game or mod files."""

    def __init__(self, path):
        self.path = path
        self._stems = None
        self.zip = zipfile.ZipFile(path) if os.path.isfile(path) else None
        self.names = {n.replace("\\", "/").lower(): n for n in self.zip.namelist()} if self.zip else {}

    def sbc(self):
        if self.zip:
            for low, n in self.names.items():
                if low.endswith(".sbc"):
                    yield self.zip.read(n)
        else:
            for dp, _, files in os.walk(self.path):
                for f in files:
                    if f.lower().endswith(".sbc"):
                        try:
                            with open(os.path.join(dp, f), "rb") as fh:
                                yield fh.read()
                        except OSError:
                            pass

    def read(self, rel):
        rel = rel.replace("\\", "/").lstrip("/")
        if self.zip:
            n = self.names.get(rel.lower())
            return self.zip.read(n) if n else None
        p = os.path.join(self.path, *rel.split("/"))
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                return fh.read()
        return None

    def find_like(self, rel):
        """Fallback for icons whose path or extension is wrong: same file name, any image extension, anywhere in this source."""
        if self._stems is None:
            self._stems = {}
            if self.zip:
                items = [(n, n) for n in self.zip.namelist()]
            else:
                items = []
                for dp, _, files in os.walk(self.path):
                    for f in files:
                        items.append((f, os.path.join(dp, f)))
            for f, full in items:
                stem, ext = os.path.splitext(os.path.basename(f.replace("\\", "/")))
                if ext.lower() in IMG_EXT:
                    self._stems.setdefault(stem.lower(), full)
        stem = os.path.splitext(os.path.basename(rel.replace("\\", "/")))[0].lower()
        full = self._stems.get(stem)
        if not full:
            return None
        if self.zip:
            return self.zip.read(full)
        with open(full, "rb") as fh:
            return fh.read()


def open_image(data):
    """Open an icon; DXT4 DDS files (premultiplied alpha, unsupported by Pillow) are read as DXT5."""
    from PIL import Image
    if data[:4] == b"DDS " and data[84:88] == b"DXT4":
        data = data[:84] + b"DXT5" + data[88:]
    return Image.open(io.BytesIO(data))


def fl(d, tag):
    try:
        return float(d.findtext(tag))
    except (TypeError, ValueError):
        return 0.0


def load_texts(content):
    texts = {}
    loc = os.path.join(content, "Data", "Localization")
    if os.path.isdir(loc):
        for f in os.listdir(loc):
            if f.lower() == "mytexts.resx":
                try:
                    for d in ET.parse(os.path.join(loc, f)).getroot().iter("data"):
                        texts[d.get("name")] = d.findtext("value") or ""
                except ET.ParseError:
                    pass
    return texts


def process(src, mod, blocks, comps, cats):
    for data in src.sbc():
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            continue
        for e in root.iter():
            ids, nm = e.find("ItemIds"), e.find("Name")
            if ids is not None and nm is not None and nm.text:
                c = cats.setdefault(nm.text, {"name": e.findtext("DisplayName") or nm.text, "items": set()})
                for s in ids:
                    c["items"].add((s.text or "").split("/")[-1].strip())
        # any element with an <Id> child: blocks and components use different wrapper names
        for d in root.iter():
            idn = d.find("Id")
            if idn is None:
                continue
            try:
                t = (idn.findtext("TypeId") or "").strip()
                s = (idn.findtext("SubtypeId") or "").strip()
                xt = d.get(XSI) or ""
                if (t == "Component" or "ComponentDefinition" in xt) and d.find("Mass") is not None:
                    comps[s] = {"mass": fl(d, "Mass"), "name": d.findtext("DisplayName") or s}
                    continue
                sz, cs = d.find("Size"), d.find("CubeSize")
                if sz is None or cs is None:
                    continue
                try:
                    size = [int(sz.get(k)) for k in "xyz"]
                except (TypeError, ValueError):
                    continue
                cm = d.find("Components")
                icon = d.findtext("Icon") or d.findtext("Icons/Icon")
                rec = blocks[s or "MyObjectBuilder_" + t] = {
                    "type": t,
                    "grid": (cs.text or "").strip(),
                    "size": size,
                    "mod": mod,
                    "name": d.findtext("DisplayName") or s or t,
                    "model": (d.findtext("Model") or "").strip(),
                    "topo": (d.findtext("CubeDefinition/CubeTopology") or "").strip(),
                    "mounts": mount_points(d) if d.find("CubeDefinition") is not None else [],
                    "pcu": int(fl(d, "PCU")),
                    "comps": [[c.get("Subtype"), int(c.get("Count") or 0)] for c in cm.findall("Component")] if cm is not None else [],
                    "thrust": fl(d, "ForceMagnitude") if "Thrust" in xt else 0,
                    "pout": fl(d, "MaxPowerOutput"),
                    "pin": next((fl(d, k) for k in POWER_IN if d.find(k) is not None), 0.0),
                    "store": fl(d, "MaxStoredPower"),
                    "public": (d.findtext("Public") or "true").strip().lower() != "false",
                    "_src": src,
                    "_icon": (icon or "").strip(),
                }
                if t == "Drill":
                    # drill spheres, in metres along the block's forward axis from its centre (game defaults when a tag is missing):
                    # sr/so = entity detection sphere, cr/co = mining sphere, dm = carving radius multiplier of cr, mo = ModelOffset
                    num = lambda tag, dflt: fl(d, tag) if d.find(tag) is not None else dflt
                    m = d.find("ModelOffset")
                    rec["drill"] = {"sr": num("SensorRadius", 1.5), "so": num("SensorOffset", 0.0), "cr": num("CutOutRadius", 2.5),
                                    "co": num("CutOutOffset", 0.0), "dm": num("DiscardingMultiplier", 3.0),
                                    "mo": [float(m.get(a) or 0) for a in "xyz"] if m is not None else [0.0, 0.0, 0.0]}
            except Exception as ex:
                log(f"definition skipped (mod {mod}): {ex}")


def mount_points(d):
    """[[side, startX, startY, endX, endY], ...] - which faces of the cell are solid in the default orientation"""
    out = []
    for mp in d.findall("MountPoints/MountPoint"):
        try:
            out.append([mp.get("Side"), float(mp.get("StartX") or 0), float(mp.get("StartY") or 0),
                        float(mp.get("EndX") or 0), float(mp.get("EndY") or 0)])
        except ValueError:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steam", default=r"C:\Program Files (x86)\Steam\steamapps")
    ap.add_argument("--out", default="catalog.json")
    ap.add_argument("--icons", default="icons")
    ap.add_argument("--size", type=int, default=96)
    a = ap.parse_args()

    blocks, comps, cats = {}, {}, {}

    ws = os.path.join(a.steam, "workshop", "content", "244850")
    if os.path.isdir(ws):
        for m in sorted(os.listdir(ws)):
            base = os.path.join(ws, m)
            if not os.path.isdir(base):
                continue
            srcs = [Src(base)]
            for f in os.listdir(base):
                p = os.path.join(base, f)
                if f.lower().endswith(".bin") and zipfile.is_zipfile(p):
                    srcs.append(Src(p))
            before = len(blocks)
            for s in srcs:
                process(s, m, blocks, comps, cats)
            if len(blocks) > before:
                log(f"mod {m}: {len(blocks) - before} blocks")
    else:
        log("Workshop folder not found:", ws)

    content = os.path.join(a.steam, "common", "SpaceEngineers", "Content")
    texts = {}
    vanilla = None
    if os.path.isdir(content):
        texts = load_texts(content)
        vanilla = Src(content)
        before = len(blocks)
        process(vanilla, "vanilla", blocks, comps, cats)  # last: vanilla takes priority
        log(f"vanilla: {len(blocks) - before} blocks added or replaced")
    else:
        log("Game folder not found:", content)
    log(f"texts loaded: {len(texts)}, components found: {len(comps)}")

    def tr(k):
        return texts.get(k, k)

    try:
        from PIL import Image
    except ImportError:
        Image = None
        log("Pillow is not installed (pip install pillow): no icons.")

    os.makedirs(a.icons, exist_ok=True)
    ok = bad = 0
    fails = []
    out = {}
    total = len(blocks)
    for n, (key, b) in enumerate(blocks.items()):
        if n % 500 == 0:
            log(f"icons: {n}/{total} (OK {ok}, failed {bad})")
        src, icon = b.pop("_src"), b.pop("_icon")
        b["name"] = tr(b["name"])
        b["cats"] = sorted({tr(v["name"]) for v in cats.values() if key in v["items"]})
        b["icon"] = None
        if Image and icon:
            data = None
            for s in (src, vanilla):  # the block's own source first, then the game's icons
                if s is None:
                    continue
                try:
                    data = s.read(icon)
                except Exception:
                    data = None
                if data:
                    break
            if not data:  # wrong extension or folder: look for the same file name in the block's own source
                try:
                    data = src.find_like(icon)
                except Exception:
                    data = None
            reason = "file not found"
            if data:
                fn = re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".png"
                try:
                    im = open_image(data).convert("RGBA")
                    im.thumbnail((a.size, a.size))
                    im.save(os.path.join(a.icons, fn))
                    b["icon"] = fn
                    ok += 1
                except Exception as ex:
                    reason = f"unreadable ({ex})"
            if not b["icon"]:
                bad += 1
                if len(fails) < 25:
                    fails.append(f"  {key} [{b['mod']}] {icon} -> {reason}")
        out[key] = b

    result = {
        "version": 2,
        "blocks": out,
        "components": {k: {"mass": v["mass"], "name": tr(v["name"])} for k, v in comps.items()},
        "categories": sorted({tr(v["name"]) for v in cats.values()}),
    }
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    if fails:
        log("first icon failures:")
        for f in fails:
            log(f)
    log(f"DONE: {len(out)} blocks, {len(comps)} components, icons OK: {ok}, failed: {bad} -> {a.out}, {a.icons}/")


if __name__ == "__main__":
    LOG = open("scan_log.txt", "w", encoding="utf-8")
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