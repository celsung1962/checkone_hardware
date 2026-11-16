# 10 - Datasheet layout review (kicad-routing 1.19.0)

**Source:** the ServiceOne main board (2026-10-05). The review is in `reports/layout_vs_datasheets.md` of the
ServiceOne repository.

**Why it exists.** That board had passed:
- KiCad DRC with 0 errors;
- schematic parity 0;
- the full audit, with 225 FAILs reviewed one by one.

It still broke three datasheet layout rules that change what the instrument measures:
- **Both INA226 current monitors read the copper as well as the shunt.** Their sense lines tapped the power
  track 8 mm and 58 mm away from the shunt pads:
  - 4 mOhm over a 20 mOhm shunt, +20 %;
  - 47 mOhm over a 100 mOhm shunt, +47 %;
  - and the copper drifts at 0.39 %/K.
- **The 8.192 MHz ADC clock ran beside a 24-bit input.** It was 0.11 mm from the input over about 10 mm.
- **Several capacitors reached their pins only through the plane.** These were output and decoupling capacitors
  2 mm from their pins, joined by two vias and the plane.

None of these is a DRC or audit finding:
- A sense line on the same net as the power track is legal copper.
- A clock beside an analog input meets every clearance.
- A capacitor joined through the plane is connected.

This review is a separate step. Run it after routing and before the manufacturing outputs.

## 0. Before routing (1.26.0): use the suggestions

Reading the layout sections only after routing turns every finding into a re-route. Since 1.26.0 the datasheets are scanned before routing, and their suggestions drive the placement and the routing:

1. `datasheet_layout_scan.py BOARD --datasheets DIR --write-params` does section 1 below for every part on the board. It matches parts to documents, finds and classes the pages, filters tables of contents, extracts the rule sentences, renders the pages, and writes the `datasheet_layout` block with every part `pending`.
2. Read each page and its image. Turn each rule into a placement move, a `layout_checks` entry (section 2) or a routing constraint: netclass, priority, `route_finish.py --exclusive` / `--avoid`, keep-out, thermal vias.
3. Record `{rule, source, applied_as}` per rule and set the part `applied` or `n/a` (with the reason).
4. Run `layout_measure.py check BOARD --pre-route`: decoupling by straight distance, so placement errors are caught before routing.
5. Route. The audit FAILs pre-flight and `route_freerouting.py` refuses to export while a part is pending.
6. After routing, the sections below measure the same entries along the copper.

ServiceOne (rev. D datasheets, scan run 2026-10-21): 40 parts with a document, 11 with layout pages. These are
the ADS131M04, TPS63001, OPA2197, LM2776, MT3608, INA226, the ESP32-S3 module (its hardware design guide has
most of them), USBLC6, MCP23017, MCP4728 and TP4056. They are the parts whose rules this reference found after
routing. One part, L2 (10 uH 3.6 A), had no document.

## 1. Find the layout sections

Extract each datasheet's text (`pdftotext`, PyMuPDF) and search for the layout headings:

```
grep -n -i -E 'layout (guideline|example|recommendation|consideration)|suggested layout|recommended layout|pcb layout|board layout|routing guideline' *.txt
```

Sort every hit into one of three classes. Only the first two give checks.

| Class | Typical heading | Use |
|---|---|---|
| Layout guidelines | "11.1 Layout Guidelines", "Layout Consideration", "Board Layout Considerations" | Rules: capacitor placement, loops, Kelvin, separation, thermal |
| Layout example | "11.2 Layout Example", "Suggested Layout" figure | Read the figure caption **and the figure in the PDF**. Text extraction loses the drawing. |
| Land pattern only | "Suggested Pad Layout", "Recommended Land Pattern", TI "Example Board Layout" at the end | Footprint check only, not routing |

Datasheets of parts no longer in the BOM (superseded regulators, the previous ADC) also come up. Filter them
against the BOM before reviewing.

What ServiceOne found, as a guide to where the rules usually are:

| Part type | Typical rule |
|---|---|
| Switching converters (buck-boost, boost, charge pump) | Input and output capacitors and the inductor at the pins on the IC layer, short wide traces, small switch node, feedback divider near FB and away from the switch node |
| Current monitors with an external shunt | Kelvin (4-wire) connection to the shunt; supply bypass at the pins |
| Delta-sigma ADCs | Digital traces away from the analog inputs; C0G on the inputs, at the pins; source termination at the clock source; supply and CAP capacitors at the pins |
| Op-amps | 0.1 uF at each supply pin; feedback parts at the inverting input; short input traces |
| Linear chargers with an exposed pad | PROG resistor at the pin; thermal copper and vias under the pad |
| ESD arrays | Short GND and VBUS connections |
| MCU modules | 10 uF + 0.1 uF at the module 3V3 pin; GND pad vias; USB as a pair, few vias, series parts at the chip |

**Separate analog / digital grounds.** The MCP4728 and OPA2197 datasheets recommend split grounds. Treat this as
a design decision for the owner, not a check. ServiceOne kept a single GND by decision.

## 2. Turn each rule into a measurement

Ask "how far apart are they?" and the answer is wrong: straight-line distance hides a 2-via plane hop or a sense
line that joins the power track. `scripts/layout_measure.py` follows the copper.

| Rule | Command | PASS when |
|---|---|---|
| Capacitor at the pin | `layout_measure.py path BOARD U1.19 C1.1 [--no-plane]` | Routed length within the limit you set (ServiceOne used about 3 mm). `--no-plane` when the capacitor must sit on the surface: converter loops, charge pumps. |
| Return / stitching length | `layout_measure.py return BOARD C31.2` | A short path to a plane via |
| Kelvin connection | `layout_measure.py kelvin BOARD U13.10 R57.1 D3.1` | `shared_mm` 0 and `bypass` false |
| Clock / digital away from analog | `layout_measure.py gap BOARD --a /ADC_AIN1P,/ADC_AIN1N --b CLKIN --exempt X,Y,R` | Minimum same-layer gap above your limit. Only F-F or B-B pairs count: the inner planes shield F from B. |

