# verification and checklist

_Manual verification procedure and one-page checklist — sections 5–6 of the full standard. The audit script automates section 5._

> **Revised 2026-09-16 (rev B).** Steps 5–7 are superseded: any arc is FAIL, widths/vias are judged against the netclass, missing `remove_unused_layers` is FAIL, spacing and edge clearance follow the project rules. See `07_review_decisions.md`; the audit script implements the current semantics.

## 5. Parsing and verification procedure for Claude Code

When asked to review, route or modify a KiCad project against this standard, execute these steps in order and report every failure with net name, layer and coordinates.

1. **Parse** `.kicad_pcb` as an s-expression tree (KiCad 9, `version 20241229`, generator `pcbnew`). Do not regex-scan; nested `(net …)`, `(layer …)`, `(at …)` tokens require a real parser.
2. **Verify stackup**: 4 copper layers, thicknesses per 3.1, `tenting front back`, `pad_to_mask_clearance 0`.
3. **Verify inner layers carry no segments**: count `segment` by layer; In1.Cu and In2.Cu must be 0.
4. **Angle check**: for every `segment`, `angle = atan2(dy,dx) mod 45°`; fail if `|angle| > 0.01°`. Report the count of 45° vs 90° corners; expect ≥ 90 % 45°.
5. **Arc check**: list every `arc`; each must belong to a net that has a tuning meander (adjacent 0.1 mm stubs, radius ≤ 0.3 mm). Any other arc is a failure.
6. **Width check**: signal width 0.2 mm; anything < 0.2 mm must be within 2 mm of a BGA pad; power widths must be in {0.5, 0.6, 0.8, 1.0, 1.5, 2.0}. Flag mid-run width changes not at a pad/via/junction.
7. **Via check**: every via is 0.45 / 0.2, `F.Cu`–`B.Cu`, `remove_unused_layers yes`, `keep_end_layers yes`; centre-to-centre ≥ 0.45 mm; no via centre inside an SMD pad outline.
8. **Via centring**: every segment endpoint within 0.2 mm of a via centre of the same net must equal it to 6 decimals.
9. **Pad entry**: compute absolute pad centres (`fp.at` + rotate(pad.at, fp.rot)); for each segment endpoint inside a pad of the same net and layer, require exact centre match unless pad ≥ 2 mm and endpoint is on the pad axis; require relative entry angle ∈ {0, 90} (45/135 only on round/square pads or BGA/fine pitch); require entry segment length ≥ 0.2 mm; require entry width ≤ min(pad w, pad h); flag ≥ 2 consecutive sub-0.3 mm segments within 1 mm of the pad.
10. **Keepout**: for every zone with `(keepout (tracks not_allowed))`, test every same-layer segment for polygon intersection; any hit fails.
11. **Diff pairs**: for every `_P/_N` pair, parallel same-layer sections must be 0.2 mm wide at 0.45 mm centre spacing (± 0.005).
12. **Zones**: every zone has `net_name`, `hatch edge 0.5`, thermal `connect_pads` with clearance 0.1 (0.05 allowed for local pours), `min_thickness` ∈ {0.05, 0.1, 0.25}, thermal gap/bridge 0.5/0.5, unique priority among overlapping zones.
13. **Footprints**: all on F.Cu unless told otherwise; `dnp` attr count equals schematic `(dnp yes)` count; mechanicals `exclude_from_bom`; references hidden; 3D model present.
14. **Edge**: Edge.Cuts is a single closed `gr_rect` (or closed polyline), stroke 0.05; no copper within 0.5 mm.
15. **Schematic**: 0 global labels; every unused pin has `no_connect`; PWR_FLAG on externally driven rails; label size 1.27; `LCSC` populated; root sheet contains only sheet symbols.
16. **Settings**: diff the project's `rule_severities`, `rules`, `net_settings.classes` and `defaults` against Sections 1.1–1.8; any deviation is reported.

Acceptance: steps 3, 4, 7, 8, 10 and 16 must be 100 % clean. Steps 5, 6, 9 and 12 may carry only the documented exceptions.

---

## 6. One-page checklist (imperatives)

- Always clone the golden `.kicad_pro` severities, rules, netclass and defaults before drawing anything.
- Always route on F.Cu / B.Cu only; keep In1.Cu = GND plane and In2.Cu = split power planes with no tracks.
- Always route at 0.2 mm, 45° lattice, mitred corners; never arcs, never curves, never teardrops.
- Always use the single 0.45 / 0.2 through via with unused-layer removal; never via-in-pad, never blind/micro vias.
- Always end tracks on the exact pad centre and exact via centre; one straight perpendicular entry segment, no neckdown, no staircase.
- Always route around same-layer keepouts; never cross them or hop layers to avoid them.
- Always keep diff pairs at 0.2 width / 0.25 gap.
- Always use thermal-relief zones with 0.5 / 0.5 spokes, hatch-edge outlines, unique priorities; solid connection only on mounting holes and heatsink pads.
- Always keep copper ≥ 0.5 mm from Edge.Cuts; hole-to-hole ≥ 0.25; hole clearance ≥ 0.15.
- Always hide references, keep silkscreen functional (connector names, logos), text ≥ 0.7 mm / 0.08 mm stroke.
- Always mark DNP in both schematic and footprint; exclude mechanicals from BOM; populate `LCSC` and `AqtechPN`.
- Always flag every unused pin with `no_connect`; use hierarchical labels and sheet pins, never global labels; add `PWR_FLAG` on externally driven rails.
- Never add a `.kicad_dru` unless asked; never downgrade an `error` severity; never resolve DRC by weakening rules—use per-instance exclusions.
