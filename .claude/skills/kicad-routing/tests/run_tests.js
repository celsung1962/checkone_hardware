#!/usr/bin/env node
/*
 * run_tests.js — self-test for the kicad-routing skill (1.2.0, post-review semantics).
 *
 * Generates synthetic KiCad 9 boards in tests/fixtures/:
 *   good.kicad_pcb — one Default-class signal routed around a keepout; one POWER_DC net (+3.3V, class width 0.6,
 *                    class via 0.6/0.3) dropped through a via to B.Cu. Must PASS with 0 FAIL / 0 WARN.
 *   bad.kicad_pcb  — one deliberate violation per hard rule; every expected FAIL must fire.
 *   params         — a kicad_golden.project.json exercising length groups and the via budget.
 * Also exercises apply_settings.js (netclasses + patterns) on a minimal .kicad_pro.
 *
 * Usage: node tests/run_tests.js        (exit 0 = all assertions passed)
 */
'use strict';
const fs = require('fs'); const path = require('path'); const { spawnSync } = require('child_process');
const here = __dirname; const fx = path.join(here, 'fixtures'); fs.rmSync(fx, { recursive: true, force: true }); fs.mkdirSync(fx, { recursive: true });
const audit = path.join(here, '..', 'scripts', 'kicad_audit.js'); const apply = path.join(here, '..', 'scripts', 'apply_settings.js');
let uid = 0; const U = () => `00000000-0000-4000-8000-${String(++uid).padStart(12, '0')}`;
const NET = ['', 'SIG', 'GND', '+3.3V', 'BUS_D0', 'BUS_D1', 'BUS_CLK', 'MYBUS_D0'];

// ------------------------------------------------------------ board template pieces
const header = `(kicad_pcb
\t(version 20241229)
\t(generator "pcbnew")
\t(generator_version "9.0")
\t(general (thickness 1.6) (legacy_teardrops no))
\t(paper "A4")
\t(layers
\t\t(0 "F.Cu" signal) (4 "In1.Cu" signal) (6 "In2.Cu" signal) (2 "B.Cu" signal)
\t\t(13 "F.Paste" user) (15 "B.Paste" user) (5 "F.SilkS" user "F.Silkscreen") (7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user) (3 "B.Mask" user) (25 "Edge.Cuts" user) (31 "F.CrtYd" user "F.Courtyard") (29 "B.CrtYd" user "B.Courtyard") (35 "F.Fab" user) (33 "B.Fab" user)
\t)
\t(setup
\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen")) (layer "F.Paste" (type "Top Solder Paste")) (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035)) (layer "dielectric 1" (type "prepreg") (thickness 0.1) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.0175)) (layer "dielectric 2" (type "core") (thickness 1.24) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.0175)) (layer "dielectric 3" (type "prepreg") (thickness 0.1) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035)) (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01)) (layer "B.Paste" (type "Bottom Solder Paste")) (layer "B.SilkS" (type "Bottom Silk Screen"))
\t\t\t(copper_finish "None") (dielectric_constraints no)
\t\t)
\t\t(pad_to_mask_clearance 0)
\t\t(allow_soldermask_bridges_in_footprints no)
\t\t(tenting front back)
\t)
${NET.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}
`;
const prop = (name, value, layer, hide) => `\t\t(property "${name}" "${value}" (at 0 0 0) (layer "${layer}")${hide ? ' (hide yes)' : ''} (uuid "${U()}") (effects (font (size 1 1) (thickness 0.15))))\n`;
const resistor = (ref, x, y, net1, net2) => `\t(footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu") (uuid "${U()}") (at ${x} ${y})
${prop('Reference', ref, 'F.SilkS', true)}${prop('Value', '10k', 'F.Fab', true)}${prop('Footprint', 'Resistor_SMD:R_0603_1608Metric', 'F.Fab', true)}${prop('Datasheet', '', 'F.Fab', true)}${prop('Description', 'Resistor', 'F.Fab', true)}\t\t(attr smd)
\t\t(fp_line (start -1.48 -0.73) (end 1.48 -0.73) (stroke (width 0.05) (type default)) (layer "F.CrtYd") (uuid "${U()}"))
\t\t(pad "1" smd roundrect (at -0.7875 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25) (net ${net1} "${NET[net1]}") (uuid "${U()}"))
\t\t(pad "2" smd roundrect (at 0.7875 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25) (net ${net2} "${NET[net2]}") (uuid "${U()}"))
\t\t(model "\${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
\t)
`;
const header1 = (ref, x, y, net) => `\t(footprint "Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical" (layer "F.Cu") (uuid "${U()}") (at ${x} ${y})
${prop('Reference', ref, 'F.SilkS', true)}${prop('Value', 'Conn', 'F.Fab', true)}${prop('Footprint', 'Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical', 'F.Fab', true)}${prop('Datasheet', '', 'F.Fab', true)}${prop('Description', 'Header', 'F.Fab', true)}\t\t(attr through_hole)
\t\t(pad "1" thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (net ${net} "${NET[net]}") (uuid "${U()}"))
\t\t(model "\${KICAD9_3DMODEL_DIR}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x01_P2.54mm_Vertical.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
\t)
`;
const seg = (x1, y1, x2, y2, w, layer, net) => `\t(segment (start ${x1} ${y1}) (end ${x2} ${y2}) (width ${w}) (layer "${layer}") (net ${net}) (uuid "${U()}"))\n`;
const via = (x, y, size, drill, net, rul = true) => `\t(via (at ${x} ${y}) (size ${size}) (drill ${drill}) (layers "F.Cu" "B.Cu")${rul ? ' (remove_unused_layers yes) (keep_end_layers yes)' : ''} (net ${net}) (uuid "${U()}"))\n`;
const plane = (layer, net, prio) => `\t(zone (net ${net}) (net_name "${NET[net]}") (layer "${layer}") (uuid "${U()}") (hatch edge 0.5) (priority ${prio}) (connect_pads (clearance 0.1)) (min_thickness 0.1) (filled_areas_thickness no)
\t\t(fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
\t\t(polygon (pts (xy 1 1) (xy 49 1) (xy 49 39) (xy 1 39)))
\t)
`;
const keepout = `\t(zone (net 0) (net_name "") (layer "F.Cu") (uuid "${U()}") (name "KO_no_tracks") (hatch edge 0.5)
\t\t(keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour allowed) (footprints allowed))
\t\t(polygon (pts (xy 13.5 9) (xy 15.5 9) (xy 15.5 10.5) (xy 13.5 10.5)))
\t)
`;
// rev I regression fixture: a keepout that lives INSIDE a footprint. Before rev I these were
// invisible to the audit (kids(pcb,'zone') sees top-level zones only) and silently counted 0.
const fpWithKeepout = (ref, x, y) => `	(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at ${x} ${y})
${prop('Reference', ref, 'F.SilkS', true)}${prop('Value', 'TP', 'F.Fab', true)}${prop('Footprint', 'Connector:TestPoint', 'F.Fab', true)}${prop('Datasheet', '', 'F.Fab', true)}${prop('Description', 'Test point', 'F.Fab', true)}		(attr smd)
		(fp_line (start -1 -1) (end 1 -1) (stroke (width 0.05) (type default)) (layer "F.CrtYd") (uuid "${U()}"))
		(zone (net 0) (net_name "") (layer "F.Cu") (uuid "${U()}") (name "KO_in_footprint") (hatch edge 0.5)
			(keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour allowed) (footprints allowed))
			(polygon (pts (xy 43 5) (xy 46 5) (xy 46 8) (xy 43 8)))
		)
	)
`;
const edge = `\t(gr_rect (start 0 0) (end 50 40) (stroke (width 0.05) (type default)) (fill no) (layer "Edge.Cuts") (uuid "${U()}"))\n`;
// R1: GND | SIG   R2: SIG | +3.3V   J1: +3.3V   R3/R4/R5: bus nets for the length group (BUS_D0, BUS_D1, BUS_CLK)
const footprints = resistor('R1', 10, 10, 2, 1) + resistor('R2', 20, 10, 1, 3) + header1('J1', 25, 10, 3) +
  resistor('R3', 10, 30, 2, 4) + resistor('R4', 10, 33, 2, 5) + resistor('R5', 10, 36, 2, 6) + resistor('R6', 40, 30, 4, 2) + resistor('R7', 40, 33, 5, 2) + resistor('R8', 40, 36, 6, 2) + fpWithKeepout('TP1', 44.5, 6.5);
const planes = plane('In1.Cu', 2, 0) + plane('In2.Cu', 3, 0);

// good: SIG (Default 0.2) detours over the keepout; +3.3V (POWER_DC 0.6, via 0.6/0.3) drops to B.Cu into J1;
// bus nets D0/D1/CLK routed straight with equal lengths (29.2125 mm) — length group spread 0
const busRoute = [4, 5, 6].map((n, i) => seg(10.7875, 30 + 3 * i, 39.2125, 30 + 3 * i, 0.2, 'F.Cu', n)).join('');
// rev P: +3.3V is a plane net (In2.Cu zone below). R2 pad 2 and J1 pad 1 each get their OWN stub
// and via to the plane — no surface track joins them (improvements #7 / D3), unlike the pre-1.16.0
// fixture which routed R2 -> via -> J1 as one shared link and would now FAIL that check.
const goodRoute =
  seg(10.7875, 10, 12, 10, 0.2, 'F.Cu', 1) + seg(12, 10, 13, 11, 0.2, 'F.Cu', 1) + seg(13, 11, 16.2125, 11, 0.2, 'F.Cu', 1) +
  seg(16.2125, 11, 17.2125, 10, 0.2, 'F.Cu', 1) + seg(17.2125, 10, 19.2125, 10, 0.2, 'F.Cu', 1) +
  seg(20.7875, 10, 21.9, 10, 0.6, 'F.Cu', 3) + via(21.9, 10, 0.6, 0.3, 3) +   // 1.20.0: via ring 0.41 mm from R2-2 (>= 0.15 mask web, review issue 10)
 
  seg(25, 10, 23.5, 10, 0.6, 'F.Cu', 3) + via(23.5, 10, 0.6, 0.3, 3) + busRoute;
const good = header + footprints + goodRoute + planes + keepout + edge + ')\n';

// bad: one violation per hard rule (+ soft ones the params file should catch)
const badRoute =
  seg(10.7875, 10, 12, 10, 0.2, 'F.Cu', 1) + seg(12, 10, 17.2125, 10, 0.2, 'F.Cu', 1) + seg(17.2125, 10, 19.2125, 10, 0.2, 'F.Cu', 1) + // crosses keepout
  seg(20.7875, 10, 22, 10, 0.2, 'F.Cu', 3) + via(22.05, 10, 0.45, 0.2, 3, false) + seg(22, 10, 25, 10, 0.2, 'B.Cu', 3) +             // +3.3V at 0.2 (class 0.6) → WARN; via 0.05 off; via lacks rul → FAIL
  seg(30, 20, 32, 20, 0.2, 'In1.Cu', 2) +                                                                                             // inner layer
  seg(30, 25, 32, 26, 0.15, 'F.Cu', 1) +                                                                                              // off-lattice + below 0.2 outside BGA
  `\t(arc (start 30 30) (mid 31 31) (end 32 30) (width 0.2) (layer "F.Cu") (net 1) (uuid "${U()}"))\n` +                            // any arc
  via(35, 20, 0.5, 0.25, 2) +                                                                                                         // matches neither class nor predefined
  via(10.7875, 10, 0.45, 0.2, 1) +                                                                                                    // via-in-pad (R1-2)
  via(36, 24, 0.45, 0.2, 1) + via(36.4, 24, 0.45, 0.2, 1) +                                                                           // hole-to-hole 0.2 < 0.25
  seg(0.3, 20, 2, 20, 0.2, 'F.Cu', 1) +                                                                                               // copper at the board edge
  `\t(zone (net 0) (net_name "") (layer "B.Cu") (uuid "${U()}") (hatch edge 0.5) (connect_pads (clearance 0.1)) (min_thickness 0.1) (filled_areas_thickness no) (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts (xy 40 30) (xy 45 30) (xy 45 35) (xy 40 35))))\n` + // zone without net
  seg(10.7875, 30, 39.2125, 30, 0.2, 'F.Cu', 4) + seg(10.7875, 33, 39.2125, 33, 0.2, 'F.Cu', 5) +                                     // BUS_D0/D1 29.2 mm
  seg(10.7875, 36, 20, 36, 0.2, 'F.Cu', 6) + via(20, 36, 0.45, 0.2, 6) + seg(20, 36, 24, 36, 0.2, 'B.Cu', 6) + via(24, 36, 0.45, 0.2, 6) + seg(24, 36, 28, 36, 0.2, 'F.Cu', 6) + via(28, 36, 0.45, 0.2, 6) + seg(28, 36, 39.2125, 36, 0.2, 'B.Cu', 6); // CLK: 3 vias (budget 2), same length as data (clock rule: shorter_or_equal ok) but group spread fine
