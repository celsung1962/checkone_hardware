# kicad-routing — user manual

How to install the tools, prepare a board in KiCad, hand it to the skill, and read what comes back.

**Start at section 0** if this machine has never run the skill — it installs KiCad, Freerouting,
the Python packages and the layer-image tooling, and ends with a check that proves they work.
**Then section 2**, the KiCad checklist, which decides whether the run is worth anything — and
**section 3’s opening**, which shows the prompt to start from and the ways a prompt goes wrong.

Everything marked **OBSERVED** is a measurement from one real board, included so you can judge a
rule — never a default to adopt. Measure your own board with `route_report.py`.

---

## 0. Install these before anything else

Four things, in this order. Each row says what stops working if you skip it.

| | What | Essential? | Without it |
|---|---|---|---|
| 0.1 | **KiCad 9 or 10** (update first) | yes | nothing runs — `pcbnew`, `kicad-cli` and the file format all come from here |
| 0.2 | **Freerouting** + a Java runtime | yes | no automated routing; audit and settings still work |
| 0.3 | **Python packages into KiCad's Python** | partly | `rail_zones.py` refuses to run; zone work loses its geometry tooling |
| 0.4 | **kicad-cli SVG + Inkscape** | no | you cannot *look* at a layer, and numeric checks alone will lie to you |

**You can ask Claude Code to do all of this** — see 0.6.

### 0.1 Update KiCad first

Do this before the rest, because KiCad supplies two of the other three: `kicad-cli` and the
**bundled Python** that every `pcbnew` script runs on. Updating KiCad replaces that Python, so
anything you pip-installed into the old one is gone — which is why 0.3 comes after this, not before.

KiCad 9 or 10. Verified on **10.0.6**.

```
Windows    winget install KiCad.KiCad
macOS      brew install --cask kicad
Linux      sudo apt install kicad          (or your distro's package / the PPA)
anywhere   https://www.kicad.org/download/
```

Version matters more than usual here. KiCad 10 writes a different board format (`20260206`) from
KiCad 9 (`20241229`), and zones changed shape with it. Two API details the skill depends on are
checked by the doctor: the two-argument `ExportSpecctraDSN` / `ImportSpecctraSES` overloads, and the
layer-aware via width accessor `GetFrontWidth()` — the arg-less `GetWidth()` trips an assertion that
can hang a headless run.

**Note where KiCad's Python lives.** You will need this path repeatedly:

```
Windows   C:\Program Files\KiCad\10.0\bin\python.exe
macOS     /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
Linux     /usr/lib/kicad/bin/python   or  /usr/bin/python3   (distro-dependent)
```

### 0.2 Freerouting, and the Java question

Freerouting ships in two forms, and **which one you get decides whether Java matters**:

- **Native launcher** (`freerouting.exe`, AppImage, `.app`) — **use this one.** It carries its own
  Java runtime, so the Java on your machine is irrelevant.
- **`.jar`** — needs **Java 21 or newer** installed separately.

This is not a hypothetical preference. On the machine this manual was written on, the only Java is
**major 8**, so the jar would not start at all; the native launcher runs fine and is what the skill
found and used. The doctor reports which one you have and whether your Java can actually run it.

Get it from **https://github.com/freerouting/freerouting/releases**. Verified on **2.4.1**.

The installer puts it somewhere the skill already looks, so there is usually nothing to configure:

```
%LOCALAPPDATA%\freerouting\freerouting.exe      <- Windows installer default
%PROGRAMFILES%\Freerouting\freerouting.exe
~/.local/share/freerouting/bin/freerouting
/opt/freerouting/bin/freerouting
```

Anywhere else, pass it explicitly: `route_freerouting.py BOARD --fr-cmd "<path>"`.

If you are stuck with the jar, install a JRE 21+ (Adoptium Temurin is the easy one) and point the
skill at `java -jar /path/freerouting.jar`.

**Freerouting has no headless mode.** A window opens for every run and **must not be closed** while
it works. A clearance sweep is three full runs, so expect three windows in sequence.

### 0.3 Python packages — into KiCad's Python, not your system one

There are two Python interpreters in play and they do not share packages. This is the single most
common setup mistake, and it fails in a confusing direction: a tool reports a package "missing"
while you can see it installed.

- Anything importing **`pcbnew`** must run on **KiCad's bundled Python**. `pcbnew` is not on PyPI —
  `pip install pcbnew` does not give you KiCad's module.
