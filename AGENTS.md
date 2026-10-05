# AGENTS.md - Tram Distribution Office (context for AI agents)

Read this before changing anything. It is the condensed working knowledge of the sessions that
built this mod: what exists, how it is built and tested, which engine facts it stands on, and the
traps that already cost time. `README.md` is the player-facing page.

---

## 1. What this is

A mod for **Workers & Resources: Soviet Republic 1.1.1.9** (`SOVIET64.exe`, image base
0x140000000; every address below is an RVA valid for this build only): a distribution office for
**cargo trams**. The game's road distribution office plans and dispatches the trams natively; the
`tramdo` plugin (C++, MSVC x64, /MT) only lets trams in and removes one fuel check. Two buildings,
`tramdo_small` (tram sets up to 30 m) and `tramdo_large` (all), on the game's small tram depot
layout. Runs on **Republic Mod Loader (RML)**, Workshop item 3787969749 (TesmioLoader API 3/4).

Cargo trams come from other authors' mods (e.g. collection 3586298879: tram packs 3563301077,
3586205860, tram cargo stations 3563264112, 3586206025). Stay compatible; never bundle them.

## 2. Ground rules

- **Branches:** commit only to `unstable`. `dev` takes pull requests from `unstable` (two
  approvals); `main` takes pull requests from `dev` (code-owner approval, @aislanfoina). The owner
  may merge with admin bypass. Never push to `dev`/`main` directly.
- **Origin of this repo:** it is exported from a private mixed workspace (`wrsr`, which also holds
  the owner's other mods) by `tools/export_tramdo.py`; the export replaces everything except
  `.git`. If you work in this repo directly, say so in the commit, so the workspace can be synced.
- **Commits** are authored as the owner; add a `Co-Authored-By:` line for the AI.
- **Never** enter Steam or other credentials, never change the owner's RML configuration (which
  plugins/items are enabled) without asking, never publish to the Workshop without an explicit go.
- Keep file formats byte-exact: `.gitattributes` is `* -text`. Write `.ini`/`.txt` the game reads
  with CRLF. Hook explanations for the owner: brief and high-level.

## 3. Repository map

```
mod/plugins/tramdo/      tramdo.cpp (the whole plugin), tramdo.ini (settings), tramdo.rml.json (RML manifest,
                         id tram-do.tramdo, priority 9780), package.txt ("tram_do": ships inside that item)
mod/packages/tram_do/    the item: tramdo_small/ and tramdo_large/ (model.nmf, building.ini, renderconfig.ini,
                         building.bbox, building.fire, imagegui.png), material/ (shared .mtl + .dds),
                         workshopconfig.ini (local id 9000310), previewimage.png
tools/tramdo_layout.py   the layout: tram_depo_small.ini's geometry lines, x stretched (SIZES: 1.0 / 1.5)
tools/tramdo_scene.py    Blender: the buildings, building.ini, previews (+ preview-only track, see 5)
tools/tramdo_workshop.py item config, store page (Steam BBCode), poster; workshop_items() for the uploader
tools/build_tramdo.py    stages: textures | yards | item | images
tools/workshop_upload.py Steam Workshop updates through the game's steam_api64.dll (owner runs it)
tools/rehelp.py, pe.py   static RE helpers (capstone): Bin(EXE).read/dis/xrefs/find_str/func_end/callers
tools/dev/               memprobe.py (read-only process memory), rml_launch.py, gdrive.py (drive the game window)
```

## 4. Build, install, run

