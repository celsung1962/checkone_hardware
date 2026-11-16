#!/usr/bin/env node
/*
 * apply_settings.js — merges golden_settings.json into a target .kicad_pro.
 *
 * Usage:
 *   node apply_settings.js <path/to/project.kicad_pro> [--dry-run] [--no-bom] [--no-erc] [--no-schematic]
 *
 * What it replaces (whole-object replace, so the result equals the golden block):
 *   board.design_settings.{defaults, rule_severities, rules, teardrop_options,
 *                          teardrop_parameters, tuning_pattern_settings,
 *                          diff_pair_dimensions, track_widths, via_dimensions,
 *                          zones_allow_external_fillets}
 *   erc.{pin_map, rule_severities}                  (skip with --no-erc)
 *   net_settings.classes  -> golden Default class only; other classes are KEPT
 *   schematic.{annotate_start_num, annotation, bom_export_filename,
 *              bom_fmt_settings, bom_settings, connection_grid_size, drawing}
 *                                                    (bom_* skipped with --no-bom; the whole block with
 *                                                     --no-schematic; an existing connection_grid_size is kept)
 * Merged, not replaced (1.18.0): via_dimensions and track_widths (union of template and project);
 *   rule_severities.unconnected_items is never lowered below a project 'error'.
 * What it never touches: drc_exclusions, layer presets, libraries, meta, cvpcb,
 *   ipc2581, pcbnew paths, sheet/text variables.
 * Approved rule deviations (board review rev. 0.2, D110): `approved_rule_deviations` in kicad_golden.project.json
 *   beside the .kicad_pro, e.g. {"min_hole_clearance": {"value": 0.2, "reason": "D110 ..."}}, are put back into
 *   board.design_settings.rules AFTER the template and the fabricator profile, and printed. A deviation below the
 *   fabricator's absolute minimum (profile absolute_min, else its kicad_rules value) is refused: nothing is written,
 *   exit 3. Without --fab the project's recorded `fabricator` block is read for that check and left untouched.
 * Economical via tier (issue 11): with --fab on a profile that has economical_via_drill_mm (JLCPCB 4L/6L: 0.2 mm;
 *   0.15 mm costs extra) the small predefined via inserted is economical_via_diameter_mm / economical_via_drill_mm
 *   (0.45 / 0.2) instead of the profile minimum (0.25 / 0.15); netclass via drills below the tier are reported.
 *   --fine-vias keeps the minimum and records fabricator.fine_vias_approved = true. The tier is recorded as
 *   fabricator.economical_via_drill_mm (the audit reads it).
 * A backup <name>.kicad_pro.bak-<timestamp> is written before saving.
 * Close the project in KiCad before running; KiCad overwrites .kicad_pro on exit.
 */