- The pure-text tools (`dsn_filter.py`, `stitch_planes.py`, `repair_import.py`, the test suites) run
  on **any** Python 3.8+.

Install the optional extras into KiCad's interpreter:

```
"C:\Program Files\KiCad\10.0\bin\python.exe" -m pip install shapely matplotlib
```

```
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 -m pip install shapely matplotlib
```

- **`shapely`** — polygon union / difference / connectivity. Required by `rail_zones.py`; a large
  help for any inner-layer zone work.
- **`matplotlib`** — rendering and cropping layer images (see 0.4).

Neither is required for routing or auditing. Everything shipped keeps working without them.

**The trap, concretely.** On this machine `shapely` 2.1.2 is installed in KiCad's Python and *not*
in the system Python. `rail_zones.py` is documented as running on the system Python — so run it with
whichever interpreter actually has `shapely`. Installing into both is the simplest cure. The doctor
reports `shapely` **per interpreter**, which is exactly why you run it twice (0.5).

### 0.4 The 2D layer-image workflow: kicad-cli SVG + Inkscape

**`kicad-cli` needs no separate install** — it ships with KiCad, next to that Python:

```
Windows   C:\Program Files\KiCad\10.0\bin\kicad-cli.exe
```

**Inkscape** is the part you add. It turns the exported SVG into a PNG at a DPI you choose, so you
can actually look at a copper layer:

```
Windows    winget install Inkscape.Inkscape
macOS      brew install --cask inkscape
Linux      sudo apt install inkscape
```

The workflow is two commands:

```bash
kicad-cli pcb export svg --layers "In2.Cu" --page-size-mode 2 --exclude-drawing-sheet \
  --output layer.svg board.kicad_pcb
inkscape --export-type=png --export-dpi=420 --export-filename=layer.png layer.svg
```

Then read the PNG. Crop with `matplotlib` when a region needs magnifying.

**Why bother, when the audit passes?** Because every numeric check can pass while the geometry is
wrong. **OBSERVED:** a 20 mm sliver slicing a +3.3V plane survived every connectivity and clearance
check on the reference board, and was found only by looking at the render.

This one is genuinely optional — without Inkscape you can still open the SVG in a browser. What you
lose is a PNG at a known DPI, scriptable and croppable.

### 0.5 Verify — run the doctor twice

Nothing above is worth trusting until the doctor confirms it. Run it with **both** interpreters,
because several answers differ between them:

```
py -3 scripts/doctor.py
"C:\Program Files\KiCad\10.0\bin\python.exe" scripts/doctor.py
```

Real output from the machine this manual was written on, KiCad's interpreter:

```
  [ ok ] python             3.11.5  (C:\Program Files\KiCad\10.0\bin\python.exe)
  [ ok ] pcbnew             10.0.6
  [ ok ] specctra dsn/ses   ExportSpecctraDSN + ImportSpecctraSES present
  [ ok ] via GetFrontWidth  layer-aware via width available
  [ ok ] shapely            2.1.2 (in THIS interpreter)
  [ ok ] node               v24.16.0
  [ ok ] kicad-cli          C:\Program Files\KiCad\10.0\bin\kicad-cli.exe
  [ ok ] java               major 8
  [ ok ] freerouting        ...\freerouting.exe  native launcher, carries its own runtime
  [ -- ] inkscape           not found - SVG layer renders unavailable

  every essential capability is present in this configuration
```

Read that carefully: **Java 8 is fine here** only because the native launcher carries its own
runtime. Had this been the `.jar`, the same line would have been a blocker. And `inkscape` missing
costs 0.4 and nothing else — the run still works.

