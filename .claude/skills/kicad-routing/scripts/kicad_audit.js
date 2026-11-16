#!/usr/bin/env node
/*
 * kicad_audit.js — audits a KiCad 9 project against the AQTech "golden" standard (skill 1.2.0).
 *
 * Usage:
 *   node kicad_audit.js <path/to/board.kicad_pcb> [--json report.json] [--no-sch] [--quiet] [--params file.json]
 *
 * Exit code 0 = no FAIL findings, 1 = at least one FAIL, 2 = usage / parse error.
 * Located automatically next to the board: <name>.kicad_pro, *.kicad_sch, and the optional
 * per-project parameter file <name>.golden.json or kicad_golden.project.json (see templates/).
 * Run from a SHORT working directory on Windows — Node refuses to start when the cwd exceeds
 * the Win32 limit; the board path itself may be long.
 *
 * Rule sources after the 2026-09-16 review:
 *   - netclasses (from the project .kicad_pro) decide track width and via stack per net (Q-04)
 *   - any track arc is a FAIL: tuning meanders must use straight corners (Q-03)
 *   - remove_unused_layers / keep_end_layers missing on a via is a FAIL (Q-06)
 *   - via spacing and edge clearance derive from the project rules (fabricator limits) (Q-11, Q-12)
 *   - length matching, via budget, silkscreen, teardrops, via-in-pad list: per-project params (Q-05, Q-07..Q-10, Q-14, Q-15)
 */
'use strict';
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------- CLI
const args = process.argv.slice(2);
const pcbPath = args.find(a => !a.startsWith('--') && !(args[args.indexOf(a) - 1] || '').startsWith('--'));
if (!pcbPath || !fs.existsSync(pcbPath)) {
  console.error('usage: node kicad_audit.js <board.kicad_pcb> [--json out.json] [--no-sch] [--quiet] [--params file.json]');
  process.exit(2);
}
const opt = name => (args.includes(name) ? args[args.indexOf(name) + 1] : null);
const jsonOut = opt('--json');
const doSch = !args.includes('--no-sch');
const quiet = args.includes('--quiet');
const goldenPath = path.join(__dirname, '..', 'golden_settings.json');

// ---------------------------------------------------------------- s-expression parser
function parse(txt) {
  let i = 0; const n = txt.length;
  const ws = () => { while (i < n && /\s/.test(txt[i])) i++; };
  function atom() {
    if (txt[i] === '"') {
      let j = i + 1, s = '';
      while (j < n) {
        if (txt.charCodeAt(j) === 92) { s += txt[j + 1]; j += 2; continue; }
        if (txt[j] === '"') break;
        s += txt[j++];
      }
      i = j + 1; return s;
    }
    let j = i; while (j < n && !/[\s()]/.test(txt[j])) j++;
    const s = txt.slice(i, j); i = j; const f = Number(s);
    return (s !== '' && !isNaN(f)) ? f : s;
  }
  function list() {
    i++; const out = [];
    for (;;) {
      ws(); if (i >= n) break;
      const c = txt[i];
      if (c === ')') { i++; return out; }
      if (c === '(') out.push(list()); else out.push(atom());
    }
    return out;
  }
  ws(); return list();
}
const kids = (node, name) => node.filter(x => Array.isArray(x) && x[0] === name);
const kid = (node, name) => node.find(x => Array.isArray(x) && x[0] === name);
const val = (node, name, idx = 1, dflt) => { const k = kid(node, name); return k ? k[idx] : dflt; };
// KiCad 10 (format 20260206+) writes a zone net as (net "NAME"); KiCad 9 wrote (net <number>) + (net_name "NAME").
// Quoted atoms always parse to strings and bare numerics to Number, so the type separates the two formats.
const zoneNet = z => { const legacy = val(z, 'net_name'); if (legacy !== undefined) return legacy; const v = val(z, 'net'); return typeof v === 'string' ? v : undefined; };

// ---------------------------------------------------------------- findings
const findings = [];
const stats = {};
function add(level, check, msg, extra) { findings.push(Object.assign({ level, check, msg }, extra || {})); }
const FAIL = (c, m, e) => add('FAIL', c, m, e);
const WARN = (c, m, e) => add('WARN', c, m, e);
const INFO = (c, m, e) => add('INFO', c, m, e);
const r6 = x => Math.round(x * 1e6) / 1e6;
const key = (x, y) => r6(x).toFixed(6) + ',' + r6(y).toFixed(6);
const cnt = arr => { const m = {}; for (const a of arr) m[a] = (m[a] || 0) + 1; return m; };
const near = (a, b, t = 1e-6) => Math.abs(a - b) <= t;

// ---------------------------------------------------------------- load board, project, params, golden
const pcb = parse(fs.readFileSync(pcbPath, 'utf8'));
if (pcb[0] !== 'kicad_pcb') { console.error('not a kicad_pcb file'); process.exit(2); }
const nets = {}; for (const nn of kids(pcb, 'net')) nets[nn[1]] = nn[2];
const netName = id => nets[id] === undefined ? String(id) : nets[id];

const proPath = pcbPath.replace(/\.kicad_pcb$/i, '.kicad_pro');
const pro = fs.existsSync(proPath) ? JSON.parse(fs.readFileSync(proPath, 'utf8')) : null;
const gold = fs.existsSync(goldenPath) ? JSON.parse(fs.readFileSync(goldenPath, 'utf8')) : null;
const rules = Object.assign({}, gold ? gold.board.design_settings.rules : {}, pro ? ((pro.board || {}).design_settings || {}).rules || {} : {});
if (!pro) INFO('settings', `no project file next to the board (${path.basename(proPath)}); golden rules assumed`);

const paramCandidates = [opt('--params'), pcbPath.replace(/\.kicad_pcb$/i, '.golden.json'), path.join(path.dirname(pcbPath), 'kicad_golden.project.json')].filter(Boolean);
const paramsPath = paramCandidates.find(p => fs.existsSync(p));
const params = paramsPath ? JSON.parse(fs.readFileSync(paramsPath, 'utf8')) : {};
stats.project_params = paramsPath ? path.basename(paramsPath) : '(none: defaults)';
const P = {
  fab: params.fabricator || {},
  lengthGroups: params.length_groups || [],
  dpRules: (params.diff_pairs || {}).rules || [],
  viaBudget: params.via_budget || { fast_patterns: [], max_vias_fast: null, max_vias_default: null },
  keepoutLayerChange: (params.keepouts || {}).layer_change_allowed === true,
  refsHidden: (params.silkscreen || {}).references_hidden !== false,
  teardrops: params.teardrops || { allowed: false, allowed_patterns: [] },
  viaInPadRefs: (params.via_in_pad || {}).allowed_refs || null, // null => any exposed/heatsink pad qualifies
  sharedGapsAllowed: (params.shared_pad_gaps || {}).allowed === true, // Q-16 / improvements #6
  // Local fix after 1.16.0 (BladeOne, 2026-09-29): gaps flanked by a pad of one of these parts may carry more
  // than one track (e.g. a 2.54 mm THT header); the tracks must then be evenly spaced instead of one centred.
  sharedGapParts: new Set((params.shared_pad_gaps || {}).allowed_parts || []),
  planeNetExceptions: (params.plane_net_exceptions || {}).allowed || [], // Q-17 / improvements #7
  // 1.29.0 (GapOne CON, owner decision 2026-11-09, D-357): the minimum distance from the pad edge to the last bend
  // is a project parameter, pad_entry.bend_min_mm (default 0.5 mm, review issue 18 / L11);
  // pad_entry.bend_check: false switches the last-bend check off for the project (one INFO line instead).
  // The other pad-entry checks (axial entry, pad centre, width, short entry, staircase) are not affected.
  bendMinMm: typeof (params.pad_entry || {}).bend_min_mm === 'number' ? params.pad_entry.bend_min_mm : 0.5,
  bendCheck: (params.pad_entry || {}).bend_check !== false,
};
const planeExceptionKeys = new Set(P.planeNetExceptions.map(e => `${e.ref}-${e.pad}`));
// 1.26.5: a datasheet decoupling check with "surface": true (layout_checks, playbook B0) asks for the surface link
// between that pin and that capacitor, which rule 17 would FAIL. The pair is excused (INFO) when both pads are in the
// same surface group; any other pad joined to them by surface copper still FAILs.
const surfacePairs = new Map();          // 'U1-18' -> Set of partner keys
for (const d of ((params.layout_checks || {}).decoupling || [])) {
  if (!d.surface || !d.pin || !d.cap) continue;
  const a = d.pin.replace('.', '-'), b = d.cap.replace('.', '-');
  for (const [x, y] of [[a, b], [b, a]]) { if (!surfacePairs.has(x)) surfacePairs.set(x, new Set()); surfacePairs.get(x).add(y); }
}

