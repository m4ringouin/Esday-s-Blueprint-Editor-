#!/usr/bin/env python3
"""Convert a Space Engineers .mwm model (a subpart such as a drill head) into the .json format of the editor's models folder.

Double-click it (no arguments): it asks for a mod's Models folder and converts every model the catalog uses,
into the models folder next to this script (catalog.json must sit next to it, or you are asked for it).

Usage for one file:
    python mwm_to_json.py <geometry.mwm> --asset "Models\\Cubes\\Large\\DrillHead.mwm" [--out models]

  <geometry.mwm>  the file that holds the triangles. Use a *_LOD0 / *_LOD1 file (the plain DrillHead.mwm is only a small stub).
  --asset         the game path the editor will ask for. For subparts it is shown in the editor's selection line
                  ("Subparts: DrillHead MISSING (Models\\Cubes\\Small\\DrillHead.mwm)") - copy that path exactly.
  --out           folder to write the .json into (default: models, next to editor.html)
No extra packages needed.
"""
import argparse, hashlib, json, os, struct, sys


class R:
    def __init__(s, b, p=0): s.b, s.p = b, p
    def i32(s): v = struct.unpack_from('<i', s.b, s.p)[0]; s.p += 4; return v
    def f32(s): v = struct.unpack_from('<f', s.b, s.p)[0]; s.p += 4; return v
    def u8(s): v = s.b[s.p]; s.p += 1; return v
    def str(s):
        n = sh = 0
        while True:
            c = s.u8(); n |= (c & 127) << sh; sh += 7
            if not c & 128: break
        v = s.b[s.p:s.p + n].decode('utf8', 'replace'); s.p += n; return v
    def halves(s, count):
        v = struct.unpack_from('<%de' % count, s.b, s.p); s.p += 2 * count; return v
    def ints(s, count):
        v = struct.unpack_from('<%di' % count, s.b, s.p); s.p += 4 * count; return v


def read_tags(b):
    v = file_version(b); vn = int(''.join(ch for ch in v if ch.isdigit()) or 0)
    if vn and vn < 1066002: raise ValueError('very old model format (%s), not supported' % v)
    r = R(b); r.str(); c = r.i32()
    for _ in range(c): r.str()
    n = r.i32(); t = {}
    for _ in range(n): k = r.str(); t[k] = r.i32()
    return t


def body(b, t, k):
    if k not in t: raise SystemExit('This file has no "%s" block: it is probably a stub. Give me the matching _LOD0 / _LOD1 file.' % k)
    r = R(b, t[k]); r.str(); return r


R_end = [0]


def file_version(b):
    try:
        r = R(b); r.str(); r.i32(); return r.str()
    except Exception:
        return '?'


def parts(b, t, ver, nverts):
    """MeshParts, read the way the game reads them (VRage MyMeshPartInfo.Import / MyMaterialDescriptor.Read) for this file version."""
    r = body(b, t, 'MeshParts'); np_ = r.i32()
    if not 0 < np_ < 10000: raise ValueError('bad part count')
    indices, mats = [], []
    for _ in range(np_):
        r.i32()                                                       # material hash
        if ver < 1052001: r.i32()                                     # draw technique
        c = r.i32()
        if not 0 <= c <= 30000000: raise ValueError('bad index count')
        idx = r.ints(c)
        if c and (max(idx) >= nverts or min(idx) < 0): raise ValueError('index out of range')
        first = len(indices) // 3; indices.extend(idx); last = len(indices) // 3 - 1
        tex, isglass = {}, False
        if r.u8():
            r.str()                                                   # material name
            if ver < 1052002:
                d, n = r.str(), r.str()
                if d: tex['ColorMetalTexture'] = d
                if n: tex['NormalGlossTexture'] = n
            else:
                for _ in range(r.i32()): kk = r.str(); tex[kk] = r.str()
            if ver >= 1068001:
                for _ in range(r.i32()): r.str(); r.str()               # user data
            if ver < 1157001:
                for _ in range(7): r.f32()                            # specular power, diffuse colour, extra data
            tech = str(r.i32()) if ver < 1052001 else r.str()
            if tech == 'GLASS':
                isglass = True
                if ver >= 1043001: r.str(); r.str(); r.u8()
                else:
                    for _ in range(4): r.f32()
        mats.append({'LastTri': last, 'FirstTri': first, 'IsGlass': isglass, 'ColorMaskHSV': {'X': 0, 'Y': 0, 'Z': 0}, 'ExportedMaterialName': None,
                     'AddMapsTexture': tex.get('AddMapsTexture'), 'AlphamaskTexture': tex.get('AlphamaskTexture'),
                     'ColorMetalTexture': tex.get('ColorMetalTexture') or tex.get('DiffuseTexture'), 'NormalGlossTexture': tex.get('NormalGlossTexture') or tex.get('NormalTexture')})
    R_end[0] = r.p
    return indices, mats


def convert(path, asset):
    b = open(path, 'rb').read(); t = read_tags(b)
    r = body(b, t, 'Vertices'); n = r.i32()
    if 0 <= n and r.p + n * 8 <= len(b):
        pos = r.halves(n * 4)
        # packed positions: x, y, z are halves scaled by the 4th value (models bigger than 1 m store w = 2, 3, 4...)
        positions = [pos[i] * (pos[i - i % 4 + 3] or 1) for i in range(n * 4) if i % 4 != 3]
    elif 0 <= n and r.p + n * 12 <= len(b):                         # old files: plain 3 floats per vertex
        positions = list(struct.unpack_from('<%df' % (n * 3), b, r.p))
    else:
        raise ValueError('vertex block not understood (file version %s)' % file_version(b))
    r = body(b, t, 'TexCoords0'); n2 = r.i32(); uvs = list(r.halves(n2 * 2))
    r = body(b, t, 'BoundingBox'); bb = [r.f32() for _ in range(6)]
    nverts = len(positions) // 3
    nxt = min([o for o in t.values() if o > t['MeshParts']] or [len(b)])     # where the MeshParts block ends
    vs = file_version(b); ver = int(''.join(ch for ch in vs if ch.isdigit()) or 0)
    indices, mats = parts(b, t, ver, nverts)
    return {'asset': asset, 'patternScale': 1, 'positions': positions, 'uvs': uvs, 'indices': indices, 'materials': mats,
            'bbox': {'Min': {'X': bb[0], 'Y': bb[1], 'Z': bb[2]}, 'Max': {'X': bb[3], 'Y': bb[4], 'Z': bb[5]}}, 'dummies': {}}


