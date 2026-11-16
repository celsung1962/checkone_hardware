# Worked examples

_Before/after s-expression snippets. "Golden" snippets are copied verbatim from the geometry reference board (uuids shortened). "Illustrative" snippets are constructed to show the defect._

## E1. Pad entry: single straight axial segment ending on the pad centre

Footprint `R59` sits at `(293.58016 157.103494 90)`; its pad 1 is at `(-0.825 0 90)` inside the footprint. Rotating the pad offset by 90° gives the absolute centre `(293.58016, 157.928494)`. The golden track ends **exactly** there, leaves along the pad's axis, and is 1.6 mm long at 0.2 mm.

```lisp
;; GOLDEN — one segment, axial entry, endpoint == pad centre to 6 decimals
(segment
	(start 293.58016 157.928494)
	(end 295.18016 157.928494)
	(width 0.2)
	(layer "F.Cu")
	(net 7)
)
```

```lisp
;; ILLUSTRATIVE DEFECT — staircase + off-centre + neckdown (all three flagged by the audit)
(segment (start 293.63 157.90) (end 293.73 157.80) (width 0.15) (layer "F.Cu") (net 7))   ; ends 0.06 mm off centre, 0.15 mm wide
(segment (start 293.73 157.80) (end 293.83 157.90) (width 0.15) (layer "F.Cu") (net 7))   ; 0.14 mm zig
(segment (start 293.83 157.90) (end 295.18 157.90) (width 0.2)  (layer "F.Cu") (net 7))   ; width step mid-run
```

Rule of thumb when generating coordinates: compute `abs = fp.at + rotate(pad.at, fp.rot)` and write that value **unrounded** into `(start …)` or `(end …)`.

## E2. Via: both tracks end on the via centre; unused inner rings removed

Golden via on net 15 with a 0.5 mm F.Cu stub and a 0.5 mm B.Cu 45° segment, both terminating at `(303.71766 160.377311)`.

```lisp
;; GOLDEN
(via
	(at 303.71766 160.377311)
	(size 0.45)
	(drill 0.2)
	(layers "F.Cu" "B.Cu")
	(remove_unused_layers yes)
	(keep_end_layers yes)
	(zone_layer_connections)
	(net 15)
)
(segment (start 303.71766 160.377311) (end 303.71766 159.652311) (width 0.5) (layer "F.Cu") (net 15))
(segment (start 305.19266 158.902311) (end 303.71766 160.377311) (width 0.5) (layer "B.Cu") (net 15))
```

```lisp
;; ILLUSTRATIVE DEFECT — 410 golden vias still look like this; do not add more
(via (at 303.71766 160.377311) (size 0.45) (drill 0.2) (layers "F.Cu" "B.Cu") (net 15))
;; and a near-miss (audit: FAIL via-centring)
(segment (start 303.7 160.4) (end 303.71766 159.652311) (width 0.5) (layer "F.Cu") (net 15))
```

## E3. Corner: 45° mitre instead of 90°

Golden, net `/ADC_1/AD_V2IN_N` on F.Cu: a 6.85 mm vertical run turns through a 45° segment.

```lisp
;; GOLDEN — 90° change of direction done as vertical + 45°
(segment (start 343.125 213.3)  (end 343.125 206.45) (width 0.2) (layer "F.Cu") (net 40))
(segment (start 343.125 206.45) (end 344.875 204.7)  (width 0.2) (layer "F.Cu") (net 40))
```

```lisp
;; ILLUSTRATIVE DEFECT — same endpoints, right-angle corner (golden has 241 of these vs 3858 mitres)
(segment (start 343.125 213.3) (end 343.125 204.7) (width 0.2) (layer "F.Cu") (net 40))
(segment (start 343.125 204.7) (end 344.875 204.7) (width 0.2) (layer "F.Cu") (net 40))
```

