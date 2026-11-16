#!/usr/bin/env node
/*
 * settings_report.js — Markdown report of a KiCad project's configuration, optionally diffed against the golden template.
 * Modelled on the "Configurações de projeto" report that came with that devboard project package (2026-09-16):
 * stackup, general constraints, netclasses, name patterns, predefined sizes, zone defaults, teardrops, tuning,
 * severities that differ from "error", and — with --diff — every difference from golden_settings.json.
 *
 * Usage:
 *   node settings_report.js <project.kicad_pro> [--pcb board.kicad_pcb] [--diff] [--out report.md]
 * The board is located automatically as <project>.kicad_pcb when --pcb is omitted. Works without a board
 * (stackup section is then skipped). Exit 0 always; this is a reporting tool, not a gate.
 */
'use strict';
const fs = require('fs'); const path = require('path');
const args = process.argv.slice(2);
const proPath = args.find(a => !a.startsWith('--') && !(args[args.indexOf(a) - 1] || '').startsWith('--'));
if (!proPath || !fs.existsSync(proPath)) { console.error('usage: node settings_report.js <project.kicad_pro> [--pcb board.kicad_pcb] [--diff] [--out report.md]'); process.exit(2); }
const opt = n => (args.includes(n) ? args[args.indexOf(n) + 1] : null);
const pcbPath = opt('--pcb') || proPath.replace(/\.kicad_pro$/i, '.kicad_pcb');
const doDiff = args.includes('--diff'); const out = opt('--out');
const pro = JSON.parse(fs.readFileSync(proPath, 'utf8'));
const gold = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'golden_settings.json'), 'utf8'));
const ds = (pro.board || {}).design_settings || {}; const gds = gold.board.design_settings;
const L = []; const p = s => L.push(s); const t = (rows) => { p('| ' + rows[0].join(' | ') + ' |'); p('|' + rows[0].map(() => '---').join('|') + '|'); for (const r of rows.slice(1)) p('| ' + r.map(x => x === undefined || x === null ? '—' : String(x)).join(' | ') + ' |'); p(''); };
const fmt = v => typeof v === 'number' ? String(Math.round(v * 1e6) / 1e6) : (v === undefined ? '—' : JSON.stringify(v));

p(`# KiCad configuration report — ${path.basename(proPath, '.kicad_pro')}`); p('');
p(`_Generated ${new Date().toISOString().slice(0, 10)} by kicad-routing ${gold._meta.skill_version} settings_report.js. Values read from the files without interpretation; millimetres unless stated._`); p('');