The same machine's *system* Python reports `pcbnew not in THIS interpreter` and `shapely not in this
interpreter`. Both are expected. Neither is a problem, as long as you run the routing tools with
KiCad's Python.

`[ ok ]` on everything marked essential is the bar. `[ -- ]` on an optional line is a choice, not a
failure.

### 0.6 Or ask Claude Code to install it for you

You do not have to do any of this by hand. A workable opening message:

> Set up my machine for the kicad-routing skill. Run `scripts/doctor.py` with both my system Python
> and KiCad's bundled Python, tell me what is missing, and install it — KiCad, Freerouting (the
> native launcher, not the jar), `shapely` and `matplotlib` into KiCad's Python, and Inkscape. Show
> me the doctor output before and after, and ask me before each install.

What to expect:

- It will **ask permission before each install** — these commands change your machine, so approve
  them one at a time and read what is being run. "Install everything without asking" is exactly the
  instruction you should not give.
- It can read the doctor's output and tell you *why* something is flagged — for example that your
  Java is too old for the jar but irrelevant if you take the native launcher.
- It cannot click through a GUI installer. If a package manager is unavailable, it will hand you the
  download link instead.
- Ask it to **re-run the doctor afterwards**. An install that reports success but lands in the wrong
  interpreter is the failure mode worth catching, and the doctor is what catches it.

`INSTALL.md` covers the same ground as a requirements table, plus how to unpack the skill itself and
run its six test suites.

---

## 1. What the skill does, and what it will not do

**It does:** enforce fabricator limits, derive netclasses from your netlist, drive Freerouting
through a Specctra round-trip, place the plane-stitching vias the router never emits, repair the
imported geometry to the standard (45° lattice, pad snapping, neckdowns, via flags), and audit the
result with a PASS/FAIL exit code.

**It will not:**

- **place components** — placement is yours, and it decides most of what follows
- **draw or change your board outline** — it sanitises stroke width and reports duplicates, but it
  will not redraw Edge.Cuts
- **edit your schematic** — never; several checks read it, none write it
- **finish the board for you** — expect to hand-route a few connections. On a 350-connection
  board the best automated result left 2 (**OBSERVED**)
- **replace DRC** — it runs `kicad-cli pcb drc` and reports it, but the golden audit is a separate,
  stricter thing

---

## 2. Before you call the skill — the KiCad checklist

This is the part that decides whether the run is worth anything. Each item says what actually
happens if you skip it.

### 2.1 Close KiCad

**Close the board and the project before running anything.** The scripts write `.kicad_pcb` and
`.kicad_pro` directly. KiCad holds both in memory and will overwrite your run's results when it
next saves — silently.

### 2.2 Schematic complete, netlist pushed

Run **Tools → Update PCB from Schematic (F8)** and resolve everything it reports.

The skill routes what is on the board. A pad with no net is invisible to it; a stale netlist routes
the old design. This is also where net *names* come from, which matters more than people expect —
see 2.6.

### 2.3 Placement finished and frozen

The skill assumes placement is a decision you have already made. It never moves a footprint.

Placement determines routability far more than any router setting. Two things to look at first:

- **Long-haul nets.** A net whose pads span most of the board will be the one left unrouted.
  `route_report.py` lists every net spanning ≥ 50 mm before you route. If a 70 mm span exists
  because of placement rather than necessity, fixing the placement is worth more than any amount
  of router tuning. **OBSERVED:** one 69 mm power net defeated a corridor search, a hand-built
  path *and* a dedicated router pass when attempted after the board was routed — but routed
  without trouble from an empty board.
- **Courtyard overlaps.** Run **Inspect → Design Rules Checker** and look at them now. The skill
  reports them and changes nothing. **OBSERVED:** 15 overlaps on one board, all a module with
  passives deliberately placed underneath — legitimate, but you want to *know* that, not discover
  it in the audit.

### 2.4 Layer count and stackup set correctly

**File → Board Setup → Board Editor Layers.** Set the copper layer count *before* calling the
skill.

The audit has a hard **pre-flight FAIL** if the board's copper layer count does not match the
fabricator profile on record. **OBSERVED:** a board described as 4-layer arrived as 2-layer
(`F.Cu`/`B.Cu` only); converting it mid-workflow also meant rewriting a physical stackup that still
described a 2-layer 1.51 mm core, and discarding a `B.Cu` ground pour that no longer made sense.

For a 4-layer board the standard requires, immutably:

```
F.Cu    Signal
In1.Cu  GND plane     ← layer type "power"
In2.Cu  POWER plane   ← layer type "power"
B.Cu    Signal
```

Set the inner layers' **type to `power`** in Board Setup. This is not cosmetic: the Specctra export
marks `power` layers as unroutable, which is the only thing stopping the router putting signal
tracks on your planes. A track on an inner layer is an audit FAIL.

### 2.5 Board outline (Edge.Cuts) clean

Requirements: **one closed polygon**, every vertex shared by exactly two segments, stroke
**0.05 mm**. Cutouts are separate closed loops and are fine.

Check for:

- **Doubled or near-coincident outlines.** Two rectangles 9 µm apart look identical on screen and
  produce two competing outlines. A clean rectangle has exactly two distinct X and two distinct Y
  coordinates; four or more means you have a duplicate.
- **Anything on Edge.Cuts that is not the outline.** Dimensions and text on that layer are a
  fabrication hazard — the fab may read them as cut paths. **OBSERVED:** three dimension objects
  sat on Edge.Cuts on a real board and had to be moved to `Dwgs.User`.
- **Footprint-internal Edge.Cuts.** Legitimate and common (slots, LED openings), but count them so
  later edge-clearance findings make sense.

The skill corrects stroke width. It will **not** deduplicate an ambiguous outline without telling
you — if your outline is doubled, it stops and asks.

### 2.6 Net names — this is the one people skip

The skill derives your power netclasses from **net names**. Good names are a prerequisite, not a
nicety.

- **Name your rails.** `+3.3V`, `+VSYS`, `+BATT`, `GND`, `GND_LED` are all recognised. A rail left
  as an auto-generated `Net-(U1-Pad3)` cannot be recognised as a rail by anything, and will route
  at signal width.
- **Suffix your sense lines.** `24V_SENSE` and `SOLAR_SENSE` are correctly *excluded* from power
  widening because of the `_SENSE` suffix — they carry no current and widening them is wrong.
  Recognised markers include `SENSE`, `FB`, `ADJ`, `MON`, `DIV`, `PG`.
- **Name your buses consistently.** `D0..D7`, `LORA_*` — indexed and prefixed names let the tools
  detect bus groups and diff pairs.

After pushing the netlist, run:

```
<kicad-python> scripts/netclass_propose.py BOARD.kicad_pcb
```

It lists every current-carrying rail it found, every sense tap it deliberately skipped, and exits
non-zero if a rail would be left on `Default`. **This catches the one defect that reaches copper
with no warning at all**: a power rail routed at 0.2 mm because a netclass pattern from a different
design matched nothing on yours.

### 2.7 Decide on footprint-local clearance overrides

A footprint can carry its own `(clearance X)`. **Specctra DSN has no field for this**, so the router
never sees it, routes to the board-global value, and every violation appears only after the import.

**OBSERVED:** one VQFN-29 at 0.4 mm pitch with a 0.15 mm local override produced **21 of 21**
clearance violations in the first routing run.

`route_report.py` lists them. Decide whether each is needed — they are not free, because
`--auto-clearance` raises the *whole board's* export clearance to the largest one, which costs
routability everywhere.

### 2.8 Review keepouts

Rule areas can live **inside footprints**, where a top-level zone scan does not see them. Know how
many you have and that they are intentional.

Confirm **`items_not_allowed` is not set to `ignore`** in Board Setup → Violation Severity. If it
is, KiCad's own DRC passes keepout violations without a word.

### 2.9 Existing copper and zones

Decide before starting:

- **Existing tracks** — ripped up for a full autoroute, or kept and routed around? Old routing drawn
  for a different layer count usually fights the new stackup.
- **Existing pours** — a `B.Cu` ground pour on a board about to gain an `In1.Cu` ground plane is
  redundant and eats routing space.
- **Locked items** — pre-existing locks are honoured by the router. Make sure they are deliberate.

### 2.9b Freerouting GUI settings a script cannot reach

Three interactive settings conflict with the standard and **cannot be set from any script** -
they are editor state, absent from the rules file, from freerouting.json and from the CLI.
Turn them off in Freerouting before routing interactively:

| Setting | Why |
|---|---|
| **Vias snap to SMD pad centers** | produces via-in-pad, which the audit FAILs |
| **Automatic neckdown** | the standard requires one width per net run; the repair strips them anyway |
| **Drag components enabled** | permits the router to move footprints, and placement is locked |

Also worth setting: **pad-to-turn gap >= 200 um** (the standard wants a 0.2 mm straight entry;
the default 100 um is half that), and a small nonzero **bend cost** for cleaner corners.

The autorouter costs - via cost, preferred direction, rip-up - are NOT in this list: those are
handled for you by `rules_writer.py` and `--auto-rules`, so they live in the project instead of
in whoever last opened the GUI.

### 2.10 Back up, or commit

The skill backs up before every destructive step (`.bak_prerouting`, `.bak_prestitch`, …), but a
version-control commit is better. Also note: **`apply_settings.js` overwrites your DRC severities
and netclass definitions** with the golden template. Custom severities you care about will be
replaced.

### 2.11 Quick pre-flight, in order

```
python  scripts/doctor.py                  # and again with KiCad's python
<kicad> scripts/init_project.py BOARD.kicad_pcb --fab jlcpcb --layers 4 --copper 1oz
node    scripts/apply_settings.js BOARD.kicad_pro --fab jlcpcb --layers 4 --copper 1oz
<kicad> scripts/netclass_propose.py BOARD.kicad_pcb --apply
<kicad> scripts/route_report.py BOARD.kicad_pcb
```

`route_report.py` is the gate. Read its three hazard sections before routing anything.

---

## 3. Running the workflow

### The prompt — start here

The skill is driven by what you ask for. Most bad runs are bad prompts, not bad routing.

#### A prompt that works

```
Route the board in this folder with the golden kicad skill.

