# AGENTS.md - Tram Distribution Office (context for AI agents)

Read this before changing anything. It is the condensed working knowledge of the sessions that
built this mod: what exists, how it is built and tested, which engine facts it stands on, and the
traps that already cost time. `README.md` is the player-facing page.

---

## 1. What this is

A mod for **Workers & Resources: Soviet Republic 1.2.0.9** (`SOVIET64.exe`, image base
0x140000000; every address the plugin uses is an RVA valid for this build only - ported from
1.1.1.9 via 1.1.1.13 and 1.2.0.8 on 2026-11-24/25, see section 6; on 1.2.0.9 its three hooks install
in game and the tram length check is recognised): a distribution office for
**cargo trams**. The game's road distribution office plans and dispatches the trams natively; the
`tramdo` plugin (C++, MSVC x64, /MT) only lets trams in and removes one fuel check. Two buildings,
`tramdo_small` (the tram end station's layout, 6 lanes, tram sets up to 30 m) and `tramdo_large`
(the big tram depot's, 8 lanes stretched to 50 m, all sets). One tram set per parking lane. Runs on **Republic Mod Loader (RML)** (TesmioLoader API 3/4); RML now ships in the **WRSR
Ultimate Pack** (Workshop 3838038411, another modder's item, built for 1.1.1.13; its RML core runs
1.2.0.9, its own plugins do not - test with them off, see the Space Race AGENTS.md section 9 for the
loader config); the original RML item 3787969749 is gone. **Hooks never chain onto unknown bytes**
since 2026-11-24 (the 1.1.1.9 build on the Workshop does, and hooked three wrong addresses on 1.2.0.8
and on 1.2.0.9). Its development build and the subscribed item share the plugin id `tram-do.tramdo`:
in a test keep the subscribed item out of the loader playlist, or both load.

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
                         workshopconfig.ini (Steam id 3814373926), previewimage.png
tools/tramdo_layout.py   the layouts: SIZES = source ini (tram_endstation / tram_depo_big) + x stretch; cost_stops
tools/tramdo_scene.py    Blender: the buildings, building.ini, previews (+ preview-only track, see 5)
tools/tramdo_workshop.py item config, store page (Steam BBCode), poster; workshop_items() for the uploader
tools/build_tramdo.py    stages: textures | yards | item | images
tools/workshop_upload.py Steam Workshop updates through the game's steam_api64.dll (owner runs it)
tools/rehelp.py, pe.py   static RE helpers (capstone): Bin(EXE).read/dis/xrefs/find_str/func_end/callers
tools/dev/               memprobe.py (read-only process memory), rml_launch.py, gdrive.py (drive the game window)
```

## 4. Build, install, run

- `.\build.ps1` compiles every `mod\plugins\*` into `build\`; `-Install` (game and RML closed) copies
  `mod\packages\tram_do` to `<game>\media_soviet\workshop_wip\3814373926`, the plugin into its
  `plugins\`. Staged copy then swap: RML once scanned an item mid-copy and missed its plugins.
- In RML: Development tab (untick *Hide Disabled*), enable item 3814373926 and the `tramdo` plugin.
  Changing that is the owner's call.
- The loader log `rml/logs/rml-runtime.log` shows `tramdo` lines: hooks (chained or not), the tram
  group id, length limits, the first `log_decisions` admit/refuse decisions, the fuel bypass.
- Content: `python tools/build_tramdo.py` (Blender 5.x at the default path or `BLENDER`).

## 5. How it works

**Design** (found by experiment, see 9): the road distribution office (`$TYPE_DISTRIBUTION_OFFICE`,
building type 0x2B) **with `$SUBTYPE_TRAM`** on a tram-depot layout. The train office (0x34) wants
railway sidings ("Building needs rail connection"); a road office without the subtype finds no
route for its trams.

**Plugin, hook 1 - CanUseBuilding 0x401C70**(game, building, vehicle type, flag, x): asked by the
purchase list, vehicle assignment and production-line delivery. For buildings whose object name
starts with `object_prefix` (`tramdo`) the plugin answers: cargo vehicles of the "tram" train group
yes (cargo class at vt+0x8650 != PASSANGER 7), all else no; plus `limit_<object> = metres` (set
length via the game's 0x2773D0). Everything else chains to the original.

**Plugin, hook 2 - road office update 0x1E02E0**(game, building): with fuel on (game+0x5D8 == 2) it
skips vehicles whose fuel (vehicle+0x5F0) is <= 0 and tries to refuel them; electric vehicles keep
+0x5F0 = 0, so trams never left. For our offices only, the plugin sets game+0x5D8 = 0 around the
original call. Assumes building updates do not run in parallel threads.

**Plugin, hook 3 - missing research 0x315C50**(game, building descriptor): fills game +0x11830
(std::vector of research records) with the researches still blocking a building; the build menu
treats a non-empty list as locked. A road office unlocks with `distribution_office` (it unlocks
building type 0x2B); for our offices the plugin appends the `research` setting's record
(`railway_distribution_office`) while it is unfinished, growing the vector with the game's own
0x41A0 as the function itself does. The yards carry no `$STYLE_FLAG` (the vanilla office's
`modern_industry` flag would also lock them behind the 1958 Modern Industry research).

All hooks chain after another plugin's 14-byte `FF 25 00000000 <addr>` jump or onto the live bytes.

**Models:** buildings only. The game draws the yard's tram track and trolley wire itself along
`$CONNECTION_TRAMROAD_DEAD` / `$CONNECTION_TRAMTROLLEYS_DEAD`, joined with curves, on the terrain:
the vanilla depot's and end station's models contain no rails, no wires and no ground plate. A
raised ground plate would bury that track. A strip below ground stretches the model box over the
whole footprint (the vanilla depot does the same). The game paves the footprint dark itself. The
previews add that paving and rails along the layout's own tram paths (its PID points, smoothed by
centripetal Catmull-Rom, long straights pinned) in a separate mesh that is never exported
(`preview_yard`). `tramdo_scene.Yard` reads a layout in lane coordinates (u along the lanes, v
across; lanes run along x in the depot, along z in the end station): the shed covers the lanes
(cut back where the trams' paths still curve, `shed_extent`), the dispatch wing stands between
shed and station track facing it, and the substation, sand tower and lamps go where a clearance
search (`find_spot`, `obstacles`) finds room clear of every path, track, wire and road piece.

## 6. Engine facts used

Offsets and the addresses the plugin uses are **1.2.0.9** (checked by `tools/port_scan.py --verify`;
hooks installed in game 2026-11-25). 1.2.0.8 moved data and structures; its values came from the new
code alone (see the Space Race AGENTS.md, section 6, for the method). 1.2.0.9 came from pairing the
1.2.0.8 and 1.2.0.9 executables with `tools/port_pair.py`: code moved -0x170..+0x2D0, the game
object's research and blocking vectors +8, everything else here unchanged. The addresses marked
*(1.1.1.9)* were not re-derived: they are a starting point, not an address (1.2.0.8 moved that
region of code by about +0x1A000).

- Trams are rail vehicles: `$TYPE VEHICLETYPE_RAIL_LOCOMOTIVE` + `$TRAINGROUP_TRAM`, wagons via
  `$TRAINSET`; they use road infrastructure (tram depot = `$TYPE_ROADDEPO` + `$SUBTYPE_TRAM`; tram
  stations = `$TYPE_CARGO_STATION` + `$SUBTYPE_TRAM` + `$ROADVEHICLE_TRAM`).
- Building: +0x318 type descriptor (ident string at +0, building type at +0x368, subtype +0x36C).
  Types: 0x0B ENGINE (conveyor engine / pump), 0x0E ROADDEPO, 0x2B DO, 0x34 DO_RAIL; subtype TRAM 0x24.
- Vehicle instance: +0x1748 its vehicle type; +0x5F0 fuel; +0x508 retry timer; +0x680 route list,
  +0x698 stop index *(1.1.1.9)*.
- Vehicle type (stride 0xA0C8): +0x200 ident; +0x2B8 kind (1 ROAD, 3 RAIL_VAGON, 4 RAIL_LOCOMOTIVE,
  6 SHIP, 8 AIRPLANE, 10 HELI); +0x7AA4 length (float, m); +0x7C58/+0x7C60 `$TRAINSET` vector,
  0x110-byte entries (name; resolved wagon type at +0x100); +0x8650 cargo class (COVERED 0 ..
  PASSANGER 7 .. WASTE 17, 18 none), +0x8654 capacity; +0x9708 std::vector<int> train groups.
- 0x277950(game = exe+0xA1EF20, "tram") = the tram group id (66 callers pass "tram", "metro", ...).
- 0x2773D0(vt) = set length: vt+0x7AA4 (coupler adjustments when vt+0x7AB0 > 0) plus each
  `$TRAINSET` wagon's +0x7AA4. The train office compares the same sum with its max train length
  (office +0xD70; +0xD74 min wagons) in the matcher 0x1DE2B0 *(1.1.1.9)*.
- Office planning *(1.1.1.9)*: 0x1C6050 -> 0x1E2380 (transfers into office +0xD58, 128-byte records) ->
  0x1E3BD0 per record (source half +0x10 building, +0x18 kind, +0x28 free fraction, +0x30 stock,
  +0x38 capacity; destination half from +0x48) -> 0x1E4BC0. Kinds 0/1 direct, 2/3 via conveyor,
  4/5 waste. The pass already looks *through* a conveyor engine to the storage, but not through a
  conveyor transfer building.
- Dispatch *(1.1.1.9)*: 0x1E5350(game, vehicle, office) -> 0x1E5480 / 0x1E5BA0 (route) -> 0x6B8EB0 (start).
- Matcher 0x1DE2B0 *(1.1.1.9)* gives waste transfers only to cargo class 0x11 vehicles.
- Research: records in game +0x11818/+0x11820, 0x138 bytes (128 in a new 1.2.0.9 game, checked live):
  name +0 (inline), progress +0x120 (>= 1.0 done). *(1.1.1.9, 0xE8-byte records:* +0x60/+0x68 buildings
  it unlocks (all must be done), +0x78/+0x80 one-is-enough unlocks, +0xA8/+0xB0 used by 0x2F7960*)*. The parser 0x2F3C60 *(1.1.1.9)* resolves
  `$UNLOCK_BUILDING_TYPE` / `_STYLE_FLAG` (descriptor +0x20D) to descriptor pointers at load.
  Building descriptors: table at exe+0xA30AF0, 0xE98 bytes, ident +0, type +0x368. game +0x10C0 set
  = research off. Unlocks: distribution_office -> type 43 (0x2B), railway_distribution_office -> 52.
- "Some buildings have unsupported settings" / "unsupported with unloading" = status text from
  0x741170 *(1.1.1.9)* (road office): UI only, dispatch still works.
- Fleet tally 0x1E1740 *(1.1.1.9)* counts vehicle kinds 1/6/8/10 only: kind 4 (trams) is not tallied, so the
  office may send more trams than a task needs. Not observed as a problem yet.
- **Purchase lists (1.2.0.9, function chunk 0x3FCCDA):** an office window has two buy buttons,
  truck-$ and truck-₽ (the rouble sign looks like a P). Before asking CanUseBuilding, each list
  drops the types without a price in its currency: $ lists (modes 1/5) need `$COST_USD` (vt+0x860C),
  ₽ lists (modes 2/6) need `$COST_RUB` (vt+0x8610). The tram packs give only `$COST_RUB` (the H51s
  `$COST_RUB 1`), so the trams are in the **₽ list only** - an empty $ list is expected. Assignment
  (0x2CE7F0, `gui_building_assign_ok/fail`): the single-vehicle path asks CanUseBuilding with no
  kind gate; a multi-vehicle selection requires kind 1 (road) for each. Not re-tested in game.

## 7. Settings (`mod/plugins/tramdo/tramdo.ini`)

`research` (default `railway_distribution_office`; empty = only the road office's own research),
`enabled`, `object_prefix` (default `tramdo`: every building whose object name starts with it is a
tram office), `log_decisions`,
`limit_<object> = metres` (`limit_tramdo_small = 30`). Small and medium cargo tram sets run
21-26 m, the large H51 sets 35-41 m.

## 8. Saves and compatibility

A save stores buildings by ident `<item id>/<object>`: moving the objects to another item id (the
Steam id on publishing) orphans them in old saves. The item is 3814373926 on Steam (created unpublished
2026-10-05; it was local id 9000310 before, so buildings placed from that are orphaned). The plugin only answers for `tramdo*` buildings and chains every other call, so other
plugins hooking the same functions keep working.

## 9. Testing (what was done)

Experiments with a prototype item (workspace only, local id 9000300, the vanilla depot model, test
offices tramdo_a..d; retired 2026-10-07):
1. Train office + tram depot layout, no plugin: no trams offered, assignment refused.
2. With the plugin: trams buyable and assignable, but the train office wants rail connections.
3. Road office (C with `$SUBTYPE_TRAM`, D without): connections found, stations accepted as tasks;
   every wagon takes an office place (6 -> full; raised to 24). Later (2026-10-06): an office also
   holds only one set per `$VEHICLE_PARKING` lane (the game's road offices have as many places as
   parking spots) - 4 lanes were full with 4 sets; hence the 6- and 8-lane layouts, and
   `$WORKING_VEHICLES_NEEDED` = lanes x 7 (descriptor +0x820; vehicle +0x510 holds its place).
4. Trams drive in and out; D: "Some vehicle cannot find route" -> the subtype is required.
5. No dispatch: the fuel check (electric trams) -> hook 2.
6. First native dispatch, then full cycles: steel (open), gravel through a conveyor (after removing
   a conveyor transfer between station and storage), waste (after the owner lowered a 20 % pickup
   threshold). Fluids untested.

7. **Game 1.2.0.9, 2026-11-25**, the owner's save `a96` (backed up first; one `tramdo_small`, four
   trams: H51 medium open, EU40 small aggregate, two H51 medium waste), only our plugins enabled
   (see the Space Race AGENTS.md section 9 for the loader playlist): the office update hook ran
   ("fuel mode 2 off"), the office showed its green tick and 4 vehicles, and the trams cycled -
   over 90 s at fast speed one came in from 2.2 km to 127 m of the office and left again, one left
   from 103 m to 1.8 km, one came within 86 m. The purchase window asked our hook about every
   vehicle type (`train group "tram" = 11`, 40 refusals logged, then the log cap): the decision
   data read from memory for all 49 tram-group locomotives gives exactly the designed result -
   7 cargo sets of 21-26 m admitted, the long 37-41 m sets over the 30 m limit, 35 passenger trams
   refused. The **₽** purchase list (the $ one is empty by design, section 6) showed exactly those
   7 sets with their rouble prices, and buying the H51 medium open tram took 83,889 ₽ and created
   the tram and its wagon. Not tested: assigning a tram, the yards, a full delivery cycle watched
   end to end. `tools/dev/tramprobe.py` lists the offices and trams with positions.

Still to test in game: the two yard buildings (placement, the game's track through the shed and
the yard, buildings clear of it) and assigning trams on 1.2.0.9.

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

- Core office: done on 1.1.1.9 (purchase, assignment, parking, dispatch, full cycles). On 1.2.0.9
  (section 9, test 7): existing trams keep working, the ₽ purchase list offers the admitted sets
  and buying works.
- Size limit and cargo-only filter: verified on 1.2.0.9 (the ₽ list shows only the 7 cargo sets
  within 30 m); yards still to be tested in game.
- Workshop: item 3814373926 created and uploaded (content, both yards + plugin) 2026-10-05,
  **unpublished**. To upload again: close the game and RML, `.\build.ps1 -Install`, start the game
  from Steam *without* RML (an item whose plugin DLL is loaded fails with Error code 2), Workshop ->
  Your items (WIP) -> click the item's picture (the magnifier only opens its Steam page) -> Save
  changes. Visibility follows `VISIBILITY` in tramdo_workshop.py (0 = unpublished).
- Open: over-dispatch (fleet tally skips trams); wagons listed as separate office entries
  (cosmetic); the fuel toggle assumes no parallel building updates; the office judges a station
  fed through a conveyor *transfer* by the transfer (looks full).

## 12. Links

- Repo: https://github.com/aislanfoina/wrsr-tramdo
- Republic Mod Loader (WRSR Ultimate Pack): https://steamcommunity.com/sharedfiles/filedetails/?id=3838038411
- RML source: https://github.com/Ultimate-Universe/WRSR-RepublicModLoader
- TesmioLoader: https://github.com/MaxLegend/TesmioLoader (branch master)
- Cargo tram collection used for testing: https://steamcommunity.com/workshop/filedetails/?id=3586298879