'use strict';
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const target = args.find(a => !a.startsWith('--'));
if (!target || !fs.existsSync(target) || !/\.kicad_pro$/i.test(target)) {
  console.error('usage: node apply_settings.js <project.kicad_pro> [--dry-run] [--no-bom] [--no-erc] [--no-schematic] [--fab F --layers N --copper W [--fab-exact] [--fine-vias]]');
  process.exit(2);
}
const dry = args.includes('--dry-run'), noBom = args.includes('--no-bom'), noErc = args.includes('--no-erc');
const noSch = args.includes('--no-schematic');
const opt = n => (args.includes(n) ? args[args.indexOf(n) + 1] : null);
// Fabricator profile (mandatory pre-routing gate, see SKILL.md): --fab jlcpcb --layers 4 --copper 1oz [--fab-exact]
const fabName = opt('--fab'), fabLayers = opt('--layers'), fabCopper = opt('--copper'), fabExact = args.includes('--fab-exact');
const fineVias = args.includes('--fine-vias');
if ((fabName || fabLayers || fabCopper) && !(fabName && fabLayers && fabCopper)) { console.error('--fab, --layers and --copper must be given together (e.g. --fab jlcpcb --layers 4 --copper 1oz)'); process.exit(2); }
let fabProfile = null, fabData = null;
if (fabName) {
  const fp = path.join(__dirname, '..', 'fabricators', fabName.toLowerCase() + '.json');
  if (!fs.existsSync(fp)) { console.error(`unknown fabricator "${fabName}" (no ${fp})`); process.exit(2); }
  fabData = JSON.parse(fs.readFileSync(fp, 'utf8'));
  const key = `${fabLayers}L-${fabCopper.toLowerCase()}`; fabProfile = fabData.profiles[key];
  if (!fabProfile) { console.error(`no profile "${key}" in ${fp}; available: ${Object.keys(fabData.profiles).join(', ')}`); process.exit(2); }
}
// Per-project parameters beside the .kicad_pro: approved rule deviations and the recorded fabricator block.
const paramsPath = path.join(path.dirname(target), 'kicad_golden.project.json');
let paramsIn = {};
if (fs.existsSync(paramsPath)) {
  try { paramsIn = JSON.parse(fs.readFileSync(paramsPath, 'utf8')); } catch (e) { console.error(`cannot parse ${paramsPath}: ${e.message}`); process.exit(2); }
}
const devIn = paramsIn.approved_rule_deviations || {};
for (const [k, v] of Object.entries(devIn)) {
  if (!k.startsWith('_') && !(v && typeof v.value === 'number')) { console.error(`approved_rule_deviations.${k}: needs {"value": <number>, "reason": "..."}`); process.exit(2); }
}
const deviations = Object.entries(devIn).filter(([k]) => !k.startsWith('_'));
// The absolute minimum a deviation may reach: the active profile's absolute_min, else its kicad_rules value. Without
// --fab: the project's recorded fabricator block (read only, never rewritten) and the profile file it names.
let recordedProfile = null;
if (!fabProfile && paramsIn.fabricator && paramsIn.fabricator.profile) {
  const fname = String(paramsIn.fabricator.name || '').split(/\s+/)[0].toLowerCase();
  const fp = fname && path.join(__dirname, '..', 'fabricators', fname + '.json');
  const file = fp && fs.existsSync(fp) ? JSON.parse(fs.readFileSync(fp, 'utf8')) : null;
  const prof = file && file.profiles[paramsIn.fabricator.profile];
  recordedProfile = { label: `${paramsIn.fabricator.name || fname} (recorded in kicad_golden.project.json)`,
    absolute_min: Object.assign({}, (prof && prof.absolute_min) || {}, paramsIn.fabricator.absolute_min || {}),
    kicad_rules: Object.assign({}, (prof && prof.kicad_rules) || {}, paramsIn.fabricator.kicad_rules || {}) };
}
const limitProfile = fabProfile ? { label: `${fabName} ${fabLayers}L ${fabCopper}`, absolute_min: fabProfile.absolute_min || {}, kicad_rules: fabProfile.kicad_rules } : recordedProfile;
const absMin = k => {
  if (!limitProfile) return undefined;
  const a = limitProfile.absolute_min[k];
  return typeof a === 'number' ? a : limitProfile.kicad_rules[k];
};
{
  const below = deviations.filter(([k, v]) => typeof absMin(k) === 'number' && v.value < absMin(k) - 1e-9);
  if (below.length) {
    console.error(`REFUSED: approved_rule_deviations below the ${limitProfile.label} absolute minimum (nothing written):`);
    for (const [k, v] of below) console.error(`  ${k} = ${v.value} < ${absMin(k)}  (${v.reason || 'no reason given'})`);
    process.exit(3);
  }
}
// Economical via tier (issue 11). Only with a profile that defines it; --fine-vias or a recorded approval keeps the minimum.
const ecoDrill = fabProfile && typeof fabProfile.economical_via_drill_mm === 'number' ? fabProfile.economical_via_drill_mm : null;
const fineApproved = fineVias || !!(paramsIn.fabricator && paramsIn.fabricator.fine_vias_approved);
const useEco = ecoDrill !== null && !fineApproved;
const gold = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'golden_settings.json'), 'utf8'));
const pro = JSON.parse(fs.readFileSync(target, 'utf8'));
const changes = [];
const APPROVED_DOC = 'Approved deviations from the template / fabricator rules (board review rev. 0.2, D110): {"<design_settings.rules key>": {"value": <mm>, "reason": "<decision id and why>"}}. apply_settings.js puts them back after applying the profile and refuses any below the fabricator absolute minimum. Starts empty.';
const set = (obj, keyPath, value) => {
  const parts = keyPath.split('.'); let o = obj;
  for (const p of parts.slice(0, -1)) { if (typeof o[p] !== 'object' || o[p] === null) o[p] = {}; o = o[p]; }
  const last = parts[parts.length - 1];
  if (JSON.stringify(o[last]) !== JSON.stringify(value)) { changes.push(keyPath); o[last] = JSON.parse(JSON.stringify(value)); }
};