Board: BoardName.kicad_pcb
Fabricator: JLCPCB, 4-layer, 1 oz outer / 0.5 oz inner
Stackup: Top=Signal, In1=GND, In2=POWER, Bottom=Signal

Constraints:
- Do NOT modify the schematic.
- Do NOT move, rotate or delete any footprint.
- Rip up the existing tracks and route from scratch.

No BGAs on this board, so full copper pours on the inner planes are fine.

Run the standard workflow: pre-flight checks, netclass derivation,
the clearance sweep, plane stitching, geometric repair, then the audit.
Report what's left for me to finish by hand.
```

#### Why each part earns its place

| Line | What it prevents |
|---|---|
| **Names the board file** | A folder can hold backups and sweep candidates. Naming the file removes the guess. |
| **Fabricator + layers + copper** | The audit has a hard **pre-flight FAIL** without a fabricator profile on record — routing is refused, by design. Layers and copper weight set the minimum track width, clearance, via and annular-ring limits everything else is measured against. |
| **Stackup, layer by layer** | Inner layers must be typed `power`, because the Specctra export marks `power` layers unroutable. That is the only thing stopping the router laying signal tracks across your planes. A track on an inner layer is an audit FAIL. |
| **Schematic locked** | Makes the boundary explicit. Several checks read the schematic; none should write it. |
| **Placement locked** | The skill never moves a footprint anyway — saying so stops any "helpful" repositioning being offered as a fix when a net will not route. |
| **Rip up / route from scratch** | A genuine behavioural switch. Left out, the router routes *around* the copper already there. **OBSERVED:** one 69 mm power net defeated a corridor search, a hand-built path and a dedicated router pass when attempted on an already-routed board — and routed without trouble from empty. |
| **"No BGAs"** | Decides whether full inner-layer pours are safe, and whether sub-0.2 mm tracks are legitimate fine-pitch escapes or a `width` FAIL. |
| **Names the workflow steps** | The steps are not all automatic. Plane stitching, repair and the audit are separate tools, and a run that stops after the router looks finished while leaving unstitched plane pads and unrepaired geometry. |
| **"Report what's left by hand"** | Sets a truthful finish line. See below. |

`1 oz outer / 0.5 oz inner` is precise and correct, not fussy: for a 4-layer JLCPCB board that is
exactly what the `4L-1oz` profile means (35 µm outer, 17.5 µm inner). Saying "1 oz" alone is fine;
saying "2 oz" when you meant the outer layers only is not.

**One caveat on "rip up the existing tracks".** There is no rip-up script — it is done directly on
the board, so make sure your own backup exists before you ask for it. The skill writes
`.bak_prerouting` when routing starts, which is *after* the tracks are gone.

#### What makes a prompt weak

| Weak | What actually happens | Say instead |
|---|---|---|
| "Route my board." | No fabricator on record → audit pre-flight **FAIL**, and the skill is told not to start routing. You get a question, not a board. | Name the board, fabricator, layer count and copper weight. |
| "It's a 4-layer board." | Layer *count* without layer *types*. If In1/In2 are not typed `power`, the router happily puts signal tracks on your ground plane — and that is an audit FAIL discovered at the end. | Spell out `Top=Signal, In1=GND, In2=POWER, Bottom=Signal`. |
| "Route it 100%." / "Finish the board." | Sets a target the tool does not hit. The best automated result on a 350-connection board left **2** connections (**OBSERVED**); a via-cost experiment on the same board left 9. Demanding completion invites padding the number rather than reporting it. | "Report what's left for me to finish by hand." |
| "Make the routing good / clean / professional." | No measurable acceptance criterion, so nothing can be checked against it. | "Run the audit and show me the FAILs." |
| "Fix whatever is wrong." | Open-ended licence over a board whose placement and schematic you probably did not mean to expose. | State what is locked. |
| "Use 0.2 mm clearance." (with no reason) | Clearance is **not** monotonic — more is often worse. **OBSERVED** on one board: 0.15 mm → 36 unrouted, 0.20 mm → 59. A guessed number costs a full router run. | "Run the clearance sweep and pick by measurement." |
| Silence about existing copper | Ambiguous. The router will work around whatever tracks are on the board, usually producing a worse result than starting empty. | Say explicitly whether to rip up or keep. |
| Silence about BGAs / fine pitch | Changes how narrow tracks and inner-plane pours are judged. | One sentence either way. |
| "Don't ask me anything, just do it." | The pre-flight gate exists because routing without a fabricator profile produces a board no one can manufacture. Suppressing questions suppresses that. | Answer the setup questions once, in the prompt. |

#### Two things a prompt cannot fix

- **KiCad must be closed** (2.1). The scripts write `.kicad_pcb` and `.kicad_pro` directly, and an
  open KiCad will overwrite the results when it next saves — silently. No wording prevents this.
- **Placement.** Placement decides routability far more than any router setting. If the board is
  poorly placed, the best prompt in the world buys you a slightly better failure.

### Single pass — the default, and right for most boards

```
<kicad> scripts/route_sweep.py BOARD.kicad_pcb --passes 100 --threads 1 --keep-all
<kicad> scripts/stitch_planes.py BOARD.kicad_pcb
        ... geometric repair, then ...