const bad = header + footprints + badRoute + planes + keepout + edge + ')\n';

fs.writeFileSync(path.join(fx, 'good.kicad_pcb'), good);
fs.writeFileSync(path.join(fx, 'bad.kicad_pcb'), bad);
const params = { project: 'fixture', length_groups: [{ name: 'BUS', pattern: '^BUS_(D\\d|CLK)$', max_spread_mm: 1.0, clock_pattern: '^BUS_CLK$', clock_rule: 'shorter_or_equal' }], via_budget: { fast_patterns: ['^BUS_'], max_vias_fast: 2, max_vias_default: null }, silkscreen: { references_hidden: true }, teardrops: { allowed: false }, via_in_pad: { allowed_refs: [] } };
fs.writeFileSync(path.join(fx, 'kicad_golden.project.json'), JSON.stringify(params, null, 2));

// ------------------------------------------------------------ project files
const minimalPro = { board: { design_settings: { drc_exclusions: [['keep|me', '']] } }, erc: {}, net_settings: { classes: [{ name: 'MyBus', clearance: 0.2, track_width: 0.5 }], netclass_patterns: [{ netclass: 'MyBus', pattern: '*MYBUS*' }, { netclass: 'POWER_DC', pattern: '+3.3V' }, { netclass: 'POWER_DC', pattern: 'GND' }] }, schematic: {}, meta: { filename: 'good.kicad_pro', version: 3 } };
fs.writeFileSync(path.join(fx, 'good.kicad_pro'), JSON.stringify(minimalPro, null, 2));
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`); };
const run = (script, argv) => spawnSync(process.execPath, [script, ...argv], { encoding: 'utf8', cwd: here });

let r = run(apply, [path.join(fx, 'good.kicad_pro')]);
check('apply_settings merges into a minimal project', r.status === 0 && /changed \d+ settings blocks/.test(r.stdout), r.stdout.split('\n')[0]);
const merged = JSON.parse(fs.readFileSync(path.join(fx, 'good.kicad_pro'), 'utf8'));
const names = merged.net_settings.classes.map(c => c.name);
check('apply_settings adds template netclasses and keeps the project one', ['Default', 'POWER_DC', 'POWER_AC', 'MyBus'].every(n => names.includes(n)) && names[0] === 'Default', names.join(','));
// rev K: the template ships NO netclass patterns on purpose - patterns captured from another
// board match nothing here while this board's own rails silently stay on Default. The tool
// must therefore preserve the project's patterns and invent none of its own.
check('apply_settings keeps the project patterns and adds none of its own',
  merged.net_settings.netclass_patterns.some(p => p.pattern === '*MYBUS*')
  && merged.net_settings.netclass_patterns.filter(p => p.pattern === '+3.3V').length === 1,
  merged.net_settings.netclass_patterns.map(p => p.pattern).join(','));
check('the shipped template carries no netclass patterns (rev K)',
  (JSON.parse(fs.readFileSync(path.join(here, '..', 'golden_settings.json'), 'utf8'))
    .net_settings.netclass_patterns || []).length === 0);
check('apply_settings keeps drc_exclusions and sets golden min_clearance', merged.board.design_settings.drc_exclusions.length === 1 && merged.board.design_settings.rules.min_clearance === 0.1);
check('apply_settings sets straight tuning corners (Q-03)', merged.board.design_settings.tuning_pattern_settings.single_track_defaults.corner_style === 2);
r = run(apply, [path.join(fx, 'good.kicad_pro'), '--dry-run']);
check('apply_settings is idempotent', /already golden/.test(r.stdout));
// mandatory pre-routing gate: fabricator profile (JLCPCB 4-layer 1oz) enforced and recorded in the params file
r = run(apply, [path.join(fx, 'good.kicad_pro'), '--fab', 'jlcpcb', '--layers', '4', '--copper', '1oz']);
const merged2 = JSON.parse(fs.readFileSync(path.join(fx, 'good.kicad_pro'), 'utf8'));
check('apply_settings --fab keeps rules at the stricter of template/JLCPCB (min_track_width stays 0.1 ≥ 0.09)', r.status === 0 && merged2.board.design_settings.rules.min_track_width === 0.1 && /profile 4L-1oz/.test(r.stdout), r.stdout.split('\n')[0]);
const paramsAfter = JSON.parse(fs.readFileSync(path.join(fx, 'kicad_golden.project.json'), 'utf8'));
check('apply_settings --fab records layers/copper/limits in kicad_golden.project.json and keeps existing params', paramsAfter.fabricator.layers === 4 && paramsAfter.fabricator.copper === '1oz' && paramsAfter.fabricator.kicad_rules.min_through_hole_diameter === 0.15 && paramsAfter.length_groups.length === 1, JSON.stringify(paramsAfter.fabricator).slice(0, 120));
r = run(apply, [path.join(fx, 'good.kicad_pro'), '--fab', 'jlcpcb', '--layers', '2', '--copper', '2oz', '--dry-run']);
check('apply_settings --fab 2L-2oz would raise min_track_width/clearance to 0.2 and via drill to 0.3', /min_track_width \(jlcpcb 2L 2oz: 0\.1 → 0\.2\)/.test(r.stdout) && /min_through_hole_diameter \(jlcpcb 2L 2oz: 0\.15 → 0\.3\)/.test(r.stdout));
r = run(apply, [path.join(fx, 'good.kicad_pro'), '--fab', 'jlcpcb', '--layers', '4']);
check('apply_settings refuses an incomplete fabricator triple', r.status === 2);
for (const f of fs.readdirSync(fx)) if (/\.bak-/.test(f)) fs.unlinkSync(path.join(fx, f));
fs.copyFileSync(path.join(fx, 'good.kicad_pro'), path.join(fx, 'bad.kicad_pro'));

// ------------------------------------------------------------ audits
r = run(audit, [path.join(fx, 'good.kicad_pcb'), '--json', path.join(fx, 'good.audit.json'), '--no-sch', '--quiet']);
const goodRep = JSON.parse(fs.readFileSync(path.join(fx, 'good.audit.json'), 'utf8'));
check('good board exits 0', r.status === 0, `exit ${r.status}`);
check('good board has 0 FAIL', !goodRep.summary.FAIL, goodRep.findings.filter(f => f.level === 'FAIL').map(f => f.msg).join(' | ') || 'clean');
// rev D: the drill conflict is resolved — min_through_hole_diameter is harmonized to the netclass via
// drill (0.15), so the good board must now be completely WARN-free and report no drill conflict at all.
const goodWarns = goodRep.findings.filter(f => f.level === 'WARN');
const drillConflict = goodWarns.filter(f => f.check === 'netclass' && /via drill 0\.15 is below min through-hole 0\.2/.test(f.msg));
check('good board has no WARN at all (rev D: drill conflict harmonized away)', goodWarns.length === 0, goodWarns.map(f => f.msg).join(' | ') || 'clean');
check('rev D: no netclass drill conflict is reported once the rule is harmonized', drillConflict.length === 0, drillConflict.map(f => f.msg).join(' | ') || 'harmonized');
check('good board: +3.3V resolved to POWER_DC (0.6 track, 0.6/0.3 via accepted)', goodRep.stats.tracks_not_at_class_width === 0 && goodRep.stats.via_stacks['0.6/0.3 F.Cu-B.Cu'] === 2, JSON.stringify(goodRep.stats.via_stacks));
check('good board: +3.3V pads each have their own via, no plane-net link (improvements #7)', goodRep.stats.plane_net_link_violations === 0, String(goodRep.stats.plane_net_link_violations));
check('good board: keepouts present (top-level + footprint-internal) and not crossed',
  goodRep.stats.keepout_zones === 2 && !goodRep.findings.some(f => f.check === 'keepout' && f.level !== 'INFO'),
  JSON.stringify({ zones: goodRep.stats.keepout_zones, inFootprints: goodRep.stats.keepout_zones_in_footprints }));
// rev I: footprint-internal rule areas must be found, and the audit must SAY what it checked -
// silence previously implied the rule had been applied when nothing had been examined.
check('rev I: footprint-internal keepout is detected', goodRep.stats.keepout_zones_in_footprints === 1,
  String(goodRep.stats.keepout_zones_in_footprints));
check('rev I: audit states the keepout count explicitly',
  goodRep.findings.some(f => f.check === 'keepout' && f.level === 'INFO' && /keepout/.test(f.msg)),
  goodRep.findings.filter(f => f.check === 'keepout').map(f => f.msg).join(' | ') || 'no keepout INFO emitted');
check('good board: all pad entries exactly centred', goodRep.stats.pad_entries.off_centre === 0 && goodRep.stats.pad_entries.exact_centre === 10, JSON.stringify(goodRep.stats.pad_entries));
check('good board: length group BUS evaluated with spread 0', goodRep.stats.length_groups.length === 1 && goodRep.stats.length_groups[0].spread_mm === 0, JSON.stringify(goodRep.stats.length_groups));
check('good board: settings match template', goodRep.stats.settings && goodRep.stats.settings.rule_mismatches === 0 && goodRep.stats.settings.netclass_mismatches === 0, JSON.stringify(goodRep.stats.settings));

r = run(audit, [path.join(fx, 'bad.kicad_pcb'), '--json', path.join(fx, 'bad.audit.json'), '--no-sch', '--quiet']);
const badRep = JSON.parse(fs.readFileSync(path.join(fx, 'bad.audit.json'), 'utf8'));
check('bad board exits 1', r.status === 1, `exit ${r.status}`);
const fails = badRep.findings.filter(f => f.level === 'FAIL'), warns = badRep.findings.filter(f => f.level === 'WARN');
const has = (list, checkName, re) => list.some(f => f.check === checkName && (!re || re.test(f.msg)));
check('bad: track on inner layer detected', has(fails, 'inner-layers'));
check('bad: off-lattice segment detected', has(fails, 'angle', /off the 45° lattice/));
check('bad: arc detected as FAIL (Q-03)', has(fails, 'arcs'));
check('bad: sub-0.2 mm track outside BGA detected', has(fails, 'width', /below 0.2 mm/));
check('bad: via matching neither class nor predefined detected', has(fails, 'via', /0\.5\/0\.25 .*matches neither/));
check('bad: via without remove_unused_layers is FAIL (Q-06)', has(fails, 'via', /lacks remove_unused_layers/));
check('bad: via-in-pad detected', has(fails, 'via', /inside SMD pad R1-2/));
check('bad: hole-to-hole below rule detected (Q-11)', has(fails, 'via', /hole-to-hole 0\.2 mm < 0\.25/));
check('bad: via near-miss detected', has(fails, 'via-centring', /0\.05 mm off via centre/));
check('bad: keepout crossing detected', has(fails, 'keepout', /crosses\/enters keepout "KO_no_tracks"/));
check('bad: copper at board edge detected (Q-12 rule-derived)', has(fails, 'edge', /within 0\.5 mm/));
check('bad: zone without net detected', has(fails, 'zone', /without net/));
check('bad: +3.3V at 0.2 mm flagged against POWER_DC class width (Q-04)', has(warns, 'width', /\+3\.3V \(class POWER_DC = 0\.6/));
check('bad: via budget exceeded on BUS_CLK (Q-09)', has(warns, 'via-budget', /BUS_CLK: 3 vias > 2/));
check('bad: plane-net surface link between R2 and J1 detected (improvements #7)', has(fails, 'plane-net', /R2-2/) && has(fails, 'plane-net', /J1-1/));
check('bad: no false FAIL on the untouched good route', !fails.some(f => f.check !== 'plane-net' && /R2-1|J1-1|BUS_D0|BUS_D1/.test(f.msg)), fails.filter(f => f.check !== 'plane-net' && /R2-1|J1-1|BUS_D0|BUS_D1/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
// 1.26.5: a datasheet "surface": true decoupling pair is excused from the plane-net rule; a third pad is not
fs.writeFileSync(path.join(fx, 'bad.dspair.params.json'), JSON.stringify({ layout_checks: { decoupling: [{ pin: 'J1.1', cap: 'R2.2', max_mm: 3, surface: true }] } }));
r = run(audit, [path.join(fx, 'bad.kicad_pcb'), '--json', path.join(fx, 'bad.dspair.audit.json'), '--no-sch', '--quiet', '--params', path.join(fx, 'bad.dspair.params.json')]);
const dsRep = JSON.parse(fs.readFileSync(path.join(fx, 'bad.dspair.audit.json'), 'utf8'));
check('1.26.5: datasheet surface pair J1-1/R2-2 is INFO, not a plane-net FAIL',
  !dsRep.findings.some(f => f.level === 'FAIL' && f.check === 'plane-net' && /R2-2|J1-1/.test(f.msg)) &&
  dsRep.findings.some(f => f.level === 'INFO' && f.check === 'plane-net' && /datasheet asks/.test(f.msg)),
  dsRep.findings.filter(f => f.check === 'plane-net').map(f => f.level + ' ' + f.msg).join(' | '));
fs.writeFileSync(path.join(fx, 'bad.dsother.params.json'), JSON.stringify({ layout_checks: { decoupling: [{ pin: 'J1.1', cap: 'C9.1', max_mm: 3, surface: true }] } }));
r = run(audit, [path.join(fx, 'bad.kicad_pcb'), '--json', path.join(fx, 'bad.dsother.audit.json'), '--no-sch', '--quiet', '--params', path.join(fx, 'bad.dsother.params.json')]);
check('1.26.5: a surface pair whose partner is not in the group excuses nothing',
  JSON.parse(fs.readFileSync(path.join(fx, 'bad.dsother.audit.json'), 'utf8')).findings.some(f => f.level === 'FAIL' && f.check === 'plane-net' && /R2-2/.test(f.msg)));

// ============================================================ rev P dedicated fixture: review.kicad_pcb
// Exercises the improvements-review rules (entries 1-11, kicad-golden 1.16.0) not covered by
// good/bad above. Footprints are placed >= 8 mm apart so each test case is geometrically isolated.
const NET2 = ['', 'A', 'B', 'THRU_A', 'THRU_B', 'THRU3', 'THRU4', 'GAPB', 'SMALLPAD', 'SPARE9', 'OFFCTR_PAD', 'SPARE11', 'ELONG_PAD', 'SPARE13', 'XTAL', 'XTAL_FOREIGN',
  'EXIT_OWN', 'EXIT_NB1', 'EXIT_NB2', 'ENTRY_OWN', 'ENTRY_FL1', 'ENTRY_FL2', 'QFN_PASS', 'POUR_OWN', 'POUR_FL1', 'POUR_FL2', 'FREE_END',
  'WIDE_GAP', 'GAP_A', 'GAP_B', 'HDR_PASS', 'UNDER1206', 'VIA_CTR', 'VIA_OFF', 'NONFACE'];
const header2 = header.replace(`${NET.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`, `${NET2.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`);
const propAt = (name, value, layer, hide, ax = 0, ay = 0) => `\t\t(property "${name}" "${value}" (at ${ax} ${ay} 0) (layer "${layer}")${hide ? ' (hide yes)' : ''} (uuid "${U()}") (effects (font (size 1 1) (thickness 0.15))))\n`;
const padR = (num, x, y, w, h, net) => `\t\t(pad "${num}" smd roundrect (at ${x} ${y}) (size ${w} ${h}) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2) (net ${net} "${NET2[net]}") (uuid "${U()}"))\n`;
const stdProps = (ref, valueLayer, valueHide, refLayer, refHide, refAt) =>
  `${propAt('Reference', ref, refLayer, refHide, refAt ? refAt[0] : 0, refAt ? refAt[1] : 0)}${propAt('Value', '10k', valueLayer, valueHide)}${propAt('Footprint', 'x', 'F.Fab', true)}${propAt('Datasheet', '', 'F.Fab', true)}${propAt('Description', 'x', 'F.Fab', true)}`;
const crtyd2 = `\t\t(fp_line (start -1.48 -0.73) (end 1.48 -0.73) (stroke (width 0.05) (type default)) (layer "F.CrtYd") (uuid "${U()}"))\n`;
const fabRect = (x0, y0, x1, y1, layer) => `\t\t(fp_rect (start ${x0} ${y0}) (end ${x1} ${y1}) (stroke (width 0.1) (type default)) (fill none) (layer "${layer}") (uuid "${U()}"))\n`;

// U1: visible Value on F.Fab (entry 1, WARN) + off-centre Fab reference (entry 2, WARN)
const U1 = `\t(footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu") (uuid "${U()}") (at 10 10)
${stdProps('U1', 'F.Fab', false, 'F.Fab', false, [0.8, 0.8])}\t\t(attr smd)
${fabRect(-1.5, -1, 1.5, 1, 'F.Fab')}${crtyd2}${padR('1', -0.7875, 0, 0.8, 0.95, 1)}${padR('2', 0.7875, 0, 0.8, 0.95, 2)}\t)
`;
// U2: hidden Value + centred Fab reference — clean comparison, must add no fab-values/fab-refs finding
const U2 = `\t(footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu") (uuid "${U()}") (at 10 25)
${stdProps('U2', 'F.Fab', true, 'F.Fab', false, [0, 0])}\t\t(attr smd)
${fabRect(-1.5, -1, 1.5, 1, 'F.Fab')}${crtyd2}${padR('1', -0.7875, 0, 0.8, 0.95, 1)}${padR('2', 0.7875, 0, 0.8, 0.95, 2)}\t)
`;
// TP2 / TP3: two DIFFERENT footprints whose single pads flank a third net's track, off-centre (entry 3).
// TP3 sits at y 10.5 (0.9 mm free between the pads): a gap between different parts is at most 1.5 mm free
// (local fix after 1.16.0); at the earlier y 11.5 (1.9 mm free) it would be open board, not a gap.
const TP2 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 30 9)
${stdProps('TP2', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 0.6, 0.6, 3)}\t)
`;
const TP3 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 30 10.5)
${stdProps('TP3', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 0.6, 0.6, 4)}\t)
`;
// P3: a 2-pad part; a foreign net passes between its OWN two pads, off-centre (entry 4 + route-around
// entry 10), and a SECOND foreign net squeezes through the SAME gap (entry 6, shared pad gap)
const P3 = `\t(footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu") (uuid "${U()}") (at 30 20)
${stdProps('P3', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', -0.7875, 0, 0.8, 0.95, 1)}${padR('2', 0.7875, 0, 0.8, 0.95, 2)}\t)
`;
// U5: small pad, entry wider than the pad's smallest dimension (entry 5, FAIL)
const U5 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 60 10)
${stdProps('U5', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 0.3, 0.3, 8)}\t)
`;
// U4: entry ends 0.1 mm off the pad centre (entry 8, FAIL — no exemption for any pad size)
const U4 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 65 10)
${stdProps('U4', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 0.6, 0.6, 10)}\t)
`;
// U3: elongated pad (1.2x0.4, ratio 3) entered perpendicular to its long axis (entry 9, WARN)
const U3 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 70 10)
${stdProps('U3', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 1.2, 0.4, 12)}\t)
`;
// Y1: crystal; a foreign net's track crosses its courtyard on F.Cu, its mounted side (entry 4 exception, FAIL)
const Y1 = `\t(footprint "Crystal_SMD:Crystal_SMD_3225_4Pin" (layer "F.Cu") (uuid "${U()}") (at 80 10)
${stdProps('Y1', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
\t\t(fp_rect (start -1 -1) (end 1 1) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd") (uuid "${U()}"))
${padR('1', -0.5, 0, 0.5, 0.5, 14)}${padR('2', 0.5, 0, 0.5, 0.5, 14)}\t)
`;

// U6 / U7: a track hugs U6 at less than twice the clearance rule for its whole 10 mm length, while
// U7 sits well clear on the other side — entry 11 (best-effort, component outlines only)
const U6 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 90 10)
${stdProps('U6', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 1, 1, 11)}\t)
`;
const U7 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 95 10)
${stdProps('U7', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 1, 1, 13)}\t)
`;