// ---------------------------------------------------------------- netclass resolution (KiCad semantics)
const classes = {}; const patterns = [];
const ns = pro ? pro.net_settings || {} : {};
for (const c of (ns.classes || [])) classes[c.name] = c;
  const compilePattern = pat => new RegExp('^' + pat.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
for (const p of (ns.netclass_patterns || [])) if (p.pattern) patterns.push({ re: compilePattern(p.pattern), cls: p.netclass });
const assignments = ns.netclass_assignments || {};
if (!classes.Default) { FAIL('netclass', 'project has no Default netclass'); classes.Default = gold ? gold.net_settings.classes.find(c => c.name === 'Default') : { name: 'Default', track_width: 0.2, clearance: 0.1, via_diameter: 0.45, via_drill: 0.2 }; }
function classOf(name) {
  const direct = assignments[name]; if (direct && classes[direct]) return classes[direct];
  const hits = patterns.filter(p => p.re.test(name)).map(p => classes[p.cls]).filter(Boolean);
  if (!hits.length) return classes.Default;
  hits.sort((a, b) => (a.priority ?? 2147483647) - (b.priority ?? 2147483647)); // lower priority value wins
  return hits[0];
}
const classCache = {}; const clsFor = id => (classCache[id] = classCache[id] || classOf(netName(id)));
stats.netclasses = Object.keys(classes);
const predefTracks = ((pro || {}).board || {}).design_settings ? (pro.board.design_settings.track_widths || []).filter(w => w > 0) : [];
const predefVias = ((pro || {}).board || {}).design_settings ? (pro.board.design_settings.via_dimensions || []).filter(v => v.diameter > 0) : [];
// rev K: isPowerNet above is deliberately loose (it also matches Net-(...) autonames) and is
// used only to exclude nets from the via budget. Rail classification needs to be exact, because
// a current-carrying rail left on Default routes at signal width and NOTHING else catches it.
// + and - must be accepted as separators: rails are commonly written "+VSYS", "+BATT", "-12V".
// Written as regex LITERALS on purpose. Built from strings, '\d' is a JS string escape that
// collapses to the letter d, so the pattern silently demands a literal "d" and matches almost
// nothing — which is how this first shipped, reporting 0 rails on a board that has 5.
// Separators include + and - : rails are commonly written "+VSYS", "+BATT", "-12V".
const RE_SUPPLY = /^[+-]?\d+(?:[.pv]\d+)?v\d*$|(?:^|[_/+-])(?:vcc|vdd|vss|vee|vbus|vsys|vin|vout|vref|vbat|batt|bat|vbatt|avdd|dvdd|avcc|dvcc|vdda|vddd|vddio|vcore|vpp)(?:$|[_0-9])/i;
const RE_GROUND = /(?:^|[_/+-])(?:gnd|agnd|dgnd|pgnd|vss|earth)(?:$|[_0-9])/i;
// A divider tap or feedback pin looks like a rail but carries no current; widening it is wrong.
const RE_SENSE = /(?:^|[_/+-])(?:sense|sns|fb|feedback|adj|div|mon|monitor|meas|detect|det|ok|pg|pgood|por|test|tp)(?:$|[_0-9])/i;
function railKind(name) {
  if (!name || /^unconnected-/.test(name)) return null;
  if (RE_SENSE.test(name)) return 'sense';
  if (RE_GROUND.test(name) || RE_SUPPLY.test(name)) return 'power';
  return null;
}
const isPowerNet = name => /^(GND|\+|-|EARTH|V(CC|DD|IN|OUT|BUS)|Net-\()/.test(name) || /^POWER/.test((classOf(name) || {}).name || '');

// ---------------------------------------------------------------- 1. layers / stackup
{
  const layerList = (kid(pcb, 'layers') || []).slice(1).filter(Array.isArray);
  const copper = layerList.filter(l => ['signal', 'power', 'mixed'].includes(l[2]));
  stats.copper_layers = copper.map(l => l[1]);
  if (copper.length !== 4) WARN('stackup', `board has ${copper.length} copper layers; standard is 4 (F.Cu, In1.Cu, In2.Cu, B.Cu)`);
  const innerTyped = copper.filter(l => /^In\d/.test(l[1]) && l[2] !== 'power');
  if (innerTyped.length) INFO('stackup', `inner layers ${innerTyped.map(l => l[1]).join(', ')} typed "${innerTyped[0][2]}"; declare plane-only layers as "power" (field practice, 2026-09-17) so KiCad treats them as planes`);
  const setup = kid(pcb, 'setup') || [];
  const thick = val(kid(pcb, 'general') || [], 'thickness');
  if (thick !== 1.6) WARN('stackup', `board thickness ${thick} mm; standard is 1.6 mm`);
  const tent = kid(setup, 'tenting');
  // KiCad 9: (tenting front back).  KiCad 10: (tenting (front yes) (back yes)).
  const tentOk = !!tent && ((tent.includes('front') && tent.includes('back')) || (val(tent, 'front') === 'yes' && val(tent, 'back') === 'yes'));
  if (!tentOk) WARN('stackup', 'via tenting is not front+back');
  if (val(setup, 'pad_to_mask_clearance') !== 0) WARN('stackup', `pad_to_mask_clearance is ${val(setup, 'pad_to_mask_clearance')}; standard is 0`);
  const su = kid(setup, 'stackup');
  if (su) for (const l of kids(su, 'layer')) {
    if (val(l, 'type') !== 'copper') continue;
    const inner = /^In\d/.test(l[1]); const expect = inner ? (P.fab.inner_copper_um ? P.fab.inner_copper_um / 1000 : 0.035) : (P.fab.outer_copper_um ? P.fab.outer_copper_um / 1000 : 0.035);
    if (Math.abs(val(l, 'thickness') - expect) > 0.0005) WARN('stackup', `${l[1]} copper thickness ${val(l, 'thickness')}; expected ${expect} (${P.fab.profile ? 'fabricator profile ' + P.fab.profile : 'standard; confirm with the fabricator — multilayer stacks usually deliver 0.5 oz inner'})`);
  }
  if (params.stackup_reference && params.stackup_reference.name) INFO('stackup', `designed on stackup "${params.stackup_reference.name}"${params.stackup_reference.diff_pair_target_ohm ? `, diff target ${params.stackup_reference.diff_pair_target_ohm} Ω` : ''}`);
  else INFO('stackup', 'no controlled-impedance stackup reference recorded in project params (Q-13: per-project decision)');
  // Mandatory pre-routing gate: the fabricator profile (layer count + copper weight) must be on record and the rules must respect it.
  if (!P.fab.profile && !P.fab.layers) FAIL('pre-flight', 'no fabricator profile on record (kicad_golden.project.json → fabricator.layers / copper). Run apply_settings.js --fab jlcpcb --layers N --copper 1oz|2oz after asking the user; routing must not start before that.');
  else {
    stats.fabricator = { name: P.fab.name, profile: P.fab.profile, layers: P.fab.layers, copper: P.fab.copper, captured: P.fab.captured };
    if (P.fab.layers && copper.length !== P.fab.layers) FAIL('pre-flight', `board has ${copper.length} copper layers but the fabricator profile on record is ${P.fab.layers}-layer`);
    for (const [k, lim] of Object.entries(P.fab.kicad_rules || {})) { const cur = rules[k]; if (cur !== undefined && !/^(max_error|min_resolved_spokes)$/.test(k) && cur < lim - 1e-9) { const dev = (params.approved_rule_deviations || {})[k], absMin = (P.fab.absolute_min || {})[k]; if (dev && typeof dev.value === 'number' && cur >= dev.value - 1e-9 && !(typeof absMin === 'number' && cur < absMin - 1e-9)) { INFO('pre-flight', `rule ${k} = ${cur} is below the ${P.fab.name || 'fabricator'} profile value ${lim}: approved deviation (${dev.reason || 'approved_rule_deviations'})`); continue; } FAIL('pre-flight', `rule ${k} = ${cur} is below the ${P.fab.name || 'fabricator'} minimum ${lim}`); } }
  }
}

// 1.26.3: the board's title block carries the revision and date of the root schematic beside it (same stem): a new
// revision is set in every title block when it starts (kicad-schematic check_revision.py). Different -> WARN.
{
  const tb = kid(pcb, 'title_block');
  const bRev = tb && kid(tb, 'rev') ? String(kid(tb, 'rev')[1]) : '', bDate = tb && kid(tb, 'date') ? String(kid(tb, 'date')[1]) : '';
  const schPath = pcbPath.replace(/\.kicad_pcb$/, '.kicad_sch');
  stats.title_block = { rev: bRev || null, date: bDate || null };
  if (fs.existsSync(schPath)) {
    const t = fs.readFileSync(schPath, 'utf8').slice(0, 20000);
    const m = /\(title_block([\s\S]*?)\(lib_symbols/.exec(t);
    const sRev = m && /\(rev\s+"([^"]*)"\)/.exec(m[1]), sDate = m && /\(date\s+"([^"]*)"\)/.exec(m[1]);
    stats.title_block.schematic_rev = sRev ? sRev[1] : null;
    if (sRev && !bRev) WARN('revision', `the board title block has no revision (the schematic is rev ${sRev[1]})`);
    else if (sRev && bRev && sRev[1] !== bRev) WARN('revision', `board title block rev ${bRev} differs from the schematic's rev ${sRev[1]} — set the new revision in every title block (kicad-schematic check_revision.py)`);
    else if (sDate && bDate && sDate[1] !== bDate) WARN('revision', `board title block date ${bDate} differs from the schematic's ${sDate[1]}`);
    else if (sRev) INFO('revision', `title block rev ${bRev} ${bDate}, same as the schematic`);
  }
}

// 1.26.0 (playbook B0): the datasheets' layout suggestions are read BEFORE routing. datasheet_layout_scan.py writes
// params.datasheet_layout (one entry per part with layout pages, status "pending"); the review sets each to "applied"
// (every rule recorded with what it became) or "n/a" (with the reason). No block on a board with ICs -> WARN; any
// "pending" part -> FAIL pre-flight.
{
  const dl = params.datasheet_layout;
  const hasIC = kids(pcb, 'footprint').some(f => /^(U|IC|PS)\d/.test(String((kids(f, 'property').find(p => p[1] === 'Reference') || [])[2] || '')));
  if (!dl || !Array.isArray(dl.parts)) {
    if (hasIC) WARN('pre-flight', 'no datasheet layout review on record (kicad_golden.project.json → datasheet_layout): run datasheet_layout_scan.py --write-params and review its pages before routing (playbook B0)');
  } else {
    const pend = dl.parts.filter(p => (p.status || 'pending') === 'pending');
    const done = dl.parts.filter(p => p.status === 'applied').length, na = dl.parts.filter(p => p.status === 'n/a').length;
    stats.datasheet_layout = { scanned: dl.scanned || null, parts: dl.parts.length, applied: done, not_applicable: na, pending: pend.length };
    if (pend.length) FAIL('pre-flight', `datasheet layout suggestions not reviewed for ${pend.length} part(s): ${pend.slice(0, 10).map(p => `${p.part} (${(p.refs || []).slice(0, 3).join(',')})`).join('; ')} — read their pages, record each rule's use in datasheet_layout and set status applied / n/a (playbook B0)`);
    else INFO('pre-flight', `datasheet layout review: ${done} part(s) applied, ${na} n/a (scanned ${dl.scanned || '?'})`);
    const noRules = dl.parts.filter(p => p.status === 'applied' && !(p.rules || []).length);
    if (noRules.length) WARN('pre-flight', `datasheet_layout: ${noRules.length} part(s) marked applied with no rule recorded: ${noRules.slice(0, 8).map(p => p.part).join(', ')}`);
    if ((dl.missing_documents || []).length) WARN('pre-flight', `datasheet_layout: no document for ${dl.missing_documents.slice(0, 8).join(', ')} — get the datasheet and scan again`);
  }
}

// ---------------------------------------------------------------- collect geometry
const segs = kids(pcb, 'segment').map(s => ({
  x1: r6(val(s, 'start', 1)), y1: r6(val(s, 'start', 2)), x2: r6(val(s, 'end', 1)), y2: r6(val(s, 'end', 2)),
  w: val(s, 'width'), layer: val(s, 'layer'), net: val(s, 'net')
}));
for (const s of segs) s.len = r6(Math.hypot(s.x2 - s.x1, s.y2 - s.y1));
const arcs = kids(pcb, 'arc').map(a => ({ s: [val(a, 'start', 1), val(a, 'start', 2)], m: [val(a, 'mid', 1), val(a, 'mid', 2)], e: [val(a, 'end', 1), val(a, 'end', 2)], w: val(a, 'width'), layer: val(a, 'layer'), net: val(a, 'net') }));
const vias = kids(pcb, 'via').map(v => ({
  x: r6(val(v, 'at', 1)), y: r6(val(v, 'at', 2)), size: val(v, 'size'), drill: val(v, 'drill'), layers: (kid(v, 'layers') || []).slice(1), net: val(v, 'net'),
  free: !!kid(v, 'free'), rul: val(v, 'remove_unused_layers'), kel: val(v, 'keep_end_layers'), blind: !!kid(v, 'blind'), micro: !!kid(v, 'micro'), teardrop: !!kid(v, 'teardrops')
}));
const fps = kids(pcb, 'footprint');
const pads = [];
for (const f of fps) {
  const at = kid(f, 'at'); const fx = at[1], fy = at[2], frot = at[3] || 0; const th = frot * Math.PI / 180;
  const ref = (kids(f, 'property').find(p => p[1] === 'Reference') || [])[2];
  for (const p of kids(f, 'pad')) {
    const pa = kid(p, 'at'); const px = pa[1], py = pa[2], prot = pa[3] || 0;
    const ax = fx + px * Math.cos(th) + py * Math.sin(th); const ay = fy - px * Math.sin(th) + py * Math.cos(th);
    const sz = kid(p, 'size') || ['size', 0, 0]; const net = kid(p, 'net');
    // 1.20.0: lx/ly = pad centre in the footprint frame, lrot = pad rotation relative to the footprint
    // (KiCad stores pad rotation absolute), fx/fy/frot = footprint origin — used by the pad-row and pin-array checks.
    pads.push({ ref, num: p[1], type: p[2], shape: p[3], x: r6(ax), y: r6(ay), rot: ((prot % 180) + 180) % 180, w: sz[1], h: sz[2], net: net ? net[1] : -1, layers: (kid(p, 'layers') || []).slice(1), prop: val(p, 'property', 1, ''), teardrop: !!kid(p, 'teardrops'),
      lx: px, ly: py, lrot: ((((prot - frot) % 180) + 180) % 180), fx, fy, frot });
  }
}
stats.segments = segs.length; stats.arcs = arcs.length; stats.vias = vias.length; stats.footprints = fps.length; stats.pads = pads.length;
const padLayerOk = (p, layer) => p.layers.includes(layer) || p.layers.includes('*.Cu');
const insidePad = (p, x, y) => { const dx = x - p.x, dy = y - p.y; const th = -p.rot * Math.PI / 180; const lx = dx * Math.cos(th) - dy * Math.sin(th), ly = dx * Math.sin(th) + dy * Math.cos(th); return { inside: Math.abs(lx) <= p.w / 2 + 1e-9 && Math.abs(ly) <= p.h / 2 + 1e-9, lx, ly, d: Math.hypot(dx, dy) }; };
const segEnds = new Map();
for (const s of segs) for (const [x, y] of [[s.x1, s.y1], [s.x2, s.y2]]) { const k = key(x, y); if (!segEnds.has(k)) segEnds.set(k, []); segEnds.get(k).push(s); }
const viaMap = new Map(); for (const v of vias) viaMap.set(key(v.x, v.y), v);
const padMap = new Map(); for (const p of pads) { const k = key(p.x, p.y); if (!padMap.has(k)) padMap.set(k, []); padMap.get(k).push(p); }
// rev K: KiCad 10 (20260206+) has no top-level (net id name) table, so `nets` is empty there.
// Any check that enumerates Object.values(nets) sees nothing and reports a vacuous pass.
// Build the net-name universe from the items actually on the board; works on both formats.
const allNetNames = (() => {
  const out = new Set();
  for (const v of Object.values(nets)) if (v) out.add(v);
  for (const p of pads) { const n = netName(p.net); if (n && n !== 'undefined') out.add(n); }
  for (const t of segs) { const n = netName(t.net); if (n && n !== 'undefined') out.add(n); }
  for (const v of vias) { const n = netName(v.net); if (n && n !== 'undefined') out.add(n); }
  out.delete('0'); out.delete('');
  return [...out];
})();
stats.nets_seen = allNetNames.length;
const padsByNet = new Map(); for (const p of pads) { if (!padsByNet.has(p.net)) padsByNet.set(p.net, []); padsByNet.get(p.net).push(p); }
const padsByNetName = new Map(); for (const p of pads) { const nm = netName(p.net); if (!padsByNetName.has(nm)) padsByNetName.set(nm, []); padsByNetName.get(nm).push(p); }
// rev P: per-footprint info (library name, mounted layer) needed for the crystal/inductor ban
// (improvements #4) and for identifying a footprint's own pad nets vs a foreign track.
const fpInfo = {};
for (const f of fps) {
  const ref = (kids(f, 'property').find(p => p[1] === 'Reference') || [])[2] || '?';
  fpInfo[ref] = { libname: f[1], layer: val(f, 'layer'), block: f, nets: new Set(pads.filter(p => p.ref === ref).map(p => p.net)) };
}
// ---------------------------------------------------------------- 1.20.0 shared helpers (board review rev. 0.2, ServiceOne 2026-10-19)
// Used by the review checks in sections 6, 7, 16 and 19-31.
const hasCuG = p => (p.layers || []).some(l => /(^|\.)Cu$/.test(l) || l === '*.Cu');
const padsByRef = new Map(); for (const p of pads) { if (!padsByRef.has(p.ref)) padsByRef.set(p.ref, []); padsByRef.get(p.ref).push(p); }
// Pin pitch = centre distance to the nearest other copper pad of the same footprint.
for (const p of pads) {
  let best = Infinity;
  if (hasCuG(p)) for (const q of padsByRef.get(p.ref)) { if (q === p || !hasCuG(q)) continue; const d = Math.hypot(q.x - p.x, q.y - p.y); if (d > 1e-6 && d < best) best = d; }
  p.pitch = best;
}
const FINE_PITCH_MM = 0.65; const isFinePitch = p => p.pitch <= FINE_PITCH_MM + 1e-6;
// Plane nets: nets with a copper zone on an inner layer (same rule as section 17).
const planeNetNames = new Set();
for (const z of kids(pcb, 'zone')) {
  if (kid(z, 'keepout')) continue;
  const zl = kid(z, 'layers') ? kid(z, 'layers').slice(1) : [val(z, 'layer')];
  if (zl.some(l => /^In\d+\.Cu$/.test(l))) { const nn = zoneNet(z); if (nn) planeNetNames.add(nn); }
}
// Vias that section 6 accepts as thermal vias in an exposed pad (INFO): the via-ring, two-pad and pad-row checks skip them.
const allowedThermalVias = new Set();
// Distance from a point to a pad outline (0 inside). Rect / roundrect / oval treated as their bounding rectangle, circle as a circle.
function padDist(p, x, y) {
  const r = insidePad(p, x, y);
  if (p.shape === 'circle') return Math.max(0, r.d - p.w / 2);
  return Math.hypot(Math.max(0, Math.abs(r.lx) - p.w / 2), Math.max(0, Math.abs(r.ly) - p.h / 2));
}
// Reach of a pad from its centre along unit direction (ux, uy) (rectangle support function).
const padReachG = (p, ux, uy) => { const th = -p.rot * Math.PI / 180; const lx = ux * Math.cos(th) - uy * Math.sin(th), ly = ux * Math.sin(th) + uy * Math.cos(th); return Math.abs(lx) * p.w / 2 + Math.abs(ly) * p.h / 2; };
// Point in the footprint frame of pad q's footprint.
const toFpLocal = (q, x, y) => { const th = q.frot * Math.PI / 180, dx = x - q.fx, dy = y - q.fy; return [dx * Math.cos(th) - dy * Math.sin(th), dx * Math.sin(th) + dy * Math.cos(th)]; };
// Economical via drill (issue 11): fabricator.economical_via_drill_mm, default 0.2 mm for a JLC* profile.
const econDrill = (() => {
  if (typeof P.fab.economical_via_drill_mm === 'number') return P.fab.economical_via_drill_mm;
  return /^JLC/i.test(String(P.fab.name || '')) || /^JLC/i.test(String(P.fab.profile || '')) ? 0.2 : null;
})();
const fineViasApproved = P.fab.fine_vias_approved === true;
// Smallest predefined via the project may use (issue 4): smallest diameter whose drill is not below the economical tier.
const smallViaSize = (() => {
  const pool = predefVias.filter(v => econDrill === null || fineViasApproved || v.drill >= econDrill - 1e-9);
  if (!pool.length) return null;
  return pool.slice().sort((a, b) => a.diameter - b.diameter || a.drill - b.drill)[0];
})();

// Liang-Barsky segment/rectangle overlap — used by the crystal/inductor courtyard check.
function segRectHit(x1, y1, x2, y2, rx0, ry0, rx1, ry1) {
  let t0 = 0, t1 = 1; const dx = x2 - x1, dy = y2 - y1;
  const pp = [-dx, dx, -dy, dy], qq = [x1 - rx0, rx1 - x1, y1 - ry0, ry1 - y1];
  for (let i = 0; i < 4; i++) {
    if (pp[i] === 0) { if (qq[i] < 0) return false; }
    else { const r = qq[i] / pp[i]; if (pp[i] < 0) { if (r > t1) return false; if (r > t0) t0 = r; } else { if (r < t0) return false; if (r < t1) t1 = r; } }
  }
  return true;
}

// ---------------------------------------------------------------- 2. inner layer routing
{
  // 6+ layers: an inner layer declared "signal" in the board's (layers) list is a routing layer (GapOne CON
  // 6-layer stack S/GND/S/PWR/GND/S, owner 2026-11-07); on 4 layers every inner layer stays plane-only.
  const copper = (kid(pcb, 'layers') || []).slice(1).filter(Array.isArray).filter(l => ['signal', 'power', 'mixed'].includes(l[2]));
  const innerSignal = new Set(copper.length >= 6 ? copper.filter(l => /^In\d/.test(l[1]) && l[2] === 'signal').map(l => l[1]) : []);
  stats.inner_signal_layers = [...innerSignal];
  const inner = segs.filter(s => /^In\d+\.Cu$/.test(s.layer) && !innerSignal.has(s.layer));
  stats.inner_layer_segments = inner.length;
  if (inner.length) FAIL('inner-layers', `${inner.length} track segments on inner layers (inner layers are plane-only)`, { by_layer: cnt(inner.map(s => s.layer)) });
  if (arcs.some(a => /^In\d+\.Cu$/.test(a.layer))) FAIL('inner-layers', 'arcs on inner layers');
}

// ---------------------------------------------------------------- 3. angle lattice
{
  let bad = 0;
  for (const s of segs) {
    if (s.len === 0) { FAIL('geometry', `zero-length segment on ${netName(s.net)} @ ${s.x1},${s.y1} (${s.layer})`); continue; }
    let a = Math.atan2(s.y2 - s.y1, s.x2 - s.x1) * 180 / Math.PI; a = ((a % 45) + 45) % 45; const dev = Math.min(a, 45 - a);
    if (dev > 0.01) { bad++; FAIL('angle', `segment off the 45° lattice by ${r6(dev)}° on ${netName(s.net)} @ ${s.x1},${s.y1} (${s.layer})`); }
  }
  stats.off_lattice_segments = bad;
  let c45 = 0, c90 = 0, other = 0;
  for (const [, list] of segEnds) if (list.length === 2) {
    const [a, b] = list; const a1 = Math.atan2(a.y2 - a.y1, a.x2 - a.x1) * 180 / Math.PI, a2 = Math.atan2(b.y2 - b.y1, b.x2 - b.x1) * 180 / Math.PI;
    let d = Math.abs(((a1 - a2) % 180 + 180) % 180); d = Math.round(Math.min(d, 180 - d)); if (d === 0) continue; if (d === 45) c45++; else if (d === 90) c90++; else other++;
  }
  stats.corners = { deg45: c45, deg90: c90, other };
  if (c45 + c90 > 0 && c45 / (c45 + c90) < 0.9) WARN('angle', `only ${(100 * c45 / (c45 + c90)).toFixed(1)}% of corners are 45° mitres (standard ≥ 90%)`);
}

// ---------------------------------------------------------------- 4. arcs (Q-03: none allowed)
{
  const byNet = cnt(arcs.map(a => netName(a.net)));
  for (const a of arcs) FAIL('arcs', `track arc on ${netName(a.net)} @ ${a.s.join(',')} (${a.layer}) — arcs are not allowed; re-tune meanders with straight (chamfered) corners`);
  if (arcs.length) INFO('arcs', `${arcs.length} arcs by net: ${JSON.stringify(byNet)}`);
}

// ---------------------------------------------------------------- 5. widths (Q-04: netclass decides)
{
  const bgaPads = pads.filter(p => p.prop === 'pad_prop_bga' || Math.max(p.w, p.h) <= 0.3);
  const nearBga = (x, y) => bgaPads.some(p => Math.hypot(p.x - x, p.y - y) <= 2.5);
  stats.width_histogram = cnt(segs.map(s => s.w));
  let mism = 0;
  for (const s of segs) {
    const c = clsFor(s.net); const cw = c.track_width;
    if (s.w < rules.min_track_width - 1e-9) { FAIL('width', `track ${s.w} mm below min_track_width ${rules.min_track_width} on ${netName(s.net)} @ ${s.x1},${s.y1}`); continue; }
    if (near(s.w, cw)) continue;
    if (s.w < 0.2 - 1e-9) { if (!(nearBga(s.x1, s.y1) || nearBga(s.x2, s.y2))) FAIL('width', `track ${s.w} mm below 0.2 mm outside a BGA/fine-pitch escape on ${netName(s.net)} @ ${s.x1},${s.y1} (${s.layer})`); continue; }
    mism++;
    const pre = predefTracks.some(w => near(w, s.w));
    WARN('width', `track ${s.w} mm on ${netName(s.net)} (class ${c.name} = ${cw} mm)${pre ? ', a predefined width' : ', not a predefined width'} @ ${s.x1},${s.y1} (${s.layer}) — widths come from the netclass, not hand-set`);
  }
  stats.tracks_not_at_class_width = mism;
  let midRun = 0;
  for (const [k, list] of segEnds) {
    if (list.length !== 2 || padMap.has(k) || viaMap.has(k)) continue;
    const [a, b] = list; if (a.w === b.w) continue;
    const a1 = Math.atan2(a.y2 - a.y1, a.x2 - a.x1) * 180 / Math.PI, a2 = Math.atan2(b.y2 - b.y1, b.x2 - b.x1) * 180 / Math.PI;
    let d = Math.abs(((a1 - a2) % 180 + 180) % 180); d = Math.min(d, 180 - d);
    if (d < 0.01) { midRun++; WARN('width', `width changes ${a.w}→${b.w} mm in the middle of a straight run on ${netName(a.net)} @ ${k} (${a.layer})`); }
  }
  stats.mid_run_width_changes = midRun;
}

// ---------------------------------------------------------------- 6. vias (Q-04, Q-05, Q-06, Q-11)
{
  stats.via_stacks = cnt(vias.map(v => `${v.size}/${v.drill} ${v.layers.join('-')}`));
  const minDrill = Math.max(rules.min_through_hole_diameter || 0, P.fab.min_via_drill_mm || 0);
  for (const v of vias) {
    const c = clsFor(v.net);
    if (v.blind || v.micro) FAIL('via', `blind/micro via on ${netName(v.net)} @ ${v.x},${v.y} (through vias only)`);
    if (!(v.layers.length === 2 && v.layers.includes('F.Cu') && v.layers.includes('B.Cu'))) FAIL('via', `via ${netName(v.net)} @ ${v.x},${v.y} spans ${v.layers.join('-')} (through F.Cu–B.Cu only)`);
    const matchClass = near(v.size, c.via_diameter) && near(v.drill, c.via_drill);
    const matchPre = predefVias.some(d => near(d.diameter, v.size) && near(d.drill, v.drill));
    if (!matchClass && !matchPre) FAIL('via', `via ${v.size}/${v.drill} on ${netName(v.net)} @ ${v.x},${v.y} matches neither its netclass ${c.name} (${c.via_diameter}/${c.via_drill}) nor a predefined via size`);
    if (v.drill < minDrill - 1e-9) WARN('via', `via drill ${v.drill} below min through-hole ${minDrill} on ${netName(v.net)} @ ${v.x},${v.y} (fabricator limit)`);
    if (v.size - v.drill < 2 * (rules.min_via_annular_width || 0) - 1e-9) FAIL('via', `via ${v.size}/${v.drill} annular ring below ${rules.min_via_annular_width} on ${netName(v.net)} @ ${v.x},${v.y}`);
    if (v.rul !== 'yes' || v.kel !== 'yes') FAIL('via', `via on ${netName(v.net)} @ ${v.x},${v.y} lacks remove_unused_layers/keep_end_layers = yes`);
  }
  // netclass vs rules conflict (reviewer table: Default drill 0.15 vs min through-hole 0.20)
  for (const c of Object.values(classes)) if (c.via_drill && c.via_drill < minDrill - 1e-9) WARN('netclass', `netclass ${c.name} via drill ${c.via_drill} is below min through-hole ${minDrill} — resolve with the fabricator (raise the class drill or lower the rule)`);
  // via-in-pad
  let vip = 0;
  // 1.17.1: a pad with no copper layer (paste-only aperture of a subdivided exposed pad) is not a pad a via can
  // be "in"; and an exposed pad is also recognised as the dominant copper pad of its footprint (>= 3x the area of
  // every other copper pad, >= 5 copper pads), since QFN/SON thermal pads are often below the 2 mm side heuristic
  // (TPS63001 DRC: 1.65 x 2.4 mm; ADS131M04 RUK: 1.7 x 1.7 mm).
  const hasCu = p => (p.layers || []).some(l => /(^|\.)Cu$/.test(l) || l === '*.Cu');
  const cuAreas = new Map();
  for (const p of pads) if (hasCu(p)) { if (!cuAreas.has(p.ref)) cuAreas.set(p.ref, []); cuAreas.get(p.ref).push(p.w * p.h); }
  const dominant = p => { const a = (cuAreas.get(p.ref) || []).slice().sort((x, y) => y - x); return a.length >= 5 && Math.abs(a[0] - p.w * p.h) < 1e-9 && a[0] >= 3 * a[1]; };
  for (const v of vias) for (const p of pads) {
    if (p.type !== 'smd' || !hasCu(p) || !insidePad(p, v.x, v.y).inside) continue;
    const exposed = p.prop === 'pad_prop_heatsink' || Math.min(p.w, p.h) >= 2 || dominant(p);
    const listed = P.viaInPadRefs ? P.viaInPadRefs.includes(p.ref) : true;
    if (exposed && p.net === v.net && listed) allowedThermalVias.add(v);
    if (exposed && p.net === v.net && listed) INFO('via', `thermal via in exposed pad ${p.ref}-${p.num} (${netName(v.net)}) — allowed for this part per project params (assess per chip datasheet)`);
    else { vip++; FAIL('via', `via inside SMD pad ${p.ref}-${p.num} (${netName(v.net)}) @ ${v.x},${v.y} — via-in-pad ${exposed && p.net === v.net ? 'not approved for this part in project params' : 'is forbidden'}`); }
    break;
  }
  stats.via_in_pad = vip;
  // 1.20.0 — economical via drill (review issue 11, lesson "price tiers, not only capability minimums"):
  // a drill below the fabricator's economical tier is a FAIL unless the project recorded the fine-via
  // surcharge as approved (fabricator.fine_vias_approved = true), then INFO.
  {
    let below = 0;
    if (econDrill !== null) {
      const hist = {};
      for (const v of vias) if (v.drill < econDrill - 1e-9) { below++; const k = `${v.size}/${v.drill}`; hist[k] = (hist[k] || 0) + 1; if (!fineViasApproved) FAIL('via', `via drill ${v.drill} mm below the economical tier ${econDrill} mm (${P.fab.name || P.fab.profile || 'fabricator'} charges extra) on ${netName(v.net)} @ ${v.x},${v.y} — use a ${econDrill} mm drill or record fabricator.fine_vias_approved (review issue 11)`); }
      if (below && fineViasApproved) INFO('via', `${below} vias below the economical drill ${econDrill} mm, approved by fabricator.fine_vias_approved: ${JSON.stringify(hist)}`);
    }
    stats.economical_via_drill = { tier_mm: econDrill, below, approved: fineViasApproved };
  }
  // spacing from fabricator/rules: hole-to-hole
  const h2h = Math.max(rules.min_hole_to_hole || 0, P.fab.min_hole_to_hole_mm || 0);
  const buck = new Map(); const B = 1;
  for (const v of vias) { const k = Math.floor(v.x / B) + ',' + Math.floor(v.y / B); if (!buck.has(k)) buck.set(k, []); buck.get(k).push(v); }
  let minGap = Infinity;
  for (const v of vias) for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
    for (const u of buck.get((Math.floor(v.x / B) + dx) + ',' + (Math.floor(v.y / B) + dy)) || []) {
      if (u === v) continue; const gap = Math.hypot(u.x - v.x, u.y - v.y) - (u.drill + v.drill) / 2; if (gap < minGap) minGap = gap;
      if (gap < h2h - 1e-6 && v.x <= u.x) FAIL('via', `vias ${netName(v.net)} / ${netName(u.net)} hole-to-hole ${r6(gap)} mm < ${h2h} @ ${v.x},${v.y}`);
    }
  }
  stats.min_hole_to_hole = r6(minGap); stats.rule_hole_to_hole = h2h;
  // centring
  let onCentre = 0, nearMiss = 0;
  for (const [k, list] of segEnds) if (viaMap.has(k)) onCentre += list.length;
  for (const v of vias) {
    if (segEnds.has(key(v.x, v.y))) continue;
    for (const s of segs) { if (s.net !== v.net) continue; for (const [x, y] of [[s.x1, s.y1], [s.x2, s.y2]]) { const d = Math.hypot(x - v.x, y - v.y); if (d > 0 && d < 0.25) { nearMiss++; FAIL('via-centring', `track endpoint ${r6(d)} mm off via centre on ${netName(v.net)} @ ${v.x},${v.y}`); } } }
  }
  stats.via_centred_endpoints = onCentre; stats.via_near_miss = nearMiss;
  // teardrops (Q-15)
  const td = vias.filter(v => v.teardrop).length + pads.filter(p => p.teardrop).length;
  if (td && !P.teardrops.allowed) WARN('geometry', `${td} teardrops present; project params do not allow teardrops`);
  else if (td) INFO('geometry', `${td} teardrops present (allowed by project params)`);
}

// ---------------------------------------------------------------- 7. pad entries (rev P: Q-08/Q-09 supersede Q-01/Q-02)
// improvements #8: inside the clearance area a pad entry is ONE straight segment along one of the
// eight lattice directions, ending EXACTLY at the pad centre — no exemption for pads >= 2 mm.
// improvements #9: an elongated pad (>= 1.5x aspect) prefers the AXIAL direction over perpendicular/45°.
// improvements #5: the segment touching the pad is no wider than the pad's smallest dimension (FAIL,
// was WARN) — the clearance-area crossing must be a narrow stub; width elsewhere is unaffected.
{
  // 1.20.0 (board review rev. 0.2):
  //   issue 18 — a non-axial entry into an elongated pad is a FAIL to fix (was WARN, Q-09), and the last bend before
  //              the pad must lie at least 0.5 mm beyond the pad edge (the entry segment runs >= 0.5 mm outside the
  //              pad). A far end at a via or another pad is not a bend; a straight width change is not a bend. No
  //              fine-pitch exemption: at 0.5 mm pitch the bend still fits 0.5 mm past the toe (Vladimir's U1 fan-out).
  //   issue 6  — at a fine-pitch pad (pitch <= 0.65 mm to its nearest same-footprint pad) any non-axial entry is a
  //              blocking FAIL with no deviation (square fine-pitch pads accept either axis).
  const BEND_MIN_MM = P.bendMinMm;
  let exact = 0, offCentre = 0, nonAxial = 0, nonAxialElong = 0, shortEntry = 0, wideEntry = 0, staircase = 0, nearBend = 0, fineNonAxial = 0;
  for (const [k, list] of segEnds) {
    const ps = padMap.get(k); if (!ps) continue;
    for (const s of list) {
      const p = ps.find(pp => pp.net === s.net) || ps[0]; exact++;
      const isStart = key(s.x1, s.y1) === k; const dx = isStart ? s.x2 - s.x1 : s.x1 - s.x2, dy = isStart ? s.y2 - s.y1 : s.y1 - s.y2;
      let a = ((Math.atan2(dy, dx) * 180 / Math.PI % 180) + 180) % 180; const rel = Math.round((((a - p.rot) % 180) + 180) % 180);
      const elongated = Math.max(p.w, p.h) / Math.max(1e-9, Math.min(p.w, p.h)) >= 1.5;
      const fine = isFinePitch(p);
      const axialRel = p.w >= p.h ? 0 : 90;
      // Issue 18 covers every pad, passives included: a non-elongated rectangular pad accepts either axis; a round
      // pad (circle, or an oval with equal sides) has no axis and accepts any lattice direction into its centre.
      const round = p.shape === 'circle' || (p.shape === 'oval' && near(p.w, p.h));
      const axialOk = round || (elongated ? rel === axialRel : (rel === 0 || rel === 90));
      if (!axialOk) {
        nonAxial++; if (elongated) nonAxialElong++; if (fine) fineNonAxial++;
        FAIL('pad-entry', `non-axial entry into ${elongated ? 'elongated ' : ''}pad ${p.ref}-${p.num} (${p.w}x${p.h} mm${fine ? `, fine pitch ${r6(p.pitch)} mm: blocking, no deviation` : ''}, ${netName(s.net)}) @ ${k} — the last segment runs straight into the pad centre along its axis (review issues 6, 18; Q-09)`);
      }
      if (s.len < 0.2) { shortEntry++; WARN('pad-entry', `entry segment only ${s.len} mm into ${p.ref}-${p.num} (${netName(s.net)})`); }
      if (s.w > Math.min(p.w, p.h) + 1e-6) { wideEntry++; FAIL('pad-entry', `entry ${s.w} mm wider than pad ${p.ref}-${p.num}'s smallest dimension ${Math.min(p.w, p.h)} mm inside its clearance area on ${netName(s.net)} @ ${k} — neck down before crossing the clearance outline (Q-05 rev P)`); }
      const farK = isStart ? key(s.x2, s.y2) : key(s.x1, s.y1); const nxt = (segEnds.get(farK) || []).filter(t => t !== s);
      let isStair = false;
      if (nxt.length === 1 && nxt[0].len < 0.3 && s.len < 0.3) { staircase++; isStair = true; FAIL('pad-entry', `staircase (jog inside the clearance area) entering ${p.ref}-${p.num} (${netName(s.net)}) — one straight segment only (Q-08)`); }
      const [fxk, fyk] = isStart ? [s.x2, s.y2] : [s.x1, s.y1];
      const farInPad = (padsByNet.get(s.net) || []).some(q => q !== p && padLayerOk(q, s.layer) && insidePad(q, fxk, fyk).inside);
      if (!isStair && s.len > 0 && nxt.length && !viaMap.has(farK) && !padMap.has(farK) && !farInPad) {
        const a1 = Math.atan2(dy, dx) * 180 / Math.PI;
        const bends = nxt.some(t => { const a2 = Math.atan2(t.y2 - t.y1, t.x2 - t.x1) * 180 / Math.PI; let d = Math.abs(((a1 - a2) % 180 + 180) % 180); d = Math.min(d, 180 - d); return d > 0.01; });
        const outside = s.len - padReachG(p, dx / s.len, dy / s.len);
        if (P.bendCheck && bends && outside < BEND_MIN_MM - 1e-6) { nearBend++; FAIL('pad-entry', `last bend before pad ${p.ref}-${p.num} (${netName(s.net)}) is only ${r6(Math.max(0, outside))} mm beyond the pad edge @ ${farK} — enter straight along the axis with the bend >= ${BEND_MIN_MM} mm from the pad (review issue 18)`); }
      }
    }
  }
  for (const [k, list] of segEnds) {
    if (list.length !== 1 || viaMap.has(k) || padMap.has(k)) continue;
    const s = list[0]; const [x, y] = key(s.x1, s.y1) === k ? [s.x1, s.y1] : [s.x2, s.y2];
    for (const p of padsByNet.get(s.net) || []) {
      if (!padLayerOk(p, s.layer)) continue; const r = insidePad(p, x, y); if (!r.inside) continue;
      offCentre++; FAIL('pad-entry', `track ends ${r6(r.d)} mm off the centre of pad ${p.ref}-${p.num} (${netName(s.net)}) @ ${k} — must end exactly at the pad centre, no exemption for pads ≥ 2 mm (Q-08 rev P)`);
      break;
    }
  }
  if (!P.bendCheck) INFO('pad-entry', 'last-bend distance check switched off by the project (pad_entry.bend_check: false)');
  stats.pad_entries = { exact_centre: exact, off_centre: offCentre, non_axial: nonAxial, non_axial_elongated: nonAxialElong, non_axial_fine_pitch: fineNonAxial, short: shortEntry, wide: wideEntry, staircase, bend_near_pad: nearBend };
}

// ---------------------------------------------------------------- 8. keepouts (Q-10)
{
  // rev I (2026-09-18): rule areas may live INSIDE footprints. kids(pcb,'zone') returns only
  // top-level zones, so a board whose keepouts are all footprint-internal reported 0 and was never
  // checked. Footprint zone polygons carry ABSOLUTE coordinates, so no transform is needed.
  const topZones = kids(pcb, 'zone');
  const fpZones = [];
  for (const f of kids(pcb, 'footprint')) for (const z of kids(f, 'zone')) fpZones.push(z);
  const zones = topZones.concat(fpZones);
  const keep = zones.filter(z => kid(z, 'keepout'));
  stats.keepout_zones = keep.length;
  stats.keepout_zones_in_footprints = fpZones.filter(z => kid(z, 'keepout')).length;
  // Never let silence imply the rule was applied (SKILL.md, Keepouts).
  if (keep.length === 0) INFO('keepout', 'board declares zero rule_area keepouts - nothing to check');
  else INFO('keepout', `${keep.length} rule_area keepout(s) checked (${stats.keepout_zones_in_footprints} footprint-internal)`);
  const segInter = (p, q, r, s) => { const o = (a, b, c) => Math.sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])); return o(p, q, r) !== o(p, q, s) && o(r, s, p) !== o(r, s, q); };
  const inPoly = (pt, poly) => { let c = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if (((yi > pt[1]) !== (yj > pt[1])) && (pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi)) c = !c; } return c; };
  for (const z of keep) {
    const ko = kid(z, 'keepout'); const tracksNo = (kid(ko, 'tracks') || [])[1] === 'not_allowed'; const viasNo = (kid(ko, 'vias') || [])[1] === 'not_allowed';
    const layers = kid(z, 'layers') ? kid(z, 'layers').slice(1) : [val(z, 'layer')];
    const poly = (kid(kid(z, 'polygon'), 'pts') || []).slice(1).map(p => [p[1], p[2]]);
    const name = val(z, 'name', 1, '') || 'unnamed';
    const bb = [Math.min(...poly.map(p => p[0])), Math.min(...poly.map(p => p[1])), Math.max(...poly.map(p => p[0])), Math.max(...poly.map(p => p[1]))];
    if (tracksNo) {
      for (const s of segs) {
        if (!layers.includes(s.layer) && !layers.includes('*.Cu')) continue;
        let hit = inPoly([s.x1, s.y1], poly) || inPoly([s.x2, s.y2], poly);
        for (let i = 0; !hit && i < poly.length; i++) if (segInter([s.x1, s.y1], [s.x2, s.y2], poly[i], poly[(i + 1) % poly.length])) hit = true;
        if (hit) FAIL('keepout', `track ${netName(s.net)} crosses/enters keepout "${name}" on ${s.layer} @ ${s.x1},${s.y1} — route around it`);
      }
      // layer change to pass under the keepout: a via within 1 mm of the polygon on each side, same net, with a track under the keepout on another layer
      if (!P.keepoutLayerChange && !layers.includes('*.Cu')) {
        const under = segs.filter(s => !layers.includes(s.layer) && (inPoly([s.x1, s.y1], poly) || inPoly([s.x2, s.y2], poly) || poly.some((p, i) => segInter([s.x1, s.y1], [s.x2, s.y2], p, poly[(i + 1) % poly.length]))));
        const nearVia = v => v.x > bb[0] - 1 && v.x < bb[2] + 1 && v.y > bb[1] - 1 && v.y < bb[3] + 1;
        for (const net of new Set(under.map(s => s.net))) { const vs = vias.filter(v => v.net === net && nearVia(v)); if (vs.length >= 2) WARN('keepout', `net ${netName(net)} passes under keepout "${name}" with a via pair — layer change to bypass a keepout is not allowed by project params (Q-10)`); }
      }
    }
    if (viasNo) for (const v of vias) if ((layers.includes('*.Cu') || v.layers.some(l => layers.includes(l))) && inPoly([v.x, v.y], poly)) FAIL('keepout', `via ${netName(v.net)} inside via-keepout "${name}" @ ${v.x},${v.y}`);
  }
}