python  scripts/repair_import.py BOARD.kicad_pcb
node    scripts/kicad_audit.js BOARD.kicad_pcb
        ... audit must PASS before the next line ...
kicad-cli pcb export gerbers --output gerbers/ --check-zones --layers "..." BOARD.kicad_pcb
kicad-cli pcb export drill   --output gerbers/ --format excellon --excellon-separate-th BOARD.kicad_pcb
```

`route_sweep.py` runs the router once per candidate clearance and keeps the best by real ratsnest.
It also generates and passes the `.rules` file, so the autorouter costs come from your project
rather than from the GUI (`--no-rules` opts out).
Clearance is **not monotonic** — more is not better. **OBSERVED:** 0.10 mm → 40 unrouted,
0.15 mm → 36, 0.20 mm → 59.

A **Freerouting window opens and must not be closed.** It has no headless mode. Use `--threads 1`;
its own log warns that multi-threaded optimisation is buggy.

### If you care about via count — turn this knob before anything else

Vias on power and long-haul nets are inductance and return-path discontinuities. Freerouting's
`via_costs` decides how hard the router works to avoid them; the default is 50. It is set in
`router_costs.via_cost` in `kicad_golden.project.json`, written into a `.rules` file by
`rules_writer.py`, and passed automatically — `route_sweep.py` and `route_freerouting.py
--auto-rules` both do this for you.

**OBSERVED** — same board, same inputs, only `via_costs` changed:

| | 50 | 150 |
|---|---|---|
| total vias | 105 | **72  (−31%)** |
| vias on the 8 key nets | 24 | **11  (−54%)** |
| length of those nets | 896.6 mm | **763.5 mm  (−15%)** |
| unrouted (pre-stitch) | 36 | 43  (+7) |
| unrouted after the FULL pipeline | **2  (99.43%)** | 9  (97.43%) |
| tracks necked to 0.15 mm | **20** | 44 |
| golden audit | **PASS** | FAIL — 16 neckdowns |

**Check for neckdowns after raising it.** Denied a via, the router threads the gap at reduced width
instead. Sub-0.2 mm segments went 20 → 44 and 16 fell outside any fine-pitch escape, failing the
`width` check. Widening those 16 back to 0.2 mm made the audit pass and added no new DRC violation,
so the narrowing bought nothing. A good `route_report.py` number does not tell you this — only
`kicad_audit.js` does.

Before this existed, the costs lived in whoever last opened the Freerouting GUI, so two engineers
got different boards from identical inputs. They are now project state.

### Phased routing — opt-in, and try the via cost first

Route critical nets first, lock them, route the rest around them. Enabled only by listing nets in
`priority_routing.critical_nets`. See the SKILL.md section for the full sequence; the order
`route → repair → audit → LOCK → next phase` is not negotiable.

**OBSERVED:** critical-net vias 24 → 10, at a cost of 2 → 11 unrouted, and that cost did *not*
shrink when the critical set was halved.

**But one parameter got essentially the same result.** `via_costs` 150 reached 11 vias on the same
nets, with *shorter* nets, no two-phase workflow and no locking contract to verify. Reach for
phased routing only when a single cost knob cannot express what you need — for instance when a few
named nets must take a specific path, not merely have fewer vias.

---

## 4. Reading the output

`kicad_audit.js` ends with a verdict block:

```
key: segments=1125 vias=218 arcs=0 off_lattice=0 inner_tracks=0 keepouts=3
     power_rails=5 unclassed_rails=0 dead_rules=0