// Q1: multi-pad IC edge. Pin 2's axial exit stub has asymmetric neighbours (pin 1 at 0.5 mm pitch, pin 3
// at 0.7 mm, as at a QFN corner). The stub is a pad exit (entries 8/9), not a pass through a gap: no
// between-pads FAIL, no route-around WARN (BladeOne U6 pins 25/29, local fix after 1.16.0).
const Q1 = `\t(footprint "Package_DFN_QFN:QFN_test" (layer "F.Cu") (uuid "${U()}") (at 60 30)
${stdProps('Q1', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', -0.5, 0, 0.25, 0.8, 17)}${padR('2', 0, 0, 0.25, 0.8, 16)}${padR('3', 0.7, 0, 0.25, 0.8, 18)}${padR('4', 0, 3, 0.25, 0.8, 18)}\t)
`;
// TP4 / TP5 / TP6: a track ends at the centre of its own pad TP4, flanked by two unrelated pads abreast
// of TP4 at unequal distances. Entry 8 fixes the track at the pad centre: no between-pads FAIL
// (BladeOne C12-1 entry, local fix after 1.16.0).
const TP4 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 70 30)
${stdProps('TP4', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 0.9, 0.9, 19)}\t)
`;
const TP5 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 68.8 30)
${stdProps('TP5', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 0.6, 0.6, 20)}\t)
`;
const TP6 = `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at 71.5 30)
${stdProps('TP6', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 0.6, 0.6, 21)}\t)
`;
// Q2: regression guard. A foreign net passes 0.05 mm off-centre between two pads of a multi-pad
// footprint and ends in none of its own pads: still FAIL, worded "between pads", not "two-pad part".
const Q2 = `\t(footprint "Package_DFN_QFN:QFN_test" (layer "F.Cu") (uuid "${U()}") (at 80 30)
${stdProps('Q2', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', -0.6, 0, 0.4, 0.8, 17)}${padR('2', 0.6, 0, 0.4, 0.8, 18)}${padR('3', 0, 3, 0.4, 0.8, 18)}\t)
`;

// TP7 / TP8: unequal pads just past the end of a POUR_OWN stub. The stub ends inside its own-net zone
// fill, so they sit abreast of the pour, not of a track: no between-pads FAIL (BladeOne SW1/SW2 stubs).
// TP9 / TP10: the same layout past a FREE_END track that ends in nothing — the look-ahead still applies
// there, so it still FAILs (regression guard).
const tp1 = (ref, x, y, net) => `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at ${x} ${y})
${stdProps(ref, 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, 0.6, 0.6, net)}\t)
`;
const pourPts = '(xy 99.5 28) (xy 100.5 28) (xy 100.5 29) (xy 99.5 29)';
const POUR = `\t(zone (net 23) (net_name "POUR_OWN") (layer "F.Cu") (uuid "${U()}") (hatch edge 0.5) (connect_pads yes (clearance 0.1)) (min_thickness 0.1) (filled_areas_thickness no)
\t\t(fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
\t\t(polygon (pts ${pourPts}))
\t\t(filled_polygon (layer "F.Cu") (pts ${pourPts}))
\t)
`;
const pourCase = tp1('TP7', 99.0, 28.2, 24) + tp1('TP8', 100.9, 28.2, 25) + tp1('TP9', 109.0, 28.2, 24) + tp1('TP10', 110.9, 28.2, 25);

// Gap width (local fix after 1.16.0): between different parts a gap is at most 1.5 mm free.
// TP11 / TP12: 2.0 mm free, WIDE_GAP runs 0.3 mm off the middle -> open board, no FAIL.
// TP13 / TP14: header-like 1.7 mm pads at 2.54 mm pitch (0.84 mm free, the improvements doc's J3 case),
// HDR_PASS 0.05 mm off-centre -> still FAIL.
// P4: 1206 two-pad part, 1.7 mm free between its own pads, UNDER1206 off-centre -> still FAIL (entry 4
// has no width limit).
const tpS = (ref, x, y, s, net) => `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at ${x} ${y})
${stdProps(ref, 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', 0, 0, s, s, net)}\t)
`;
const P4 = `\t(footprint "Resistor_SMD:R_1206_3216Metric" (layer "F.Cu") (uuid "${U()}") (at 140 31)
${stdProps('P4', 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}${padR('1', -1.4, 0, 1.1, 1.8, 28)}${padR('2', 1.4, 0, 1.1, 1.8, 29)}\t)
`;
const gapCase = tpS('TP11', 120, 30, 0.6, 28) + tpS('TP12', 120, 32.6, 0.6, 29) + tpS('TP13', 130, 30, 1.7, 28) + tpS('TP14', 130, 32.54, 1.7, 29) + P4;

// Via flanks (local fix after 1.16.0): a track between a pad and an other-net via is in a gap. The via is
// 0.30/0.26 (0.02 mm ring), so with the template hole clearance (0.15) against 0.1 copper clearance the
// HOLE binds: the allowed channel is centred at x = pad + 0.66, not at the copper-edge midpoint (+0.675).
// VIA_CTR at +0.66 must pass; VIA_OFF at +0.80 must FAIL.
const viaCase = tpS('TP15', 150, 30, 0.6, 28) + tpS('TP16', 160, 30, 0.6, 28);
// Facing test (local fix after 1.16.0): TP17 near the START of a 10 mm NONFACE track on one side, TP18 near its FAR END on the
// other, 0.6 mm free across - they do not face each other, so this is not a gap: no between-pads FAIL.
const faceCase = tpS('TP17', 170, 30, 0.6, 28) + tpS('TP18', 171.2, 39, 0.6, 29);