// ---------------------------------------------------------------- 9. differential pairs and length matching (Q-07, Q-08)
const netLen = {};
for (const s of segs) netLen[s.net] = (netLen[s.net] || 0) + s.len;
for (const a of arcs) netLen[a.net] = (netLen[a.net] || 0) + Math.hypot(a.m[0] - a.s[0], a.m[1] - a.s[1]) + Math.hypot(a.e[0] - a.m[0], a.e[1] - a.m[1]);
{
  const pairs = {};
  for (const [id, name] of Object.entries(nets)) { const m = String(name).match(/^(.*?)(_P|_N|P|N)$/); if (!m) continue; if (!/(TX|RX|TD|RD|IN|CLK|D\d|LVDS|USB|MDI)/i.test(name)) continue; (pairs[m[1]] = pairs[m[1]] || []).push(+id); }
  const dp = Object.entries(pairs).filter(([, ids]) => ids.length === 2);
  stats.diff_pairs = dp.length;
  let coupled = 0;
  for (const [b, [n1, n2]] of dp) {
    const c = clsFor(n1); const dw = c.diff_pair_width || 0.2, dg = c.diff_pair_gap || 0.25;
    const s1 = segs.filter(s => s.net === n1), s2 = segs.filter(s => s.net === n2);
    for (const a of s1) for (const cc of s2) {
      if (a.layer !== cc.layer || a.len < 3 || cc.len < 3) continue;
      const a1 = Math.atan2(a.y2 - a.y1, a.x2 - a.x1), a2 = Math.atan2(cc.y2 - cc.y1, cc.x2 - cc.x1);
      let d = Math.abs(((a1 - a2) * 180 / Math.PI % 180 + 180) % 180); if (d > 0.01 && Math.abs(d - 180) > 0.01) continue;
      const nx = -(a.y2 - a.y1) / a.len, ny = (a.x2 - a.x1) / a.len; const dist = Math.abs((cc.x1 - a.x1) * nx + (cc.y1 - a.y1) * ny);
      if (dist > 0.3 && dist < 0.7) { coupled++; if (!near(dist, dw + dg, 0.005) || !near(a.w, dw) || !near(cc.w, dw)) WARN('diff-pair', `pair ${b}: coupled section at ${r6(dist)} mm centre spacing / ${a.w} mm width (class ${c.name}: ${dw} / gap ${dg}) on ${a.layer} @ ${a.x1},${a.y1}`); }
    }
    const rule = P.dpRules.find(r => new RegExp(r.pattern).test(b.replace(/^.*\//, '')) || new RegExp(r.pattern).test(b));
    if (rule && rule.max_mismatch_mm !== null && rule.max_mismatch_mm !== undefined) {
      const mm = Math.abs((netLen[n1] || 0) - (netLen[n2] || 0));
      if (mm > rule.max_mismatch_mm + 1e-6) WARN('length', `pair ${b}: intra-pair mismatch ${r6(mm)} mm > ${rule.max_mismatch_mm} mm (project params)`);
    }
  }
  stats.diff_pair_coupled_sections = coupled;
  // length groups
  const groupResults = [];
  for (const g of P.lengthGroups) {
    const re = new RegExp(g.pattern); const members = Object.entries(nets).filter(([, n]) => re.test(String(n))).map(([id, n]) => ({ id: +id, name: String(n), len: netLen[id] || 0 })).filter(m => m.len > 0);
    if (members.length < 2) { INFO('length', `group "${g.name}": ${members.length} routed member(s) matched by /${g.pattern}/ — skipped`); continue; }
    const lens = members.map(m => m.len); const spread = Math.max(...lens) - Math.min(...lens);
    const clk = g.clock_pattern ? members.find(m => new RegExp(g.clock_pattern).test(m.name)) : null;
    const data = clk ? members.filter(m => m !== clk) : members;
    const dSpread = data.length > 1 ? Math.max(...data.map(m => m.len)) - Math.min(...data.map(m => m.len)) : 0;
    groupResults.push({ group: g.name, members: members.length, spread_mm: r6(spread), data_spread_mm: r6(dSpread), clock_len: clk ? r6(clk.len) : null });
    if (g.max_spread_mm !== null && g.max_spread_mm !== undefined) {
      const judged = g.clock_rule === 'shorter_or_equal' ? dSpread : spread;
      if (judged > g.max_spread_mm + 1e-6) WARN('length', `group "${g.name}": spread ${r6(judged)} mm > ${g.max_spread_mm} mm (longest ${members.sort((a, b) => b.len - a.len)[0].name.replace(/^.*\//, '')}, shortest ${members[members.length - 1].name.replace(/^.*\//, '')})`);
    }
    if (clk && g.clock_rule === 'shorter_or_equal' && clk.len > Math.max(...data.map(m => m.len)) + 1e-6) WARN('length', `group "${g.name}": clock ${clk.name.replace(/^.*\//, '')} (${r6(clk.len)} mm) is longer than the data lines`);
  }
  stats.length_groups = groupResults;
  if (!P.lengthGroups.length) INFO('length', 'no length groups defined in project params (Q-07/Q-08: per-bus decision) — length matching not audited');
}

// ---------------------------------------------------------------- 10. via budget (Q-09)
{
  const vb = P.viaBudget; const viaCount = {}; for (const v of vias) viaCount[v.net] = (viaCount[v.net] || 0) + 1;
  const signalNets = [...new Set(segs.map(s => s.net))].filter(id => !isPowerNet(netName(id)));
  const hist = cnt(signalNets.map(id => viaCount[id] || 0)); stats.signal_net_via_histogram = hist;
  const fast = (vb.fast_patterns || []).map(p => new RegExp(p));
  let over = 0;
  for (const id of signalNets) {
    const n = netName(id); const isFast = fast.some(re => re.test(n)); const cap = isFast ? vb.max_vias_fast : vb.max_vias_default;
    if (cap !== null && cap !== undefined && (viaCount[id] || 0) > cap) { over++; WARN('via-budget', `${n}: ${viaCount[id]} vias > ${cap} allowed for ${isFast ? 'fast' : 'default'} nets (project params)`); }
  }
  stats.via_budget_violations = over;
  if ((vb.max_vias_fast === null || vb.max_vias_fast === undefined) && (vb.max_vias_default === null || vb.max_vias_default === undefined)) INFO('via-budget', `no via budget set in project params (Q-09) — histogram only: ${JSON.stringify(hist)}`);
}

// ---------------------------------------------------------------- 11. zones
{
  // rev I: copper zones are top-level only; footprint zones are rule areas, handled in check 8.
  const zones = kids(pcb, 'zone').filter(z => !kid(z, 'keepout'));
  stats.copper_zones = zones.length;
  // Immutable 4-layer order: F.Cu signal | In1.Cu GND plane | In2.Cu POWER plane | B.Cu signal
  if (stats.copper_layers && stats.copper_layers.length === 4) {
    const zl = l => zones.filter(z => (kid(z, 'layers') ? kid(z, 'layers').slice(1) : [val(z, 'layer')]).includes(l)).map(z => String(zoneNet(z) || ''));
    const in1 = zl('In1.Cu'), in2 = zl('In2.Cu'); const isGnd = n => /GND|GROUND|^0V$|EARTH|AGND|DGND|PGND/i.test(n);
    if (!in1.some(isGnd)) FAIL('stackup-order', `In1.Cu carries no GND zone (${in1.length ? in1.join(', ') : 'no zones'}); layer 2 must be the ground plane`);
    if (in1.some(n => n && !isGnd(n))) WARN('stackup-order', `In1.Cu carries non-ground zones (${in1.filter(n => !isGnd(n)).join(', ')}); the standard reserves layer 2 for GND (EARTH-class islands tolerated)`);
    if (!in2.length) FAIL('stackup-order', 'In2.Cu carries no zone; layer 3 must be the power plane');
    else if (in2.some(isGnd) && !in2.some(n => !isGnd(n))) WARN('stackup-order', `In2.Cu carries only GND (${in2.join(', ')}); layer 3 is the POWER plane in the standard`);
    stats.stackup_roles = { In1: in1, In2: in2 };
  }
  const byLayer = {};
  for (const z of zones) {
    const nn = zoneNet(z); const layer = kid(z, 'layers') ? kid(z, 'layers').slice(1).join(',') : val(z, 'layer'); const prio = val(z, 'priority', 1, 0);
    const tag = `${nn || '(no net)'} on ${layer}`;
    if (!nn) FAIL('zone', `zone without net on ${layer}`);
    const hatch = kid(z, 'hatch'); if (!hatch || hatch[1] !== 'edge' || hatch[2] !== 0.5) WARN('zone', `${tag}: outline hatch is ${hatch ? hatch.slice(1).join(' ') : 'none'}; standard is "edge 0.5"`);
    const cp = kid(z, 'connect_pads') || []; const mode = cp.slice(1).find(x => !Array.isArray(x)); const clr = val(cp, 'clearance');
    if (mode === 'yes') INFO('zone', `${tag}: solid pad connection (standard uses thermal reliefs except mounting/heatsink pads)`);
    if (mode === 'no') WARN('zone', `${tag}: pads not connected to zone`);
    if (![0.05, 0.1].some(v => near(v, clr, 1e-9))) WARN('zone', `${tag}: zone clearance ${clr}; standard is 0.1 (0.05 for small local pours)`);
    const mt = val(z, 'min_thickness'); if (![0.05, 0.1, 0.25].some(v => near(v, mt, 1e-9))) WARN('zone', `${tag}: min_thickness ${mt}; standard uses 0.1 (planes) / 0.25 (outer pours) / 0.05 (small pours)`);
    if (val(z, 'filled_areas_thickness') === 'yes') WARN('zone', `${tag}: filled_areas_thickness yes; standard is no`);
    const fill = kid(z, 'fill') || []; if (val(fill, 'thermal_gap') !== 0.5 || val(fill, 'thermal_bridge_width') !== 0.5) WARN('zone', `${tag}: thermal gap/bridge ${val(fill, 'thermal_gap')}/${val(fill, 'thermal_bridge_width')}; standard 0.5/0.5`);
    if (kid(fill, 'mode') && val(fill, 'mode') !== 'solid') WARN('zone', `${tag}: hatched fill; standard is solid`);
    for (const l of layer.split(',')) { byLayer[l] = byLayer[l] || []; byLayer[l].push({ tag, prio, z }); }
  }
  const bb = z => { const pts = (kid(kid(z, 'polygon'), 'pts') || []).slice(1).map(p => [p[1], p[2]]); return [Math.min(...pts.map(p => p[0])), Math.min(...pts.map(p => p[1])), Math.max(...pts.map(p => p[0])), Math.max(...pts.map(p => p[1]))]; };
  for (const [, list] of Object.entries(byLayer)) for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
    if (list[i].prio !== list[j].prio) continue;
    const A = bb(list[i].z), Bb = bb(list[j].z); const overlap = A[0] < Bb[2] && Bb[0] < A[2] && A[1] < Bb[3] && Bb[1] < A[3];
    if (overlap && zoneNet(list[i].z) !== zoneNet(list[j].z)) WARN('zone', `zones "${list[i].tag}" and "${list[j].tag}" overlap with equal priority ${list[i].prio} — assign distinct priorities`);
  }
}

// ---------------------------------------------------------------- 12. footprints / silkscreen / edge (Q-12, Q-14)
{
  stats.footprint_layers = cnt(fps.map(f => val(f, 'layer')));
  stats.dnp_footprints = fps.filter(f => (kid(f, 'attr') || []).includes('dnp')).length;
  let visibleRefs = 0;
  for (const f of fps) {
    const ref = (kids(f, 'property').find(p => p[1] === 'Reference') || [])[2] || '?'; const attr = kid(f, 'attr') || [];
    if (/^(MH|FID|G|LOGO)\d*/.test(ref) && !attr.includes('exclude_from_bom')) WARN('footprint', `${ref} looks mechanical but is not exclude_from_bom`);
    // 1.20.0: the 3D-model test moved to section 31 (FAIL 'model', review issue 20).
    const rp = kids(f, 'property').find(p => p[1] === 'Reference'); const hidden = rp && kid(rp, 'hide') && kid(rp, 'hide')[1] === 'yes';
    if (!hidden && !/^(J|CN|CONN|SFP|POF)/.test(ref)) visibleRefs++;
  }
  stats.visible_references = visibleRefs;
  if (P.refsHidden && visibleRefs) WARN('silkscreen', `${visibleRefs} reference designators visible on silkscreen; project params say references are hidden (Q-14)`);
  if (!P.refsHidden && visibleRefs === 0 && fps.length) WARN('silkscreen', 'project params require visible references (third-party assembly/debug) but all are hidden');
  const edgeItems = ['gr_rect', 'gr_line', 'gr_arc', 'gr_poly', 'gr_circle'].flatMap(t => kids(pcb, t)).filter(g => val(g, 'layer') === 'Edge.Cuts');
  stats.edge_items = edgeItems.length;
  if (!edgeItems.length) FAIL('edge', 'no Edge.Cuts outline');
  for (const g of edgeItems) { const w = val(kid(g, 'stroke') || [], 'width'); if (w !== 0.05) WARN('edge', `Edge.Cuts stroke ${w}; standard is 0.05`); }
  const edgeClr = Math.max(rules.min_copper_edge_clearance || 0, P.fab.min_copper_to_edge_mm || 0); stats.rule_edge_clearance = edgeClr;
  const rect = edgeItems.find(g => g[0] === 'gr_rect');
  if (rect) {
    const x0 = Math.min(val(rect, 'start', 1), val(rect, 'end', 1)), x1 = Math.max(val(rect, 'start', 1), val(rect, 'end', 1));
    const y0 = Math.min(val(rect, 'start', 2), val(rect, 'end', 2)), y1 = Math.max(val(rect, 'start', 2), val(rect, 'end', 2));
    stats.board_size_mm = [r6(x1 - x0), r6(y1 - y0)];
    const edgeDist = (x, y) => Math.min(x - x0, x1 - x, y - y0, y1 - y);
    for (const s of segs) for (const [x, y] of [[s.x1, s.y1], [s.x2, s.y2]]) if (edgeDist(x, y) - s.w / 2 < edgeClr - 1e-6) FAIL('edge', `track ${netName(s.net)} within ${edgeClr} mm of board edge @ ${x},${y}`);
    for (const v of vias) if (edgeDist(v.x, v.y) - v.size / 2 < edgeClr - 1e-6) FAIL('edge', `via ${netName(v.net)} within ${edgeClr} mm of board edge @ ${v.x},${v.y}`);
  }
}

// ---------------------------------------------------------------- 13. project settings vs template
if (pro && gold) {
  const ds = (pro.board || {}).design_settings || {}; const gds = gold.board.design_settings;
  let sevDiff = 0, ruleDiff = 0, clsDiff = 0;
  for (const [k, v] of Object.entries(gds.rules)) {
    const cur = (ds.rules || {})[k]; if (JSON.stringify(cur) === JSON.stringify(v)) continue;
    const fabLim = (P.fab.kicad_rules || {})[k];
    if (fabLim !== undefined && typeof cur === 'number' && Math.abs(cur - fabLim) < 1e-9 && cur >= v) { INFO('settings', `board rule ${k} = ${cur} raised above the template ${v} to the ${P.fab.name || 'fabricator'} minimum`); continue; }
    // High-Density Via Allowance (rev H): on 4-layer and denser boards the profile's via size limits
    // REPLACE the template values, so a board sitting exactly on them is compliant, not deviant.
    if (fabLim !== undefined && typeof cur === 'number' && Math.abs(cur - fabLim) < 1e-9 && (P.fab.layers || 0) >= 4 && /^(min_via_diameter|min_via_annular_width)$/.test(k)) { INFO('settings', `board rule ${k} = ${cur} set to the ${P.fab.name || 'fabricator'} ${P.fab.layers}-layer via limit (template ${v}) — High-Density Via Allowance`); continue; }
    ruleDiff++; WARN('settings', `board rule ${k} = ${JSON.stringify(cur)}; template ${JSON.stringify(v)} — acceptable only if it reflects the fabricator's capability (Q-11/Q-12)`);
  }
  for (const [k, v] of Object.entries(gds.rule_severities)) if ((ds.rule_severities || {})[k] !== v) { sevDiff++; WARN('settings', `DRC severity ${k} = ${(ds.rule_severities || {})[k]}; template ${v}`); }
  for (const [k, v] of Object.entries(gold.erc.rule_severities)) if (((pro.erc || {}).rule_severities || {})[k] !== v) { sevDiff++; WARN('settings', `ERC severity ${k} = ${((pro.erc || {}).rule_severities || {})[k]}; template ${v}`); }
  for (const gc of gold.net_settings.classes) {
    const c = classes[gc.name];
    if (!c) { clsDiff++; if (/^(Default|POWER_DC|POWER_AC)$/.test(gc.name)) WARN('netclass', `netclass ${gc.name} not defined in the project (template defines it)`); else INFO('netclass', `template netclass ${gc.name} not defined (project-specific bus class)`); continue; }
    for (const k of ['clearance', 'track_width', 'via_diameter', 'via_drill', 'diff_pair_width', 'diff_pair_gap']) if (gc[k] !== undefined && c[k] !== gc[k]) {
      // 1.20.0 (review issue 11): a class drill raised from the template to the fabricator's economical tier is the
      // intended setting (apply_settings.js --fab raises it), not a deviation.
      if (k === 'via_drill' && econDrill !== null && !fineViasApproved && near(c[k], econDrill) && gc[k] < econDrill) { INFO('netclass', `netclass ${gc.name}.via_drill = ${c[k]} raised from the template ${gc[k]} to the economical drill tier`); continue; }
      clsDiff++; WARN('netclass', `netclass ${gc.name}.${k} = ${c[k]}; template ${gc[k]}`);
    }
  }
  if (!patterns.length && Object.keys(classes).length > 1) WARN('netclass', 'netclasses exist but no name patterns assign nets to them');
  // rev K: a current-carrying rail on Default is a FAIL, not a warning. It is the one defect a
  // settings template cannot catch for you - patterns captured from another board match nothing
  // here, the rail quietly routes at signal width, and the error reaches copper.
  {
    const padCountByName = new Map();
    for (const [id, list] of padsByNet) { const nm = netName(id); if (nm) padCountByName.set(nm, (padCountByName.get(nm) || 0) + list.length); }
    const MIN_RAIL_PADS = 3;
    const rails = [], senses = [];
    for (const nm of allNetNames) {
      const k = railKind(nm);
      if (k === 'sense') senses.push(nm);
      else if (k === 'power' && (padCountByName.get(nm) || 0) >= MIN_RAIL_PADS) rails.push(nm);
    }
    const onDefault = rails.filter(n => classOf(n).name === 'Default');
    stats.power_rails = rails.length;
    stats.power_rails_unclassed = onDefault.length;
    for (const n of onDefault) FAIL('netclass', `current-carrying rail ${n} (${padCountByName.get(n)} pads) resolves to Default and would route at signal width — assign it to POWER_DC (scripts/netclass_propose.py --apply)`);
    if (rails.length && !onDefault.length) INFO('netclass', `${rails.length} current-carrying rail(s) all resolve to a power netclass`);
    if (senses.length) INFO('netclass', `${senses.length} sense/feedback tap(s) correctly left on Default: ${senses.slice(0, 6).join(', ')}${senses.length > 6 ? '…' : ''}`);
  }
  // rev K: a rule inherited from another design matches zero nets and then reports a clean pass
  // while auditing nothing. Silence here is indistinguishable from success, so say it out loud.
  {
    const allNames = allNetNames;
    const dead = [];
    for (const pat of (ns.netclass_patterns || [])) {
      if (!pat.pattern) continue;
      const re = compilePattern(pat.pattern);
      if (!allNames.some(n => re.test(n))) dead.push(`netclass pattern "${pat.pattern}" -> ${pat.netclass}`);
    }
    for (const g of P.lengthGroups) if (g.pattern && !allNames.some(n => new RegExp(g.pattern).test(n))) dead.push(`length group "${g.name || g.pattern}"`);
    for (const r of P.dpRules) if (r.pattern && !allNames.some(n => new RegExp(r.pattern).test(n))) dead.push(`diff-pair rule "${r.pattern}"`);
    for (const f of (P.viaBudget.fast_patterns || [])) if (!allNames.some(n => new RegExp(f).test(n))) dead.push(`via-budget pattern "${f}"`);
    stats.rules_matching_nothing = dead.length;
    if (dead.length) {
      WARN('settings', `${dead.length} configured rule(s) match no net on this board — they audit nothing and their "pass" is meaningless: ${dead.slice(0, 6).join('; ')}${dead.length > 6 ? '…' : ''}`);
    }
  }
  const tps = ds.tuning_pattern_settings || {}; for (const k of Object.keys(gds.tuning_pattern_settings)) if (tps[k] && tps[k].corner_style !== gds.tuning_pattern_settings[k].corner_style) WARN('settings', `tuning ${k}.corner_style = ${tps[k].corner_style}; template ${gds.tuning_pattern_settings[k].corner_style} (straight corners: boards must carry zero arcs, Q-03)`);
  const gd = gds.defaults, d = ds.defaults || {};
  for (const k of ['silk_text_size_h', 'silk_text_thickness', 'silk_line_width', 'courtyard_line_width', 'board_outline_line_width', 'fab_line_width', 'fab_text_thickness', 'copper_text_thickness']) if (d[k] !== gd[k]) WARN('settings', `default ${k} = ${d[k]}; template ${gd[k]}`);
  for (const [k, v] of Object.entries(gd.zones || {})) if ((d.zones || {})[k] !== v) WARN('settings', `zone default ${k} = ${(d.zones || {})[k]}; template ${v}`);
  stats.settings = { rule_mismatches: ruleDiff, severity_mismatches: sevDiff, netclass_mismatches: clsDiff };
}

// ---------------------------------------------------------------- 14. schematic
if (doSch) {
  const dir = path.dirname(pcbPath); const schFiles = fs.readdirSync(dir).filter(f => /\.kicad_sch$/i.test(f));
  let glob = 0, hier = 0, nc = 0, syms = 0, dnpSym = 0, lcscMissing = 0, badLabel = 0, ncOnWire = 0;
  for (const f of schFiles) {
    let sch; try { sch = parse(fs.readFileSync(path.join(dir, f), 'utf8')); } catch (e) { WARN('schematic', `${f}: parse error ${e.message}`); continue; }
    const g = kids(sch, 'global_label'); glob += g.length; if (g.length) WARN('schematic', `${f}: ${g.length} global labels (standard uses hierarchical labels + sheet pins only)`);
    hier += kids(sch, 'hierarchical_label').length; const ncs = kids(sch, 'no_connect'); nc += ncs.length;
    const symbols = kids(sch, 'symbol'); syms += symbols.length;
    for (const s of symbols) {
      const lib = String(val(s, 'lib_id')); const props = kids(s, 'property'); const ref = (props.find(p => p[1] === 'Reference') || [])[2] || '?';
      if (/^power:|PWR_FLAG/.test(lib) || ref.startsWith('#')) continue;
      const isDnp = val(s, 'dnp') === 'yes'; if (isDnp) dnpSym++;
      const inBom = val(s, 'in_bom') !== 'no'; const lcsc = props.find(p => p[1] === 'LCSC');
      if (inBom && !isDnp && (!lcsc || lcsc[2] === '') && !/^(TP|TC|MH|FID|G|J|CN|CONN|BORAX)\d*/.test(ref)) lcscMissing++;
      const fpp = props.find(p => p[1] === 'Footprint'); if (inBom && (!fpp || fpp[2] === '')) WARN('schematic', `${f}: ${ref} has no footprint`);
    }
    for (const l of [...g, ...kids(sch, 'hierarchical_label'), ...kids(sch, 'label')]) { const sz = kid(kid(kid(l, 'effects') || [], 'font') || [], 'size'); if (sz && (sz[1] !== 1.27 || sz[2] !== 1.27)) badLabel++; }
    const wireEnds = new Set(kids(sch, 'wire').flatMap(w => kid(w, 'pts').slice(1).map(p => key(p[1], p[2]))));
    for (const n of ncs) if (wireEnds.has(key(val(n, 'at', 1), val(n, 'at', 2)))) ncOnWire++;
  }
  stats.schematic = { sheets: schFiles.length, symbols: syms, global_labels: glob, hierarchical_labels: hier, no_connects: nc, dnp_symbols: dnpSym, lcsc_missing: lcscMissing, non_1p27_labels: badLabel, no_connect_on_wire: ncOnWire };
  if (badLabel) WARN('schematic', `${badLabel} labels not 1.27 x 1.27 mm`);
  if (lcscMissing) WARN('schematic', `${lcscMissing} BOM symbols without an LCSC part number`);
  if (ncOnWire) WARN('schematic', `${ncOnWire} no_connect flags placed on a wire end instead of a pin`);
  if (schFiles.length && dnpSym !== stats.dnp_footprints) WARN('schematic', `DNP mismatch: ${dnpSym} schematic symbols vs ${stats.dnp_footprints} footprints flagged dnp`);
  if (schFiles.length && nc === 0) WARN('schematic', 'no no_connect flags anywhere — unused pins must be flagged (pin_not_connected is an ERC error)');
}

// ---------------------------------------------------------------- 15. Fab layer hygiene (improvements #1, #2)
{
  let visibleValues = 0, offCentreRefs = 0, missingRefs = 0;
  for (const f of fps) {
    const ref = (kids(f, 'property').find(p => p[1] === 'Reference') || [])[2] || '?';
    const mountLayer = val(f, 'layer'); const fabLayer = mountLayer === 'B.Cu' ? 'B.Fab' : 'F.Fab';
    // entry 1: Value must be hidden on Fab layers (hidden, never deleted), and no visible ${VALUE} user text
    const valProp = kids(f, 'property').find(p => p[1] === 'Value');
    if (valProp) {
      const vl = val(valProp, 'layer'); const hidden = !!kid(valProp, 'hide') && kid(valProp, 'hide')[1] === 'yes';
      if ((vl === 'F.Fab' || vl === 'B.Fab') && !hidden) { visibleValues++; WARN('fab-values', `${ref}: Value "${valProp[2]}" visible on ${vl} — hide it (never delete; BOM and Update-from-Schematic read it)`); }
    }
    for (const t of kids(f, 'fp_text')) {
      if (t[1] !== 'user' || typeof t[2] !== 'string' || !t[2].includes('${VALUE}')) continue;
      const tl = val(t, 'layer'); const hidden = !!kid(t, 'hide') && kid(t, 'hide')[1] === 'yes';
      if ((tl === 'F.Fab' || tl === 'B.Fab') && !hidden) { visibleValues++; WARN('fab-values', `${ref}: \${VALUE} text visible on ${tl} — hide it`); }
    }
    // entry 2: Fab reference centred on the Fab outline's bounding box, shrunk to fit
    const fabGfx = ['fp_line', 'fp_rect', 'fp_poly', 'fp_arc'].flatMap(t => kids(f, t)).filter(g => val(g, 'layer') === fabLayer);
    const pts = [];
    for (const g of fabGfx) {
      const a = kid(g, 'start'), b = kid(g, 'end'); if (a) pts.push([a[1], a[2]]); if (b) pts.push([b[1], b[2]]);
      const ptsNode = kid(g, 'pts'); if (ptsNode) for (const xy of ptsNode.slice(1)) if (Array.isArray(xy)) pts.push([xy[1], xy[2]]);
    }
    let refText = null, refTag = null;
    const rp = kids(f, 'property').find(p => p[1] === 'Reference');
    if (rp && val(rp, 'layer') === fabLayer) { refText = rp; refTag = 'Reference property'; }
    if (!refText) { const ft = kids(f, 'fp_text').find(t => val(t, 'layer') === fabLayer && typeof t[2] === 'string' && t[2].includes('${REFERENCE}')); if (ft) { refText = ft; refTag = '${REFERENCE} text'; } }
    if (!pts.length) continue; // no Fab outline on this footprint's mounted side — nothing to compare against
    const bx0 = Math.min(...pts.map(p => p[0])), bx1 = Math.max(...pts.map(p => p[0]));
    const by0 = Math.min(...pts.map(p => p[1])), by1 = Math.max(...pts.map(p => p[1]));
    const cx = (bx0 + bx1) / 2, cy = (by0 + by1) / 2;
    if (!refText) { missingRefs++; continue; }
    const at = kid(refText, 'at'); const d = Math.hypot(at[1] - cx, at[2] - cy);
    if (d > 0.05) { offCentreRefs++; WARN('fab-refs', `${ref}: Fab ${refTag} is ${r6(d)} mm off the outline centre (outline ${r6(bx1 - bx0)}x${r6(by1 - by0)} mm) — centre it (improvements #2)`); }
  }
  stats.fab_hygiene = { visible_values: visibleValues, off_centre_refs: offCentreRefs, footprints_missing_fab_ref: missingRefs };
  if (missingRefs) INFO('fab-refs', `${missingRefs} footprint(s) have no Fab reference text at all — fab_layer_fix.py --add-missing-refs adds one`);
}

// ---------------------------------------------------------------- 16. between-pad centring, shared gaps, route-around, crystal/inductor ban (improvements #3, #4, #6, #10)
{
  const BUCKET = 2; const padBuckets = new Map();
  const bkey = (x, y) => Math.floor(x / BUCKET) + ',' + Math.floor(y / BUCKET);
  // Other-net vias are flanks too (local fix after 1.16.0): a track squeezed between a pad and a via is in a
  // gap just as much as between two pads. Round, so their reach is the radius in every direction.
  const viaFlanks = vias.filter(v => v.size).map(v => ({ ref: 'via@' + r6(v.x) + ',' + r6(v.y), num: 'V', x: v.x, y: v.y, w: v.size, h: v.size, rot: 0,
    net: v.net, layers: v.layers && v.layers.length ? v.layers : ['F.Cu', 'B.Cu'], isVia: true, drill: v.drill || 0 }));
  for (const p of pads.concat(viaFlanks)) { const k = bkey(p.x, p.y); if (!padBuckets.has(k)) padBuckets.set(k, []); padBuckets.get(k).push(p); }
  const holeClr = rules.min_hole_clearance || 0;
  function nearbyPads(x0, y0, x1, y1, pad = 3) {
    const out = []; const bx0 = Math.floor((Math.min(x0, x1) - pad) / BUCKET), bx1 = Math.floor((Math.max(x0, x1) + pad) / BUCKET);
    const by0 = Math.floor((Math.min(y0, y1) - pad) / BUCKET), by1 = Math.floor((Math.max(y0, y1) + pad) / BUCKET);
    for (let bx = bx0; bx <= bx1; bx++) for (let by = by0; by <= by1; by++) { const l = padBuckets.get(bx + ',' + by); if (l) out.push(...l); }
    return out;
  }
  function padReach(p, ux, uy) {
    const th = -p.rot * Math.PI / 180; const lx = ux * Math.cos(th) - uy * Math.sin(th), ly = ux * Math.sin(th) + uy * Math.cos(th);
    return Math.abs(lx) * p.w / 2 + Math.abs(ly) * p.h / 2;
  }
  // Same-net copper a segment can terminate in: zone fills (by net name and layer) and vias.
  const fillsByNetLayer = new Map();
  for (const z of kids(pcb, 'zone')) {
    if (kid(z, 'keepout')) continue; const nn = zoneNet(z); if (!nn) continue;
    for (const fp of kids(z, 'filled_polygon')) {
      const k = nn + '|' + val(fp, 'layer'); const pts = (kid(fp, 'pts') || []).slice(1).map(p => [p[1], p[2]]);
      if (!fillsByNetLayer.has(k)) fillsByNetLayer.set(k, []); fillsByNetLayer.get(k).push(pts);
    }
  }
  const inPoly = (pts, x, y) => { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const [xi, yi] = pts[i], [xj, yj] = pts[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; };
  const inOwnFill = (s, x, y) => (fillsByNetLayer.get(netName(s.net) + '|' + s.layer) || []).some(pts => inPoly(pts, x, y));
  const onOwnVia = (s, x, y) => vias.some(v => v.net === s.net && Math.hypot(v.x - x, v.y - y) <= (v.size || 0) / 2 + 1e-6);
  // "Two-pad part" means two distinct pad numbers (a thermal pad split into several copper pads counts once).
  const padNumsByRef = new Map();
  for (const p of pads) { if (!padNumsByRef.has(p.ref)) padNumsByRef.set(p.ref, new Set()); padNumsByRef.get(p.ref).add(p.num); }
  const GAP_MAX_MM = 1.5;
  let mismatchCount = 0, routeAround = 0, ownPadFlanksSkipped = 0, wideGapsSkipped = 0, nonFacingSkipped = 0;
  const gapPairs = new Map(); // pad-pair key -> Set(net) — Q-16 / improvements #6
  const gapPadsByKey = new Map(); // pad-pair key -> [pad, pad] (1.20.0: free-alternative search, review issue 8)
  const allowedGapTracks = []; // segments in gaps the project allows to be shared (shared_pad_gaps.allowed_parts)
  for (const s of segs) {
    if (s.layer !== 'F.Cu' && s.layer !== 'B.Cu') continue;
    if (s.len < 0.3) continue; // pad-entry stubs are handled by check 7
    const ux = (s.x2 - s.x1) / s.len, uy = (s.y2 - s.y1) / s.len; const nx = -uy, ny = ux;
    const near = nearbyPads(s.x1, s.y1, s.x2, s.y2, 3);
    // A segment that starts or ends inside one of its own pads is, over that pad's length, a pad exit or
    // entry governed by entries 8/9 (straight, ending at the centre). Pads abreast of that own pad flank
    // the pad, not a gap the track passes through; centring against them would pull the track off the
    // pad centre. Only pads abreast of the segment's free run are gap candidates.
    // The 0.5 mm look-ahead past an end applies only where the track continues (a junction). Past an end
    // that terminates in same-net copper (pad, zone fill, via) there is no track, so pads abreast of that
    // copper do not flank this segment.
    const ownWin = []; const term = [false, false];
    [[s.x1, s.y1, 0], [s.x2, s.y2, s.len]].forEach(([ex, ey, tE], i) => {
      for (const p of near) if (p.net === s.net && padLayerOk(p, s.layer) && insidePad(p, ex, ey).inside) { ownWin.push([tE, padReach(p, ux, uy)]); term[i] = true; }
      if (!term[i] && (inOwnFill(s, ex, ey) || onOwnVia(s, ex, ey))) term[i] = true;
    });
    const tLo = term[0] ? 0 : -0.5, tHi = term[1] ? s.len : s.len + 0.5;
    const abreastOfOwnPad = p => { const t = (p.x - s.x1) * ux + (p.y - s.y1) * uy; return ownWin.some(([tE, reach]) => Math.abs(t - tE) <= reach + 1e-6); };
    const cands = near.filter(p => p.net !== s.net && padLayerOk(p, s.layer) && !(ownWin.length && abreastOfOwnPad(p) && ++ownPadFlanksSkipped));
    // 1.20.0 (review issue 15, the U102 miss): the flanks used to be the single nearest pad on each side over the
    // WHOLE segment. When those two did not face each other the segment was skipped, although it passed a real
    // gap elsewhere along its length: Net-(U102-1Y0) runs 4.5 mm west between U102 pins 10/11 (the nearest pads
    // on each side) but a pad of another part at its far end is nearer on one side, so the pair failed the facing
    // test and the gap was never checked (same reason J3 pins 8/9 with OUT1/OUT2_VSET were missed, issue 8).
    // Now every pair of MUTUALLY nearest facing flanks (one per side) is a gap of its own; a segment can pass several.
    const posC = [], negC = [];
    for (const p of cands) {
      const t = (p.x - s.x1) * ux + (p.y - s.y1) * uy; if (t < tLo || t > tHi) continue;
      const d = (p.x - s.x1) * nx + (p.y - s.y1) * ny;
      (d >= 0 ? posC : negC).push({ p, d, t });
    }
    if (!posC.length || !negC.length) continue;
    // Facing test (local fix after 1.16.0): two flanks form a gap only when they face each other across the
    // track - their offset ALONG the track may not exceed the sum of their reaches in that direction. Without
    // it, a long segment is "between" a pad near its start and another near its far end (BladeOne: +VSYS
    // paired R37-1 with C23-2, 12 mm apart), or between vias lying behind and beyond it.
    const faces = (A, Bq) => Math.abs(A.t - Bq.t) <= padReach(A.p, ux, uy) + padReach(Bq.p, ux, uy) + 1e-6;
    const pairList = [];
    for (const A of posC) {
      let bestB = null; for (const Bq of negC) if (faces(A, Bq) && (!bestB || Bq.d > bestB.d)) bestB = Bq;
      if (!bestB) continue;
      let bestA = null; for (const A2 of posC) if (faces(A2, bestB) && (!bestA || A2.d < bestA.d)) bestA = A2;
      if (bestA === A) pairList.push([A, bestB]);
    }
    if (!pairList.length) { nonFacingSkipped++; continue; }
    for (const [bestPos, bestNeg] of pairList) {
    if (Math.abs(bestPos.d) + Math.abs(bestNeg.d) > 6) continue; // not a tight gap — pads too far apart
    const p1 = bestPos.p, p2 = bestNeg.p;
    // Clearance to a flank, in copper-edge terms. For a via the binding keep-out may be its HOLE: the track
    // must stay hole-clearance from the drill edge, which on a thin annulus is further than copper clearance
    // from the ring. Converting the hole margin back to copper-edge terms (subtracting the extra it demands)
    // makes "equal clearance" mean "centred in the channel the track may actually use".
    const segClr = clsFor(s.net).clearance || rules.min_clearance || 0.1;
    const flankClr = (p, dAbs) => {
      if (!p.isVia) return dAbs - s.w / 2 - padReach(p, nx, ny);
      const cu = dAbs - s.w / 2 - p.w / 2, hole = dAbs - s.w / 2 - p.drill / 2;
      return Math.min(cu, hole - Math.max(0, holeClr - segClr));
    };
    const c1 = flankClr(p1, Math.abs(bestPos.d));
    const c2 = flankClr(p2, Math.abs(bestNeg.d));
    const sameFp = p1.ref === p2.ref;
    const twoPad = sameFp && (padNumsByRef.get(p1.ref) || new Set()).size === 2;
    // A gap between pads of different parts (or of a multi-pad part) is one whose free copper-edge width is at
    // most GAP_MAX_MM (the improvements doc's own example, header J3 at 2.54 mm pitch, is 0.84 mm). Wider
    // spaces are open board, not a gap to centre in. Under a two-pad part (entry 4) any gap width counts.
    if (!twoPad && c1 + c2 + s.w > GAP_MAX_MM + 1e-9) { wideGapsSkipped++; continue; }
    const gk = [p1.ref + '-' + p1.num, p2.ref + '-' + p2.num].sort().join(' / ');
    if (!gapPairs.has(gk)) gapPairs.set(gk, new Set());
    gapPairs.get(gk).add(s.net); if (!gapPadsByKey.has(gk)) gapPadsByKey.set(gk, [p1, p2]);
    if (sameFp) { routeAround++; WARN('route-around', `${netName(s.net)} passes under ${p1.ref} between its own pads ${p1.num}/${p2.num} @ ${r6(s.x1)},${r6(s.y1)} — go around unless the detour exceeds the project's detour_limits (improvements #10)`); }
    if (P.sharedGapParts.has(p1.ref) || P.sharedGapParts.has(p2.ref)) {
      // allowed shared gap: the verdict waits until every track of this gap is known (evenly spaced test below)
      allowedGapTracks.push({ gk, s, c1, c2, p1, p2, twoPad, nx, ny, mx: (p1.x + p2.x) / 2, my: (p1.y + p2.y) / 2 });
      continue;
    }
    if (Math.abs(c1 - c2) > 0.01) {
      mismatchCount++;
      const kind = twoPad ? `under two-pad part ${p1.ref}` : `between pads ${p1.ref}-${p1.num} / ${p2.ref}-${p2.num}`;
      FAIL('between-pads', `${netName(s.net)} runs ${kind} off-centre: ${r6(c1)} mm vs ${r6(c2)} mm clearance (must match within 0.01 mm) @ ${r6(s.x1)},${r6(s.y1)} (${s.layer}) — blocking, fix it (no deviation, review issue 15)`);
    }
    } // pairs
  }
  // Evenly spaced test for allowed shared gaps. Each track's clearance on either side is to its nearest
  // neighbour there: the flank pad, or another net's track in the same gap on the same layer (edge to edge,
  // measured across the track at the point nearest the gap centre). A gap with one track reduces to the
  // ordinary centring test. The FAIL keeps the between-pads wording, so centring tools read it unchanged:
  // moving each track to the middle of its neighbours converges to even spacing.
  const segPt = (s, px, py) => { const L2 = s.len * s.len; const t = L2 ? Math.max(0, Math.min(1, ((px - s.x1) * (s.x2 - s.x1) + (py - s.y1) * (s.y2 - s.y1)) / L2)) : 0; return [s.x1 + t * (s.x2 - s.x1), s.y1 + t * (s.y2 - s.y1)]; };
  let allowedGapUneven = 0;
  for (const e of allowedGapTracks) {
    const [qx, qy] = segPt(e.s, e.mx, e.my);
    let left = e.c1, right = e.c2; const nbNames = [];
    for (const o of allowedGapTracks) {
      if (o === e || o.gk !== e.gk || o.s.layer !== e.s.layer || o.s.net === e.s.net) continue;
      const [ox, oy] = segPt(o.s, qx, qy); const off = (ox - qx) * e.nx + (oy - qy) * e.ny;
      const clr = Math.abs(off) - e.s.w / 2 - o.s.w / 2;
      if (off >= 0) { if (clr < left) { left = clr; } } else if (clr < right) { right = clr; }
      nbNames.push(netName(o.s.net));
    }
    if (Math.abs(left - right) > 0.01) {
      mismatchCount++; allowedGapUneven++;
      const kind = e.twoPad ? `under two-pad part ${e.p1.ref}` : `between pads ${e.p1.ref}-${e.p1.num} / ${e.p2.ref}-${e.p2.num}`;
      const how = nbNames.length ? `unevenly spaced in the allowed shared gap (with ${[...new Set(nbNames)].join(', ')})` : 'off-centre in an allowed shared gap';
      FAIL('between-pads', `${netName(e.s.net)} runs ${kind} off-centre: ${r6(left)} mm vs ${r6(right)} mm clearance — ${how}, must match within 0.01 mm @ ${r6(e.s.x1)},${r6(e.s.y1)} (${e.s.layer})`);
    }
  }
  stats.allowed_shared_gap_tracks = allowedGapTracks.length; stats.allowed_shared_gap_uneven = allowedGapUneven;
  stats.between_pad_mismatches = mismatchCount; stats.route_around_candidates = routeAround;
  stats.between_pad_own_pad_flanks_skipped = ownPadFlanksSkipped; stats.between_pad_wide_gaps_skipped = wideGapsSkipped;
  stats.between_pad_non_facing_skipped = nonFacingSkipped;

  // 1.20.0 — free alternative for a shared gap (review issue 8, lesson "one track per gap, even where the project
  // allows two"): for a gap between two pads of one footprint, look at the neighbouring gaps of the same pin row
  // (the pad one pitch beyond either flank, same footprint). A neighbour gap that no track crosses on a shared copper
  // layer is named in the finding as the place to move one of the tracks.
  const gapIsFree = (pA, pB) => {
    const L = Math.hypot(pB.x - pA.x, pB.y - pA.y); if (L < 1e-6) return false;
    const ax = (pB.x - pA.x) / L, ay = (pB.y - pA.y) / L, bx = -ay, by = ax;
    const t0 = padReach(pA, ax, ay), t1 = L - padReach(pB, ax, ay); if (t1 <= t0) return false;
    const half = Math.min(padReach(pA, bx, by), padReach(pB, bx, by));
    for (const t of segs) {
      if (!(padLayerOk(pA, t.layer) && padLayerOk(pB, t.layer))) continue;
      const f = (x, y) => [(x - pA.x) * ax + (y - pA.y) * ay, (x - pA.x) * bx + (y - pA.y) * by];
      const [u1, v1] = f(t.x1, t.y1), [u2, v2] = f(t.x2, t.y2);
      if (segRectHit(u1, v1, u2, v2, t0, -half - t.w / 2, t1, half + t.w / 2)) return false;
    }
    return true;
  };
  const neighbourPad = (p, vx, vy) => (padsByRef.get(p.ref) || []).find(q => hasCuG(q) && Math.hypot(q.x - (p.x + vx), q.y - (p.y + vy)) < 0.05);
  let sharedGaps = 0, sharedWithFree = 0;
  for (const [gk, netSet] of gapPairs) {
    if (netSet.size < 2) continue;
    sharedGaps++;
    let freeHint = '';
    const pp = gapPadsByKey.get(gk);
    if (pp && !pp[0].isVia && !pp[1].isVia && pp[0].ref === pp[1].ref) {
      const [pA, pB] = pp; const vx = pB.x - pA.x, vy = pB.y - pA.y;
      const alts = [[pB, neighbourPad(pB, vx, vy)], [neighbourPad(pA, -vx, -vy), pA]].filter(([a, b]) => a && b);
      const free = alts.filter(([a, b]) => { const k2 = [a.ref + '-' + a.num, b.ref + '-' + b.num].sort().join(' / '); return !gapPairs.has(k2) && gapIsFree(a, b); });
      if (free.length) { sharedWithFree++; freeHint = `; free alternative: gap ${free.map(([a, b]) => `${a.ref}-${a.num} / ${b.ref}-${b.num}`).join(' or ')} of the same pin row carries no track — move one track there (review issue 8)`; }
    }
    // 1.28.0 (L42): net names sorted, so the message (and the finding's identity in audit_gate.py) does not depend on
    // the order of the tracks in the file - a pcbnew save and a KiCad GUI save write them in different orders.
    const msg = `pad gap ${gk} carries ${netSet.size} tracks (${[...netSet].map(netName).sort().join(', ')}) — at most one track per gap unless the project allows it (Q-16)${freeHint}`;
    const allowedByPart = gk.split(' / ').some(k => P.sharedGapParts.has(k.replace(/-[^-]*$/, '')));
    if (allowedByPart) WARN('shared-gap', msg.replace('unless the project allows it', 'allowed here by shared_pad_gaps.allowed_parts; tracks must be evenly spaced'));
    else if (P.sharedGapsAllowed) WARN('shared-gap', msg); else FAIL('shared-gap', msg);
  }
  stats.shared_pad_gaps = sharedGaps; stats.shared_pad_gaps_with_free_alternative = sharedWithFree;

  // improvements #4 exception: no OTHER net's track under a crystal or inductor's own courtyard,
  // on the copper layer it is mounted on.
  let crystalHits = 0;
  const isCrystalInductor = fi => /crystal|oscillator|resonator/i.test(fi.libname) || /inductor|choke|ferrite/i.test(fi.libname) || /^[YXL]\d+$/.test(fi.ref || '');
  for (const [ref, fi] of Object.entries(fpInfo)) {
    fi.ref = ref; if (!isCrystalInductor(fi)) continue;
    const crtLayer = fi.layer === 'B.Cu' ? 'B.CrtYd' : 'F.CrtYd';
    const f = fi.block; const at = kid(f, 'at'); const fx = at[1], fy = at[2], th = (at[3] || 0) * Math.PI / 180;
    const gfx = ['fp_line', 'fp_rect', 'fp_poly', 'fp_arc'].flatMap(t => kids(f, t)).filter(g => val(g, 'layer') === crtLayer);
    const pts = [];
    for (const g of gfx) { const a = kid(g, 'start'), b = kid(g, 'end'); if (a) pts.push([a[1], a[2]]); if (b) pts.push([b[1], b[2]]); }
    if (!pts.length) continue;
    const abs = pts.map(([px, py]) => [fx + px * Math.cos(th) + py * Math.sin(th), fy - px * Math.sin(th) + py * Math.cos(th)]);
    const rx0 = Math.min(...abs.map(p => p[0])), rx1 = Math.max(...abs.map(p => p[0]));
    const ry0 = Math.min(...abs.map(p => p[1])), ry1 = Math.max(...abs.map(p => p[1]));
    for (const s of segs) {
      if (s.layer !== fi.layer) continue; if (fi.nets.has(s.net)) continue;
      if (segRectHit(s.x1, s.y1, s.x2, s.y2, rx0, ry0, rx1, ry1)) { crystalHits++; FAIL('crystal-inductor', `${netName(s.net)} enters ${ref}'s courtyard on ${s.layer} — another net's track under a crystal/inductor is forbidden (improvements #4 exception) @ ${r6(s.x1)},${r6(s.y1)}`); }
    }
  }
  stats.crystal_inductor_violations = crystalHits;
}

// ---------------------------------------------------------------- 17. plane-net pads are via-only (improvements #7, D3 promoted to a Core rule)
{
  const planeNets = new Set();
  for (const z of kids(pcb, 'zone')) {
    if (kid(z, 'keepout')) continue;
    const layer = kid(z, 'layers') ? kid(z, 'layers').slice(1) : [val(z, 'layer')];
    if (layer.some(l => /^In\d+\.Cu$/.test(l))) { const nn = zoneNet(z); if (nn) planeNets.add(nn); }
  }
  stats.plane_nets = [...planeNets];
  let violations = 0, exceptions = 0;
  for (const pn of planeNets) {
    const netSegs = segs.filter(s => (s.layer === 'F.Cu' || s.layer === 'B.Cu') && netName(s.net) === pn);
    if (!netSegs.length) continue;
    const parent = new Map();
    const find = k => { while (parent.get(k) !== k) { parent.set(k, parent.get(parent.get(k))); k = parent.get(k); } return k; };
    const ensure = k => { if (!parent.has(k)) parent.set(k, k); return k; };
    const union = (a, b) => { a = find(ensure(a)); b = find(ensure(b)); if (a !== b) parent.set(a, b); };
    for (const s of netSegs) union(key(s.x1, s.y1), key(s.x2, s.y2));
    const groups = new Map();
    for (const p of (padsByNetName.get(pn) || [])) {
      const k = key(p.x, p.y); if (!parent.has(k)) continue; // pad with no surface track at all — fine
      const root = find(k); if (!groups.has(root)) groups.set(root, []); groups.get(root).push(p);
    }
    for (const [, padsHere] of groups) {
      if (padsHere.length < 2) continue;
      const keysHere = new Set(padsHere.map(p => `${p.ref}-${p.num}`));
      const datasheet = padsHere.filter(p => [...(surfacePairs.get(`${p.ref}-${p.num}`) || [])].some(k => keysHere.has(k)));
      const dsKeys = new Set(datasheet.map(p => `${p.ref}-${p.num}`));
      const flagged = padsHere.filter(p => !planeExceptionKeys.has(`${p.ref}-${p.num}`) && !dsKeys.has(`${p.ref}-${p.num}`));
      const excepted = padsHere.filter(p => planeExceptionKeys.has(`${p.ref}-${p.num}`) && !dsKeys.has(`${p.ref}-${p.num}`));
      if (excepted.length) { exceptions += excepted.length; INFO('plane-net', `${pn}: ${excepted.map(p => p.ref + '-' + p.num).join(', ')} joined by surface track to a same-net via — allowed per project params (Q-17)`); }
      if (datasheet.length) { exceptions += datasheet.length; INFO('plane-net', `${pn}: ${datasheet.map(p => p.ref + '-' + p.num).join(', ')} joined by a surface track as the datasheet asks (layout_checks decoupling "surface": true) — allowed`); }
      if (flagged.length >= 2 || (flagged.length >= 1 && datasheet.length)) { violations++; FAIL('plane-net', `${pn}: pads ${flagged.map(p => p.ref + '-' + p.num).join(', ')} are joined by a surface track instead of each getting its own via to the plane (improvements #7, D3)`); }
    }
  }
  stats.plane_net_link_violations = violations; stats.plane_net_exceptions_used = exceptions;
}

// ---------------------------------------------------------------- 18. even spacing (improvements #11, best-effort)
// Scoped to component outlines only (not track-to-track spacing), sampled at each segment's
// midpoint. Narrower than the full corridor scan the source material describes — see SKILL.md
// §Post-Routing Geometric Refinement for what this does and does not cover.
{
  const BUCKET2 = 2; const padBuckets2 = new Map();
  const bkey2 = (x, y) => Math.floor(x / BUCKET2) + ',' + Math.floor(y / BUCKET2);
  for (const p of pads) { const k = bkey2(p.x, p.y); if (!padBuckets2.has(k)) padBuckets2.set(k, []); padBuckets2.get(k).push(p); }
  function nearPads2(x, y, r) {
    const out = []; const b0x = Math.floor((x - r) / BUCKET2), b1x = Math.floor((x + r) / BUCKET2);
    const b0y = Math.floor((y - r) / BUCKET2), b1y = Math.floor((y + r) / BUCKET2);
    for (let bx = b0x; bx <= b1x; bx++) for (let by = b0y; by <= b1y; by++) { const l = padBuckets2.get(bx + ',' + by); if (l) out.push(...l); }
    return out;
  }
  let tight = 0;
  for (const s of segs) {
    if (s.len < 2) continue; if (s.layer !== 'F.Cu' && s.layer !== 'B.Cu') continue;
    const mx = (s.x1 + s.x2) / 2, my = (s.y1 + s.y2) / 2;
    const ux = (s.x2 - s.x1) / s.len, uy = (s.y2 - s.y1) / s.len; const nx = -uy, ny = ux;
    const c = clsFor(s.net); const clr = c.clearance || rules.min_clearance || 0.1;
    const cands = nearPads2(mx, my, 6).filter(p => p.net !== s.net && padLayerOk(p, s.layer));
    let posGap = Infinity, negGap = Infinity;
    for (const p of cands) {
      const dx = p.x - mx, dy = p.y - my; const d = dx * nx + dy * ny; const along = Math.abs(dx * ux + dy * uy);
      if (along > s.len / 2 + 1) continue; // roughly abreast of the segment, not off its end
      const gap = Math.abs(d) - s.w / 2 - Math.max(p.w, p.h) / 2;
      if (d >= 0) posGap = Math.min(posGap, gap); else negGap = Math.min(negGap, gap);
    }
    if (posGap === Infinity || negGap === Infinity) continue;
    const near = Math.min(posGap, negGap), far = Math.max(posGap, negGap);
    if (near < 2 * clr && far >= 3 * near && far - near > 0.2) { tight++; WARN('spreading', `${netName(s.net)} runs ${r6(near)} mm from a component outline for ${r6(s.len)} mm while ${r6(far)} mm is free on the other side — spread it (improvements #11, component outlines only)`); }
  }
  stats.tight_against_free_space = tight;
}

// ================================================================ 1.20.0 board-review checks (ServiceOne rev. 0.2, reports/board_review_rev02.md)
// Shared by sections 19-29.
const endPad = (net, layer, x, y) => { for (const p of padsByNet.get(net) || []) if (hasCuG(p) && padLayerOk(p, layer) && insidePad(p, x, y).inside) return p; return null; };
const distPtSeg = (px, py, s) => { const L2 = s.len * s.len; const t = L2 ? Math.max(0, Math.min(1, ((px - s.x1) * (s.x2 - s.x1) + (py - s.y1) * (s.y2 - s.y1)) / L2)) : 0; return Math.hypot(px - (s.x1 + t * (s.x2 - s.x1)), py - (s.y1 + t * (s.y2 - s.y1))); };
// Liang-Barsky clip of a segment to a rectangle: [t0, t1] of the inside part, or null.
function segClip(x1, y1, x2, y2, rx0, ry0, rx1, ry1) {
  let t0 = 0, t1 = 1; const dx = x2 - x1, dy = y2 - y1;
  const pp = [-dx, dx, -dy, dy], qq = [x1 - rx0, rx1 - x1, y1 - ry0, ry1 - y1];
  for (let i = 0; i < 4; i++) {
    if (pp[i] === 0) { if (qq[i] < 0) return null; }
    else { const r = qq[i] / pp[i]; if (pp[i] < 0) { if (r > t1) return null; if (r > t0) t0 = r; } else { if (r < t0) return null; if (r < t1) t1 = r; } }
  }
  return [t0, t1];
}
const outerSegs = segs.filter(s => s.len > 0 && (s.layer === 'F.Cu' || s.layer === 'B.Cu'));
const groupBy = (list, kf) => { const m = new Map(); for (const it of list) { const k = kf(it); if (!m.has(k)) m.set(k, []); m.get(k).push(it); } return m; };

// ---------------------------------------------------------------- 19. pad-entry end cap (review issues 3, 5, 6; lesson "track end cap outside its pad outline")
// A track ending inside one of its own pads must keep its round end cap (radius w/2) and its body inside the pad
// outline. Checked at EVERY segment end inside a same-net pad, not only at the exact centre: an off-axis run that
// ends inside the pad and jogs to the centre (U1 pins 9/10) sticks out at its end, and a wide track ending at a
// fine-pitch pad (U8 pin 10) sticks out on both sides. DRC flags neither. A track wider than the pad ending at its
// centre is reported once, by section 7 (wide entry). Rect / roundrect / trapezoid use the bounding rectangle,
// circle and oval their true outline; custom pads are skipped.
{
  let caps = 0; const capSeen = new Set();
  for (const s of outerSegs) for (const [x, y] of [[s.x1, s.y1], [s.x2, s.y2]]) {
    const p = endPad(s.net, s.layer, x, y); if (!p || p.shape === 'custom') continue;
    const ck = p.ref + '#' + p.num + '@' + key(x, y) + '/' + s.w; if (capSeen.has(ck)) continue; capSeen.add(ck);
    const r = insidePad(p, x, y);
    if (r.d < 1e-6 && s.w > Math.min(p.w, p.h) + 1e-6) continue; // section 7 reports it
    let out;
    if (p.shape === 'circle' || (p.shape === 'oval' && near(p.w, p.h))) out = r.d + s.w / 2 - p.w / 2;
    else if (p.shape === 'oval') { const rr = Math.min(p.w, p.h) / 2, a = Math.max(p.w, p.h) / 2 - rr; const [al, cr] = p.w >= p.h ? [r.lx, r.ly] : [r.ly, r.lx]; out = Math.hypot(Math.max(0, Math.abs(al) - a), cr) + s.w / 2 - rr; }
    else out = Math.max(Math.abs(r.lx) + s.w / 2 - p.w / 2, Math.abs(r.ly) + s.w / 2 - p.h / 2);
    if (out > 0.005) { caps++; FAIL('pad-entry', `track end cap (${s.w} mm wide) sticks ${r6(out)} mm out of pad ${p.ref}-${p.num} (${p.w}x${p.h} mm, ${netName(s.net)}) @ ${r6(x)},${r6(y)} (${s.layer}) — neck down to the pad width and end on the pad axis (review issues 3, 5, 6)`); }
  }
  stats.pad_entry_end_cap_outside = caps;
}

// ---------------------------------------------------------------- 20. plane vias at fine-pitch pads use the small via (review issue 4)
// A via of a plane net within 1.5 mm of a fine-pitch SMD pad (pitch <= 0.65 mm) should be the smallest predefined via
// (not below the economical drill): it fits closer to the pin and the stub is shorter. Larger -> WARN; the small via
// is recorded as allowed (INFO), whatever its netclass.
{
  let small = 0, large = 0;
  if (smallViaSize) {
    const fine = pads.filter(p => p.type === 'smd' && hasCuG(p) && isFinePitch(p));
    for (const v of vias) {
      if (!planeNetNames.has(netName(v.net)) || allowedThermalVias.has(v)) continue;
      let hit = null, hd = Infinity; for (const p of fine) { if (Math.abs(p.x - v.x) > 4 || Math.abs(p.y - v.y) > 4) continue; const d = padDist(p, v.x, v.y); if (d <= 1.5 && d < hd) { hit = p; hd = d; } }
      if (!hit) continue;
      if (v.size > smallViaSize.diameter + 1e-6) { large++; WARN('via', `plane via ${v.size}/${v.drill} on ${netName(v.net)} @ ${v.x},${v.y} is ${r6(hd)} mm from fine-pitch pad ${hit.ref}-${hit.num} (pitch ${r6(hit.pitch)} mm) — use the small plane via ${smallViaSize.diameter}/${smallViaSize.drill} and move it closer to the pin (review issue 4)`); }
      else small++;
    }
    if (small) INFO('via', `${small} plane via(s) next to fine-pitch pads use the small plane via ${smallViaSize.diameter}/${smallViaSize.drill} — allowed (review issue 4)`);
  }
  stats.plane_vias_fine_pitch = { small, large, small_via: smallViaSize ? `${smallViaSize.diameter}/${smallViaSize.drill}` : null };
}

// ---------------------------------------------------------------- 21. same-net crossing tracks (review issue 7)
// Two segments of one net on one layer that cross (intersection not at an end of either) are tangled copper: U202
// pins 5/6 reached their GND vias by two diagonals crossing under the body.
{
  let crossings = 0; const EPS = 1e-5;
  const orient = (ax, ay, bx, by, cx, cy) => (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
  const opp = (o1, o2) => (o1 > EPS && o2 < -EPS) || (o1 < -EPS && o2 > EPS);
  for (const [, list] of groupBy(outerSegs, s => netName(s.net) + '|' + s.layer)) {
    for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
      const a = list[i], b = list[j];
      if (Math.max(a.x1, a.x2) < Math.min(b.x1, b.x2) || Math.max(b.x1, b.x2) < Math.min(a.x1, a.x2) || Math.max(a.y1, a.y2) < Math.min(b.y1, b.y2) || Math.max(b.y1, b.y2) < Math.min(a.y1, a.y2)) continue;
      const o1 = orient(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1), o2 = orient(a.x1, a.y1, a.x2, a.y2, b.x2, b.y2);
      const o3 = orient(b.x1, b.y1, b.x2, b.y2, a.x1, a.y1), o4 = orient(b.x1, b.y1, b.x2, b.y2, a.x2, a.y2);
      if (!opp(o1, o2) || !opp(o3, o4)) continue;
      const t = o3 / (o3 - o4); const ix = a.x1 + t * (a.x2 - a.x1), iy = a.y1 + t * (a.y2 - a.y1);
      if ([[a.x1, a.y1], [a.x2, a.y2], [b.x1, b.y1], [b.x2, b.y2]].some(([x, y]) => Math.hypot(x - ix, y - iy) < 0.01)) continue;
      crossings++; FAIL('geometry', `same-net tracks of ${netName(a.net)} cross each other @ ${r6(ix)},${r6(iy)} (${a.layer}) — one straight route per pad (review issue 7)`);
    }
  }
  stats.same_net_crossings = crossings;
}

// ---------------------------------------------------------------- 22. via between the pads of a two-pad part (review issue 9)
// A via whose centre lies in the region between the two pads of a 2-pad SMD footprint (from inner pad edge to inner
// pad edge, as wide as the narrower pad) — tombstoning, trapped flux, no inspection. Own-pad plane vias and other-net
// vias alike; the message says which.
{
  let own = 0, other = 0;
  for (const [ref, list] of padsByRef) {
    const cu = list.filter(hasCuG);
    if (cu.length !== 2 || cu[0].num === cu[1].num || cu.some(p => p.type !== 'smd')) continue;
    const [pA, pB] = cu; const L = Math.hypot(pB.x - pA.x, pB.y - pA.y); if (L < 1e-6) continue;
    const ax = (pB.x - pA.x) / L, ay = (pB.y - pA.y) / L, bx = -ay, by = ax;
    const t0 = padReachG(pA, ax, ay), t1 = L - padReachG(pB, ax, ay); if (t1 <= t0) continue;
    const half = Math.min(padReachG(pA, bx, by), padReachG(pB, bx, by));
    for (const v of vias) {
      if (Math.abs(v.x - pA.x) > L + 1 || Math.abs(v.y - pA.y) > L + 1) continue;
      const u = (v.x - pA.x) * ax + (v.y - pA.y) * ay, w = (v.x - pA.x) * bx + (v.y - pA.y) * by;
      if (u <= t0 + 1e-6 || u >= t1 - 1e-6 || Math.abs(w) > half + 1e-6) continue;
      const isOwn = v.net === pA.net || v.net === pB.net; if (isOwn) own++; else other++;
      FAIL('via', `${isOwn ? 'own-pad' : 'other-net'} via ${netName(v.net)} @ ${v.x},${v.y} between the pads of two-pad part ${ref} — ${isOwn ? 'move it outside the part on the pad axis with a short stub' : 'move it out from under the body'} (review issue 9)`);
    }
  }
  stats.vias_between_two_pad_parts = { own_pad: own, other_net: other };
}

// ---------------------------------------------------------------- 23. via ring near an SMD pad (review issue 10)
// Keep >= 0.15 mm (solder-mask web) between a via's annular ring (radius size/2) and the edge of every SMD pad, same
// net included. Vias whose centre is inside a pad are section 6's (via-in-pad); thermal vias that section 6 allows in
// an exposed pad are skipped entirely.
{
  const WEB = 0.15; let hits = 0, merged = 0;
  const smd = pads.filter(p => p.type === 'smd' && hasCuG(p) && p.layers.some(l => l === 'F.Cu' || l === 'B.Cu' || l === '*.Cu'));
  for (const v of vias) {
    if (allowedThermalVias.has(v)) continue;
    let worst = null;
    for (const p of smd) {
      if (Math.abs(p.x - v.x) > 3 || Math.abs(p.y - v.y) > 3) continue;
      const d = padDist(p, v.x, v.y); if (d <= 0) continue;
      const gap = d - (v.size || 0) / 2; if (gap < WEB - 1e-6 && (!worst || gap < worst.gap)) worst = { p, gap };
    }
    if (!worst) continue;
    hits++; if (worst.gap <= 0) merged++;
    FAIL('via', `via ${netName(v.net)} ${v.size}/${v.drill} @ ${v.x},${v.y}: ring ${worst.gap <= 0 ? 'touches / merges with' : r6(worst.gap) + ' mm from'} SMD pad ${worst.p.ref}-${worst.p.num} (${netName(worst.p.net)}${worst.p.net === v.net ? ', same net' : ''}) — keep >= ${WEB} mm mask web: move the via along its stub on the pad axis (review issue 10)`);
  }
  stats.via_ring_near_smd_pad = { total: hits, touching: merged };
}

// ---------------------------------------------------------------- 24. detours (review issue 12)
// Chains of segments of one net on one layer between nodes (pads, vias, free ends, junctions of 3+ segments). WARN when
//   - the chain is longer than 3 mm and longer than 1.8 x its end-to-end distance, or
//   - it turns back: two consecutive corners turning the same way by more than 135 deg in total (a U-turn), or a bump
//     (out and back: the run leaves its direction by two opposite legs of >= 0.2 mm lateral each and resumes the same
//     direction right after; Net-(Q3-S) climbing toward Q3 pad 3 and coming back down).
// A detour around an obstacle with a straight run in the middle (trapezoid) is not a bump.
{
  const RATIO = 1.8, MIN_LEN = 3, LAT_MIN = 0.2; let detours = 0, ratioHits = 0, uTurns = 0, bumps = 0;
  const ang = (dx, dy) => Math.atan2(dy, dx) * 180 / Math.PI;
  const norm = a => { a = ((a + 180) % 360 + 360) % 360 - 180; return a; };
  for (const [, list] of groupBy(outerSegs, s => netName(s.net) + '|' + s.layer)) {
    const adj = new Map(); for (const s of list) for (const k of [key(s.x1, s.y1), key(s.x2, s.y2)]) { if (!adj.has(k)) adj.set(k, []); adj.get(k).push(s); }
    const nodeCache = new Map();
    const isNode = k => { if (nodeCache.has(k)) return nodeCache.get(k); const l = adj.get(k); let n = l.length !== 2 || viaMap.has(k); if (!n) { const [x, y] = k.split(',').map(Number); n = !!endPad(l[0].net, l[0].layer, x, y); } nodeCache.set(k, n); return n; };
    const seen = new Set();
    for (const [k0, l0] of adj) {
      if (!isNode(k0)) continue;
      for (const s0 of l0) {
        if (seen.has(s0)) continue;
        const chain = []; let cur = k0, s = s0;
        for (;;) {
          seen.add(s); const fwd = key(s.x1, s.y1) === cur; const to = fwd ? key(s.x2, s.y2) : key(s.x1, s.y1);
          chain.push({ s, dx: fwd ? s.x2 - s.x1 : s.x1 - s.x2, dy: fwd ? s.y2 - s.y1 : s.y1 - s.y2 });
          cur = to; if (isNode(cur)) break;
          const nxt = adj.get(cur).find(t => t !== s); if (!nxt || seen.has(nxt)) break; s = nxt;
        }
        if (chain.length < 2) continue;
        const [sx, sy] = k0.split(',').map(Number), [ex, ey] = cur.split(',').map(Number);
        const L = chain.reduce((a, c) => a + c.s.len, 0), D = Math.hypot(ex - sx, ey - sy);
        const why = [];
        if (L > MIN_LEN && (D < 1e-6 || L / D > RATIO)) { ratioHits++; why.push(`${r6(L)} mm long for ${r6(D)} mm end to end (ratio ${D < 1e-6 ? 'inf' : r6(L / D)} > ${RATIO})`); }
        const h = chain.map(c => ang(c.dx, c.dy)); const turn = h.slice(1).map((a, i) => norm(a - h[i]));
        let rev = null;
        for (let i = 0; i < turn.length && !rev; i++) {
          if (Math.abs(turn[i]) > 135 + 1e-6) rev = `turns back by ${r6(Math.abs(turn[i]))} deg`;
          else if (i + 1 < turn.length && Math.sign(turn[i]) === Math.sign(turn[i + 1]) && Math.abs(turn[i] + turn[i + 1]) > 135 + 1e-6) rev = `U-turn (${r6(Math.abs(turn[i] + turn[i + 1]))} deg over two corners)`;
        }
        if (rev) uTurns++;
        for (let i = 1; !rev && i + 2 < chain.length; i++) {
          const r = chain[i - 1], a = chain[i], b = chain[i + 1];
          if (Math.abs(norm(h[i + 2] - h[i - 1])) > 1) continue;
          const rl = Math.hypot(r.dx, r.dy); const ux = r.dx / rl, uy = r.dy / rl;
          const la = ux * a.dy - uy * a.dx, lb = ux * b.dy - uy * b.dx;
          if (la * lb < 0 && Math.min(Math.abs(la), Math.abs(lb)) >= LAT_MIN - 1e-6) { rev = `bump of ${r6(Math.min(Math.abs(la), Math.abs(lb)))} mm out and back`; bumps++; }
        }
        if (rev) why.push(rev);
        if (!why.length) continue;
        detours++; WARN('detour', `${netName(s0.net)} detour from ${r6(sx)},${r6(sy)} to ${r6(ex)},${r6(ey)} (${s0.layer}): ${why.join('; ')} — straighten it (review issue 12)`);
      }
    }
  }
  stats.detours = { total: detours, ratio: ratioHits, u_turns: uTurns, bumps };
}

// ---------------------------------------------------------------- 25. same-net loops and duplicate copper (review issue 14)
// Cycles in a net's track graph: nodes are segment ends, a via joins the layers at its centre, a pad (by reference and
// number) joins every track end inside it; zones are not part of the graph. A segment closing a cycle -> FAIL 'loop'.
// Also near-parallel same-net segments closer than 0.3 mm centre to centre over more than 0.5 mm -> FAIL 'loop'
// (offset duplicates that Cleanup's co-linear merge does not catch: Q302 pad 2 to tab).
{
  let cycles = 0, dups = 0;
  for (const [nm, list] of groupBy(segs.filter(s => s.len > 0), s => netName(s.net))) {
    const parent = new Map();
    const find = k => { if (!parent.has(k)) parent.set(k, k); while (parent.get(k) !== k) { parent.set(k, parent.get(parent.get(k))); k = parent.get(k); } return k; };
    const nodeOf = (s, x, y) => { const k = key(x, y); const v = viaMap.get(k); if (v && v.net === s.net) return 'V' + k; const p = endPad(s.net, s.layer, x, y); if (p) return 'P' + p.ref + '#' + p.num; return s.layer + '|' + k; };
    // A segment whose centreline crosses a same-net pad without ending in it is connected to that pad too (KiCad
    // connectivity): Q302's duplicate runs from the tab (pad 4) straight over pad 2 and on, 0.4 mm beside the
    // pad 2 -> tab link, so the loop closes through pad 2.
    const throughPads = s => {
      const out = [];
      for (const p of padsByNet.get(s.net) || []) {
        if (!hasCuG(p) || !padLayerOk(p, s.layer)) continue;
        if (Math.max(s.x1, s.x2) < p.x - p.w - p.h || Math.min(s.x1, s.x2) > p.x + p.w + p.h || Math.max(s.y1, s.y2) < p.y - p.w - p.h || Math.min(s.y1, s.y2) > p.y + p.w + p.h) continue;
        const a = insidePad(p, s.x1, s.y1), b = insidePad(p, s.x2, s.y2);
        if (a.inside || b.inside) continue;
        if (segRectHit(a.lx, a.ly, b.lx, b.ly, -p.w / 2, -p.h / 2, p.w / 2, p.h / 2)) out.push({ p, t: (p.x - s.x1) * (s.x2 - s.x1) + (p.y - s.y1) * (s.y2 - s.y1) });
      }
      return out.sort((u, v) => u.t - v.t).map(o => 'P' + o.p.ref + '#' + o.p.num);
    };
    for (const s of list) {
      const chainNodes = [nodeOf(s, s.x1, s.y1), ...throughPads(s), nodeOf(s, s.x2, s.y2)].filter((n, i, arr) => i === 0 || n !== arr[i - 1]);
      let closed = false;
      for (let i = 0; i + 1 < chainNodes.length; i++) {
        const ra = find(chainNodes[i]), rb = find(chainNodes[i + 1]);
        if (ra === rb) closed = true; else parent.set(ra, rb);
      }
      if (closed) { cycles++; FAIL('loop', `${nm}: segment ${r6(s.x1)},${r6(s.y1)} -> ${r6(s.x2)},${r6(s.y2)} (${s.layer}) closes a loop in the net's track graph (duplicate or parallel path; planes excluded) — delete the redundant branch (review issue 14)`); }
    }
  }
  for (const [, list] of groupBy(outerSegs.filter(s => s.len > 0.5), s => netName(s.net) + '|' + s.layer)) {
    for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
      const a = list[i], b = list[j];
      const ux = (a.x2 - a.x1) / a.len, uy = (a.y2 - a.y1) / a.len;
      const vx = (b.x2 - b.x1) / b.len, vy = (b.y2 - b.y1) / b.len;
      if (Math.abs(ux * vy - uy * vx) > Math.sin(Math.PI / 180)) continue; // not parallel within 1 deg
      const perp = (x, y) => Math.abs((x - a.x1) * -uy + (y - a.y1) * ux);
      if (Math.max(perp(b.x1, b.y1), perp(b.x2, b.y2)) >= 0.3) continue;
      const t1 = (b.x1 - a.x1) * ux + (b.y1 - a.y1) * uy, t2 = (b.x2 - a.x1) * ux + (b.y2 - a.y1) * uy;
      const ov = Math.min(a.len, Math.max(t1, t2)) - Math.max(0, Math.min(t1, t2));
      if (ov <= 0.5) continue;
      dups++; FAIL('loop', `${netName(a.net)}: duplicate copper — two parallel segments ${r6(Math.max(perp(b.x1, b.y1), perp(b.x2, b.y2)))} mm apart over ${r6(ov)} mm @ ${r6(a.x1)},${r6(a.y1)} / ${r6(b.x1)},${r6(b.y1)} (${a.layer}) — keep one (review issue 14)`);
    }
  }
  stats.same_net_loops = cycles; stats.same_net_duplicates = dups;
}

// ---------------------------------------------------------------- 26. via inside an IC pad-row band (review issue 16, Vladimir's rule)
// For U*/IC* footprints with >= 6 copper pads: a pad row is >= 3 equal pads on one footprint-frame line at a uniform
// pitch (0.1-2.6 mm), not all with the same number (an exposed pad split into a grid). Its band runs across the row from the inner pad ends to 0.5 mm beyond the outer pad ends, and
// along it from the first to the last pin centre. Any via whose copper reaches it -> FAIL (vias go beyond the row or under the body between
// the rows). Via-in-pad is section 6's; allowed exposed-pad thermal vias are skipped.
{
  let bandHits = 0, rowsFound = 0;
  for (const [ref, list] of padsByRef) {
    if (!/^(U|IC)\d/.test(ref)) continue;
    const cu = list.filter(hasCuG); if (cu.length < 6) continue;
    const ext = p => (Math.round(p.lrot) % 180 === 90) ? [p.h, p.w] : [p.w, p.h];
    const rows = [];
    for (const axis of ['x', 'y']) {
      const cAt = p => axis === 'x' ? p.lx : p.ly, along = p => axis === 'x' ? p.ly : p.lx;
      for (const [, g] of groupBy(cu, p => { const [ex, ey] = ext(p); return Math.round(cAt(p) * 100) + '|' + Math.round(ex * 1000) + '|' + Math.round(ey * 1000); })) {
        if (g.length < 3 || new Set(g.map(p => p.num)).size === 1) continue; // one number = exposed-pad grid
        g.sort((a, b) => along(a) - along(b));
        const gaps = g.slice(1).map((p, i) => along(p) - along(g[i]));
        if (gaps.some(d => Math.abs(d - gaps[0]) > 0.02) || gaps[0] > 2.6 || gaps[0] < 0.1) continue;
        const c = cAt(g[0]); const [ex, ey] = ext(g[0]); const half = (axis === 'x' ? ex : ey) / 2;
        if (Math.abs(c) <= half + 1e-6) continue; // a row through the footprint origin has no inner/outer side
        rows.push({ axis, c, half, g, along });
      }
    }
    rowsFound += rows.length; if (!rows.length) continue;
    const q0 = cu[0];
    for (const v of vias) {
      if (allowedThermalVias.has(v) || Math.hypot(v.x - q0.fx, v.y - q0.fy) > 40) continue;
      if (cu.some(p => insidePad(p, v.x, v.y).inside)) continue;
      const [vx, vy] = toFpLocal(q0, v.x, v.y);
      for (const row of rows) {
        const across = row.axis === 'x' ? vx : vy, al = row.axis === 'x' ? vy : vx;
        if (Math.sign(across) !== Math.sign(row.c)) continue;
        // the via's copper must stay out of the band (as KiCad's DRC and the router's via keep-out see it)
        const a = Math.abs(across), inner = Math.abs(row.c) - row.half, outer = Math.abs(row.c) + row.half + 0.5;
        const s0 = row.along(row.g[0]), s1 = row.along(row.g[row.g.length - 1]), r = (v.size || 0) / 2;
        const dA = Math.max(inner - a, 0, a - outer), dS = Math.max(s0 - al, 0, al - s1);
        if (Math.hypot(dA, dS) >= r - 0.0005 && (dA > 0 || dS > 0)) continue;
        const alc = Math.min(Math.max(al, s0 + 1e-6), s1 - 1e-6);
        const i = row.g.findIndex((p, j) => j < row.g.length - 1 && alc >= row.along(p) && alc <= row.along(row.g[j + 1]));
        if (i < 0) continue;
        bandHits++; FAIL('via', `via ${netName(v.net)} @ ${v.x},${v.y} inside the pad-row band of ${ref} between pins ${row.g[i].num}/${row.g[i + 1].num} — move it beyond the outer pad ends (+0.5 mm) or under the body between the rows (review issue 16)`);
        break;
      }
    }
  }
  stats.pad_row_bands = rowsFound; stats.vias_in_pad_row_band = bandHits;
}

// ---------------------------------------------------------------- 27. mechanical keep-outs (review issue 17)
// params.mechanical_keepouts = [{ "refs": ["H5", ...] | "pattern": "H*", "radius_mm": 3.0, "layers": ["F.Cu", "B.Cu"] | "all" }]
// Any track or via of a net other than the footprint's own pad nets within radius_mm of the footprint origin on the
// listed layers -> FAIL 'mech-keepout' (copper edge to centre; through vias are on every layer). Zone fills are not
// checked here (use rule areas for those). A MountingHole* footprint with no entry -> INFO.
{
  const mk = Array.isArray(params.mechanical_keepouts) ? params.mechanical_keepouts : [];
  let hits = 0; const covered = new Set();
  const refOf = f => (kids(f, 'property').find(p => p[1] === 'Reference') || [])[2] || '?';
  for (const e of mk) {
    const re = e.pattern ? compilePattern(e.pattern) : null; const refs = new Set(e.refs || []); const radius = Number(e.radius_mm) || 0;
    const lay = (!e.layers || e.layers === 'all') ? null : [].concat(e.layers);
    for (const f of fps) {
      const ref = refOf(f); if (!(refs.has(ref) || (re && re.test(ref)))) continue;
      covered.add(ref);
      const at = kid(f, 'at'); const cx = at[1], cy = at[2]; const own = (fpInfo[ref] || {}).nets || new Set();
      for (const s of segs) {
        if (lay && !lay.includes(s.layer)) continue; if (own.has(s.net)) continue;
        const d = distPtSeg(cx, cy, s) - s.w / 2;
        if (d < radius - 1e-6) { hits++; FAIL('mech-keepout', `track ${netName(s.net)} (${s.layer}) ${r6(Math.max(0, d))} mm from ${ref}'s centre, inside its ${radius} mm mechanical keep-out @ ${r6(s.x1)},${r6(s.y1)} -> ${r6(s.x2)},${r6(s.y2)} (review issue 17)`); }
      }
      for (const v of vias) {
        if (lay && (v.blind || v.micro) && !v.layers.some(l => lay.includes(l))) continue; // through vias are on every layer if (own.has(v.net)) continue;
        const d = Math.hypot(v.x - cx, v.y - cy) - (v.size || 0) / 2;
        if (d < radius - 1e-6) { hits++; FAIL('mech-keepout', `via ${netName(v.net)} @ ${v.x},${v.y} ${r6(Math.max(0, d))} mm from ${ref}'s centre, inside its ${radius} mm mechanical keep-out (review issue 17)`); }
      }
    }
  }
  // 1.25.0 (L24): a footprint that carries its own keep-out (a rule area forbidding tracks, e.g. KO_MECH written by
  // mounting_hole_fp.py) is covered: KiCad's DRC and the Specctra export enforce it, so it needs no params entry.
  const ownKo = f => kids(f, 'zone').some(z => { const k = kid(z, 'keepout'); return k && kids(k, 'tracks').some(t => t[1] === 'not_allowed'); });
  const carried = fps.filter(f => /MountingHole/i.test(String(f[1])) && !covered.has(refOf(f)) && ownKo(f)).map(refOf);
  for (const r of carried) covered.add(r);
  if (carried.length) INFO('mech-keepout', `${carried.length} mounting-hole footprint(s) carry their own keep-out rule area (checked by KiCad DRC): ${carried.slice(0, 12).join(', ')}${carried.length > 12 ? '…' : ''}`);
  const unlisted = fps.filter(f => /MountingHole/i.test(String(f[1])) && !covered.has(refOf(f))).map(refOf);
  if (unlisted.length) INFO('mech-keepout', `${unlisted.length} mounting-hole footprint(s) have no mechanical_keepouts entry in project params (contact diameter + 0.5 mm, review issue 17): ${unlisted.slice(0, 12).join(', ')}${unlisted.length > 12 ? '…' : ''}`);
  stats.mechanical_keepouts = { entries: mk.length, footprints: covered.size, violations: hits, mounting_holes_unlisted: unlisted.length, mounting_holes_own_keepout: carried.length };
}

// ---------------------------------------------------------------- 28. 3D models (review issue 20)
// Every footprint carries a (model ...) unless it matches params.models_not_needed — either an array of glob
// patterns (tested against reference, library id and footprint name) or { "libs": [...], "refs": [...] }.
// Default: libs MountingHole*, Fiducial*, TestPoint*, *Logo* / *logo* / *LOGO*, Symbol*; refs H*, FID*, TP*, LOGO*;
// board_only footprints are exempt too. A model path using ${KIPRJMOD} (or a plain relative path) whose file does
// not exist -> FAIL; library-variable paths (${KICADn_3DMODEL_DIR}) are not resolved and only counted. A model
// whose file name ends in _approx -> INFO listing the approximate models (they belong in the release note).
{
  const dflt = { libs: ['MountingHole*', 'Fiducial*', 'TestPoint*', '*Logo*', '*logo*', '*LOGO*', 'Symbol*'], refs: ['H*', 'FID*', 'TP*', 'LOGO*'] };
  const mnn = params.models_not_needed;
  const cfg = Array.isArray(mnn) ? { libs: mnn, refs: mnn } : Object.assign({}, dflt, mnn || {});
  const libRe = (cfg.libs || []).map(compilePattern), refRe = (cfg.refs || []).map(compilePattern);
  const boardDir = path.dirname(path.resolve(pcbPath));
  let missing = 0, missingFile = 0, unresolved = 0, exempt = 0, libChecked = 0; const approx = [];
  for (const f of fps) {
    const ref = (kids(f, 'property').find(p => p[1] === 'Reference') || [])[2] || '?'; const lib = String(f[1]); const fpName = lib.replace(/^[^:]*:/, '');
    const attr = kid(f, 'attr') || [];
    const models = kids(f, 'model');
    if (!models.length) {
      if (attr.includes('board_only') || libRe.some(re => re.test(lib) || re.test(fpName)) || refRe.some(re => re.test(ref))) { exempt++; continue; }
      missing++; FAIL('model', `${ref} (${lib}) has no 3D model — fetch one (KiCad library, EasyEDA by LCSC code, manufacturer) or build an approximate *_approx model; list exemptions in models_not_needed (review issue 20)`);
      continue;
    }
    for (const m of models) {
      const mp = String(m[1]);
      if (/_approx\.[a-z0-9]+$/i.test(mp) || /_approx$/i.test(mp)) approx.push(`${ref}: ${path.basename(mp)}`);
      let resolved = null;
      if (mp.includes('${KIPRJMOD}') || mp.includes('$(KIPRJMOD)')) resolved = mp.replace(/\$\{KIPRJMOD\}|\$\(KIPRJMOD\)/g, boardDir);
      else if (!/\$\{|\$\(/.test(mp)) resolved = path.isAbsolute(mp) ? mp : path.join(boardDir, mp);
      else {
        // ${KICADn_3DMODEL_DIR}: from the environment, else the default install location of KiCad n; unresolved -> counted only.
        const m2 = mp.match(/^\$\{(KICAD(\d+)_3DMODEL_DIR)\}(.*)$/);
        const base = m2 && (process.env[m2[1]] || [`C:/Program Files/KiCad/${m2[2]}.0/share/kicad/3dmodels`, `/usr/share/kicad/${m2[2]}.0/3dmodels`, `/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels`].find(d => { try { return fs.existsSync(d); } catch (e) { return false; } }));
        if (!base) { unresolved++; continue; }
        resolved = path.join(base, m2[3]); libChecked++;
      }
      if (!fs.existsSync(resolved)) { missingFile++; FAIL('model', `${ref}: 3D model file not found: ${mp} (review issue 20)`); }
    }
  }
  if (approx.length) INFO('model', `${approx.length} approximate 3D model(s) (*_approx, list them in the release note): ${approx.join(', ')}`);
  stats.models = { missing, missing_file: missingFile, library_paths_checked: libChecked, library_paths_unchecked: unresolved, exempt, approximate: approx.length };
}

// ---------------------------------------------------------------- 29. pin-array routing (review issue 21)
// Inside the courtyard box of a footprint whose copper pads form a full regular grid of >= 2 x 3 pins at a uniform
// pitch (THT connectors, DIP, headers; SMD arrays only with params.pin_array.include_smd = true), a segment of any net
// whose part inside the box is diagonal (in the footprint frame) and longer than one pin pitch -> FAIL 'pin-array':
// tracks in an array run orthogonally on the channel centrelines, 45 deg corners only at the turns.
// 1.24.0 (L21, second half): an orthogonal run inside the array with pads of the array on both sides within one pitch
// and a channel wider than the between-pads limit (1.5 mm; narrower gaps are section 16's) must sit on the channel
// centreline: its clearances to the nearest pad on each side match within 0.02 mm, else FAIL 'pin-array' "off-centre".
// The message has the between-pads form, so center_gaps_safe.py / centre_gated.py centre it.
{
  const includeSmd = (params.pin_array || {}).include_smd === true;
  // Diagonal length limit as a fraction of the pin pitch (default 1.0 = the review's rule; 0.5 also catches the
  // pad-to-channel 45 deg legs of a square grid).
  const diagFrac = typeof (params.pin_array || {}).max_diagonal_pitch_fraction === 'number' ? params.pin_array.max_diagonal_pitch_fraction : 0.5; // 1.20.0: half a pitch (Celso, 2026-10-20) - the J1 escape diagonals of ServiceOne are 0.7 pitch
  let arrays = 0, hits = 0, offCentre = 0;
  for (const [ref, list] of padsByRef) {
    const cu = list.filter(hasCuG); if (cu.length < 6) continue;
    if (!includeSmd && !cu.every(p => p.type === 'thru_hole')) continue;
    const ux = [...new Set(cu.map(p => Math.round(p.lx * 100)))].sort((a, b) => a - b), uy = [...new Set(cu.map(p => Math.round(p.ly * 100)))].sort((a, b) => a - b);
    const nx = ux.length, ny = uy.length;
    if (cu.length !== nx * ny || Math.min(nx, ny) < 2 || Math.max(nx, ny) < 3) continue;
    const uni = arr => { const d = arr.slice(1).map((v, i) => v - arr[i]); return d.every(x => Math.abs(x - d[0]) <= 2) ? d[0] / 100 : null; };
    const px = uni(ux), py = uni(uy); if (px === null || py === null) continue;
    const pitch = Math.min(px, py);
    const f = fpInfo[ref] && fpInfo[ref].block; if (!f) continue;
    const pts = [];
    for (const g of ['fp_line', 'fp_rect', 'fp_poly'].flatMap(t => kids(f, t)).filter(g => /CrtYd$/.test(String(val(g, 'layer'))))) {
      const a = kid(g, 'start'), b = kid(g, 'end'); if (a) pts.push([a[1], a[2]]); if (b) pts.push([b[1], b[2]]);
      const pn = kid(g, 'pts'); if (pn) for (const xy of pn.slice(1)) if (Array.isArray(xy)) pts.push([xy[1], xy[2]]);
    }
    let bx0, by0, bx1, by1;
    if (pts.length) { bx0 = Math.min(...pts.map(p => p[0])); bx1 = Math.max(...pts.map(p => p[0])); by0 = Math.min(...pts.map(p => p[1])); by1 = Math.max(...pts.map(p => p[1])); }
    else { bx0 = ux[0] / 100 - 0.5 - pitch / 2; bx1 = ux[nx - 1] / 100 + 0.5 + pitch / 2; by0 = uy[0] / 100 - 0.5 - pitch / 2; by1 = uy[ny - 1] / 100 + 0.5 + pitch / 2; }
    arrays++;
    const q0 = cu[0]; const R = Math.hypot(bx1 - bx0, by1 - by0);
    for (const s of outerSegs) {
      if (distPtSeg(q0.fx, q0.fy, s) > R) continue;
      const [a1, b1] = toFpLocal(q0, s.x1, s.y1), [a2, b2] = toFpLocal(q0, s.x2, s.y2);
      let ang = Math.abs(Math.atan2(b2 - b1, a2 - a1) * 180 / Math.PI) % 90; ang = Math.min(ang, 90 - ang);
      if (ang < 0.5) {
        const c0 = segClip(a1, b1, a2, b2, bx0, by0, bx1, by1); if (!c0 || (c0[1] - c0[0]) * s.len <= 0.5 * pitch) continue;
        if (cu.some(p => insidePad(p, s.x1, s.y1).inside || insidePad(p, s.x2, s.y2).inside)) continue;
        const ux_ = (s.x2 - s.x1) / s.len, uy_ = (s.y2 - s.y1) / s.len, nx_ = -uy_, ny_ = ux_;
        const best = [null, null];
        for (const p of cu) {
          const t = (p.x - s.x1) * ux_ + (p.y - s.y1) * uy_; if (t < 0 || t > s.len) continue;
          const d = (p.x - s.x1) * nx_ + (p.y - s.y1) * ny_; if (Math.abs(d) < 1e-6 || Math.abs(d) > pitch + 1e-6) continue;
          const k = d > 0 ? 0 : 1, clr = Math.abs(d) - padReachG(p, nx_, ny_) - s.w / 2;
          if (!best[k] || clr < best[k].clr) best[k] = { p, clr };
        }
        if (!best[0] || !best[1] || best[0].clr + best[1].clr + s.w <= 1.5 + 1e-6) continue;
        if (Math.abs(best[0].clr - best[1].clr) > 0.02 + 1e-9) {
          offCentre++;
          FAIL('pin-array', `${netName(s.net)} runs between pads ${ref}-${best[0].p.num} / ${ref}-${best[1].p.num} off-centre: ${r6(best[0].clr)} mm vs ${r6(best[1].clr)} mm (must match within 0.02 mm) @ ${r6(s.x1)},${r6(s.y1)} (${s.layer}) — on the channel centreline of ${ref}'s pin array (review issue 21; center_gaps_safe.py centres it)`);
        }
        continue;
      }
      const c = segClip(a1, b1, a2, b2, bx0, by0, bx1, by1); if (!c) continue;
      const inside = (c[1] - c[0]) * s.len;
      if (inside > diagFrac * pitch + 1e-6) { hits++; FAIL('pin-array', `${netName(s.net)} runs diagonally ${r6(inside)} mm through ${ref}'s pin array (pitch ${r6(pitch)} mm) @ ${r6(s.x1)},${r6(s.y1)} -> ${r6(s.x2)},${r6(s.y2)} (${s.layer}) — route orthogonally on the channel centrelines (review issue 21)`); }
    }
  }
  stats.pin_arrays = arrays; stats.pin_array_diagonals = hits; stats.pin_array_off_centre = offCentre;
}

// ---------------------------------------------------------------- 30. plane plan (L23, review issue 13)
// Power planes are planned, not taken as given: params.plane_plan (written by scripts/plane_plan.py after the designer
// decides) declares the main plane of each inner layer and the islands cut into it. Island zones on the board are ordinary
// copper zones (net = rail, layer = island layer), matched to a plan island by zone name (= island name) when the zone is
// named, else by (net, layer). Without plane_plan the main plane of each inner layer is the net of its largest zone and
// GND is never split. Not covered yet: min_neck_mm (narrow plane pieces) and sense-net vias on an island.
{
  const pp = params.plane_plan || {};
  const islandsPlan = Array.isArray(pp.islands) ? pp.islands.filter(i => i && typeof i === 'object') : [];
  const neverSplit = new Set(Array.isArray(pp.never_split) ? pp.never_split : ['GND']);
  const gapTable = (Array.isArray(pp.gap_by_voltage) && pp.gap_by_voltage.length ? pp.gap_by_voltage
    : [{ max_v: 5, gap_mm: 0.3 }, { max_v: 30, gap_mm: 0.5 }, { max_v: 60, gap_mm: 1.0 }, { max_v: 1000, gap_mm: 2.0 }]).slice().sort((a, b) => a.max_v - b.max_v);
  const isInner = l => /^In\d+\.Cu$/.test(l);
  const zLayers = z => kid(z, 'layers') ? kid(z, 'layers').slice(1).filter(x => typeof x === 'string') : [val(z, 'layer')].filter(Boolean);
  const zPoly = z => (kid(kid(z, 'polygon') || [], 'pts') || []).slice(1).filter(p => Array.isArray(p) && p[0] === 'xy').map(p => [p[1], p[2]]);
  const polyArea = pts => { let a = 0; for (let i = 0; i < pts.length; i++) { const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length]; a += x1 * y2 - x2 * y1; } return Math.abs(a) / 2; };
  const inPoly = (pts, x, y) => { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const [xi, yi] = pts[i], [xj, yj] = pts[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; };
  // Segment AB vs segment CD: proper crossing (a track ending exactly on the boundary is not counted).
  const orient = (px, py, qx, qy, rx, ry) => Math.sign((qx - px) * (ry - py) - (qy - py) * (rx - px));
  const segX = (ax, ay, bx, by, cx, cy, dx, dy) => {
    const o1 = orient(ax, ay, bx, by, cx, cy), o2 = orient(ax, ay, bx, by, dx, dy), o3 = orient(cx, cy, dx, dy, ax, ay), o4 = orient(cx, cy, dx, dy, bx, by);
    return o1 * o2 < 0 && o3 * o4 < 0;
  };
  const crossesPoly = (pts, s) => { for (let i = 0; i < pts.length; i++) { const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length]; if (segX(s.x1, s.y1, s.x2, s.y2, x1, y1, x2, y2)) return true; } return false; };
  // "+24V" -> 24, "+3.3V" -> 3.3, "3V3" -> 3.3, "-24V" -> 24; no digit-V pattern -> null.
  const voltFromName = n => { const m = /(\d+)(?:[.,](\d+))?V(\d+)?/i.exec(String(n || '')); if (!m) return null; return Number(m[1] + '.' + (m[2] || m[3] || '0')); };
  const gapFor = v => { for (const g of gapTable) if (v <= g.max_v + 1e-9) return g.gap_mm; return gapTable.length ? gapTable[gapTable.length - 1].gap_mm : null; };
  // Copper zones on inner layers, one entry per zone and layer.
  const innerZ = [];
  for (const z of kids(pcb, 'zone')) {
    if (kid(z, 'keepout') || !zoneNet(z)) continue;
    for (const l of zLayers(z)) if (isInner(l)) innerZ.push({ z, layer: l, net: zoneNet(z), name: val(z, 'name'), pts: zPoly(z) });
  }
  // Main plane per inner layer: plane_plan.main_planes first, else the net with the largest zone area on the layer.
  const main = {};
  for (const [l, list] of groupBy(innerZ, e => e.layer)) {
    const area = {}; for (const e of list) area[e.net] = (area[e.net] || 0) + polyArea(e.pts);
    main[l] = Object.entries(area).sort((a, b) => b[1] - a[1])[0][0];
  }
  for (const [l, n] of Object.entries(pp.main_planes || {})) if (typeof n === 'string' && n && !l.startsWith('_')) main[l] = n;
  // Physical copper order (F.Cu, In1..InN, B.Cu) and the signal layers facing an island layer: the nearest layer above and
  // below, unless that layer carries a main plane (it shields the island). 4 layers: In1 -> F.Cu, In2 -> B.Cu.
  const rank = x => x === 'F.Cu' ? -1 : x === 'B.Cu' ? 1e6 : Number((/^In(\d+)/.exec(x) || [0, 1e5])[1]);
  const order = (stats.copper_layers || []).slice().sort((a, b) => rank(a) - rank(b));
  const adjSignal = l => { const i = order.indexOf(l); if (i < 0) return []; return [order[i - 1], order[i + 1]].filter(x => x && !main[x]); };
  // Board zone -> plan island: by zone name when the zone is named, else by (net, layer).
  const byName = new Map(islandsPlan.filter(i => i.name).map(i => [i.name, i]));
  const matchIsland = e => {
    if (e.name) { const isl = byName.get(e.name); return isl && (!isl.layer || isl.layer === e.layer) ? isl : null; }
    return islandsPlan.find(i => i.rail === e.net && i.layer === e.layer) || null;
  };
  const st = { main_planes: main, islands_declared: islandsPlan.length, islands_found: 0, islands_missing: 0, undeclared: 0, never_split: 0, crossings: 0, gap_fails: 0, gap_unchecked: 0, thin_islands: 0, served: {} };
  const found = new Map(); // plan island -> board zone entries
  for (const e of innerZ) {
    const m = main[e.layer]; if (e.net === m) continue;
    const zt = `zone ${e.net}${e.name ? ` "${e.name}"` : ''} on ${e.layer}`;
    // Check 2 - never split: any zone of another net on a layer whose main plane is in never_split (default GND) -> FAIL,
    // declared island or not.
    if (neverSplit.has(m)) { st.never_split++; FAIL('plane-plan', `${zt} splits the ${m} plane — ${m} is never split (L23); put the island on a power layer`); }
    const isl = matchIsland(e);
    if (isl) { if (!found.has(isl)) found.set(isl, []); found.get(isl).push(e); continue; }
    // Check 1 - undeclared island on a power layer -> WARN (on a never-split layer the FAIL above already reports it).
    if (!neverSplit.has(m)) { st.undeclared++; WARN('plane-plan', `undeclared plane island: ${zt} (main plane ${m}) — plan it (L23): declare it in plane_plan.islands (scripts/plane_plan.py)`); }
  }
  for (const isl of islandsPlan) {
    const tag = `island ${isl.name || '(unnamed)'} (${isl.rail} on ${isl.layer})`;
    const ents = found.get(isl) || [];
    // Check 1 (cont.) - a declared island with no zone on the board -> WARN.
    if (!ents.length) { st.islands_missing++; WARN('plane-plan', `${tag} is declared in plane_plan but has no zone on the board — draw it (zone name "${isl.name || ''}", net ${isl.rail}, layer ${isl.layer})`); }
    else st.islands_found++;
    // Outline for checks 3 and 5: the board zone(s), else the plan outline (lets the plan be checked before it is drawn).
    const polys = ents.length ? ents.map(e => e.pts).filter(p => p.length >= 3)
      : (Array.isArray(isl.outline) && isl.outline.length >= 3 ? [isl.outline.map(p => [Number(p[0]), Number(p[1])])] : []);
    const src = ents.length ? 'zone outline' : 'plan outline';
    // Check 3 - split crossing: a track on the facing signal layer that crosses the island boundary loses its continuous
    // return path -> WARN, one per (net, layer) with the count. Tracks of the island's own rail are skipped.
    if (polys.length) {
      const per = new Map();
      for (const l of adjSignal(isl.layer)) for (const s of segs) {
        if (s.layer !== l || s.len <= 0 || netName(s.net) === isl.rail) continue;
        if (!polys.some(p => crossesPoly(p, s))) continue;
        const k = `${netName(s.net)}\u0000${l}`; if (!per.has(k)) per.set(k, { n: 0, s }); per.get(k).n++;
      }
      for (const [k, v] of per) { const [n, l] = k.split('\u0000'); st.crossings += v.n; WARN('plane-plan', `${n} on ${l} crosses the boundary of ${tag} ${v.n}x (${src}; first @ ${r6(v.s.x1)},${r6(v.s.y1)} -> ${r6(v.s.x2)},${r6(v.s.y2)}) — route away from the split or add a stitching capacitor (L23)`); }
    }
    // Check 4 - gap by voltage: the island zone clearance must reach island.gap_mm, else gap_by_voltage for voltage_v,
    // else gap_by_voltage for the voltage in the rail name; none of these -> INFO, not checked.
    if (ents.length) {
      let need = typeof isl.gap_mm === 'number' ? isl.gap_mm : null, why = 'plan gap_mm';
      if (need === null) {
        const v = typeof isl.voltage_v === 'number' ? Math.abs(isl.voltage_v) : voltFromName(isl.rail);
        if (v !== null) { need = gapFor(v); why = `${v} V per gap_by_voltage`; }
      }
      if (need === null) { st.gap_unchecked++; INFO('plane-plan', `${tag}: no gap_mm, voltage_v or voltage in the rail name — gap not checked`); }
      else for (const e of ents) {
        const cp = kid(e.z, 'connect_pads') || []; let clr = val(cp, 'clearance'); if (typeof clr !== 'number') clr = val(e.z, 'clearance');
        if (typeof clr !== 'number' || clr < need - 1e-9) { st.gap_fails++; FAIL('plane-plan', `${tag}: zone clearance ${typeof clr === 'number' ? clr : '(none)'} mm is below the required gap ${need} mm (${why}) — raise the zone clearance (L23)`); }
      }
    }
    // Check 5 - an island earns its split only if it serves at least 2 pads of its rail (pad centre inside the outline).
    if (polys.length) {
      const served = (padsByNetName.get(isl.rail) || []).filter(p => hasCuG(p) && polys.some(pl => inPoly(pl, p.x, p.y)));
      st.served[isl.name || `${isl.rail}@${isl.layer}`] = served.map(p => `${p.ref}.${p.num}`);
      if (served.length < 2) { st.thin_islands++; WARN('plane-plan', `${tag} serves ${served.length} pad${served.length === 1 ? '' : 's'} of ${isl.rail} (${src}) — an island needs at least 2; drop or enlarge it (L23)`); }
    }
  }
  INFO('plane-plan', `main planes ${Object.entries(main).map(([l, n]) => `${l}=${n}`).join(', ') || '(none)'}; ${islandsPlan.length} island(s) declared, ${st.islands_found} found on the board, ${st.islands_missing} missing${params.plane_plan ? '' : ' (no plane_plan in project params: defaults)'}`);
  stats.plane_plan = st;
}

// ---------------------------------------------------------------- 31. fan-out pattern (L22, review issue 19)
// For the pad rows of U*/IC* parts (as section 26: >= 6 copper pads, rows of >= 3 equal pads at a uniform pitch, not one
// pad number): a track that leaves a pin straight along the row's outward axis and then bends is a fan-out track. The
// tracks of one row that bend the same way form a group; their first bends must lie on one line across the row (the
// distance from the pad centre to the bend within 0.1 mm), which also makes the parallel runs equally spaced. A group of
// >= 2 tracks with a larger spread -> WARN 'fan-out'. fanout_regularise.py aligns them.
{
  let groupsSeen = 0, unaligned = 0;
  for (const [ref, list] of padsByRef) {
    if (!/^(U|IC)\d/.test(ref)) continue;
    const cu = list.filter(hasCuG); if (cu.length < 6) continue;
    const ext = p => (Math.round(p.lrot) % 180 === 90) ? [p.h, p.w] : [p.w, p.h];
    for (const axis of ['x', 'y']) {
      const cAt = p => axis === 'x' ? p.lx : p.ly, along = p => axis === 'x' ? p.ly : p.lx;
      for (const [, g] of groupBy(cu, p => { const [ex, ey] = ext(p); return Math.round(cAt(p) * 100) + '|' + Math.round(ex * 1000) + '|' + Math.round(ey * 1000); })) {
        if (g.length < 3 || new Set(g.map(p => p.num)).size === 1) continue;
        g.sort((a, b) => along(a) - along(b));
        const gaps = g.slice(1).map((p, i) => along(p) - along(g[i]));
        if (gaps.some(d => Math.abs(d - gaps[0]) > 0.02) || gaps[0] > 2.6 || gaps[0] < 0.1) continue;
        const c = cAt(g[0]); const [ex, ey] = ext(g[0]); if (Math.abs(c) <= (axis === 'x' ? ex : ey) / 2 + 1e-6) continue;
        const sg = Math.sign(c), groups = new Map();
        for (const p of g) {
          for (const s of segEnds.get(key(p.x, p.y)) || []) {
            if (s.net !== p.net) continue;
            const start = key(s.x1, s.y1) === key(p.x, p.y);
            const [fx, fy] = start ? [s.x2, s.y2] : [s.x1, s.y1];
            const [l0x, l0y] = toFpLocal(p, p.x, p.y), [l1x, l1y] = toFpLocal(p, fx, fy);
            const dA = axis === 'x' ? l1x - l0x : l1y - l0y, dS = axis === 'x' ? l1y - l0y : l1x - l0x;
            if (dA * sg <= 0 || Math.abs(dS) > 1e-3) continue;              // not an axial outward exit
            const fk = key(fx, fy); if (viaMap.has(fk) || padMap.has(fk)) continue;
            const nxt = (segEnds.get(fk) || []).filter(t => t !== s && t.layer === s.layer); if (nxt.length !== 1) continue;
            const t = nxt[0], tStart = key(t.x1, t.y1) === fk;
            const [gx, gy] = tStart ? [t.x2, t.y2] : [t.x1, t.y1];
            const [m1x, m1y] = toFpLocal(p, gx, gy);
            const eA = axis === 'x' ? m1x - l1x : m1y - l1y, eS = axis === 'x' ? m1y - l1y : m1x - l1x;
            if (Math.abs(eS) < 1e-6) continue;                                // no bend
            const dir = Math.round(Math.atan2(eS, eA * sg) * 180 / Math.PI);
            const gk = s.layer + '|' + dir;
            if (!groups.has(gk)) groups.set(gk, []);
            groups.get(gk).push({ p, D: Math.abs(dA) });
          }
        }
        for (const [gk, items] of groups) {
          if (items.length < 2) continue;
          groupsSeen++;
          const Ds = items.map(i => i.D), spread = Math.max(...Ds) - Math.min(...Ds);
          if (spread > 0.1 + 1e-6) {
            unaligned++;
            const pins = items.map(i => i.p.num).join(', ');
            WARN('fan-out', `fan-out of ${ref} (pins ${pins}, ${gk.split('|')[0]}): the first bends lie ${+Math.min(...Ds).toFixed(3)} to ${+Math.max(...Ds).toFixed(3)} mm from the pad centres — align them on one line per side so the parallel runs are equally spaced (review issue 19; fanout_regularise.py)`);
          }
        }
      }
    }
  }
  stats.fanout_groups = groupsSeen; stats.fanout_unaligned = unaligned;
}

// ---------------------------------------------------------------- 32. acute joints (1.27.0, ServiceOne rev. 0.2 review of D133)
// No turn sharper than 90 degrees: at every point where tracks of one net meet on one layer, two neighbouring
// branches must be >= 90 degrees apart. Section 3 counts a 135-degree turn (interior 45) as a mitre, so before 1.27.0
// nothing caught it. Pad centres and vias are exempt: several entries meet there by design.
{
  let acute = 0;
  const byPt = new Map();
  for (const s of segs) {
    if (s.len === 0) continue;
    for (const [x, y, ox, oy] of [[s.x1, s.y1, s.x2, s.y2], [s.x2, s.y2, s.x1, s.y1]]) {
      const k = s.net + '|' + s.layer + '|' + key(x, y);
      if (!byPt.has(k)) byPt.set(k, { x, y, net: s.net, layer: s.layer, dirs: [] });
      byPt.get(k).dirs.push(Math.atan2(oy - y, ox - x) * 180 / Math.PI);
    }
  }
  for (const pt of byPt.values()) {
    if (pt.dirs.length < 2) continue;
    const pk = key(pt.x, pt.y);
    if (viaMap.has(pk) || (padMap.get(pk) || []).some(p => padLayerOk(p, pt.layer))) continue;
    const d = pt.dirs.map(a => ((a % 360) + 360) % 360).sort((a, b) => a - b);
    let min = 360;
    for (let i = 0; i < d.length; i++) { const g = (i + 1 < d.length ? d[i + 1] : d[0] + 360) - d[i]; if (g < min) min = g; }
    if (min < 90 - 0.01) {
      acute++;
      FAIL('acute', `acute joint on ${netName(pt.net)} @ ${pt.x},${pt.y} (${pt.layer}): ${r6(min)}° between two branches (${pt.dirs.length} track ends) — no turn sharper than 90°, re-route the corner as two 45° bends`);
    }
  }
  stats.acute_joints = acute;
}

// ---------------------------------------------------------------- 33. orthogonal-first routing (1.28.0, L41, ServiceOne review issue 22)
// Tracks run horizontal or vertical; a 45-degree segment is a corner chamfer or a short link. A 45-degree segment
// longer than params.routing_style.diagonal_max_mm (default 3 mm) outside the fan-out zone of an IC -> WARN
// 'diagonal': long diagonals cut the board into triangles where no via, part or shoved track fits later. Exempt: nets
// listed in routing_style.diagonal_exceptions (fan-out escapes, datasheet loops, clock / analog lines where length
// matters - record the reason beside the entry), and the part of a segment inside an IC's fan-out zone (the pad
// bounding box of a U* / IC* part with >= 6 copper pads, grown by routing_style.fanout_zone_mm, default 1.5 mm).
// Pin arrays are section 29's (a stricter limit). INFO: the share of track length that is diagonal, per layer.
{
  const rs = params.routing_style || {};
  const maxD = typeof rs.diagonal_max_mm === 'number' ? rs.diagonal_max_mm : 3;
  const zoneMm = typeof rs.fanout_zone_mm === 'number' ? rs.fanout_zone_mm : 1.5;
  const exempt = new Set(Array.isArray(rs.diagonal_exceptions) ? rs.diagonal_exceptions.map(e => (e && typeof e === 'object') ? e.net : e) : []);
  const zones = [];
  for (const [ref, list] of padsByRef) {
    if (!/^(U|IC)\d/.test(ref)) continue;
    const cu = list.filter(hasCuG); if (cu.length < 6) continue;
    zones.push([Math.min(...cu.map(p => p.x - p.w / 2)) - zoneMm, Math.min(...cu.map(p => p.y - p.h / 2)) - zoneMm,
                Math.max(...cu.map(p => p.x + p.w / 2)) + zoneMm, Math.max(...cu.map(p => p.y + p.h / 2)) + zoneMm]);
  }
  const perLayer = {};
  let long = 0;
  for (const s of segs) {
    if (s.len === 0) continue;
    const L = perLayer[s.layer] || (perLayer[s.layer] = { total: 0, diag: 0 });
    L.total += s.len;
    let ang = Math.abs(Math.atan2(s.y2 - s.y1, s.x2 - s.x1) * 180 / Math.PI) % 90;
    if (Math.abs(ang - 45) > 1) continue;
    L.diag += s.len;
    if (s.len <= maxD + 1e-6 || exempt.has(netName(s.net))) continue;
    let inZone = 0;
    for (const z of zones) { const c = segClip(s.x1, s.y1, s.x2, s.y2, z[0], z[1], z[2], z[3]); if (c) inZone = Math.max(inZone, (c[1] - c[0]) * s.len); }
    const outside = s.len - inZone;
    if (outside <= maxD + 1e-6) continue;
    long++;
    WARN('diagonal', `${netName(s.net)} runs ${r6(outside)} mm at 45° @ ${r6(s.x1)},${r6(s.y1)} -> ${r6(s.x2)},${r6(s.y2)} (${s.layer}), over the ${maxD} mm limit — route horizontal / vertical with 45° corners, or list the net in routing_style.diagonal_exceptions with its reason (L41, review issue 22)`);
  }
  for (const [layer, L] of Object.entries(perLayer).sort()) {
    if (L.total > 0) INFO('diagonal', `${layer}: ${Math.round(L.diag / L.total * 100)} % of the track length is diagonal (${r6(L.diag)} of ${r6(L.total)} mm)`);
  }
  stats.long_diagonals = long;
}

// ---------------------------------------------------------------- report
const byLevel = cnt(findings.map(f => f.level));
const report = { board: path.basename(pcbPath), skill_version: gold ? gold._meta.skill_version : 'unknown', date: new Date().toISOString(), summary: byLevel, stats, findings };
if (jsonOut) fs.writeFileSync(jsonOut, JSON.stringify(report, null, 2));
if (!quiet) {
  console.log(`KiCad golden audit ${report.skill_version} — ${report.board}   params: ${stats.project_params}`);
  console.log(`FAIL ${byLevel.FAIL || 0}   WARN ${byLevel.WARN || 0}   INFO ${byLevel.INFO || 0}`);
  // rev K: a passing board still produces hundreds of findings, and the numbers that decide whether
  // it can be manufactured were buried in a single-line JSON dump. Lead with those; the full stats
  // object stays in --json for tooling.
  const kv = (k, v) => v === undefined ? null : `${k}=${v}`;
  console.log('key:', [
    kv('segments', stats.segments), kv('vias', stats.vias), kv('arcs', stats.arcs),
    kv('off_lattice', stats.off_lattice_segments), kv('inner_tracks', stats.inner_layer_segments),
    kv('keepouts', stats.keepout_zones), kv('power_rails', stats.power_rails),
    kv('unclassed_rails', stats.power_rails_unclassed), kv('dead_rules', stats.rules_matching_nothing),
  ].filter(Boolean).join('  '));
  const show = (lvl, perCheck) => {
    const l = findings.filter(f => f.level === lvl); if (!l.length) return;
    console.log(`\n--- ${lvl} (${l.length}) ---`);
    const groups = {}; for (const f of l) (groups[f.check] = groups[f.check] || []).push(f);
    for (const [check, list] of Object.entries(groups).sort((a, b) => b[1].length - a[1].length)) {
      console.log(`[${check}] ${list.length}`);
      for (const f of list.slice(0, perCheck)) console.log(`    ${f.msg}`);
      if (list.length > perCheck) console.log(`    … ${list.length - perCheck} more (see --json)`);
    }
  };
  show('FAIL', 40); show('WARN', 8); show('INFO', 3);
  // rev K: say plainly what blocks and what is only advice, so a 100-WARN pass is still readable.
  {
    const blockers = {};
    for (const f of findings) if (f.level === 'FAIL') blockers[f.check] = (blockers[f.check] || 0) + 1;
    const warnTop = {};
    for (const f of findings) if (f.level === 'WARN') warnTop[f.check] = (warnTop[f.check] || 0) + 1;
    console.log('\n--- VERDICT ---');
    if (Object.keys(blockers).length) {
      console.log('  BLOCKING: ' + Object.entries(blockers).sort((a, b) => b[1] - a[1])
        .map(([k, v]) => `${k} (${v})`).join(', '));
    } else {
      console.log('  nothing blocks: 0 FAIL');
    }
    if (stats.power_rails_unclassed) {
      console.log(`  !! ${stats.power_rails_unclassed} current-carrying rail(s) on Default — run scripts/netclass_propose.py --apply`);
    }
    if (stats.rules_matching_nothing) {
      console.log(`  !! ${stats.rules_matching_nothing} configured rule(s) match no net — they audit nothing`);
    }
    const adv = Object.entries(warnTop).sort((a, b) => b[1] - a[1]).slice(0, 4);
    if (adv.length) console.log('  advice (WARN): ' + adv.map(([k, v]) => `${k} ${v}`).join(', ')
      + (Object.keys(warnTop).length > 4 ? `, +${Object.keys(warnTop).length - 4} more` : ''));
  }
  console.log(`\nresult: ${(byLevel.FAIL || 0) ? 'FAIL' : 'PASS'} (exit ${(byLevel.FAIL || 0) ? 1 : 0})`);
}
process.exit((byLevel.FAIL || 0) > 0 ? 1 : 0);