const gds = gold.board.design_settings;
// 1.18.0: keep what a whole-object replace would silently lose (found routing ServiceOne, playbook 22 item 5):
//  - predefined via sizes and track widths are MERGED (union), so project vias such as 0.45/0.15 survive;
//  - unconnected_items is never lowered below the project's 'error': a board with open connections must fail DRC.
const prevDs = JSON.parse(JSON.stringify((pro.board && pro.board.design_settings) || {}));
for (const k of Object.keys(gds)) {
  if (k === 'via_dimensions' || k === 'track_widths') continue;
  set(pro, `board.design_settings.${k}`, gds[k]);
}
{
  const ds = pro.board.design_settings;
  const vkey = v => `${v.diameter}/${v.drill}`;
  const vias = new Map();
  for (const v of [...(gds.via_dimensions || []), ...(prevDs.via_dimensions || [])]) vias.set(vkey(v), { diameter: v.diameter, drill: v.drill });
  const vm = [...vias.values()].sort((a, b) => a.diameter - b.diameter || a.drill - b.drill);
  if (JSON.stringify(vm) !== JSON.stringify(prevDs.via_dimensions)) changes.push('board.design_settings.via_dimensions (merged with the project sizes)');
  ds.via_dimensions = vm;
  const tw = [...new Set([...(gds.track_widths || []), ...(prevDs.track_widths || [])])].sort((a, b) => a - b);
  if (JSON.stringify(tw) !== JSON.stringify(prevDs.track_widths)) changes.push('board.design_settings.track_widths (merged with the project widths)');
  ds.track_widths = tw;
  const prevUnc = prevDs.rule_severities && prevDs.rule_severities.unconnected_items;
  if (prevUnc === 'error' && ds.rule_severities && ds.rule_severities.unconnected_items !== 'error') {
    ds.rule_severities.unconnected_items = 'error';
    console.log('kept: rule_severities.unconnected_items = error (the template value would hide open connections)');
  }
}