const reviewFootprints = U1 + U2 + TP2 + TP3 + P3 + U5 + U4 + U3 + Y1 + U6 + U7 + Q1 + TP4 + TP5 + TP6 + Q2 + pourCase + gapCase + viaCase + faceCase;
const reviewRoute =
  seg(28, 9.8, 32, 9.8, 0.2, 'F.Cu', 5) +                      // entry 3: off-centre between TP2/TP3
  seg(30.15, 18, 30.15, 22, 0.2, 'F.Cu', 6) +                   // entry 4 + 10: off-centre under P3's own pads
  seg(29.85, 18, 29.85, 22, 0.2, 'F.Cu', 7) +                   // entry 6: a SECOND net through the same P3 gap
  seg(60, 10, 61, 10, 0.5, 'F.Cu', 8) +                         // entry 5: entry wider than the 0.3 mm pad
  seg(63, 10, 65.1, 10, 0.2, 'F.Cu', 10) +                      // entry 8: ends 0.1 mm off the pad centre
  seg(70, 12, 70, 10, 0.2, 'F.Cu', 12) +                        // entry 9: perpendicular entry into an elongated pad
  seg(78, 10, 82, 10, 0.2, 'F.Cu', 15) +                        // entry 4 exception: foreign net crosses Y1's courtyard
  seg(90.75, 5, 90.75, 15, 0.2, 'F.Cu', 9) +                    // entry 11: hugs U6, U7 is free space on the other side
  seg(60, 30, 60, 28.5, 0.2, 'F.Cu', 16) +                      // Q1 pin 2 axial exit, asymmetric neighbours
  seg(70, 28.5, 70, 30, 0.2, 'F.Cu', 19) +                      // TP4 entry to its centre, unequal flanks TP5/TP6
  seg(80.05, 28.5, 80.05, 31.5, 0.2, 'F.Cu', 22) +              // Q2: genuine off-centre pass between pads 1/2
  seg(100, 31, 100, 28.5, 0.2, 'F.Cu', 23) +                    // POUR_OWN: stub ends inside its own zone fill
  seg(110, 31, 110, 28.5, 0.2, 'F.Cu', 26) +                    // FREE_END: same geometry, ends in nothing
  seg(119, 31.0, 121, 31.0, 0.2, 'F.Cu', 27) +                  // WIDE_GAP: 2.0 mm free, 0.3 mm off the middle
  seg(129, 31.32, 131, 31.32, 0.2, 'F.Cu', 30) +                // HDR_PASS: 0.84 mm free, 0.05 mm off-centre
  seg(140.1, 29, 140.1, 33, 0.2, 'F.Cu', 31) +                  // UNDER1206: 1.7 mm free, 0.1 mm off-centre
  via(151.2, 30, 0.3, 0.26, 29) + seg(150.66, 29, 150.66, 33, 0.2, 'F.Cu', 32) +   // VIA_CTR: centred in the allowed channel
  via(161.2, 30, 0.3, 0.26, 29) + seg(160.8, 29, 160.8, 33, 0.2, 'F.Cu', 33) +     // VIA_OFF: off-centre against a via
  seg(170.5, 29, 170.5, 40, 0.2, 'F.Cu', 34);                   // NONFACE: flanks at opposite ends, not a gap
const review = header2 + reviewFootprints + reviewRoute + POUR + edge + ')\n';
fs.writeFileSync(path.join(fx, 'review.kicad_pcb'), review);