// ---- stackup from board
if (fs.existsSync(pcbPath)) {
  const txt = fs.readFileSync(pcbPath, 'utf8');
  const layers = [...txt.matchAll(/^\t\t\((\d+) "([^"]+)" (signal|power|mixed|jumper|user)(?: "([^"]+)")?\)/gm)].filter(m => /Cu$/.test(m[2])).map(m => ({ name: m[2], type: m[3] }));
  const stackTxt = (txt.match(/\(stackup([\s\S]*?)\n\t\t\)/) || ['', ''])[1];
  const stack = [...stackTxt.matchAll(/\(layer "([^"]+)"([\s\S]*?)\n\t\t\t\)/g)].map(m => { const b = m[2]; const g = re => (b.match(re) || [])[1]; return { layer: m[1], type: g(/\(type "([^"]+)"\)/), thk: g(/\(thickness ([\d.]+)/), mat: g(/\(material "([^"]+)"\)/), er: g(/\(epsilon_r ([\d.]+)\)/), td: g(/\(loss_tangent ([\d.]+)\)/) }; });
  const thick = (txt.match(/\(general[\s\S]*?\(thickness ([\d.]+)\)/) || [])[1];
  const tentM = txt.match(/\(tenting\s*\(front (yes|no)\)\s*\(back (yes|no)\)\s*\)/) || txt.match(/\(tenting((?: (?:front|back))+)\)/);
  const tent = tentM ? (tentM.length === 3 ? `tenting front ${tentM[1]} / back ${tentM[2]}` : `tenting${tentM[1]}`) : '';
  const maskMin = (txt.match(/\(solder_mask_min_width ([\d.]+)\)/) || [])[1];
  const p2m = (txt.match(/\(pad_to_mask_clearance ([\d.]+)\)/) || [])[1];
  p(`## 1. Stackup (${path.basename(pcbPath)})`); p('');
  p(`Copper layers: ${layers.map(l => `${l.name} (${l.type})`).join(', ')}. Board thickness ${thick || '?'} mm. ${tent ? 'Vias: ' + tent + '.' : ''} Pad-to-mask clearance ${p2m ?? '—'}${maskMin ? `, solder mask min width ${maskMin}` : ''}.`); p('');
  const inner = layers.filter(l => /^In\d/.test(l.name));
  if (inner.some(l => l.type !== 'power')) p(`> Note: inner layers typed \`${inner.map(l => l.type).join('/')}\`. The standard's inner layers are plane-only; declare them as \`power\` so KiCad treats them as planes (field practice).`), p('');
  t([['Layer', 'Type', 'Thickness', 'Material', 'εr', 'tan δ'], ...stack.filter(s => s.type === 'copper' || /core|prepreg|Mask/.test(s.type)).map(s => [s.layer, s.type, s.thk, s.mat, s.er, s.td])]);
} else { p('## 1. Stackup'); p(''); p(`_Board file not found (${path.basename(pcbPath)}); stackup skipped._`); p(''); }

// ---- rules
p('## 2. General constraints'); p('');
const R = ds.rules || {}; const ruleKeys = Object.keys(Object.assign({}, gds.rules, R)).sort();
t([['Constraint', 'Value', ...(doDiff ? ['Golden', 'Δ'] : [])], ...ruleKeys.map(k => [k, fmt(R[k]), ...(doDiff ? [fmt(gds.rules[k]), R[k] === gds.rules[k] ? '' : '**differs**'] : [])])]);

// ---- netclasses
p('## 3. Netclasses'); p('');
const cls = ((pro.net_settings || {}).classes || []);
t([['Netclass', 'Prio', 'Track', 'Clearance', 'Via ø/drill', 'µVia ø/drill', 'Diff w/gap', 'DP via gap'], ...cls.map(c => [c.name, c.priority === 2147483647 || c.priority === undefined ? '—' : c.priority, fmt(c.track_width), fmt(c.clearance), c.via_diameter !== undefined ? `${c.via_diameter} / ${c.via_drill}` : '—', c.microvia_diameter !== undefined ? `${c.microvia_diameter} / ${c.microvia_drill}` : '—', c.diff_pair_width !== undefined ? `${c.diff_pair_width} / ${c.diff_pair_gap}` : '—', fmt(c.diff_pair_via_gap)])]);
if (doDiff) {
  const gcls = gold.net_settings.classes;
  const missing = gcls.filter(g => !cls.some(c => c.name === g.name)).map(g => g.name); const extra = cls.filter(c => !gcls.some(g => g.name === c.name)).map(c => c.name);
  const diffs = [];
  for (const g of gcls) { const c = cls.find(x => x.name === g.name); if (!c) continue; for (const k of ['track_width', 'clearance', 'via_diameter', 'via_drill', 'diff_pair_width', 'diff_pair_gap', 'priority']) if (g[k] !== undefined && c[k] !== g[k]) diffs.push(`${g.name}.${k}: ${fmt(c[k])} (golden ${fmt(g[k])})`); }
  p(`Golden classes missing here: ${missing.length ? missing.join(', ') : 'none'}. Project-specific classes: ${extra.length ? extra.join(', ') : 'none'}. Value differences: ${diffs.length ? diffs.join('; ') : 'none'}.`); p('');
}
p('### 3.1 Assignment by name pattern'); p('');
const pats = ((pro.net_settings || {}).netclass_patterns || []);
if (pats.length) t([['Pattern', 'Netclass'], ...pats.map(x => [x.pattern === '' ? '(empty)' : '`' + x.pattern + '`', x.netclass])]); else p('_No name patterns._'), p('');
const asg = (pro.net_settings || {}).netclass_assignments; if (asg && Object.keys(asg).length) { p('### 3.2 Explicit assignments'); p(''); t([['Net', 'Netclass'], ...Object.entries(asg)]); }
const noPat = cls.filter(c => c.name !== 'Default' && !pats.some(x => x.netclass === c.name) && !(asg && Object.values(asg).includes(c.name))).map(c => c.name);
if (noPat.length) p(`> Classes that receive no net by pattern or assignment: ${noPat.join(', ')}.`), p('');

// ---- predefined sizes
p('## 4. Predefined dimensions'); p('');
t([['Type', 'Values'], ['Track widths', (ds.track_widths || []).filter(w => w > 0).join(' · ') || '—'], ['Vias (ø / drill)', (ds.via_dimensions || []).filter(v => v.diameter > 0).map(v => `${v.diameter} / ${v.drill}`).join(' · ') || '—'], ['Diff pairs (w / gap / via gap)', (ds.diff_pair_dimensions || []).filter(d => d.width > 0).map(d => `${d.width} / ${d.gap} / ${d.via_gap}`).join(' · ') || '—']]);

// ---- zones, teardrops, tuning
p('## 5. Zone defaults, teardrops, tuning'); p('');
const z = (ds.defaults || {}).zones || {};
t([['Parameter', 'Value', ...(doDiff ? ['Golden'] : [])], ...['min_thickness', 'min_clearance', 'min_island_area', 'pad_connection', 'thermal_relief_gap', 'thermal_relief_spoke_width', 'remove_islands', 'border_display_style', 'border_hatch_pitch'].map(k => [k, fmt(z[k]), ...(doDiff ? [fmt((gds.defaults.zones || {})[k])] : [])])]);
const td = (ds.teardrop_options || [])[0]; if (td) p(`Teardrops: on vias ${td.td_onvia ? 'yes' : 'no'}, SMD pads ${td.td_onsmdpad ? 'yes' : 'no'}, PTH pads ${td.td_onpthpad ? 'yes' : 'no'}, track ends ${td.td_ontrackend ? 'yes' : 'no'}.`), p('');
const tp = (ds.tuning_pattern_settings || {}).single_track_defaults; if (tp) p(`Tuning (single track): corner_style ${tp.corner_style} (${tp.corner_style === 1 ? 'round → produces arcs' : tp.corner_style === 2 ? 'chamfer → straight corners' : 'unknown'}), radius ${tp.corner_radius_percentage} %, amplitude ${tp.min_amplitude}–${tp.max_amplitude}, spacing ${tp.spacing}.`), p('');
const d = ds.defaults || {}; t([['Text / line defaults', 'Value'], ['Silk text h × thickness / line', `${fmt(d.silk_text_size_h)} × ${fmt(d.silk_text_thickness)} / ${fmt(d.silk_line_width)}`], ['Fab text h × thickness / line', `${fmt(d.fab_text_size_h)} × ${fmt(d.fab_text_thickness)} / ${fmt(d.fab_line_width)}`], ['Copper text h × thickness / line', `${fmt(d.copper_text_size_h)} × ${fmt(d.copper_text_thickness)} / ${fmt(d.copper_line_width)}`], ['Courtyard / outline line', `${fmt(d.courtyard_line_width)} / ${fmt(d.board_outline_line_width)}`]]);

// ---- severities
p('## 6. Severities differing from "error"'); p('');
const sev = ds.rule_severities || {}; const erc = (pro.erc || {}).rule_severities || {};
const grp = (m) => ({ warning: Object.keys(m).filter(k => m[k] === 'warning').sort(), ignore: Object.keys(m).filter(k => m[k] === 'ignore').sort(), exclusion: Object.keys(m).filter(k => m[k] === 'exclusion').sort() });
const gs = grp(sev), ge = grp(erc);
p(`**DRC → warning** (${gs.warning.length}): ${gs.warning.join(' · ') || '—'}`); p(''); p(`**DRC → ignore** (${gs.ignore.length}): ${gs.ignore.join(' · ') || '—'}`); p('');
p(`**ERC → warning** (${ge.warning.length}): ${ge.warning.join(' · ') || '—'}`); p(''); p(`**ERC → ignore** (${ge.ignore.length}): ${ge.ignore.join(' · ') || '—'}`); p('');
const risky = ['clearance', 'copper_edge_clearance', 'annular_width', 'drill_out_of_range', 'solder_mask_bridge', 'invalid_outline', 'shorting_items', 'tracks_crossing', 'track_dangling', 'missing_footprint', 'unconnected_items', 'starved_thermal', 'zones_intersect'].filter(k => sev[k] && sev[k] !== 'error');
if (risky.length) p(`> **Fabrication/electrical checks not at error**: ${risky.map(k => `${k} = ${sev[k]}`).join(', ')}. The golden standard keeps these at error (unconnected_items is warning in golden); do not import these severities into a new project.`), p('');
if (doDiff) {
  const dd = Object.keys(Object.assign({}, gds.rule_severities, sev)).filter(k => sev[k] !== gds.rule_severities[k]).map(k => `${k}: ${sev[k] ?? '—'} (golden ${gds.rule_severities[k] ?? '—'})`);
  const de = Object.keys(Object.assign({}, gold.erc.rule_severities, erc)).filter(k => erc[k] !== gold.erc.rule_severities[k]).map(k => `${k}: ${erc[k] ?? '—'} (golden ${gold.erc.rule_severities[k] ?? '—'})`);
  p(`### 6.1 Differences from golden`); p(''); p(`DRC (${dd.length}): ${dd.join('; ') || 'none'}`); p(''); p(`ERC (${de.length}): ${de.join('; ') || 'none'}`); p('');
}
p(`DRC exclusions recorded: ${(ds.drc_exclusions || []).length}.`); p('');

// ---- BOM & libs
p('## 7. BOM preset and libraries'); p('');
const bf = ((pro.schematic || {}).bom_settings || {}).fields_ordered || [];
p(`Visible BOM fields: ${bf.filter(f => f.show).map(f => f.label).join(', ') || '—'}. Grouped by: ${bf.filter(f => f.group_by).map(f => f.label).join(', ') || '—'}. Sort: ${((pro.schematic || {}).bom_settings || {}).sort_field || '—'}.`); p('');
for (const tbl of ['fp-lib-table', 'sym-lib-table']) { const f = path.join(path.dirname(proPath), tbl); if (fs.existsSync(f)) { const libs = [...fs.readFileSync(f, 'utf8').matchAll(/\(name "([^"]+)"\)[^)]*\(type "([^"]+)"\)\s*\(uri "([^"]+)"\)/g)].map(m => `${m[1]} → ${m[3]}`); p(`${tbl}: ${libs.join('; ') || 'empty'}`); p(''); } }

const md = L.join('\n');
if (out) { fs.writeFileSync(out, md); console.log(`written ${out}`); } else console.log(md);