Check: for every segment `|dx| == 0`, `|dy| == 0` or `|dx| == |dy|` (to 1e-6). Anything else is off the lattice.

## E4. Differential pair coupled section

Two same-layer segments, both 0.2 mm, parallel, 0.45 mm apart centre-to-centre (0.25 mm gap), same length, same direction.

```lisp
;; ILLUSTRATIVE (geometry identical to the golden PHY/SFP pairs)
(segment (start 320.000 262.000) (end 320.000 250.000) (width 0.2) (layer "F.Cu") (net 501))   ; PHY1_TXP
(segment (start 320.450 262.000) (end 320.450 250.000) (width 0.2) (layer "F.Cu") (net 502))   ; PHY1_TXN
;; a 45° turn keeps the 0.45 spacing: offset both by (±0.318, ±0.318) along the corner
```

## E5. Keepout bypass on the same layer

From the skill's own test fixture (`tests/run_tests.js`). Keepout on F.Cu spans x 13.5–15.5, y 9–10.5. The track lifts to y = 11 with two 45° jogs and never enters the polygon.

```lisp
(zone (net 0) (net_name "") (layer "F.Cu") (name "KO_no_tracks") (hatch edge 0.5)
	(keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour allowed) (footprints allowed))
	(polygon (pts (xy 13.5 9) (xy 15.5 9) (xy 15.5 10.5) (xy 13.5 10.5))))

;; GOOD — detour on F.Cu
(segment (start 10.7875 10) (end 12 10)       (width 0.2) (layer "F.Cu") (net 1))
(segment (start 12 10)      (end 13 11)       (width 0.2) (layer "F.Cu") (net 1))
(segment (start 13 11)      (end 16.2125 11)  (width 0.2) (layer "F.Cu") (net 1))
(segment (start 16.2125 11) (end 17.2125 10)  (width 0.2) (layer "F.Cu") (net 1))
(segment (start 17.2125 10) (end 19.2125 10)  (width 0.2) (layer "F.Cu") (net 1))

;; BAD — straight through (audit: FAIL keepout); also bad: dropping to B.Cu with two vias to pass underneath
(segment (start 12 10) (end 17.2125 10) (width 0.2) (layer "F.Cu") (net 1))
```

## E6. Copper zone block (In1.Cu GND plane, golden)

```lisp
(zone
	(net 35)
	(net_name "GND")
	(layer "In1.Cu")
	(hatch edge 0.5)
	(priority 1)
	(connect_pads (clearance 0.1))          ; no mode atom => thermal reliefs
	(min_thickness 0.1)
	(filled_areas_thickness no)
	(fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
	(polygon (pts …))
)
```

Outer-layer power pours differ only in `(min_thickness 0.25)`; small LC-node islands use `(connect_pads (clearance 0.05))` and `(min_thickness 0.05)`.

## E7. Schematic: hierarchical label, sheet pin, no_connect, PWR_FLAG (golden)

```lisp
;; Reset.kicad_sch — inter-sheet signal leaves through a hierarchical label with an explicit direction
(hierarchical_label "BRX_HPS_nRST"
	(shape output)
	(at 85.09 118.11 180)
	(effects (font (size 1.27 1.27)) (justify right))
)

;; Memory_&_Clock.kicad_sch — every unused IC pin gets a flag (126 on this sheet)
(no_connect (at 382.27 160.02))

;; Power_Supply.kicad_sch — externally driven rail
(symbol (lib_id "power:PWR_FLAG") (at 280.67 134.62 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) …)
```

Never write a `(global_label …)` for a signal; the golden project has zero.

## E8. DNP part, both sides consistent

```lisp
;; schematic symbol
(symbol (lib_id "Device:R") … (dnp yes) (in_bom yes) (on_board yes) …)
;; board footprint
(footprint "Resistor_SMD:R_0603_1608Metric" … (attr smd dnp) …)
```

The audit warns when the two counts differ (golden: 89 = 89).