--- VERDICT ---
  nothing blocks: 0 FAIL
  advice (WARN): pad-entry 65, width 45
```

- **FAIL** blocks. Exit code 1. The hard gates are: pre-flight (fabricator profile, layer count,
  rules below fabricator minimums), tracks on inner layers, track arcs, off-lattice segments,
  keepout intrusion, via stack and flags, **an unclassed current-carrying rail**, and edge clearance.
- **WARN** is advice. A passing board routinely produces 100+, mostly pad-entry and width notes on
  router output. Do not treat the count as a quality score.
- **`dead_rules`** — configured rules matching no net on this board. They audit nothing, and their
  "pass" is meaningless. Clean them up.
- **`unclassed_rails`** — must be 0.

`route_report.py` gives the completion number: connections routed out of `pads − 1`.

---

## 5. After the run

1. **Open the board and press `B`** (Edit → Fill All Zones). Zones are filled programmatically;
   let KiCad's filler have the last word before plotting.
2. **Finish what the router left.** Expect a handful. `route_finish.py` routes one connection at a
   time on the 45° lattice (a second Freerouting pass is forbidden — it corrupts via padstacks):

   ```bash
   <kicad> scripts/route_finish.py BOARD --net "SCL" --from 109.411,161.925 --to 86.250,101.200 \
     --width 0.2 --grid 0.05 --safety 0.05 --dry-run
   ```

   Endpoints come from the DRC report's `unconnected_items`; the width comes from the netclass.
   **Routing order changes what is reachable** — measured 3 / 4 / 4 unrouted for three orderings of
   the same 8 connections. Try two, keep the better. DRC after each net and revert anything that
   raises the count.
3. **Re-run DRC** and confirm the error count is zero.
3a. **Datasheet layout review (1.19.0).** DRC and the audit do not read the datasheets' layout sections.
   Before the outputs:
   - find those sections;
   - record the rules as `layout_checks` in `kicad_golden.project.json` (Kelvin sense lines, capacitors at pins,
     clock away from analog inputs);
   - run the check:

   ```bash
   <kicad> scripts/layout_measure.py check BOARD
   <kicad> scripts/layout_measure.py kelvin BOARD U13.10 R57.1 D3.1      # one check by hand
   ```

   A Kelvin FAIL is fixed with a dedicated trace:
   `route_finish.py BOARD --net NET --from-pad R57.1 --to-pad U13.10 --exclusive --block-courtyards`.
   Parts far from their pins need a re-placement. Procedure and pitfalls: `references/10_datasheet_layout_review.md`.
4. **Re-apply `corner_style`** if you care about it: any `pcbnew` session rewrites the `.kicad_pro`
   and reverts it. Do it last.
5. **Generate the manufacturing outputs** from the corrected board — gerbers *and* drill files,
   into a dedicated `gerbers/` directory:

   ```bash
   kicad-cli pcb export gerbers --output gerbers/ --check-zones \
     --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts" \
     "<board>.kicad_pcb"
   kicad-cli pcb export drill --output gerbers/ --format excellon \
     --excellon-separate-th --generate-map --map-format gerberx2 "<board>.kicad_pcb"
   ```

   **X2 is the default — there is no `--use-gerber-x2` flag** (KiCad 10 rejects it outright). The
   flag that exists is the opt-out `--no-x2`, which demotes the `%TF.` attributes to `G04 #@!`
   comments no fabricator reads. Verify: `head -1 gerbers/*F_Cu.gtl` must start `%TF.`.

   **Add the user layers that carry content.** Naming `--layers` keeps the nine empty `User_*`
   files, `Courtyard` and `Fab` out — but a user layer holding dimensions or a fab drawing belongs
   in the package, and excluding it drops that drawing silently. Check what is really there, then
   append the populated ones (`User.1,Cmts.User,Dwgs.User`):

   ```python
   import pcbnew, collections
   b = pcbnew.LoadBoard(board); c = collections.Counter()
   for d in b.GetDrawings(): c[b.GetLayerName(d.GetLayer())] += 1
   print(c)
   ```

   **Check `Edge.Cuts` holds nothing but the outline.** It becomes the profile the board is cut to,
   so a dimension object living there is plotted into `*-Edge_Cuts.gm1` as outline geometry. DRC
   calls it `text_on_edge_cuts`, at *error* severity. **OBSERVED:** one board had 3 orthogonal
   dimensions on `Edge.Cuts` beside the single real outline shape, with 5 more correctly on
   `User.1`; moving them cleared all 3 errors and cut the profile gerber down to 5 draw points.

   Full detail in SKILL.md → *Manufacturing Outputs Generation*.