// Fabricator enforcement: every KiCad rule must be at least as strict as the fabricator minimum.
// Default = stricter of (golden template, fabricator limit). --fab-exact = fabricator limit wherever the template is stricter
// (use only when the user explicitly wants to exploit the fabricator's full capability, e.g. 0.15 mm via drill on JLCPCB 4-layer).
const fabEnforced = [];
if (fabProfile) {
  const rules = pro.board.design_settings.rules;
  for (const [k, lim] of Object.entries(fabProfile.kicad_rules)) {
    const cur = rules[k]; let next;
    if (cur === undefined) next = lim;
    else if (/^(max_error|min_resolved_spokes)$/.test(k)) next = cur;
    // Rule Harmonization (rev D): min_through_hole_diameter EQUALS the profile value, never exceeds it.
    // A rule stricter than a netclass via drill turns every via in that class into a DRC error against our own board.
    else if (k === 'min_through_hole_diameter') next = lim;
    // High-Density Via Allowance (rev H, 2026-09-18): on 4-layer and denser builds the fabricator's
    // via diameter / annular limits REPLACE the golden defaults rather than being max()'d with them.
    // The golden 0.45 mm / 0.10 mm cannot be placed beside fine-pitch pads (DFN/QFN 0.4-0.5 mm pitch),
    // so plane-stitching vias there are forced sub-minimum and every one becomes a self-inflicted
    // DRC error. JLCPCB builds 0.25 / 0.05 on 4L+ as a standard service. 2-layer is unaffected: its
    // own profile limit (0.5 / 0.1) is stricter and still wins through the max() below.
    else if (fabProfile.layers >= 4 && /^(min_via_diameter|min_via_annular_width)$/.test(k)) next = lim;
    else next = fabExact ? lim : Math.max(cur, lim);
    if (next !== cur) { rules[k] = next; changes.push(`board.design_settings.rules.${k} (${fabName} ${fabLayers}L ${fabCopper}: ${cur} → ${next})`); }
    fabEnforced.push([k, lim, rules[k]]);
  }
  // High-Density Via Allowance (rev H): make the profile's minimum via a predefined size on 4L+, so a
  // legitimately placed stitching via is not reported by kicad_audit.js as "matches neither its
  // netclass nor a predefined via size".
  if (fabProfile.layers >= 4) {
    const vd = pro.board.design_settings.via_dimensions = pro.board.design_settings.via_dimensions || [];
    // Issue 11 (2026-10-20): the small via is the ECONOMICAL one (0.45 / 0.2 on JLCPCB 4L/6L) unless --fine-vias.
    const d = useEco ? Math.max(fabProfile.economical_via_diameter_mm || 0.45, fabProfile.kicad_rules.min_via_diameter) : fabProfile.kicad_rules.min_via_diameter;
    const dr = useEco ? ecoDrill : fabProfile.kicad_rules.min_through_hole_diameter;
    if (!vd.some(v => Math.abs(v.diameter - d) < 1e-9 && Math.abs(v.drill - dr) < 1e-9)) {
      const at = (vd.length && vd[0].diameter === 0) ? 1 : 0;
      vd.splice(at, 0, { diameter: d, drill: dr });
      changes.push(`board.design_settings.via_dimensions[${d}/${dr}] (added, ${fabName} ${fabLayers}L ${useEco ? 'economical tier' : 'high-density allowance'})`);
    }
    if (useEco) {
      const fine = vd.filter(v => v.diameter > 0 && v.drill < ecoDrill - 1e-9);
      if (fine.length) console.log(`note: predefined via(s) ${fine.map(v => `${v.diameter}/${v.drill}`).join(', ')} have a drill below the ${fabName} economical tier ${ecoDrill} mm (extra charge); kept because the project defines them - remove them, or pass --fine-vias to approve`);
    }
  }
  // via annular sanity: template via classes must respect the profile
  for (const c of gold.net_settings.classes) if (c.via_drill && c.via_drill < fabProfile.kicad_rules.min_through_hole_diameter) console.log(`note: netclass ${c.name} via drill ${c.via_drill} is below the ${fabName} minimum ${fabProfile.kicad_rules.min_through_hole_diameter}`);
}
if (!noErc) { set(pro, 'erc.pin_map', gold.erc.pin_map); set(pro, 'erc.rule_severities', gold.erc.rule_severities); }

