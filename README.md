# BP-Editor-Browser-Esday

https://youtu.be/jAPOnOPp8-s

<img width="1909" height="923" alt="BP Editor" src="https://github.com/user-attachments/assets/a3833bf4-44cf-4832-b9f9-dad5d74c7690" />

# SE Blueprint Editor

A browser-based editor for **Space Engineers** blueprints (`bp.sbc`). Open a ship, edit it in 3D, paint it, swap blocks and download a new blueprint, without starting the game.

> ⚠️ **Work in progress.** This project is still under active development, and all of it was vibe-coded with AI. Expect bugs, and **always keep a backup of your blueprints** before overwriting them.

## Features

- **3D view** of your ship with the real block models, textures and armor skins (once you have converted them, see below)
- **Edit:** place, delete, move and rotate blocks, copy / paste, mirror, stretch or shrink a section, with full undo / redo
- **Swap blocks:** armor tiers (Light → Heavy → …) and tech tiers (2x / 4x / 8x / 10x), with your own swap lists
- **Paint:** brush, bucket, gradients, image projection, over 100 procedural patterns, Star Trek palettes and your own palettes, plus skins
- **3D model import (.obj / .stl):** turns a model into armor blocks, with slopes, long slopes and mirrored halves
- **Info:** components, mass, PCU, thrust per direction, power, block list by category
- **View tools:** quad view, ghost hull, layer slicing, thruster flames and drill range
- **Themes:** Default or STC (Star Trek Continuum style)
- Works with **vanilla and modded blocks** (Workshop mods)

## Requirements

- **Windows** with Space Engineers installed through Steam
- **Python 3.10 or newer**: [python.org/downloads](https://www.python.org/downloads/) (tick *"Add Python to PATH"* during the install)
- **Pillow** (image library), needed for icons, textures, skins and glow:
  ```
  pip install --upgrade pillow
  ```
- A recent browser: Chrome, Edge or Firefox

## Installation

### 1. Get the files

Download this repository (green **Code** button → **Download ZIP**) and unzip it to its own folder, for example `C:\SE-Blueprint-Editor\`.

### 2. Build the block catalog (required)

Double-click **`scan_catalog.py`**, or run it from a terminal in the folder:

```
python scan_catalog.py
```

It reads the game and every Workshop mod you have downloaded, and writes:

- `catalog.json`: every block with its name, size and stats
- `icons/`: the block icons

If Steam is not installed in the default place, give it your `steamapps` folder:

```
python scan_catalog.py --steam "D:\SteamLibrary\steamapps"
```

Run it again whenever you add or update mods.

### 3. Block models (optional, for the real 3D look)

Without models, blocks show as plain boxes. Everything still works.

- **Mod models:** double-click **`mwm_to_json.py`**. When it asks for a folder, press **Enter** to convert every Workshop mod the catalog uses, or drag one mod folder into the window. The models go into `models/`, and any file that could not be converted is listed in `failed_models.txt`.
- **One model by hand** (for example a drill head):
  ```
  python mwm_to_json.py "path\to\DrillHead_LOD1.mwm" --asset "Models\Cubes\Large\DrillHead.mwm"
  ```

### 4. Armor skins (optional)

```
python convert_skins.py
```

Converts the game's armor skins into `skins/` and writes `skins.json`.

### 5. Glow masks (optional, after step 3)

```
python make_glow.py
```

Makes glowing parts (Glowing armor, Neon skins, lights) light up in the 3D view.

All of these scripts accept `--steam "D:\...\steamapps"` if Steam is not in the default place.

## Running the editor

The editor needs to be opened **through a small local web server**. That is how it finds `catalog.json`, the models and the skins on its own. Open a terminal in the editor folder and run:

```
python -m http.server 8000
```

Then open **http://localhost:8000/editor.html** in your browser. Leave the terminal open while you use the editor.

> You can also double-click `editor.html` directly, but then the browser won't let it read the other files. You will have to load `catalog.json` by hand with the **Files** card, and models and skins won't show.

### Your folder should look like this

```
SE-Blueprint-Editor/
├── editor.html
├── scan_catalog.py
├── mwm_to_json.py
├── convert_skins.py
├── make_glow.py
├── catalog.json        ← made by scan_catalog.py
├── icons/              ← made by scan_catalog.py
├── models/             ← made by mwm_to_json.py (optional)
├── skins/              ← made by convert_skins.py (optional)
├── skins.json          ← made by convert_skins.py (optional)
└── textures/           ← made by make_glow.py (optional)
```

## Editing a blueprint

1. Your blueprints are in `%AppData%\SpaceEngineers\Blueprints\local\<ship name>\`.
2. In the editor, **Ship** tab → **Files** → **Blueprint**, pick that ship's `bp.sbc`.
3. Edit the ship. Press **⌨** for the controls and **?** next to any card for help.
4. Click **Download…** to save a new `bp.sbc`.
5. Copy the new file into a **new** blueprint folder, or over the old one after backing it up.

> **Important:** if the blueprint folder also has a `bp.sbcB5` file, delete it. The game loads that cached copy instead of your edited `bp.sbc`.

## Notes

- Nothing is uploaded anywhere. The editor runs entirely in your browser, on your computer.
- The game files, models, textures and mod assets belong to Keen Software House and the mod authors. They are **not** part of this repository: each user converts them from their own game install.
- Bug reports and ideas are welcome in the Issues tab.