---

## 6. Known traps

| Symptom | Cause |
|---|---|
| Clearance violations clustered on one part | A footprint-local `(clearance)` the DSN cannot express. Use `--auto-clearance`. |
| Changing `min_clearance` does nothing | The DSN takes clearance from the **netclass**, not that rule. |
| Vias come back with a drill larger than the pad | A DSN/SES round-trip over already-routed copper. Route from bare, or finish by hand. The padstack gate now refuses to save such a board. |
| Plane pads all unconnected | Freerouting places **no** vias on plane nets. Run `stitch_planes.py`. |
| A power rail routed at signal width | No netclass pattern matched it. `netclass_propose.py --apply`. |
| `rail_zones.py` says shapely is missing when it is installed | Wrong interpreter. Run `doctor.py` with both. |
| Via cost / preferred direction seem to have no effect | The `.rules` design name was unquoted, so Freerouting stopped at the first space and ignored the whole file. `rules_writer.py` quotes it. |
| Two engineers get different boards from the same files | Autorouter costs were GUI state. Use `--auto-rules` so they come from `router_costs`. |
| A `.kicad_pro` edit vanished | `pcbnew` caches the project by path and `SaveBoard` writes the cached copy back. Edit before the first load or after the last save. |
| DRC reports a short but the audit passes | Hand-drawn copper. A `PCB_SHAPE` on a copper layer is **not in the DSN**, so Freerouting routes straight through it. Convert it to a track or cover it with a keepout. Only `kicad-cli pcb drc` catches this. |
| `text_on_edge_cuts` errors | Dimension or text objects on `Edge.Cuts`. They are plotted into the profile gerber as if they were outline geometry. Move them to `User.1`. |
| The fab package is missing a drawing | `--layers` excluded a populated user layer. List what is really on each user layer, then add the populated ones. |
| Fixing one endpoint broke other nets' angles | A snapper scoped to a tolerance instead of to a net. Scope it to the net you are repairing and re-audit. |
| `route_finish.py --exclusive` finds no path into a fine-pitch pin | The neighbouring pin is on the same net (VBUS beside IN-) and is an obstacle in exclusive mode: list it with `--allow U13.8`. Also clear leftover stubs of the old route on those pins first - they are obstacles too. |
| `--avoid /NET` has no effect in Git Bash | Git Bash rewrote `/NET` into a Windows path. Run with `MSYS_NO_PATHCONV=1`. |
| `route_finish.py` says no path for a short connection | Either `--safety` sealed the channel (try `--grid 0.05 --safety 0.05`) or the corridor is genuinely full. Millions of expansions against the cell count means exhausted, not slow. |
| Script hangs with no output | `PCB_VIA.GetWidth()` without a layer argument asserts and can open a modal dialog. Use `GetFrontWidth()`. |
| A gated run ends with "STOP RULE: keep rate ..." | Intended (1.28.0, L30): fewer than 1 in 5 attempts were kept after 10 attempts or 30 min. Do not raise the budget to grind on; read why the attempts were refused, hand the rest to the interactive router (`<board>.finish_open.json`, `open_ends.py`). `--no-stop-rule` only for experiments. |
| "REVERTED (locked ... moved or changed)" | The change moved locked copper (1.28.0, L40). Leave it, or unlock that copper in KiCad on purpose first. `locks.py BOARD --list` shows what is locked; stitching vias locked by `stitch_residual.py` are tool locks and can be released before interactive routing. |
| A gated driver keeps nothing on a board saved by KiCad's GUI | The baseline and the trial were saved by different programs. Since 1.28.0 the shared-gap message is order-independent; for other cases snapshot with `stage_gate.py --snap --normalise` (L42). |
| After KiCad's Cleanup, new pad-entry FAILs at pad centres | "Delete tracks fully inside pads" removed the stubs that end at the pad centre (L44). Turn it off, gate the board, restore the stubs. |

---

## 7. Getting help from the skill itself

Every script prints its full usage when run with no arguments. `doctor.py` tells you what your
machine can do. `route_report.py --fail-on-gap` is suitable as a CI gate.