Record the decisions in `kicad_golden.project.json` -> `layout_checks` (written empty by `init_project.py`), then
run `layout_measure.py check BOARD`. It exits 1 on any FAIL. Each entry is a design decision from a datasheet;
never copy another board's entries.

## 3. Fix

### Kelvin

Remove the sense branch up to the point where it joins the load path. Then draw a dedicated trace from the shunt
pad with `route_finish.py --exclusive`, which treats every other copper item of the net as an obstacle:

```
route_finish.py BOARD --net "+24V" --from-pad R57.1 --to-pad U13.10 --exclusive --block-courtyards --width 0.25
route_finish.py BOARD --net "Net-(Q3-S)" --from-pad R57.2 --to-pad U13.9 --allow U13.8,C43.1 --exclusive --block-courtyards
```

- `--allow` adds same-net pads that belong at the sense end, such as VBUS tied to IN- and its bypass capacitor.
  Without it, a fine-pitch pin between two own-net pins cannot be entered.
- Then run `layout_measure.py kelvin`. It also confirms that the sense pad reaches the load only through the shunt
  pad (`bypass` false). A forgotten old link makes a parallel current path through the new trace.

### Capacitors and resistors far from their pins

This is a **placement** problem; routing cannot fix it.
1. Look for a legal spot first (courtyard search near the pin).
2. On ServiceOne four of six had **no legal spot within 6 mm**. They need a local re-placement, usually moving a
   neighbouring group.
3. Record them; do not force them.

The one fix that is routing is a surface track from the IC pin (or its via) to the capacitor pad. The audit's
plane-net rule (improvements #7) then FAILs it, because it wants plane pads joined only through vias. A converter
datasheet outranks that rule: record both pads in `plane_net_exceptions` with the datasheet section as the reason,
and keep each pad's own via.

### Clock beside analog

Only placement fixes it, if the autorouter has already shared a corridor. On ServiceOne CLKIN sat between AIN1N and
AIN2N in a 1.5 mm channel; no reroute existed on either layer. Prevent it **before** autorouting:
- place the oscillator at the clock pin, on the digital side of the ADC;
- give the clock (or the analog inputs) a class with a larger clearance in the DSN, so the router keeps them apart.

### USB

The fix that worked:
1. Move the series resistors to the module pins (courtyard search).
2. Rip D+/D- and their chip-side nets, then route the two lines one after the other with `--from-pad/--to-pad`.

Result: 119 / 107 mm became 32 / 36 mm. Full Speed (12 Mbit/s) is tolerant of skew, and the pair was not
impedance-routed. For High Speed, route it as a differential pair in KiCad.

## 4. Verify - and diff the audit by message

After every change:
- KiCad DRC (with `--schematic-parity`);
- the open-connection list compared with the one before;
- `kicad_audit.js`, compared **finding by finding (by message)** with the run before.

Counting the FAILs is not enough:
- A new via or a moved part changes which "pads" a neighbouring, untouched track runs between. Old off-centre
  tracks then come back as new between-pads / shared-gap FAILs. On ServiceOne 9 of the 26 new FAILs were of this
  kind.
- Real new FAILs from routed copper are mostly pad entries a few hundredths of a millimetre off an off-grid pad
  centre.

## 5. Tool gotchas (measured, ServiceOne 2026-10-05)

**Router clearances before 1.19.0:**
- `route_finish.py` kept only the copper clearance to vias and drilled pads. It produced hole_clearance warnings and
  a track inside a mounting hole's clearance.
- It kept a fixed 0.3 mm to the outline, which gave edge errors on a 0.5 mm board.
- Both now come from the board design settings.

**Vias written through pcbnew** do not get `remove_unused_layers` / `keep_end_layers` unless set; the audit FAILs
them. `route_finish.py` now sets them.

**pcbnew scripting:**
- After `BOARD.Remove()` inside a loop, re-iterating `GetTracks()` can return a bare `SwigPyObject`. Collect
  `[t.Cast() for t in list(b.GetTracks())]` first, and run removal passes one process at a time.
- Moving a via without re-filling the zones gives clearance errors against the planes. Run
  `ZONE_FILLER.Fill(b.Zones())` before saving.

**Grid offsets.** A grid router that ends "anywhere in the pad" leaves ends 0.01-0.08 mm off the centre (audit
pad-entry). `--from-pad/--to-pad` aligns the grid to 0.05 mm and snaps the end vertex. Pads at odd coordinates
(55.0375) can still be 0.0125 mm off when snapping would leave the lattice.

**Git Bash path conversion.** Git Bash rewrites any argument that starts with "/" into a Windows path. Net names
like `/ADC_AIN1P` then reach the script as `C:/Program Files/Git/ADC_AIN1P`, and an `--avoid` list silently matches
nothing. Set `MSYS_NO_PATHCONV=1`.

**Sub-micron segments.** An imported board can carry segments under 1 um long (17 on ServiceOne; the audit reports
the zero-length ones). Delete them; they connect nothing.

## 6. Feed back to placement

The items routing could not fix are placement rules. Check them in the placement phase, before the autorouter
fixes the corridors:
- the oscillator at the clock pin;
- input RC capacitors at the ADC pins;
- the current monitor beside its shunt;
- USB series parts at the MCU;
- decoupling at every supply pin.