// netclasses (review Q-04): every template class is inserted or replaced by name; classes the
// project defines beyond the template are kept. Template name patterns are added when absent;
// existing project patterns are kept (a project may route its own buses to its own classes).
pro.net_settings = pro.net_settings || {};
const classes = Array.isArray(pro.net_settings.classes) ? pro.net_settings.classes : [];
for (const gc of gold.net_settings.classes) {
  const idx = classes.findIndex(c => c.name === gc.name);
  if (idx < 0) { classes.push(JSON.parse(JSON.stringify(gc))); changes.push(`net_settings.classes[${gc.name}] (added)`); }
  else if (JSON.stringify(classes[idx]) !== JSON.stringify(gc)) { classes[idx] = JSON.parse(JSON.stringify(gc)); changes.push(`net_settings.classes[${gc.name}]`); }
}
// Default first, then by priority
classes.sort((a, b) => (a.name === 'Default' ? -1 : b.name === 'Default' ? 1 : (a.priority ?? 0) - (b.priority ?? 0)));
pro.net_settings.classes = classes;

// Rule Harmonization (rev D), second half: the merge above restores template drills, so raise any class
// via drill that sits below the active profile minimum (e.g. JLCPCB 2-layer needs 0.30, template ships 0.15).
if (fabProfile) {
  const minDrill = fabProfile.kicad_rules.min_through_hole_diameter;
  const minDia = minDrill + 2 * fabProfile.kicad_rules.min_via_annular_width;
  for (const c of pro.net_settings.classes) {
    if (c.via_drill && c.via_drill < minDrill) {
      changes.push(`net_settings.classes[${c.name}].via_drill (${fabName} ${fabLayers}L minimum: ${c.via_drill} → ${minDrill})`);
      c.via_drill = minDrill;
    }
    // Issue 11: a class drill below the economical tier is manufacturable but charged extra. Netclasses are the
    // template's (the audit compares them with it), so this is reported, not changed; the audit FAILs the vias.
    if (useEco && c.via_drill && c.via_drill < ecoDrill - 1e-9)
      console.log(`note: netclass ${c.name} via drill ${c.via_drill} is below the ${fabName} economical tier ${ecoDrill} mm (extra charge) - set it to ${ecoDrill} or pass --fine-vias to approve`);
    if (c.via_diameter && c.via_diameter < minDia) {
      const d = Math.round(minDia * 1000) / 1000;
      changes.push(`net_settings.classes[${c.name}].via_diameter (annular ring: ${c.via_diameter} → ${d})`);
      c.via_diameter = d;
    }
  }
}
const pats = Array.isArray(pro.net_settings.netclass_patterns) ? pro.net_settings.netclass_patterns : [];
for (const gp of gold.net_settings.netclass_patterns || []) {
  if (!pats.some(p => p.pattern === gp.pattern)) { pats.push({ netclass: gp.netclass, pattern: gp.pattern }); changes.push(`net_settings.netclass_patterns[${gp.pattern} → ${gp.netclass}] (added)`); }
}
pro.net_settings.netclass_patterns = pats;
if (pro.net_settings.netclass_assignments === undefined) pro.net_settings.netclass_assignments = null;
if (!pro.net_settings.meta) pro.net_settings.meta = { version: 5 };

for (const k of Object.keys(gold.schematic)) {
  if (noSch) break;
  if (noBom && /^bom_/.test(k)) continue;
  // 1.18.0: the connection grid is a drawing decision of the project, not a board rule - keep the project's
  if (k === 'connection_grid_size' && pro.schematic && pro.schematic.connection_grid_size !== undefined) continue;
  set(pro, `schematic.${k}`, gold.schematic[k]);
}

// Approved rule deviations (D110): the template and the fabricator profile have been applied; put the project's
// recorded decisions back (already checked against the absolute minimum above).
const keptDeviations = [];
if (deviations.length) {
  const rules = pro.board.design_settings.rules = pro.board.design_settings.rules || {};
  for (const [k, v] of deviations) {
    const before = rules[k];
    if (before !== v.value) { rules[k] = v.value; changes.push(`board.design_settings.rules.${k} (approved deviation: ${before} → ${v.value})`); }
    keptDeviations.push([k, v]);
  }
}

