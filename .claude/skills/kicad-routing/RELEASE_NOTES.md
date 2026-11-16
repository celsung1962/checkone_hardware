# kicad-routing 1.28.1 - release notes

Package `kicad-routing-1.28.1.zip`, 2026-11-02, from the `aqtech-skills` repository. No change to any tool or
audit result: the test suites run in CI on KiCad 10.0.8 (Linux) and in one command, `python tests/run_all.py
--strict`. On Linux install matplotlib, numpy and shapely for KiCad's Python (see `INSTALL.md`). The 1.28.0 notes
below still describe everything that changed since 1.19.x.

# kicad-routing 1.28.0 - release notes

Package `kicad-routing-1.28.0.zip`, 2026-10-31. Changes since 1.19.x, grouped by what they do for you. The full
list, with the reasons, is in `CHANGELOG.md`; the lessons behind 1.20-1.28 are in
`references/11_board_review_lessons.md` (ServiceOne rev. 0.2 board review, Vladimir Duk).

## Before you update

- **KiCad must be closed** on the boards you work on: since 1.20.0 every script that saves a board refuses while
  KiCad's lock files exist or the `.kicad_pro` is missing (`board_guard.py`). Override with `--force-write` only when
  you know why.
- **The audit is stricter.** Boards that passed under 1.19 will show new FAILs (pad entries, vias between the pads
  of two-pad parts, vias in IC pad-row bands, duplicate copper, same-net crossings). That is intended: they are the
  defects of the rev. 0.2 review. Record the ones you accept in `approved_rule_deviations` /
  `plane_net_exceptions` of `kicad_golden.project.json`.
- **Datasheet review gate (1.26.0).** `route_freerouting.py` and the audit pre-flight stop while the project's
  `datasheet_layout` review is pending. Run `datasheet_layout_scan.py` first (playbook B0).
- **New-FAIL gate and acute joints (1.27.0).** The audit FAILs acute joints (section 32): a board that passed 1.26 may
  show some. `finish_gated.py`, `centre_gated.py` and `refinish_gated.py` now revert any change that adds an audit
  FAIL, so they keep fewer changes than before - the ones they dropped were creating defects elsewhere. Gate your own
  scripted or hand edits the same way: `audit_gate.py <board before> <board after>`.
- **Stop rule, locks, diagonals (1.28.0).** `finish_gated.py` and `refinish_gated.py` now stop a run that keeps fewer
  than 1 in 5 attempts or would exceed its budget (`--budget`, default 60 min; `--no-stop-rule` for experiments), and
  revert any change that moves a locked track or via. The audit WARNs 45-degree segments longer than 3 mm outside IC
  fan-outs (section 33); list the nets that need them in `routing_style.diagonal_exceptions` with the reason. Run
  KiCad's Cleanup with "Delete tracks fully inside pads" off.

## New