r = run(audit, [path.join(fx, 'review.kicad_pcb'), '--json', path.join(fx, 'review.audit.json'), '--no-sch', '--quiet']);
const revRep = JSON.parse(fs.readFileSync(path.join(fx, 'review.audit.json'), 'utf8'));
const revFails = revRep.findings.filter(f => f.level === 'FAIL'), revWarns = revRep.findings.filter(f => f.level === 'WARN');
const rHas = (list, checkName, re) => list.some(f => f.check === checkName && (!re || re.test(f.msg)));
check('review: visible Fab value on U1 detected (improvements #1)', rHas(revWarns, 'fab-values', /U1/));
check('review: hidden Fab value on U2 produces no finding (improvements #1)', !revWarns.some(f => f.check === 'fab-values' && /U2/.test(f.msg)));
check('review: off-centre Fab reference on U1 detected (improvements #2)', rHas(revWarns, 'fab-refs', /U1/));
check('review: centred Fab reference on U2 produces no finding (improvements #2)', !revWarns.some(f => f.check === 'fab-refs' && /U2/.test(f.msg)));
check("review: off-centre track between two footprints' pads (improvements #3)", rHas(revFails, 'between-pads', /between pads/));
check("review: off-centre track under a two-pad part's own pads (improvements #4)", rHas(revFails, 'between-pads', /under two-pad part P3/));
check('review: route-around candidate flagged under P3 (improvements #10)', rHas(revWarns, 'route-around', /P3/));
check('review: shared pad gap on P3 detected, default disallowed -> FAIL (Q-16 / improvements #6)', rHas(revFails, 'shared-gap', /P3-1/));
check("review: entry wider than pad's smallest dimension is FAIL (improvements #5)", rHas(revFails, 'pad-entry', /wider than pad U5/));
check('review: entry not ending exactly at pad centre is FAIL, no size exemption (improvements #8)', rHas(revFails, 'pad-entry', /U4/));
check('review: non-axial entry into an elongated pad is FAIL (improvements #9, promoted by review issue 18)', rHas(revFails, 'pad-entry', /non-axial entry into elongated pad U3/));
check("review: foreign net crossing a crystal's courtyard is FAIL (improvements #4 exception)", rHas(revFails, 'crystal-inductor', /Y1/));
check('review: track hugging one component while clear on the other side is WARN (improvements #11, best-effort)', rHas(revWarns, 'spreading', /SPARE9/));
const revAll = revRep.findings;
check('review: axial exit stub from a multi-pad IC pin with asymmetric neighbours is not a between-pads FAIL',
  !revAll.some(f => f.check === 'between-pads' && /EXIT_OWN/.test(f.msg)), revAll.filter(f => /EXIT_OWN/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check('review: axial exit stub is not a route-around candidate', !revAll.some(f => f.check === 'route-around' && /EXIT_OWN/.test(f.msg)));
check('review: entry ending at its own pad centre, flanked by unequal unrelated pads, is not a between-pads FAIL',
  !revAll.some(f => f.check === 'between-pads' && /ENTRY_OWN/.test(f.msg)), revAll.filter(f => /ENTRY_OWN/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check('review: off-centre pass between two pads of a multi-pad footprint still FAILs, worded "between pads"',
  rHas(revFails, 'between-pads', /QFN_PASS runs between pads Q2-\d \/ Q2-\d/) && !revAll.some(f => /QFN_PASS runs under two-pad part/.test(f.msg)),
  revAll.filter(f => /QFN_PASS/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check('review: the multi-pad pass is still a route-around candidate', rHas(revWarns, 'route-around', /QFN_PASS passes under Q2/));
check('review: stub ending in its own zone fill is not flanked by pads abreast of the pour',
  !revAll.some(f => (f.check === 'between-pads' || f.check === 'shared-gap') && /POUR_OWN/.test(f.msg)), revAll.filter(f => /POUR_OWN/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check('review: 2.0 mm of free space between two different parts is open board, not a gap (no between-pads FAIL)',
  !revAll.some(f => f.check === 'between-pads' && /WIDE_GAP/.test(f.msg)), revAll.filter(f => /WIDE_GAP/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check("review: header-pitch gap (0.84 mm free, the improvements doc's J3 case) off-centre still FAILs",
  rHas(revFails, 'between-pads', /HDR_PASS runs between pads TP1[34]-1 \/ TP1[34]-1/), revAll.filter(f => /HDR_PASS/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check('review: off-centre under a 1206 two-pad part (1.7 mm free) still FAILs — no width limit for entry 4',
  rHas(revFails, 'between-pads', /UNDER1206 runs under two-pad part P4/), revAll.filter(f => /UNDER1206/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check('review: track centred in the channel a via allows (hole clearance binding) is not a between-pads FAIL',
  !revAll.some(f => f.check === 'between-pads' && /VIA_CTR/.test(f.msg)), revAll.filter(f => /VIA_CTR/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check('review: flanks near opposite ends of a long track do not face each other - not a gap (facing test)',
  !revAll.some(f => f.check === 'between-pads' && /NONFACE/.test(f.msg)), revAll.filter(f => /NONFACE/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check('review: track off-centre between a pad and an other-net via FAILs (vias are flanks)',
  rHas(revFails, 'between-pads', /VIA_OFF runs between pads (TP16-1 \/ via@|via@.* \/ TP16-1)/), revAll.filter(f => /VIA_OFF/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
check('review: the same stub ending in nothing still FAILs (look-ahead kept at free ends)', rHas(revFails, 'between-pads', /FREE_END runs between pads TP(9|10)-1 \/ TP(9|10)-1/),
  revAll.filter(f => /FREE_END/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');

// ============================================================ allowed shared gaps (local fix after 1.16.0, BladeOne 2026-09-29)
// Header-like pads (1.7 mm at 2.54 mm pitch, 0.84 mm free). The project allows the gaps of H1, H3 and H5 to be
// shared (shared_pad_gaps.allowed_parts); two tracks there must be evenly spaced (0.1467 mm each side of each).
const NET3 = ['', 'A', 'B', 'EVEN_A', 'EVEN_B', 'UNEVEN_A', 'UNEVEN_B', 'SOLO_OFF'];
const header3 = header.replace(`${NET.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`, `${NET3.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`);
const hp = (ref, x, y, net) => `\t(footprint "Connector:TestPoint" (layer "F.Cu") (uuid "${U()}") (at ${x} ${y})
${stdProps(ref, 'F.Fab', true, 'F.SilkS', true)}\t\t(attr smd)
${crtyd2}\t\t(pad "1" smd roundrect (at 0 0) (size 1.7 1.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2) (net ${net} "${NET3[net]}") (uuid "${U()}"))\n\t)
`;
const sgFootprints = hp('H1', 200, 30, 1) + hp('H2', 200, 32.54, 2) + hp('H3', 210, 30, 1) + hp('H4', 210, 32.54, 2) + hp('H5', 220, 30, 1) + hp('H6', 220, 32.54, 2);
const sgRoute =
  seg(199, 31.0967, 201, 31.0967, 0.2, 'F.Cu', 3) + seg(199, 31.4433, 201, 31.4433, 0.2, 'F.Cu', 4) +     // evenly spaced pair
  seg(209, 31.05, 211, 31.05, 0.2, 'F.Cu', 5) + seg(209, 31.4433, 211, 31.4433, 0.2, 'F.Cu', 6) +         // uneven pair
  seg(219, 31.32, 221, 31.32, 0.2, 'F.Cu', 7);                                                            // single track, 0.05 off-centre
fs.writeFileSync(path.join(fx, 'sharedgap.kicad_pcb'), header3 + sgFootprints + sgRoute + edge + ')\n');
fs.writeFileSync(path.join(fx, 'sharedgap.params.json'), JSON.stringify({ shared_pad_gaps: { allowed_parts: ['H1', 'H3', 'H5'] } }));
r = run(audit, [path.join(fx, 'sharedgap.kicad_pcb'), '--json', path.join(fx, 'sharedgap.audit.json'), '--no-sch', '--quiet', '--params', path.join(fx, 'sharedgap.params.json')]);
const sgAll = JSON.parse(fs.readFileSync(path.join(fx, 'sharedgap.audit.json'), 'utf8')).findings;
const sgMsgs = re => sgAll.filter(f => re.test(f.msg)).map(f => f.level + ' ' + f.check + ': ' + f.msg).join(' | ') || 'none';
check('allowed shared gap: two evenly spaced tracks are not a between-pads FAIL',
  !sgAll.some(f => f.check === 'between-pads' && /EVEN_[AB] /.test(f.msg) && !/UNEVEN/.test(f.msg)), sgMsgs(/(^| )EVEN_/));
check('allowed shared gap: the shared gap itself is a WARN, not a FAIL',
  sgAll.some(f => f.check === 'shared-gap' && f.level === 'WARN' && /H1-1/.test(f.msg)) && !sgAll.some(f => f.check === 'shared-gap' && f.level === 'FAIL'), sgMsgs(/pad gap/));
check('allowed shared gap: an unevenly spaced track FAILs, worded as uneven spacing',
  sgAll.some(f => f.check === 'between-pads' && f.level === 'FAIL' && /UNEVEN_A .*unevenly spaced/.test(f.msg)), sgMsgs(/UNEVEN/));
check('allowed shared gap: a single off-centre track in an allowed gap still FAILs',
  sgAll.some(f => f.check === 'between-pads' && f.level === 'FAIL' && /SOLO_OFF/.test(f.msg)), sgMsgs(/SOLO_OFF/));

// 1.28.0 (L42): the shared-gap message must not depend on the order of the tracks in the file (a pcbnew save and a
// KiCad GUI save write them in different orders; audit_gate.py then saw a "new" FAIL on an unchanged board).
{
  const sgRev = seg(209, 31.4433, 211, 31.4433, 0.2, 'F.Cu', 6) + seg(209, 31.05, 211, 31.05, 0.2, 'F.Cu', 5) +
    seg(199, 31.4433, 201, 31.4433, 0.2, 'F.Cu', 4) + seg(199, 31.0967, 201, 31.0967, 0.2, 'F.Cu', 3) + seg(219, 31.32, 221, 31.32, 0.2, 'F.Cu', 7);
  fs.writeFileSync(path.join(fx, 'sharedgap_rev.kicad_pcb'), header3 + sgFootprints + sgRev + edge + ')\n');
  run(audit, [path.join(fx, 'sharedgap_rev.kicad_pcb'), '--json', path.join(fx, 'sharedgap_rev.audit.json'), '--no-sch', '--quiet', '--params', path.join(fx, 'sharedgap.params.json')]);
  const revAll = JSON.parse(fs.readFileSync(path.join(fx, 'sharedgap_rev.audit.json'), 'utf8')).findings;
  const gapMsgs = list => list.filter(f => f.check === 'shared-gap').map(f => f.msg).sort().join('\n');
  check('shared gap: the message is the same whatever the order of the tracks in the file (1.28.0, L42)',
    gapMsgs(sgAll) !== '' && gapMsgs(sgAll) === gapMsgs(revAll), gapMsgs(sgAll) + ' || ' + gapMsgs(revAll));
}

// ============================================================ 1.18.0: apply_settings keeps project decisions (ServiceOne, 2026-10-04)
// A whole-object replace dropped the project's 0.45/0.15 via (6 via FAILs came back), reset the schematic connection
// grid to 50 mil and lowered unconnected_items to warning, which hides open connections from DRC.
const keepPro = { board: { design_settings: { rule_severities: { unconnected_items: 'error' }, via_dimensions: [{ diameter: 0, drill: 0 }, { diameter: 0.45, drill: 0.15 }], track_widths: [0, 0.26] } },
  erc: {}, net_settings: { classes: [] }, schematic: { connection_grid_size: 25.0 }, meta: { filename: 'keep.kicad_pro', version: 3 } };
fs.writeFileSync(path.join(fx, 'keep.kicad_pro'), JSON.stringify(keepPro, null, 2));
r = run(apply, [path.join(fx, 'keep.kicad_pro'), '--fab', 'jlcpcb', '--layers', '4', '--copper', '1oz', '--no-bom', '--no-erc']);
const kept = JSON.parse(fs.readFileSync(path.join(fx, 'keep.kicad_pro'), 'utf8'));
for (const f of fs.readdirSync(fx)) if (/^keep\.kicad_pro\.bak-/.test(f)) fs.rmSync(path.join(fx, f));   // apply_settings backup
const kds = kept.board.design_settings;
check('apply_settings keeps the project connection grid (a drawing decision, not a board rule)', kept.schematic.connection_grid_size === 25, String(kept.schematic.connection_grid_size));
check('apply_settings never lowers unconnected_items below a project error', kds.rule_severities.unconnected_items === 'error', kds.rule_severities.unconnected_items);
// 1.20.0 (review issue 11): with the JLCPCB economical drill tier apply_settings adds the economical 0.45/0.2 via instead
// of the 0.25/0.15 minimum (unless --fine-vias); the project's own 0.45/0.15 is still kept.
check('apply_settings merges predefined vias: project 0.45/0.15 kept, economical 0.45/0.2 added, no 0.25/0.15 minimum',
  kds.via_dimensions.some(v => v.diameter === 0.45 && v.drill === 0.15) && kds.via_dimensions.some(v => v.diameter === 0.45 && v.drill === 0.2) && !kds.via_dimensions.some(v => v.diameter === 0.25 && v.drill === 0.15) && kds.via_dimensions[0].diameter === 0,
  kds.via_dimensions.map(v => `${v.diameter}/${v.drill}`).join(' '));
{
  const kp = JSON.parse(fs.readFileSync(path.join(fx, 'kicad_golden.project.json'), 'utf8')).fabricator || {};
  check('apply_settings --fab jlcpcb 4L records economical_via_drill_mm 0.2 and fine_vias_approved false', kp.economical_via_drill_mm === 0.2 && kp.fine_vias_approved === false, JSON.stringify({ e: kp.economical_via_drill_mm, f: kp.fine_vias_approved }));
}
// --fine-vias keeps the fabricator minimum 0.25/0.15 (own folder: apply_settings writes kicad_golden.project.json beside the .kicad_pro)
{
  const fvDir = path.join(fx, 'finevias'); fs.mkdirSync(fvDir, { recursive: true });
  const fvPro = path.join(fvDir, 'fine.kicad_pro');
  fs.writeFileSync(fvPro, JSON.stringify(Object.assign({}, keepPro, { board: { design_settings: { via_dimensions: [{ diameter: 0, drill: 0 }], track_widths: [0] } }, meta: { filename: 'fine.kicad_pro', version: 3 } }), null, 2));
  r = run(apply, [fvPro, '--fab', 'jlcpcb', '--layers', '4', '--copper', '1oz', '--no-bom', '--no-erc', '--fine-vias']);
  const fv = JSON.parse(fs.readFileSync(fvPro, 'utf8')).board.design_settings.via_dimensions;
  const fvp = fs.existsSync(path.join(fvDir, 'kicad_golden.project.json')) ? (JSON.parse(fs.readFileSync(path.join(fvDir, 'kicad_golden.project.json'), 'utf8')).fabricator || {}) : {};
  check('apply_settings --fine-vias still inserts the 0.25/0.15 minimum and records fine_vias_approved',
    r.status === 0 && fv.some(v => v.diameter === 0.25 && v.drill === 0.15) && fvp.fine_vias_approved === true, `exit ${r.status}; ${fv.map(v => `${v.diameter}/${v.drill}`).join(' ')}; approved=${fvp.fine_vias_approved}`);
  for (const f of fs.readdirSync(fvDir)) if (/\.bak-/.test(f)) fs.rmSync(path.join(fvDir, f));   // apply_settings backup
}
check('apply_settings merges predefined track widths: project 0.26 kept', kds.track_widths.includes(0.26) && kds.track_widths.length > 2, kds.track_widths.join(' '));

// ============================================================ 1.17.1: via-in-pad on a listed part (ServiceOne, 2026-10-04)
// A QFN-style exposed pad 1.65 x 2.4 mm (smaller than the 2 mm "min side" heuristic) with paste-only sub-apertures,
// as KiCad's Texas_DRC0010J ships it. Thermal vias in the EP of a listed part are INFO; vias under the paste-only
// apertures are not "inside an SMD pad" (no copper); a via in a signal pad of the same part still FAILs.
const NET4 = ['', 'GND', 'SIGV'];
const header4 = header.replace(`${NET.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`, `${NET4.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`);
const vipPad = (num, x, y, w, h, layers, net) => `\t\t(pad "${num}" smd roundrect (at ${x} ${y}) (size ${w} ${h}) (layers ${layers}) (roundrect_rratio 0.2)${net ? ` (net ${net} "${NET4[net]}")` : ''} (uuid "${U()}"))\n`;
const vipFp = `\t(footprint "Package_SON:Texas_DRC0010J" (layer "F.Cu") (uuid "${U()}") (at 100 100)
${prop('Reference', 'U9', 'F.SilkS', true)}${prop('Value', 'TPS63001', 'F.Fab', true)}${prop('Footprint', 'Package_SON:Texas_DRC0010J', 'F.Fab', true)}${prop('Datasheet', '', 'F.Fab', true)}${prop('Description', 'QFN', 'F.Fab', true)}\t\t(attr smd)
${[[-0.4, -0.6], [0.4, -0.6], [-0.4, 0.6], [0.4, 0.6]].map(([x, y]) => vipPad('', x, y, 0.6, 0.9, '"F.Paste"', 0)).join('')}${vipPad('11', 0, 0, 1.65, 2.4, '"F.Cu" "F.Mask"', 1)}${[-0.75, -0.25, 0.25, 0.75].map((y, i) => vipPad(String(i + 1), -1.45, y, 0.6, 0.24, '"F.Cu" "F.Paste" "F.Mask"', i === 0 ? 2 : 1)).join('')}\t)
`;
const vipVias = via(99.625, 99.25, 0.45, 0.2, 1) + via(100.375, 99.25, 0.45, 0.2, 1) + via(99.625, 100.75, 0.45, 0.2, 1) + via(100.375, 100.75, 0.45, 0.2, 1) + via(98.55, 99.25, 0.45, 0.2, 2);
fs.writeFileSync(path.join(fx, 'vip.kicad_pcb'), header4 + vipFp + vipVias + edge + ')\n');
fs.writeFileSync(path.join(fx, 'vip.params.json'), JSON.stringify({ via_in_pad: { allowed_refs: ['U9'] } }));
r = run(audit, [path.join(fx, 'vip.kicad_pcb'), '--json', path.join(fx, 'vip.audit.json'), '--no-sch', '--quiet', '--params', path.join(fx, 'vip.params.json')]);
const vipAll = JSON.parse(fs.readFileSync(path.join(fx, 'vip.audit.json'), 'utf8')).findings;
const vipMsgs = re => vipAll.filter(f => re.test(f.msg)).map(f => f.level + ' ' + f.check + ': ' + f.msg).join(' | ') || 'none';
check('via-in-pad: thermal vias in a listed part\'s 1.65 x 2.4 mm exposed pad are INFO, not FAIL',
  vipAll.filter(f => f.level === 'INFO' && /thermal via in exposed pad U9-11/.test(f.msg)).length === 4 && !vipAll.some(f => f.level === 'FAIL' && /U9-11/.test(f.msg)), vipMsgs(/U9-11/));
check('via-in-pad: paste-only apertures (no copper) are not SMD pads',
  !vipAll.some(f => /inside SMD pad U9- /.test(f.msg)), vipMsgs(/U9- /));
check('via-in-pad: a via in a signal pad of a listed part still FAILs',
  vipAll.some(f => f.level === 'FAIL' && /inside SMD pad U9-1 \(SIGV\)/.test(f.msg)), vipMsgs(/U9-1 /));

// ============================================================ 1.20.0: board-review checks (ServiceOne rev. 0.2, reports/board_review_rev02.md)
// One isolated case per new check (sections 6, 7, 16, 19-29 of kicad_audit.js). Nets are registered by name.
const NET5 = ['']; const N5 = name => { let i = NET5.indexOf(name); if (i < 0) { NET5.push(name); i = NET5.length - 1; } return i; };
const fp5 = (lib, ref, x, y, padList, extra = '') => `\t(footprint "${lib}" (layer "F.Cu") (uuid "${U()}") (at ${x} ${y})
${prop('Reference', ref, 'F.SilkS', true)}${prop('Value', 'x', 'F.Fab', true)}${prop('Footprint', lib, 'F.Fab', true)}${prop('Datasheet', '', 'F.Fab', true)}${prop('Description', 'x', 'F.Fab', true)}\t\t(attr ${padList.every(p => p[1] === 'smd') ? 'smd' : 'through_hole'})
${extra}${padList.map(([num, type, shape, lx, ly, w, h, net]) => {
    const layers = type === 'smd' ? '"F.Cu" "F.Paste" "F.Mask"' : '"*.Cu" "*.Mask"';
    const drill = type === 'smd' ? '' : ` (drill ${type === 'np_thru_hole' ? w : 1})`;
    return `\t\t(pad "${num}" ${type} ${shape} (at ${lx} ${ly}) (size ${w} ${h})${drill} (layers ${layers})${shape === 'roundrect' ? ' (roundrect_rratio 0.2)' : ''}${net ? ` (net ${N5(net)} "${net}")` : ''} (uuid "${U()}"))\n`;
  }).join('')}\t)
`;
const seg5 = (x1, y1, x2, y2, w, layer, net) => seg(x1, y1, x2, y2, w, layer, N5(net));
const via5 = (x, y, size, drill, net) => via(x, y, size, drill, N5(net));
const r0603 = (ref, x, y, n1, n2) => fp5('Resistor_SMD:R_0603_1608Metric', ref, x, y, [['1', 'smd', 'roundrect', -0.7875, 0, 0.8, 0.95, n1], ['2', 'smd', 'roundrect', 0.7875, 0, 0.8, 0.95, n2]]);
N5('GND');
// U20: fine-pitch IC, 8 pads 1.5 x 0.3 at 0.5 mm pitch (left 1-4, right 5-8)
const U20 = fp5('Package_SO:FinePitch_test', 'U20', 20, 20, [
  ['1', 'smd', 'roundrect', -2.5, -0.75, 1.5, 0.3, 'U20_P1'], ['2', 'smd', 'roundrect', -2.5, -0.25, 1.5, 0.3, 'CAP_OFF'], ['3', 'smd', 'roundrect', -2.5, 0.25, 1.5, 0.3, 'FINE_DIAG'], ['4', 'smd', 'roundrect', -2.5, 0.75, 1.5, 0.3, 'GND'],
  ['5', 'smd', 'roundrect', 2.5, 0.75, 1.5, 0.3, 'U20_P5'], ['6', 'smd', 'roundrect', 2.5, 0.25, 1.5, 0.3, 'U20_P6'], ['7', 'smd', 'roundrect', 2.5, -0.25, 1.5, 0.3, 'U20_P7'], ['8', 'smd', 'roundrect', 2.5, -0.75, 1.5, 0.3, 'GND']]);
// J5: 1x4 THT header (shared gap allowed by params), J6: 2x3 THT pin array with a courtyard
const thtPad = (num, lx, ly, net) => [num, 'thru_hole', 'circle', lx, ly, 1.7, 1.7, net];
const J5 = fp5('Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical', 'J5', 60, 10, [thtPad('1', 0, 0, 'J5P1'), thtPad('2', 0, 2.54, 'J5P2'), thtPad('3', 0, 5.08, 'J5P3'), thtPad('4', 0, 7.62, 'J5P4')]);
const J6 = fp5('Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical', 'J6', 80, 60, [thtPad('1', 0, 0, 'J6N1'), thtPad('2', 2.54, 0, 'J6N2'), thtPad('3', 0, 2.54, 'J6N3'), thtPad('4', 2.54, 2.54, 'J6N4'), thtPad('5', 0, 5.08, 'J6N5'), thtPad('6', 2.54, 5.08, 'J6N6')],
  `\t\t(fp_rect (start -1.33 -1.33) (end 3.87 6.41) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd") (uuid "${U()}"))\n`);
// Q30: SOT-223-like, pad 2 and the tab (pad 4) on one net (Q302 duplicate case)
const Q30 = fp5('Package_TO_SOT_SMD:SOT-223', 'Q30', 150, 40, [['1', 'smd', 'roundrect', 0, -2.3, 1.5, 1.5, 'Q30X'], ['2', 'smd', 'roundrect', 0, 0, 1.5, 1.5, 'THRUL'], ['4', 'smd', 'roundrect', 5, 0, 2, 3.8, 'THRUL']]);
// U40: SOIC-like (1.95 x 0.6 at 1.27 mm) + TP41 nearer to the track at its far end (the U102 pins 10/11 miss)
const U40 = fp5('Package_SO:SOIC-8_test', 'U40', 20, 60, [
  ['1', 'smd', 'roundrect', -2.475, -1.905, 1.95, 0.6, 'U40_P1'], ['2', 'smd', 'roundrect', -2.475, -0.635, 1.95, 0.6, 'U40_P2'], ['3', 'smd', 'roundrect', -2.475, 0.635, 1.95, 0.6, 'U40_P3'], ['4', 'smd', 'roundrect', -2.475, 1.905, 1.95, 0.6, 'U40_P4'],
  ['5', 'smd', 'roundrect', 2.475, 1.905, 1.95, 0.6, 'U40_P5'], ['6', 'smd', 'roundrect', 2.475, 0.635, 1.95, 0.6, 'U40_P6'], ['7', 'smd', 'roundrect', 2.475, -0.635, 1.95, 0.6, 'U40_P7'], ['8', 'smd', 'roundrect', 2.475, -1.905, 1.95, 0.6, 'U40_P8']]);
const TP41 = fp5('TestPoint:TestPoint_Pad_test', 'TP41', 13, 59.5, [['1', 'smd', 'roundrect', 0, 0, 0.6, 0.6, 'TP41N']]);
const holeFp = (ref, x, y) => fp5('MountingHole:MountingHole_2.3mm_M2', ref, x, y, [['', 'np_thru_hole', 'circle', 0, 0, 2.3, 2.3, null]]);
const modelFp = (ref, x, y, file) => fp5('Resistor_SMD:R_0603_1608Metric', ref, x, y, [['1', 'smd', 'roundrect', -0.7875, 0, 0.8, 0.95, ref + 'A'], ['2', 'smd', 'roundrect', 0.7875, 0, 0.8, 0.95, ref + 'B']],
  `\t\t(model "\${KIPRJMOD}/review2.3dshapes/${file}" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))\n`);
const fp5All = U20 + J5 + J6 + Q30 + U40 + TP41 + holeFp('H30', 60, 60) + holeFp('H31', 70, 85) +
  r0603('R20', 80, 10, 'R20A', 'R20B') + r0603('R21', 90, 10, 'R21A', 'R21B') + r0603('R22', 100, 10, 'R22A', 'R22B') +
  r0603('R23', 140, 10, 'R23A', 'LOOPN') + r0603('R24', 145.7875, 10, 'LOOPN', 'R24B') + r0603('R26', 100, 30, 'R26A', 'BENDN') + r0603('R27', 100, 40, 'R27A', 'CORNERN') +
  modelFp('M50', 170, 70, 'missing.step') + modelFp('M51', 180, 70, 'BOX_approx.step');
const route5 =
  seg5(15, 19.83, 17.5, 19.83, 0.2, 'F.Cu', 'CAP_OFF') + seg5(17.5, 19.83, 17.5, 19.75, 0.2, 'F.Cu', 'CAP_OFF') +   // 1/14: off-axis run ends in U20-2, jogs to the centre
  seg5(16.5, 21.25, 17.5, 20.25, 0.2, 'F.Cu', 'FINE_DIAG') +                                                    // 3: 45 deg entry into fine-pitch U20-3
  seg5(17.5, 20.75, 15.9, 20.75, 0.6, 'F.Cu', 'GND') + via5(15.9, 20.75, 0.6, 0.3, 'GND') +                         // 2: plane via 0.6/0.3 at fine pitch -> WARN
  seg5(22.5, 19.25, 24, 19.25, 0.6, 'F.Cu', 'GND') + via5(24, 19.25, 0.45, 0.2, 'GND') +                        // 2: small plane via 0.45/0.2 -> allowed (INFO)
  via5(23.5, 20.5, 0.45, 0.2, 'BANDV') +                                                                        // 12: via in U20's pad-row band, pins 5/6
  seg5(40, 10, 44, 14, 0.2, 'F.Cu', 'XNET') + seg5(40, 14, 44, 10, 0.2, 'F.Cu', 'XNET') +                       // 4: same-net crossing
  seg5(58, 11.0967, 62, 11.0967, 0.2, 'F.Cu', 'SG_A') + seg5(58, 11.4433, 62, 11.4433, 0.2, 'F.Cu', 'SG_B') +   // 5: two tracks in J5-1/J5-2, J5-2/J5-3 free
  via5(80, 10, 0.45, 0.2, 'R20A') + via5(90, 10, 0.45, 0.2, 'OTHERV') +                                          // 6: own-pad via under R20, other-net via under R21
  via5(101.4625, 10, 0.45, 0.2, 'RINGV') +                                                                       // 7: via ring 0.05 mm from R22-2
  via5(110, 30, 0.45, 0.15, 'ECONV') +                                                                           // 8: 0.15 mm drill below the JLC economical tier
  seg5(120, 20, 124, 20, 0.2, 'F.Cu', 'DETOUR') + seg5(124, 20, 124, 22, 0.2, 'F.Cu', 'DETOUR') + seg5(124, 22, 120.5, 22, 0.2, 'F.Cu', 'DETOUR') + // 9: U-turn, ratio 4.6
  seg5(120, 30, 122, 30, 0.2, 'F.Cu', 'BUMP') + seg5(122, 30, 122.5, 29.5, 0.2, 'F.Cu', 'BUMP') + seg5(122.5, 29.5, 123, 30, 0.2, 'F.Cu', 'BUMP') + seg5(123, 30, 125, 30, 0.2, 'F.Cu', 'BUMP') + // 9: bump
  seg5(140.7875, 10, 145, 10, 0.2, 'F.Cu', 'LOOPN') + seg5(140.7875, 10, 141.7875, 11, 0.2, 'F.Cu', 'LOOPN') + seg5(141.7875, 11, 144, 11, 0.2, 'F.Cu', 'LOOPN') + seg5(144, 11, 145, 10, 0.2, 'F.Cu', 'LOOPN') + // 10: loop R23-2 -> R24-1 twice
  seg5(140, 20, 144, 20, 0.2, 'F.Cu', 'DUPN') + seg5(140, 20.2, 144, 20.2, 0.2, 'F.Cu', 'DUPN') +               // 10: offset duplicate 0.2 mm
  seg5(155, 40, 150, 40, 0.2, 'F.Cu', 'THRUL') + seg5(155, 40.4, 147, 40.4, 0.2, 'F.Cu', 'THRUL') +             // 10: tab -> pad 2, and a duplicate running over pad 2
  seg5(18.65, 60.1, 12, 60.1, 0.2, 'F.Cu', 'U40_Y0') +                                                           // 11: off-centre between U40-2/U40-3, TP41 nearer at the far end
  seg5(57, 62, 63, 62, 0.2, 'F.Cu', 'MECHN') + via5(60, 57.5, 0.45, 0.2, 'MECHV') +                             // 13: copper inside H30's 3 mm keep-out
  seg5(100.7875, 30, 101.3, 30, 0.2, 'F.Cu', 'BENDN') + seg5(101.3, 30, 102.3, 31, 0.2, 'F.Cu', 'BENDN') +      // 14: bend 0.11 mm beyond the R26-2 edge
  seg5(100.7875, 40, 101.7875, 41, 0.2, 'F.Cu', 'CORNERN') +                                                     // 14: diagonal corner entry into R27-2 (SW3 -> R8)
  seg5(79, 59.5, 83, 63.5, 0.2, 'F.Cu', 'PADIAG') +                                                              // 16: 5.7 mm diagonal through J6's pin array
  seg5(160, 10, 164, 10, 0.2, 'F.Cu', 'ACUTE2') + seg5(164, 10, 161, 13, 0.2, 'F.Cu', 'ACUTE2') +               // 17: 135-degree turn (interior 45)
  seg5(170, 10, 173, 10, 0.2, 'F.Cu', 'ACUTET') + seg5(173, 10, 176, 10, 0.2, 'F.Cu', 'ACUTET') + seg5(173, 10, 176, 13, 0.2, 'F.Cu', 'ACUTET') + // 17: T branch 45 deg off the run
  seg5(160, 20, 164, 20, 0.2, 'F.Cu', 'RIGHTN') + seg5(164, 20, 164, 24, 0.2, 'F.Cu', 'RIGHTN') +               // 17: 90-degree turn: allowed
  seg5(160, 30, 164, 30, 0.2, 'F.Cu', 'MITREN') + seg5(164, 30, 167, 33, 0.2, 'F.Cu', 'MITREN') +               // 17: 45-degree mitre: allowed
  seg5(160, 40, 164, 40, 0.2, 'F.Cu', 'ACVIA') + seg5(164, 40, 161, 43, 0.2, 'F.Cu', 'ACVIA') + via5(164, 40, 0.45, 0.2, 'ACVIA') + // 17: sharp meeting at a via: exempt
  seg5(180, 50, 184, 54, 0.2, 'B.Cu', 'DIAGL') +                                                                // 22: 5.66 mm at 45 deg -> WARN diagonal (1.28.0)
  seg5(180, 60, 182, 62, 0.2, 'B.Cu', 'DIAGS') +                                                                // 22: 2.83 mm at 45 deg, under 3 mm: allowed
  seg5(180, 70, 184, 74, 0.2, 'B.Cu', 'DIAGX');                                                                 // 22: long, but listed in routing_style.diagonal_exceptions
const gnd5 = `\t(zone (net ${N5('GND')}) (net_name "GND") (layer "In1.Cu") (uuid "${U()}") (hatch edge 0.5) (priority 0) (connect_pads (clearance 0.1)) (min_thickness 0.1) (filled_areas_thickness no)
\t\t(fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
\t\t(polygon (pts (xy 1 1) (xy 199 1) (xy 199 99) (xy 1 99)))
\t)
`;
const edge5 = `\t(gr_rect (start 0 0) (end 200 100) (stroke (width 0.05) (type default)) (fill no) (layer "Edge.Cuts") (uuid "${U()}"))\n`;
const body5 = fp5All + route5 + gnd5 + edge5; // builds NET5 as a side effect
const header5 = header.replace(`${NET.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`, `${NET5.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`);
fs.writeFileSync(path.join(fx, 'review2.kicad_pcb'), header5 + body5 + ')\n');
fs.copyFileSync(path.join(fx, 'good.kicad_pro'), path.join(fx, 'review2.kicad_pro'));
fs.mkdirSync(path.join(fx, 'review2.3dshapes'), { recursive: true });
fs.writeFileSync(path.join(fx, 'review2.3dshapes', 'BOX_approx.step'), 'ISO-10303-21;\nEND-ISO-10303-21;\n');
const p5 = { fabricator: { name: 'JLCPCB 4-layer 1oz', profile: '4L-1oz', layers: 4 }, shared_pad_gaps: { allowed_parts: ['J5'] }, mechanical_keepouts: [{ refs: ['H30'], radius_mm: 3, layers: 'all' }] };
p5.routing_style = { diagonal_max_mm: 3, diagonal_exceptions: [{ net: 'DIAGX', reason: 'test: length-critical line' }] };
fs.writeFileSync(path.join(fx, 'review2.params.json'), JSON.stringify(p5, null, 2));
r = run(audit, [path.join(fx, 'review2.kicad_pcb'), '--json', path.join(fx, 'review2.audit.json'), '--no-sch', '--quiet', '--params', path.join(fx, 'review2.params.json')]);
const r2 = JSON.parse(fs.readFileSync(path.join(fx, 'review2.audit.json'), 'utf8'));
const r2All = r2.findings;
const r2Has = (lvl, chk, re) => r2All.some(f => f.level === lvl && f.check === chk && re.test(f.msg));
const r2Msgs = re => r2All.filter(f => re.test(f.msg)).map(f => f.level + ' ' + f.check + ': ' + f.msg).join(' | ') || 'none';
check('review2 #1: end cap of an off-axis run ending inside a fine-pitch pad sticks out -> FAIL (issues 3, 5, 6)', r2Has('FAIL', 'pad-entry', /end cap .*U20-2/), r2Msgs(/U20-2/));
check('review2 #2: 0.6/0.3 plane via at a fine-pitch pad -> WARN suggesting the small via (issue 4)', r2Has('WARN', 'via', /plane via 0\.6\/0\.3 on GND .*U20-4.*0\.45\/0\.2/), r2Msgs(/plane via/));
check('review2 #2: the small plane via 0.45/0.2 is recorded as allowed (INFO)', r2Has('INFO', 'via', /1 plane via.*small plane via 0\.45\/0\.2/) && r2.stats.plane_vias_fine_pitch.small === 1, JSON.stringify(r2.stats.plane_vias_fine_pitch));
check('review2 #3: non-axial entry into a fine-pitch pad is a blocking FAIL (issue 6)', r2Has('FAIL', 'pad-entry', /non-axial entry into elongated pad U20-3 .*fine pitch 0\.5 mm: blocking/), r2Msgs(/U20-3/));
check('review2 #4: same-net tracks crossing each other -> FAIL geometry (issue 7)', r2Has('FAIL', 'geometry', /XNET cross/) && r2.stats.same_net_crossings === 1, r2Msgs(/XNET/));
check('review2 #5: shared THT gap names the free neighbouring gap (issue 8)', r2Has('WARN', 'shared-gap', /J5-1 \/ J5-2 carries 2 tracks.*free alternative: gap J5-[23] \/ J5-[23]/), r2Msgs(/pad gap/));
check('review2 #6: own-pad via between the pads of a two-pad part -> FAIL (issue 9)', r2Has('FAIL', 'via', /own-pad via R20A .*two-pad part R20/), r2Msgs(/R20/));
check('review2 #6: other-net via under a two-pad part -> FAIL, worded other-net (issue 9)', r2Has('FAIL', 'via', /other-net via OTHERV .*two-pad part R21/), r2Msgs(/OTHERV/));
check('review2 #7: via ring 0.05 mm from an SMD pad -> FAIL (issue 10)', r2Has('FAIL', 'via', /via RINGV .*ring 0\.05 mm from SMD pad R22-2/), r2Msgs(/RINGV/));
check('review2 #8: via drill 0.15 below the JLC economical tier -> FAIL (issue 11)', r2Has('FAIL', 'via', /via drill 0\.15 mm below the economical tier 0\.2 mm/), r2Msgs(/economical/));
check('review2 #9: U-turn / ratio detour -> WARN (issue 12)', r2Has('WARN', 'detour', /DETOUR detour .*ratio .*U-turn/), r2Msgs(/DETOUR/));
check('review2 #9: out-and-back bump -> WARN (issue 12, Q3-S)', r2Has('WARN', 'detour', /BUMP detour .*bump of 0\.5 mm/), r2Msgs(/BUMP/));
check('review2 #10: two routes between the same pads -> FAIL loop (issue 14)', r2Has('FAIL', 'loop', /LOOPN: segment .*closes a loop/), r2Msgs(/LOOPN/));
check('review2 #10: duplicate run over a same-net pad closes a loop through that pad (Q302) -> FAIL loop', r2Has('FAIL', 'loop', /THRUL: segment .*closes a loop/), r2Msgs(/THRUL/));
check('review2 #10: offset parallel duplicate 0.2 mm apart -> FAIL loop', r2Has('FAIL', 'loop', /DUPN: duplicate copper — two parallel segments 0\.2 mm apart over 4 mm/), r2Msgs(/DUPN/));
check('review2 #11: off-centre pass between U40-2/3 with a nearer pad at the far end is caught (U102 pins 10/11 miss)', r2Has('FAIL', 'between-pads', /U40_Y0 runs between pads U40-[23] \/ U40-[23] off-centre/), r2Msgs(/U40_Y0/));
check('review2 #12: via inside an IC pad-row band -> FAIL (issue 16)', r2Has('FAIL', 'via', /via BANDV .*pad-row band of U20 between pins [56]\/[56]/), r2Msgs(/BANDV/));
check('review2 #12: the plane vias whose copper ends beyond the outer pad ends + 0.5 mm are not in a band', !r2All.some(f => /pad-row band/.test(f.msg) && /GND/.test(f.msg)), r2Msgs(/pad-row band/));
check('review2 #13: track and via inside a mechanical keep-out -> FAIL (issue 17)', r2Has('FAIL', 'mech-keepout', /track MECHN .*H30/) && r2Has('FAIL', 'mech-keepout', /via MECHV .*H30/), r2Msgs(/mechanical keep-out/));
check('review2 #13: mounting hole without a keep-out entry -> INFO', r2Has('INFO', 'mech-keepout', /1 mounting-hole footprint.*H31/), r2Msgs(/mounting-hole/));
check('review2 #14: last bend 0.11 mm beyond the pad edge -> FAIL (issue 18)', r2Has('FAIL', 'pad-entry', /last bend before pad R26-2 .*0\.1125 mm/), r2Msgs(/R26-2/));
check('review2 #14: diagonal corner entry into a 0603 pad -> FAIL (issue 18, SW3 -> R8)', r2Has('FAIL', 'pad-entry', /non-axial entry into pad R27-2/), r2Msgs(/R27-2/));
// 1.29.0: pad_entry.bend_min_mm / bend_check in the project params (GapOne CON, owner 2026-11-09)
const auditPadEntry = (tag, padEntry) => {
  fs.writeFileSync(path.join(fx, `review2_${tag}.params.json`), JSON.stringify(Object.assign({}, p5, { pad_entry: padEntry }), null, 2));
  run(audit, [path.join(fx, 'review2.kicad_pcb'), '--json', path.join(fx, `review2_${tag}.audit.json`), '--no-sch', '--quiet', '--params', path.join(fx, `review2_${tag}.params.json`)]);
  return JSON.parse(fs.readFileSync(path.join(fx, `review2_${tag}.audit.json`), 'utf8')).findings;
};
const peMin = auditPadEntry('bendmin', { bend_min_mm: 0.1 });
check('review2 #14: pad_entry.bend_min_mm 0.1 -> the 0.11 mm bend at R26-2 passes', !peMin.some(f => f.check === 'pad-entry' && /last bend before pad R26-2/.test(f.msg)), peMin.filter(f => /R26-2/.test(f.msg)).map(f => f.msg).join(' | ') || 'none');
const peOff = auditPadEntry('bendoff', { bend_check: false });
check('review2 #14: pad_entry.bend_check false -> no last-bend FAIL, one INFO; other pad-entry checks stay (R27-2)',
  !peOff.some(f => f.level === 'FAIL' && /last bend before pad/.test(f.msg))
  && peOff.some(f => f.level === 'INFO' && f.check === 'pad-entry' && /last-bend distance check switched off/.test(f.msg))
  && peOff.some(f => f.level === 'FAIL' && f.check === 'pad-entry' && /non-axial entry into pad R27-2/.test(f.msg)),
  peOff.filter(f => f.check === 'pad-entry').map(f => f.level + ' ' + f.msg).slice(0, 6).join(' | '));
check('review2 #15: footprint without a 3D model -> FAIL; test points and mounting holes exempt (issue 20)',
  r2Has('FAIL', 'model', /^U20 .*has no 3D model/) && !r2All.some(f => f.check === 'model' && /^(TP41|H30|H31) /.test(f.msg)), r2Msgs(/3D model/));
check('review2 #15: ${KIPRJMOD} model file missing -> FAIL', r2Has('FAIL', 'model', /M50: 3D model file not found: .*missing\.step/), r2Msgs(/M50/));
check('review2 #15: *_approx model listed as INFO', r2Has('INFO', 'model', /1 approximate 3D model.*M51: BOX_approx\.step/) && !r2All.some(f => f.level === 'FAIL' && /M51/.test(f.msg) && f.check === 'model'), r2Msgs(/approx/));
check('review2 #16: diagonal longer than one pitch inside a pin array -> FAIL (issue 21)', r2Has('FAIL', 'pin-array', /PADIAG runs diagonally .*J6's pin array \(pitch 2\.54 mm\)/), r2Msgs(/PADIAG/));
check('review2 #17: 135-degree turn (interior 45) -> FAIL acute (1.27.0)', r2Has('FAIL', 'acute', /acute joint on ACUTE2 @ 164,10 .*45° between two branches/), r2Msgs(/ACUTE2/));
check('review2 #17: T branch 45 degrees off the run -> FAIL acute', r2Has('FAIL', 'acute', /acute joint on ACUTET @ 173,10 .*3 track ends/), r2Msgs(/ACUTET/));
check('review2 #17: 90-degree turn, 45-degree mitre and a sharp meeting at a via are not acute',
  !r2All.some(f => f.check === 'acute' && /RIGHTN|MITREN|ACVIA/.test(f.msg)) && r2.stats.acute_joints === 2, r2Msgs(/acute/));
check('good board: no acute joint', goodRep.stats.acute_joints === 0, String(goodRep.stats.acute_joints));
check('review2 #22: a 5.7 mm 45-degree run -> WARN diagonal (1.28.0, L41)', r2Has('WARN', 'diagonal', /DIAGL runs 5\.65\d* mm at 45° .*over the 3 mm limit/), r2Msgs(/DIAG/));
check('review2 #22: a 2.8 mm diagonal and an excepted net are not flagged; INFO gives the diagonal share per layer',
  !r2All.some(f => f.check === 'diagonal' && f.level === 'WARN' && /DIAGS|DIAGX/.test(f.msg)) && r2All.some(f => f.check === 'diagonal' && f.level === 'INFO' && /^B\.Cu: \d+ % of the track length is diagonal/.test(f.msg)), r2Msgs(/DIAG|diagonal/));
check('good board: no long diagonal', goodRep.stats.long_diagonals === 0, String(goodRep.stats.long_diagonals));
// fine vias approved: the economical-tier FAIL becomes an INFO
fs.writeFileSync(path.join(fx, 'review2.fine.params.json'), JSON.stringify(Object.assign({}, p5, { fabricator: Object.assign({}, p5.fabricator, { fine_vias_approved: true }) }), null, 2));
r = run(audit, [path.join(fx, 'review2.kicad_pcb'), '--json', path.join(fx, 'review2.fine.audit.json'), '--no-sch', '--quiet', '--params', path.join(fx, 'review2.fine.params.json')]);
const r2f = JSON.parse(fs.readFileSync(path.join(fx, 'review2.fine.audit.json'), 'utf8')).findings;
check('review2 #8: with fabricator.fine_vias_approved the sub-tier drill is INFO, not FAIL', r2f.some(f => f.level === 'INFO' && /below the economical drill 0\.2 mm, approved/.test(f.msg)) && !r2f.some(f => f.level === 'FAIL' && /economical tier/.test(f.msg)));
check('good board: none of the 1.20.0 review checks fires', goodRep.stats.same_net_crossings === 0 && goodRep.stats.same_net_loops === 0 && goodRep.stats.same_net_duplicates === 0 && goodRep.stats.detours.total === 0 && goodRep.stats.via_ring_near_smd_pad.total === 0 && goodRep.stats.models.missing === 0 && goodRep.stats.pad_entry_end_cap_outside === 0,
  JSON.stringify({ x: goodRep.stats.same_net_crossings, l: goodRep.stats.same_net_loops, d: goodRep.stats.detours, ring: goodRep.stats.via_ring_near_smd_pad, m: goodRep.stats.models }));

// ------------------------------------------------------------ plane plan (L23, review issue 13): 4-layer fixture
// In1 GND / In2 +3.3V main planes; +5V zone on In1 (never split -> FAIL); undeclared +12V island on In2 (WARN);
// declared PP_24V_BAD (named zone, clearance 0.2 < 0.5 for 24 V -> FAIL; B.Cu track crossing it -> WARN; F.Cu track
// crossing it is shielded by In1 -> nothing); clean PP_15V_OK (unnamed, matched by net+layer, 2 pads, gap 0.5);
// PP_MISSING declared with no zone and no pads (WARN missing + WARN serves 0 pads).
const NET6 = ['', 'GND', '+3.3V', '+5V', '+12V', '+24V', '+15V', 'SIGB', 'SIGF'];
const N6 = n => NET6.indexOf(n);
const header6 = header.replace(`${NET.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`, `${NET6.map((n, i) => `\t(net ${i} "${n}")`).join('\n')}\n`);
const zone6 = (net, layer, prio, x0, y0, x1, y1, clr, name) => `\t(zone (net ${N6(net)}) (net_name "${net}") (layer "${layer}") (uuid "${U()}")${name ? ` (name "${name}")` : ''} (hatch edge 0.5) (priority ${prio}) (connect_pads (clearance ${clr})) (min_thickness 0.1) (filled_areas_thickness no)
\t\t(fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
\t\t(polygon (pts (xy ${x0} ${y0}) (xy ${x1} ${y0}) (xy ${x1} ${y1}) (xy ${x0} ${y1})))
\t)
`;
const r6fp = (ref, x, y, net) => `\t(footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu") (uuid "${U()}") (at ${x} ${y})
${prop('Reference', ref, 'F.SilkS', true)}${prop('Value', '0R', 'F.Fab', true)}${prop('Footprint', 'Resistor_SMD:R_0603_1608Metric', 'F.Fab', true)}${prop('Datasheet', '', 'F.Fab', true)}${prop('Description', 'x', 'F.Fab', true)}\t\t(attr smd)
\t\t(pad "1" smd roundrect (at -0.7875 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25) (net ${N6(net)} "${net}") (uuid "${U()}"))
\t\t(pad "2" smd roundrect (at 0.7875 0) (size 0.8 0.95) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25) (net ${N6(net)} "${net}") (uuid "${U()}"))
\t)
`;
const body6 = r6fp('R60', 45, 10, '+24V') + r6fp('R61', 80, 10, '+15V') +
  seg(35, 15, 50, 15, 0.2, 'B.Cu', N6('SIGB')) + seg(35, 20, 50, 20, 0.2, 'F.Cu', N6('SIGF')) +
  zone6('GND', 'In1.Cu', 0, 1, 1, 99, 59, 0.1) + zone6('+3.3V', 'In2.Cu', 0, 1, 1, 99, 59, 0.1) +
  zone6('+5V', 'In1.Cu', 1, 5, 5, 15, 15, 0.3) + zone6('+12V', 'In2.Cu', 1, 20, 5, 30, 15, 0.5) +
  zone6('+24V', 'In2.Cu', 2, 40, 5, 60, 25, 0.2, 'PP_24V_BAD') + zone6('+15V', 'In2.Cu', 3, 70, 5, 90, 25, 0.5) +
  `\t(gr_rect (start 0 0) (end 100 60) (stroke (width 0.05) (type default)) (fill no) (layer "Edge.Cuts") (uuid "${U()}"))\n`;
fs.writeFileSync(path.join(fx, 'planeplan.kicad_pcb'), header6 + body6 + ')\n');
const p6 = { fabricator: { name: 'JLCPCB 4-layer 1oz', profile: '4L-1oz', layers: 4 }, plane_plan: {
  main_planes: { 'In1.Cu': 'GND', 'In2.Cu': '+3.3V' }, never_split: ['GND'], min_neck_mm: 1.0,
  islands: [
    { name: 'PP_24V_BAD', rail: '+24V', layer: 'In2.Cu', voltage_v: 24, outline: [[40, 5], [60, 5], [60, 25], [40, 25]], pads: ['R60.1', 'R60.2'] },
    { name: 'PP_15V_OK', rail: '+15V', layer: 'In2.Cu', voltage_v: 15, outline: [[70, 5], [90, 5], [90, 25], [70, 25]], pads: ['R61.1', 'R61.2'] },
    { name: 'PP_MISSING', rail: '+24V', layer: 'In2.Cu', gap_mm: 0.5, outline: [[5, 40], [15, 40], [15, 50], [5, 50]] },
  ] } };
fs.writeFileSync(path.join(fx, 'planeplan.params.json'), JSON.stringify(p6, null, 2));
r = run(audit, [path.join(fx, 'planeplan.kicad_pcb'), '--json', path.join(fx, 'planeplan.audit.json'), '--no-sch', '--quiet', '--params', path.join(fx, 'planeplan.params.json')]);
const r6rep = JSON.parse(fs.readFileSync(path.join(fx, 'planeplan.audit.json'), 'utf8'));
const ppF = r6rep.findings.filter(f => f.check === 'plane-plan');
const ppHas = (lvl, re) => ppF.some(f => f.level === lvl && re.test(f.msg));
const ppMsgs = () => ppF.map(f => f.level + ': ' + f.msg).join(' | ') || 'none';
check('plane-plan #1: undeclared +12V island on In2 -> WARN (L23)', ppHas('WARN', /undeclared plane island: zone \+12V on In2\.Cu \(main plane \+3\.3V\)/), ppMsgs());
check('plane-plan #2: +5V zone on the GND plane layer -> FAIL never split', ppHas('FAIL', /zone \+5V on In1\.Cu splits the GND plane/) && r6rep.stats.plane_plan.never_split === 1, ppMsgs());
check('plane-plan #3: B.Cu track crossing the In2 island outline -> WARN; F.Cu track (shielded by In1) silent', ppHas('WARN', /SIGB on B\.Cu crosses the boundary of island PP_24V_BAD .*stitching capacitor/) && !ppF.some(f => /SIGF/.test(f.msg)), ppMsgs());
check('plane-plan #4: declared island clearance 0.2 below the 0.5 mm gap for 24 V -> FAIL', ppHas('FAIL', /island PP_24V_BAD .*zone clearance 0\.2 mm is below the required gap 0\.5 mm \(24 V/) && r6rep.stats.plane_plan.gap_fails === 1, ppMsgs());
check('plane-plan #5: declared island with no zone -> WARN missing, and serves 0 pads -> WARN', ppHas('WARN', /island PP_MISSING .*has no zone on the board/) && ppHas('WARN', /island PP_MISSING .*serves 0 pads/), ppMsgs());
check('plane-plan: clean declared island (matched by net + layer) fires nothing', !ppF.some(f => f.level !== 'INFO' && /PP_15V_OK|\+15V/.test(f.msg)) && JSON.stringify(r6rep.stats.plane_plan.served.PP_15V_OK) === '["R61.1","R61.2"]', JSON.stringify(r6rep.stats.plane_plan.served));
check('plane-plan: INFO summary counts 3 declared / 2 found / 1 missing', ppHas('INFO', /3 island\(s\) declared, 2 found on the board, 1 missing/), ppMsgs());
check('good board: plane plan quiet (no FAIL/WARN, In1=GND In2=+3.3V by default)', !goodRep.findings.some(f => f.check === 'plane-plan' && f.level !== 'INFO') && goodRep.stats.plane_plan.main_planes['In1.Cu'] === 'GND' && goodRep.stats.plane_plan.main_planes['In2.Cu'] === '+3.3V', JSON.stringify(goodRep.stats.plane_plan));

// ---- pre-flight honours approved_rule_deviations (D110: min_hole_clearance 0.2 against the profile's 0.254)
{
  const os = require('os');
  const td = fs.mkdtempSync(path.join(os.tmpdir(), 'kr_dev_'));
  fs.copyFileSync(path.join(fx, 'good.kicad_pcb'), path.join(td, 'd.kicad_pcb'));
  fs.writeFileSync(path.join(td, 'd.kicad_pro'), fs.readFileSync(path.join(fx, 'good.kicad_pro'), 'utf8').replace('"min_hole_clearance": 0.254', '"min_hole_clearance": 0.2'));
  const fab = { name: 'JLCPCB test', profile: 'test', kicad_rules: { min_hole_clearance: 0.254 } };
  const pre = params => {
    fs.writeFileSync(path.join(td, 'p.json'), JSON.stringify(params));
    run(audit, [path.join(td, 'd.kicad_pcb'), '--json', path.join(td, 'a.json'), '--no-sch', '--quiet', '--params', path.join(td, 'p.json')]);
    return JSON.parse(fs.readFileSync(path.join(td, 'a.json'), 'utf8')).findings.filter(f => f.check === 'pre-flight' && /min_hole_clearance/.test(f.msg));
  };
  let f = pre({ fabricator: fab });
  check('pre-flight: a rule below the profile with no approval -> FAIL', f.some(x => x.level === 'FAIL' && /min_hole_clearance = 0\.2 is below/.test(x.msg)), JSON.stringify(f));
  f = pre({ fabricator: fab, approved_rule_deviations: { min_hole_clearance: { value: 0.2, reason: 'D110 test' } } });
  check('pre-flight: the same rule as an approved deviation -> INFO, no FAIL', !f.some(x => x.level === 'FAIL') && f.some(x => x.level === 'INFO' && /approved deviation \(D110 test\)/.test(x.msg)), JSON.stringify(f));
  f = pre({ fabricator: Object.assign({}, fab, { absolute_min: { min_hole_clearance: 0.25 } }), approved_rule_deviations: { min_hole_clearance: { value: 0.2, reason: 'too low' } } });
  check('pre-flight: an approved deviation below the absolute minimum still FAILs', f.some(x => x.level === 'FAIL'), JSON.stringify(f));
  fs.rmSync(td, { recursive: true, force: true });
}

// ---- 1.26.3: board title block revision vs the root schematic beside it
{
  const os = require('os');
  const td = fs.mkdtempSync(path.join(os.tmpdir(), 'kr_rev_'));
  const brd = fs.readFileSync(path.join(fx, 'good.kicad_pcb'), 'utf8');
  const withTb = rev => brd.replace(/\(general/, `(title_block (title "T") (date "2026-10-21") (rev "${rev}"))\n\t(general`);
  fs.writeFileSync(path.join(td, 'r.kicad_sch'), '(kicad_sch (version 20260306) (generator "eeschema") (uuid "x") (paper "A4") (title_block (title "T") (date "2026-10-21") (rev "0.2")) (lib_symbols))\n');
  const revF = text => {
    fs.writeFileSync(path.join(td, 'r.kicad_pcb'), text);
    run(audit, [path.join(td, 'r.kicad_pcb'), '--json', path.join(td, 'a.json'), '--no-sch', '--quiet']);
    return JSON.parse(fs.readFileSync(path.join(td, 'a.json'), 'utf8')).findings.filter(f => f.check === 'revision');
  };
  let f = revF(withTb('0.1'));
  check('revision: board rev 0.1 vs schematic rev 0.2 -> WARN', f.some(x => x.level === 'WARN' && /rev 0\.1 differs from the schematic's rev 0\.2/.test(x.msg)), JSON.stringify(f));
  f = revF(withTb('0.2'));
  check('revision: same rev and date -> INFO only', !f.some(x => x.level !== 'INFO') && f.some(x => /same as the schematic/.test(x.msg)), JSON.stringify(f));
  f = revF(brd);
  check('revision: board without a title block next to a rev 0.2 schematic -> WARN', f.some(x => x.level === 'WARN' && /no revision/.test(x.msg)), JSON.stringify(f));
  fs.rmSync(td, { recursive: true, force: true });
}

const failed = results.filter(x => !x.ok).length;
console.log(`\n${results.length - failed}/${results.length} assertions passed`);
process.exit(failed ? 1 : 0);