if (fabProfile) {
  console.log(`fabricator ${fabData.fabricator} profile ${fabLayers}L-${fabCopper} (captured ${fabData.captured}) — rule = ${fabExact ? 'fabricator limit' : 'stricter of template/limit'}:`);
  for (const [k, lim, v] of fabEnforced) console.log(`  ${k.padEnd(32)} limit ${String(lim).padEnd(6)} → rule ${v}`);
  if (fabProfile.stackup) console.log(`  stackup: ${fabProfile.stackup.order.join(' | ')}; copper outer ${fabProfile.stackup.outer_copper_um} µm, inner ${fabProfile.stackup.inner_copper_um} µm`);
  for (const n of fabProfile.notes || []) console.log(`  note: ${n}`);
}
for (const [k, v] of keptDeviations) console.log(`kept approved deviation: ${k} = ${v.value}${typeof absMin(k) === 'number' ? ` (absolute minimum ${absMin(k)})` : ''} - ${v.reason || 'no reason given'}`);
if (!fabProfile && recordedProfile) console.log(`fabricator block in kicad_golden.project.json left untouched (${recordedProfile.label}); pass --fab/--layers/--copper to re-apply the profile`);
if (!changes.length && !fabProfile) { console.log('already golden — nothing to change'); process.exit(0); }
if (changes.length) { console.log(`${dry ? '[dry-run] would change' : 'changed'} ${changes.length} settings blocks:`); for (const c of changes) console.log('  ' + c); }
else console.log('settings already golden; fabricator profile recorded only');
if (dry) process.exit(0);
if (changes.length) {
  const bak = `${target}.bak-${new Date().toISOString().replace(/[:.]/g, '-')}`;
  fs.copyFileSync(target, bak);
  fs.writeFileSync(target, JSON.stringify(pro, null, 2) + '\n');
  console.log(`saved ${target}\nbackup ${bak}`);
}
// Record the fabricator decision in the per-project parameter file so the audit enforces it from now on.
if (fabProfile) {
  let params = {}; if (fs.existsSync(paramsPath)) params = JSON.parse(fs.readFileSync(paramsPath, 'utf8'));
  else { const tpl = path.join(__dirname, '..', 'templates', 'kicad_golden.project.json'); if (fs.existsSync(tpl)) { params = JSON.parse(fs.readFileSync(tpl, 'utf8')); params.length_groups = []; params.diff_pairs = { rules: [] }; params.via_in_pad = { allowed_refs: [] }; params.project = path.basename(target, '.kicad_pro'); } }
  params.fabricator = Object.assign({}, params.fabricator || {}, {
    name: `${fabData.fabricator} ${fabLayers}-layer ${fabCopper}`, profile: `${fabLayers}L-${fabCopper.toLowerCase()}`, layers: Number(fabLayers), copper: fabCopper, captured: fabData.captured,
    min_hole_to_hole_mm: fabProfile.kicad_rules.min_hole_to_hole, min_via_drill_mm: fabProfile.kicad_rules.min_through_hole_diameter, min_copper_to_edge_mm: fabProfile.kicad_rules.min_copper_edge_clearance,
    inner_copper_um: fabProfile.stackup ? fabProfile.stackup.inner_copper_um : undefined, outer_copper_um: fabProfile.stackup ? fabProfile.stackup.outer_copper_um : undefined,
    kicad_rules: fabProfile.kicad_rules, stackup_order: fabProfile.stackup ? fabProfile.stackup.order : undefined,
    economical_via_drill_mm: ecoDrill !== null ? ecoDrill : fabProfile.kicad_rules.min_through_hole_diameter,
    fine_vias_approved: fineApproved,
  });
  if (fabProfile.absolute_min) params.fabricator.absolute_min = Object.fromEntries(Object.entries(fabProfile.absolute_min).filter(([k]) => !k.startsWith('_')));
  if (params.approved_rule_deviations === undefined) params.approved_rule_deviations = { _doc: APPROVED_DOC };
  fs.writeFileSync(paramsPath, JSON.stringify(params, null, 2) + '\n');
  console.log(`fabricator profile written to ${paramsPath}`);
}