- `.\build.ps1` compiles every `mod\plugins\*` into `build\`; `-Install` (game and RML closed) copies
  `mod\packages\tram_do` to `<game>\media_soviet\workshop_wip\9000310`, the plugin into its
  `plugins\`. Staged copy then swap: RML once scanned an item mid-copy and missed its plugins.
- In RML: Development tab (untick *Hide Disabled*), enable item 9000310 and the `tramdo` plugin.
  Changing that is the owner's call.
- The loader log `rml/logs/rml-runtime.log` shows `tramdo` lines: hooks (chained or not), the tram
  group id, length limits, the first `log_decisions` admit/refuse decisions, the fuel bypass.
- Content: `python tools/build_tramdo.py` (Blender 5.x at the default path or `BLENDER`).

## 5. How it works

**Design** (found by experiment, see 9): the road distribution office (`$TYPE_DISTRIBUTION_OFFICE`,
building type 0x2B) **with `$SUBTYPE_TRAM`** on a tram-depot layout. The train office (0x34) wants
railway sidings ("Building needs rail connection"); a road office without the subtype finds no
route for its trams.

**Plugin, hook 1 - CanUseBuilding 0x3E2900**(game, building, vehicle type, flag, x): asked by the
purchase list, vehicle assignment and production-line delivery. For buildings whose object name
starts with `object_prefix` (`tramdo`) the plugin answers: cargo vehicles of the "tram" train group
yes (cargo class at vt+0x8600 != PASSANGER 7), all else no; plus `limit_<object> = metres` (set
length via the game's 0x25C270). Everything else chains to the original.

**Plugin, hook 2 - road office update 0x1C6050**(game, building): with fuel on (game+0x5B0 == 2) it
skips vehicles whose fuel (vehicle+0x5F0) is <= 0 and tries to refuel them; electric vehicles keep
+0x5F0 = 0, so trams never left. For our offices only, the plugin sets game+0x5B0 = 0 around the
original call. Assumes building updates do not run in parallel threads.

Both hooks chain after another plugin's 14-byte `FF 25 00000000 <addr>` jump or onto the live bytes.

**Models:** buildings only. The game draws the yard's tram track and trolley wire itself along
`$CONNECTION_TRAMROAD_DEAD` / `$CONNECTION_TRAMTROLLEYS_DEAD`, joined with curves, on the terrain:
the vanilla depot's and end station's models contain no rails, no wires and no ground plate. A
raised ground plate would bury that track. A strip below ground stretches the model box over the
whole footprint (the vanilla depot does the same). The previews add ground, track and wires in a
separate mesh that is never exported (`track_plan`, `preview_yard`); it approximates where the game
draws them and should be checked against in-game screenshots. Buildings stand where the tracks
leave room: shed over the lanes, dispatch wing between shed and station track, substation in the
south-east corner beyond the exit curve, sand tower and a lamp in the south-west corner.

## 6. Engine facts used (1.1.1.9)

- Trams are rail vehicles: `$TYPE VEHICLETYPE_RAIL_LOCOMOTIVE` + `$TRAINGROUP_TRAM`, wagons via
  `$TRAINSET`; they use road infrastructure (tram depot = `$TYPE_ROADDEPO` + `$SUBTYPE_TRAM`; tram
  stations = `$TYPE_CARGO_STATION` + `$SUBTYPE_TRAM` + `$ROADVEHICLE_TRAM`).
- Building: +0x318 type descriptor (ident string at +0, building type at +0x360, subtype +0x364).
  Types: 0x0B ENGINE (conveyor engine / pump), 0x0E ROADDEPO, 0x2B DO, 0x34 DO_RAIL; subtype TRAM 0x24.
- Vehicle instance: +0x1708 its vehicle type; +0x5F0 fuel; +0x680 route list, +0x698 stop index.
- Vehicle type: +0x200 ident; +0x294 kind (1 ROAD, 3 RAIL_VAGON, 4 RAIL_LOCOMOTIVE, 6 SHIP, 8 AIRPLANE,
  10 HELI); +0x7A78 length (float, m); +0x7C08/+0x7C10 `$TRAINSET` vector, 0x110-byte entries (name;
  resolved wagon type at +0x100); +0x8600 cargo class (COVERED 0 .. PASSANGER 7 .. WASTE 17, 18 none),
  +0x8604 capacity; +0x8680 byte0 electric; +0x96B8 std::vector<int> train groups.
- 0x25C7B0(game = exe+0x9D4F10, "tram") = the tram group id (11 in a modded game, looked up live).
- 0x25C270(vt) = set length: vt+0x7A78 (coupler adjustments when vt+0x2A0 is set) plus each
  `$TRAINSET` wagon's +0x7A78. The train office compares the same sum with its max train length
  (office +0xD70; +0xD74 min wagons) in the matcher 0x1DE2B0.
- Office planning: 0x1C6050 -> 0x1E2380 (transfers into office +0xD58, 128-byte records) ->
  0x1E3BD0 per record (source half +0x10 building, +0x18 kind, +0x28 free fraction, +0x30 stock,
  +0x38 capacity; destination half from +0x48) -> 0x1E4BC0. Kinds 0/1 direct, 2/3 via conveyor,
  4/5 waste. The pass already looks *through* a conveyor engine to the storage, but not through a
  conveyor transfer building.
- Dispatch: 0x1E5350(game, vehicle, office) -> 0x1E5480 / 0x1E5BA0 (route) -> 0x6B8EB0 (start).
- Matcher 0x1DE2B0 gives waste transfers only to cargo class 0x11 vehicles.
- "Some buildings have unsupported settings" / "unsupported with unloading" = status text from
  0x741170 (road office): UI only, dispatch still works.
- Fleet tally 0x1E1740 counts vehicle kinds 1/6/8/10 only: kind 4 (trams) is not tallied, so the
  office may send more trams than a task needs. Not observed as a problem yet.

## 7. Settings (`mod/plugins/tramdo/tramdo.ini`)

`enabled`, `object_prefix` (default `tramdo`: every building whose object name starts with it is a
tram office, so the old test buildings tramdo_a..d are covered too), `log_decisions`,
`limit_<object> = metres` (`limit_tramdo_small = 30`). Small and medium cargo tram sets run
21-26 m, the large H51 sets 35-41 m.

## 8. Saves and compatibility

A save stores buildings by ident `<item id>/<object>`: moving the objects to another item id (the
Steam id on publishing) orphans them in old saves. The local id is 9000310 until the item exists on
Steam. The plugin only answers for `tramdo*` buildings and chains every other call, so other
plugins hooking the same functions keep working.

## 9. Testing (what was done)

Experiments with the prototype item (workspace only, local id 9000300, the vanilla depot model):
1. Train office + tram depot layout, no plugin: no trams offered, assignment refused.
2. With the plugin: trams buyable and assignable, but the train office wants rail connections.
3. Road office (C with `$SUBTYPE_TRAM`, D without): connections found, stations accepted as tasks;
   every wagon takes an office place (6 -> full; raised to 24).
4. Trams drive in and out; D: "Some vehicle cannot find route" -> the subtype is required.
5. No dispatch: the fuel check (electric trams) -> hook 2.
6. First native dispatch, then full cycles: steel (open), gravel through a conveyor (after removing
   a conveyor transfer between station and storage), waste (after the owner lowered a 20 % pickup
   threshold). Fluids untested.

Still to test in game: the two yard buildings (placement, the game's track through the shed and
the yard, buildings clear of it), the cargo-only filter (passenger trams refused) and the 30 m
limit (the H51 large set refused by the small yard, medium sets admitted).

## 10. Traps that already cost time

- The game shows models **mirrored**: lettering is modelled mirrored, and the README renders are
  flipped to look like the game.
- RML's Development tab shows nothing with *Hide Disabled* on.
- RML scanning an item mid-copy missed its `plugins/` folder: install by staging and renaming.
- Uploading an item that carries plugins fails ("Error code 2") while RML has the DLLs loaded:
  start the game from Steam without RML for the upload.
- `$VISIBILITY` in workshopconfig.ini is the game's numbering: 0 unpublished, 1 friends, 2 PUBLIC
  (Steam's own enum has 0 = public).
- `tools/workshop_upload.py` must run outside any sandbox (SteamAPI_Init fails in one); the owner
  runs it from their own terminal.
- Bash heredocs mangle backslashes: write scripts containing escapes with a file tool.

## 11. Status and open items

- Core office: done (purchase, assignment, parking, dispatch, full cycles).
- Yards, size limit, cargo-only filter: built, to be tested in game (section 9).
- Workshop: not published. `python tools/workshop_upload.py tram_do create` (owner) gives the Steam
  id for `ITEMS` in tools/tramdo_workshop.py; then rebuild, install and upload.
- Open: over-dispatch (fleet tally skips trams); wagons listed as separate office entries
  (cosmetic); the fuel toggle assumes no parallel building updates; the office judges a station
  fed through a conveyor *transfer* by the transfer (looks full).

## 12. Links

- Repo: https://github.com/aislanfoina/wrsr-tramdo
- Republic Mod Loader: https://steamcommunity.com/sharedfiles/filedetails/?id=3787969749
- RML source: https://github.com/Ultimate-Universe/WRSR-RepublicModLoader
- TesmioLoader: https://github.com/MaxLegend/TesmioLoader (branch master)
- Cargo tram collection used for testing: https://steamcommunity.com/workshop/filedetails/?id=3586298879