def file_name(asset):
    return asset.replace('\\', '_').replace('.', '_') + '_' + hashlib.md5(asset.encode()).hexdigest()[:8].upper() + '.json'


def workshop_dirs():
    """Space Engineers workshop folders of every Steam library on this PC."""
    libs = [r'C:\Program Files (x86)\Steam\steamapps']
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'); libs.insert(0, os.path.join(winreg.QueryValueEx(k, 'SteamPath')[0], 'steamapps'))
    except Exception:
        pass
    for lib in list(libs):
        vdf = os.path.join(lib, 'libraryfolders.vdf')
        if os.path.exists(vdf):
            for m in __import__('re').findall(r'"path"\s+"([^"]+)"', open(vdf, encoding='utf-8', errors='ignore').read()):
                libs.append(os.path.join(m.replace('\\\\', '\\'), 'steamapps'))
    seen, out = set(), []
    for lib in libs:
        d = os.path.normcase(os.path.join(lib, 'workshop', 'content', '244850'))
        if d not in seen and os.path.isdir(d): seen.add(d); out.append(d)
    return out


def batch():
    """Double-click mode: convert every model of a mod folder that the catalog uses, into models/ next to this script."""
    here = os.path.dirname(os.path.abspath(sys.argv[0]))
    cat = os.path.join(here, 'catalog.json')
    if not os.path.exists(cat):
        cat = input('catalog.json was not found next to this script. Drag it here (or type its path) and press Enter:\n> ').strip().strip('"')
    c = json.load(open(cat, encoding='utf-8')); c = c.get('blocks', c)
    assets = {}                                                      # file name (lower case) -> game path the editor asks for
    for v in c.values():
        if isinstance(v, dict) and v.get('model'): assets.setdefault(v['model'].replace('/', '\\').split('\\')[-1].lower(), set()).add(v['model'])
    while True:
        src = input('Drag a folder with .mwm files here (a mod folder, or its Models folder) and press Enter.\n'
                    'Or just press Enter to scan all your Steam workshop mods:\n> ').strip().strip('"').strip("'")
        roots = [src] if src else workshop_dirs()
        roots = [r for r in roots if os.path.isdir(r)]
        if roots: break
        print('  That folder was not found.' if src else '  The Steam workshop folder was not found: drag a folder instead.')
    out = os.path.join(here, 'models'); os.makedirs(out, exist_ok=True)
    files = {}
    for r in roots:
        print('Looking in', r)
        for root, _, names in os.walk(r):
            for n in names:
                if n.lower().endswith('.mwm'): files[n.lower()] = os.path.join(root, n)
    ok = skipped = failed = kept = 0; fails = []
    for low, path in sorted(files.items()):
        if low not in assets: skipped += 1; continue                 # LODs, build stages, models no block uses
        base = low[:-4]; last_err = None
        for cand in [path] + [files[base + s + '.mwm'] for s in ('_lod0', '_lod1') if base + s + '.mwm' in files]:
            try:
                d = convert(cand, '')
            except SystemExit:
                continue                                             # a stub without triangles: try its LOD file
            except Exception as ex:
                last_err = '%s (%s, %s)' % (cand, ex, file_version(open(cand, 'rb').read(64))); continue
            for asset in sorted(assets[low]):                        # blocks may spell the same path differently: one file per spelling
                d['asset'] = asset; fn = os.path.join(out, file_name(asset))
                if os.path.exists(fn):                               # keep models made by the in-game exporter (they carry dummies / subparts)
                    with open(fn, encoding='utf-8', errors='ignore') as f: old = f.read()
                    if '"dummies":{}' not in old.replace(' ', ''): kept += 1; continue
                with open(fn, 'w') as f: json.dump(d, f, separators=(',', ':'))
                ok += 1
            print('  %s' % os.path.basename(cand)); break
        else:
            failed += 1
            if last_err: print('  could not read %s' % last_err); fails.append(last_err)
    if fails:
        with open(os.path.join(here, 'failed_models.txt'), 'w', encoding='utf-8') as f: f.write('\n'.join(fails))
    print('\nDone: %d models written to %s, %d kept (already exported by the game), %d files not used by any block, %d could not be converted.' % (ok, out, kept, skipped, failed) + ('\nThe list of models that failed is in failed_models.txt next to this script.' if fails else ''))


if __name__ == '__main__' and len(sys.argv) == 1:
    try:
        batch()
    except Exception as ex:
        print('\nError: %s' % ex)
    input('\nPress Enter to close.')
    sys.exit()

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('mwm'); ap.add_argument('--asset', required=True); ap.add_argument('--out', default='models')
    a = ap.parse_args()
    d = convert(a.mwm, a.asset); os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, file_name(a.asset))
    with open(fn, 'w') as f: json.dump(d, f, separators=(',', ':'))
    print('%s: %d vertices, %d triangles, %d materials -> %s' % (os.path.basename(a.mwm), len(d['positions']) // 3, len(d['indices']) // 3, len(d['materials']), fn))