| Version | What | Script / check |
|---|---|---|
| 1.20.0 | Board review rules: 16 new or stricter audit checks, pre-write guard, stale zone fills, layout (Kelvin) gate in `finish_gated.py`, economical via tier | `kicad_audit.js` §19-29, `board_guard.py`, `zone_fill_check.py` |
| 1.21.0 | Plan the inner power planes before routing | `plane_plan.py map / apply / check`, audit §30 |
| 1.22.0 | "No vias" rule areas over every IC pad-row band | `pad_row_keepouts.py`, `export_keepouts.py --pad-row-bands` |
| 1.23.0 | Axial pad entries: every routed pad end is a straight stub to pad edge + 0.5 mm; realign existing entries | `route_finish.py --refinish`, `refinish_gated.py` |
| 1.24.0 | Fan-out pattern and pin-array centreline | audit §31, `fanout_regularise.py` |
| 1.25.0 | Approximate 3D models, mounting holes with their own keep-out | `model_builder.py`, `mounting_hole_fp.py` |
| 1.26.0 | Datasheet layout suggestions scanned before routing; they become placement moves and `layout_checks` | `datasheet_layout_scan.py`, `layout_measure.py check --pre-route` |
| 1.26.1 | Pre-flight honours `approved_rule_deviations` | audit pre-flight |
| 1.26.2 | Datasheet scan reads hand-imported documents and keeps the review's own fields | `datasheet_layout_scan.py` |
| 1.26.3 | Board title-block revision compared with the schematic | audit `revision` WARN |
| 1.26.4 | Island mode: a route from an open end goes to another island of its net instead of running back along its own copper | `route_finish.py`, `finish_gated.py` pad-to-pad ends |
| 1.26.5 | A datasheet `"surface": true` pin-capacitor pair is excused from the plane-net rule (INFO) | audit rule 17 |
| 1.26.6 | `--avoid-exempt` takes several circles (`X,Y,R;X,Y,R`); island mode no longer crashes when the route starts on a pad | `route_finish.py` |
| 1.27.0 | Rules enforced, not counted (ServiceOne D133 review): acute joints FAIL; a change that adds any FAIL is blocked however much the total falls; the gated drivers apply it; the router never turns sharper than 90°; no hand-off with dangling copper | audit §32, `audit_gate.py`, `finish_gated.py` / `centre_gated.py` / `refinish_gated.py`, `route_finish.py` (exit 5, `--allow-acute`) |
| 1.28.0 | Finishing a routed board under the gates (ServiceOne rev. 0.2, L30-L44): stop rule, locks honoured, fast per-attempt DRC, area filters, orthogonal-first routing check, shared-gap message independent of file order, gated single-candidate tools | `stop_rule.py`, `locks.py`, `stage_gate.py`, `gate_each.py`, `via_relocate.py`, `open_ends.py`, `dangling_classify.py`, `via_spot.py`, `dedupe_copper.py`, `edit_tracks.py`, audit §33 `diagonal` |

## Fixed

- `route_finish.py` could turn back at 135° at the end of an axial stub when the target lay behind the pad (an acute
  joint the audit did not see before 1.27.0); the 1.23 SOIC test route had one (1.27.0).
- The scripted gates compared only the board's total FAIL count, so a rework that removed old FAILs could add new ones
  unseen (ServiceOne D133: 220 new FAILs, total 1 932 -> 1 795) (1.27.0).
- `route_finish.py` island mode: a route starting on a via was sealed in (the free circle was smaller than the via),
  and a route starting on a pad crashed with `'PAD' object has no attribute 'GetWidth'` (1.26.4, 1.26.6).
- JSON written by the scans with CRLF on Windows (1.26.2).

- The audit's shared-gap message listed its nets in file order, so a pcbnew save of an unchanged board "added" a FAIL
  and `centre_gated.py` kept nothing (1.28.0).
- Gated drivers could move or delete locked copper: DRC and the audit do not see locks (1.28.0).

## Known limits

- `route_finish.py` and `finish_gated.py` cannot shove neighbouring copper. Pads boxed in by finished nets stay
  open: finish them in KiCad's interactive router (shove mode). The ServiceOne ADC region (2026-10-21) ended with 32
  such connections after a scripted re-placement.
- There is no dedicated test suite yet for the island mode of `route_finish.py`; it was verified on the ServiceOne
  board (U7 and ADC regions).

- `audit_gate.py` compares findings by identity (check + message without its numbers). A part that moved can re-key a
  finding that names a via by its coordinates, and the same FAIL then shows as new: read the list, do not wave it
  through.

- `via_relocate.py` checks copper and hole clearances of the new via spot but not the between-pads centring of the
  tracks beside it; most of its moves are then refused by the gate (ServiceOne sample: 0 of 4). Drive it with
  `gate_each.py`, never with `--apply` on its own on a board that goes to review.
- Stage 3 of reference 11 (section 10) is planned, not shipped: plane vias placed on the pad axis by the stitcher,
  tool-lock tags, `route_finish.py` exact centre ends and cluster mode, layer directions in `rules_writer.py`.

## Verify after installing

Run `scripts/doctor.py` with the system Python and with KiCad's Python, then the 14 test suites listed in
`INSTALL.md` (366 assertions in 1.28.0, all passing on the release machine).
