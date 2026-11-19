"""Generate, score and compare placement candidates for a KiCad board.

Run with KiCad's Python:

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" run_placement.py BOARD.kicad_pcb --out OUT_DIR -n 12

Steps: extract model -> N annealing workers in parallel (different seeds and weight
profiles) -> score every candidate and the current placement the same way -> write
OUT_DIR/gallery.html, OUT_DIR/summary.json, and the top candidates as board copies in
OUT_DIR/boards/. The source board is never modified.
"""
import argparse
import html
import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import evaluate as ev  # noqa: E402
from place_core import PROFILES  # noqa: E402

ROWS = [
    ("index", "Índice (atual = 100)", "%.1f", True),
    ("mst", "Ratsnest (mm)", "%.0f", True),
    ("crossings", "Cruzamentos", "%d", True),
    ("cong_peak", "Pico de congestionamento", "%.0f", True),
    ("dec_mean", "Desacoplamento médio (mm)", "%.2f", True),
    ("dec_max", "Desacoplamento pior (mm)", "%.1f", True),
    ("clu_spread", "Dispersão dos grupos (mm)", "%.1f", True),
    ("gap_med", "Vão típico entre vizinhos (mm)", "%.2f", False),
    ("gap_tight", "Componentes com vizinho a menos de 0,3 mm", "%d", False),
    ("via_starved", "Pads de plano sem lugar para via", "%d", False),
    ("reg_viol", "Componentes fora da região", "%d", False),
    ("pp_viol", "Pares de pinos fora do limite", "%d", False),
    ("ov_pairs", "Sobreposições de courtyard", "%d", False),
    ("fb_area", "Área fora / em keep-out (mm²)", "%.1f", False),
]

CSS = """
:root{--bg:#f4f5f7;--card:#fff;--ink:#1c2330;--mute:#5d6878;--line:#d9dde4;--board:#eef1f4;
--edge:#3b4656;--good:#1a7f4b;--bad:#b3321f;--accent:#2f5fb3}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2128;--ink:#e6e9ee;--mute:#98a2b1;
--line:#2f3540;--board:#262b34;--edge:#aab4c3;--good:#5fcf92;--bad:#ff8a75;--accent:#8fb2f2}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.45 system-ui,"Segoe UI",sans-serif}
header{padding:20px 24px 8px}h1{margin:0 0 4px;font-size:20px}
header p{margin:2px 0;color:var(--mute);max-width:980px}
.bar{display:flex;flex-wrap:wrap;gap:14px 22px;align-items:center;padding:8px 24px 14px}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px}.legend span{display:inline-flex;align-items:center;gap:6px;color:var(--mute)}
.legend i{width:12px;height:12px;border-radius:2px;display:inline-block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;padding:0 24px 32px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.card.base{border-color:var(--accent);border-width:2px}
.card h2{margin:0;padding:10px 12px 6px;font-size:15px;display:flex;justify-content:space-between;gap:8px}
.card h2 small{font-weight:400;color:var(--mute)}
.card .pic{cursor:zoom-in;padding:0 8px}
svg.board{display:block;width:100%;height:auto}
.outline{fill:var(--board);stroke:var(--edge);stroke-width:.35}
.keepout{fill:rgba(200,60,40,.18);stroke:#c83c28;stroke-width:.25;stroke-dasharray:1 .7}
.region{fill:rgba(47,95,179,.07);stroke:var(--accent);stroke-width:.3;stroke-dasharray:1.6 .8}
.region.excl{fill:rgba(160,90,200,.10);stroke:#a05ac8;stroke-width:.45;stroke-dasharray:none}
.fp{stroke:rgba(0,0,0,.45);stroke-width:.08;fill-opacity:.85}
.fp.fixed{stroke:var(--ink);stroke-width:.4}
.fp.back{fill-opacity:.35;stroke-dasharray:.5 .4}
.fp.clash{stroke:#e0102a;stroke-width:.45}
.pin{fill:var(--ink);opacity:.55}
svg.board text{text-anchor:middle;dominant-baseline:central;fill:#111;font-family:system-ui,sans-serif;pointer-events:none}
.rats line{stroke:var(--ink);stroke-width:.09;opacity:.5}
body.norats .rats{display:none}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
td{padding:3px 12px;border-top:1px solid var(--line)}td+td{text-align:right}
td.d{width:70px;color:var(--mute)}td.good{color:var(--good)}td.bad{color:var(--bad)}
tr.idx td{font-weight:600}
.note{padding:6px 12px 10px;color:var(--mute);font-size:12.5px}
.warn{color:var(--bad)}
dialog{border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);padding:10px;width:min(96vw,96vh)}
dialog::backdrop{background:rgba(0,0,0,.6)}dialog h3{margin:2px 6px 8px;font-size:15px}
"""

JS = """
const dlg=document.querySelector('dialog');
document.querySelectorAll('.pic').forEach(p=>p.addEventListener('click',()=>{
  dlg.querySelector('h3').textContent=p.dataset.title;
  dlg.querySelector('div').innerHTML=p.innerHTML;dlg.showModal();}));
dlg.addEventListener('click',()=>dlg.close());
document.querySelector('#rats').addEventListener('change',e=>document.body.classList.toggle('norats',!e.target.checked));
"""


def run_workers(model_path, jobs, out_dir, max_par):
    pending = list(jobs)
    running = []
    core = os.path.join(HERE, "place_core.py")
    while pending or running:
        while pending and len(running) < max_par:
            j = pending.pop(0)
            cmd = [sys.executable, core, model_path, j["file"], "--seed", str(j["seed"]),
                   "--profile", j["profile"], "--moves", str(j["moves"]), "--init", j["init"],
                   "--margin", str(j["margin"]), "--cluster", str(j["cluster"])]
            if j.get("init_file"):
                cmd += ["--init-file", j["init_file"]]
            running.append((j, subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)))
        time.sleep(0.5)
        for item in list(running):
            j, pr = item
            if pr.poll() is not None:
                out = pr.stdout.read().strip()
                print("  [%s] %s" % (j["id"], out.splitlines()[-1] if out else "(no output)"), flush=True)
                if pr.returncode != 0:
                    print(out, flush=True)
                    j["failed"] = True
                running.remove(item)


def add_constraints(model, board, a):
    """Constraints that come from outside the board file. Mutates the model."""
    import math
    from place_core import rot_pt
    comps = {c["ref"]: c for c in model["comps"]}

    # freeze: parts on the given nets stay where the source board has them. Use it for
    # a domain whose zones and keep-outs were drawn around its parts.
    frozen = []
    nets = {s.strip() for s in (a.freeze_nets or "").split(",") if s.strip()}
    refs = {s.strip() for s in (a.freeze or "").split(",") if s.strip()}
    for c in model["comps"]:
        if c["locked"]:
            continue
        if c["ref"] in refs or any(p["net"] in nets for p in c["pads"]):
            c["locked"] = True
            c["frozen"] = True
            frozen.append(c["ref"])

    pairs = []
    seen = set()

    def pad_xy(ref, num):
        c = comps[ref]
        for p in c["pads"]:
            if p["num"] == num:
                dx, dy = rot_pt(p["x"], p["y"], c["rot"])
                return c["x"] + dx, c["y"] + dy
        return None

    # datasheet decoupling entries recorded by the kicad-routing skill: THIS capacitor
    # pad at THAT pin. The limit is the placement rule, not the routed-length limit.
    golden = os.path.join(os.path.dirname(os.path.abspath(board)), "kicad_golden.project.json")
    n_dec = 0
    if os.path.exists(golden) and not a.no_layout_checks:
        with open(golden, encoding="utf-8") as fh:
            lc = json.load(fh).get("layout_checks", {})
        for e in lc.get("decoupling", []):
            pin, cap = e["pin"].rsplit(".", 1), e["cap"].rsplit(".", 1)
            if pin[0] in comps and cap[0] in comps:
                pairs.append({"a": pin, "b": cap, "max": min(float(e.get("max_mm", 3.5)), a.decoupling_mm),
                              "kind": "decoupling"})
                seen.add(frozenset((tuple(pin), tuple(cap))))
                n_dec += 1

    # pairs the source placement keeps tight on small signal nets: do not loosen them
    n_tight = 0
    if a.keep_tight > 0:
        nets_p = {}
        for c in model["comps"]:
            for p in c["pads"]:
                if p["net"]:
                    nets_p.setdefault(p["net"], []).append((c["ref"], p["num"]))
        import re
        skip = re.compile(r"GND|VSS|CHASSIS|EARTH|^[+-]\d|^\+|^V(CC|DD|BUS|BAT|IN)\b", re.I)
        for net, pl in nets_p.items():
            if len(pl) > 3 or skip.search(net) or net in model.get("plane_nets", []):
                continue
            for i in range(len(pl)):
                for j in range(i + 1, len(pl)):
                    if pl[i][0] == pl[j][0] or frozenset((pl[i], pl[j])) in seen:
                        continue
                    pa, pb = pad_xy(*pl[i]), pad_xy(*pl[j])
                    d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                    if d <= a.keep_tight:
                        pairs.append({"a": list(pl[i]), "b": list(pl[j]), "max": max(d * 1.25, 3.0),
                                      "kind": "tight"})
                        n_tight += 1
    model["pin_pairs"] = pairs
    print("restrições: %d desacoplamentos do datasheet, %d pares mantidos próximos, %d componentes congelados%s" % (
        n_dec, n_tight, len(frozen), (" (" + " ".join(sorted(frozen)) + ")") if frozen else ""), flush=True)


def describe(model):
    """Print how the placer understood the board's regions and clusters.
    Returns the number of problems that would make a run pointless."""
    from place_core import Problem
    P = Problem(model, margin=0.0)
    bad = 0
    regs = model.get("regions", [])
    kind_pt = {"sheet": "folha", "class": "classe", "group": "grupo"}
    print("regiões de placement: %d" % len(regs))
    info = {r["name"]: r for r in P.region_info}
    locked = {c["ref"] for c in model["comps"] if c["locked"]}
    for r in regs:
        anchors = [m for m in r["members"] if m in locked]
        where = "na placa (rígida%s)" % (", exclusiva" if r["exclusive"] else "") if r["onboard"] \
            else "fora da placa (só agrupamento)"
        print("  %-22s %s=%s  %d componentes, %d travados  %s" % (
            r["name"], kind_pt[r["kind"]], r["source"], len(r["members"]), len(anchors), where))
        if not r["members"]:
            bad += 1
            print("    PROBLEMA: nenhum componente corresponde a esta origem")
        i = info.get(r["name"])
        if i and i["need"] > 0.85 * i["area"]:
            bad += 1
            print("    PROBLEMA: área livre %.0f mm² para %.0f mm² de componentes (lado único); aumente a região" % (
                i["area"], i["need"]))
        elif i:
            print("    área livre %.0f mm², componentes %.0f mm² (%.0f%% de ocupação)" % (
                i["area"], i["need"], 100.0 * i["need"] / i["area"] if i["area"] else 0))
    for note in P.region_notes:
        print("  aviso: " + note)
    mv, lk = P.region_viol()
    if lk:
        print("  aviso: travados que violam uma região e não serão movidos: %s" % ", ".join(lk))
    if regs:
        print("  no placement atual, %d componentes livres estão fora da sua região" % len(mv))
    anch = sum(1 for mem in P.clusters if any(P.fixed[i] for i in mem))
    print("grupos pelo esquemático: %d (%d ancorados em travados), %d componentes agrupados" % (
        len(P.clusters), anch, sum(len(m) for m in P.clusters)))
    return bad


def card(title, sub, svg, m, base, cls="", note=""):
    rows = []
    for key, label, fmt, compare in ROWS:
        v = m[key]
        d, dc = "", "d"
        if compare and base is not None and base[key]:
            pct = 100.0 * (v - base[key]) / base[key]
            d = "%+.0f%%" % pct
            dc = "d good" if pct < -0.5 else ("d bad" if pct > 0.5 else "d")
        rows.append('<tr class="%s"><td>%s</td><td>%s</td><td class="%s">%s</td></tr>' % (
            "idx" if key == "index" else "", label, fmt % v, dc, d))
    return ('<section class="card %s"><h2><span>%s</span><small>%s</small></h2>'
            '<div class="pic" data-title="%s">%s</div><table>%s</table>%s</section>') % (
        cls, html.escape(title), html.escape(sub), html.escape(title + " · " + sub), svg, "".join(rows),
        '<div class="note">%s</div>' % note if note else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--out", required=True)
    ap.add_argument("-n", type=int, default=12, help="candidates generated from scratch")
    ap.add_argument("--refine", type=int, default=1, help="extra candidates that start from the current placement")
    ap.add_argument("--moves", type=int, default=1500000)
    ap.add_argument("--profiles", default="balanced,wirelength,blocks,decoupling")
    ap.add_argument("--margin", default="auto",
                    help="gap kept between courtyards, mm; 'auto' (default) measures the gap the source "
                         "placement keeps (lower quartile of nearest-neighbour gaps, 0.15 to 0.6 mm)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--apply", type=int, default=3, help="write this many top candidates as board copies")
    ap.add_argument("--seed0", type=int, default=1)
    ap.add_argument("--cluster", type=float, default=1.0,
                    help="strength of schematic clustering: 0 off, 1 default, 2 tighter groups")
    ap.add_argument("--decoupling-mm", type=float, default=3.5,
                    help="straight-line limit for the datasheet decoupling pairs of kicad_golden.project.json")
    ap.add_argument("--no-layout-checks", action="store_true", help="ignore kicad_golden.project.json")
    ap.add_argument("--keep-tight", type=float, default=0.0,
                    help="pin pairs on 2-3 pin signal nets at most this far apart (mm) in the source "
                         "placement are not allowed to loosen; 0 = off")
    ap.add_argument("--freeze-nets", default="", help="parts on these nets keep their source position")
    ap.add_argument("--freeze", default="", help="references that keep their source position")
    ap.add_argument("--repair", default=None,
                    help="candidate JSON to repair: every job starts from it instead of from scratch")
    ap.add_argument("--check", action="store_true",
                    help="only read the board and report regions, anchors and clusters")
    ap.add_argument("--force", action="store_true", help="run even if a region looks wrong")
    ap.add_argument("--reuse", action="store_true",
                    help="keep candidate files that already exist; only re-score and rebuild the gallery")
    a = ap.parse_args()

    out = os.path.abspath(a.out)
    cdir = os.path.join(out, "candidates")
    os.makedirs(cdir, exist_ok=True)
    model_path = os.path.join(out, "model.json")

    import extract_model
    t0 = time.time()
    model = extract_model.extract(a.board)
    add_constraints(model, a.board, a)
    with open(model_path, "w", encoding="utf-8") as fh:
        json.dump(model, fh)
    n_all = len(model["comps"])
    n_lock = sum(1 for c in model["comps"] if c["locked"])
    print("model: %d footprints, %d locked, %d free" % (n_all, n_lock, n_all - n_lock), flush=True)
    if a.margin == "auto":
        from place_core import Problem
        g_med, g_q25, g_tight = ev.gap_stats(Problem(model, margin=0.0))
        a.margin = min(0.6, max(0.15, math.floor(g_q25 / 0.05 + 1e-6) * 0.05))
        print("margin auto: the source placement keeps %.2f mm between neighbours (median %.2f); using %.2f mm" % (
            g_q25, g_med, a.margin), flush=True)
    else:
        a.margin = float(a.margin)
    problems = describe(model)
    if a.check:
        return
    if problems and not a.force:
        raise SystemExit("regiões com problema (acima). Corrija no KiCad ou rode com --force.")

    profiles = [p for p in a.profiles.split(",") if p]
    for p in profiles:
        if p not in PROFILES:
            raise SystemExit("unknown profile %r (have %s)" % (p, ", ".join(sorted(PROFILES))))
    jobs = []
    if a.repair:
        for k in range(a.n):
            jobs.append({"id": "F%d" % (k + 1), "seed": a.seed0 + 2000 + k, "profile": profiles[k % len(profiles)],
                         "init": "file", "init_file": os.path.abspath(a.repair), "moves": a.moves,
                         "margin": a.margin})
    else:
        for k in range(a.n):
            jobs.append({"id": "%02d" % (k + 1), "seed": a.seed0 + k, "profile": profiles[k % len(profiles)],
                         "init": "random", "moves": a.moves, "margin": a.margin})
        for k in range(a.refine):
            jobs.append({"id": "R%d" % (k + 1), "seed": a.seed0 + 1000 + k, "profile": profiles[k % len(profiles)],
                         "init": "current", "moves": a.moves, "margin": a.margin})
    for j in jobs:
        j["file"] = os.path.join(cdir, "cand_%s.json" % j["id"])
        j["cluster"] = a.cluster
    todo = [j for j in jobs if not (a.reuse and os.path.exists(j["file"]))]
    print("annealing %d candidates (%d reused), %d at a time, %d moves each" % (
        len(todo), len(jobs) - len(todo), a.jobs, a.moves), flush=True)
    run_workers(model_path, todo, out, a.jobs)

    colors = ev.sheet_colors(model)
    base_m, base_d = ev.evaluate(model)
    base_m["index"] = 100.0
    cands = []
    for j in jobs:
        if j.get("failed") or not os.path.exists(j["file"]):
            continue
        with open(j["file"], encoding="utf-8") as fh:
            res = json.load(fh)
        m, d = ev.evaluate(model, res["placement"])
        m["index"] = ev.index(m, base_m)
        cands.append({"job": j, "res": res, "m": m, "d": d})
    # An overlap between two locked/frozen parts is inherited from the source board and is
    # the same in every candidate: it must not hide the candidates that have a defect of
    # their own (a part the engine could not legalise, a new overlap, a region broken).
    for c in cands:
        c["own_ov"] = c["m"]["ov_pairs"] - c["m"]["ov_fixed"]
        c["pending"] = c["own_ov"] > 0 or c["res"]["illegal_left"] > 0 or c["m"]["reg_viol"] > 0
    cands.sort(key=lambda c: (c["pending"], c["m"]["index"]))

    applied = {}
    if a.apply > 0:
        import apply_placement
        for c in cands[:a.apply]:
            bdir = os.path.join(out, "boards", "cand_%s" % c["job"]["id"])
            info = apply_placement.apply(a.board, c["res"]["placement"], bdir, model)
            applied[c["job"]["id"]] = info
            print("  board cand_%s: moved %d, pad check %.4f mm -> %s" % (
                c["job"]["id"], info["moved"], info["pad_error_mm"], info["board"]), flush=True)

    name = os.path.splitext(os.path.basename(a.board))[0]
    legend = "".join('<span><i style="background:%s"></i>%s</span>' % (col, html.escape(s.strip("/") or "raiz"))
                     for s, col in colors.items())
    cards = [card("Atual (manual)", "referência", ev.svg(model, base_d, colors), base_m, None, "base",
                  "Placement que está hoje na placa. Todos os outros são comparados com este.")]
    for rank, c in enumerate(cands, 1):
        j = c["job"]
        kind = {"random": "do zero", "current": "a partir do atual", "file": "reparo de candidato"}[j["init"]]
        note = []
        if c["own_ov"] > 0:
            note.append('<span class="warn">Ainda há sobreposição: não usar sem corrigir.</span>')
        elif c["res"]["illegal_left"]:
            note.append('<span class="warn">%d componente(s) sem o espaçamento pedido ou encostado em área '
                        'proibida: conferir antes de usar.</span>' % c["res"]["illegal_left"])
        if c["m"]["ov_fixed"]:
            note.append("%d sobreposição(ões) entre componentes travados, herdada(s) da placa de origem."
                        % c["m"]["ov_fixed"])
        if c["m"]["reg_viol"]:
            note.append('<span class="warn">Fora da região: %s.</span>' % html.escape(", ".join(c["m"]["reg_refs"][:12])))
        if j["id"] in applied:
            note.append("Placa gerada em boards/cand_%s" % j["id"])
        cards.append(card("#%d · candidato %s" % (rank, j["id"]),
                          "%s · %s · semente %d" % (j["profile"], kind, j["seed"]),
                          ev.svg(model, c["d"], colors), c["m"], base_m, "", " ".join(note)))
    page = ("<!doctype html><html lang='pt-br'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Placement %s</title><style>%s</style></head><body>"
            "<header><h1>Placement · %s</h1>"
            "<p>%d footprints, %d travados (contorno grosso) e %d livres. %d candidatos, ordenados pelo índice. "
            "Índice = 40%% ratsnest + 25%% cruzamentos + 15%% pico de congestionamento + 20%% desacoplamento, "
            "relativo ao placement atual (menor é melhor). Regiões de placement aparecem tracejadas em azul; "
            "as exclusivas (ISO_), em roxo. Clique numa placa para ampliar.</p></header>"
            "<div class='bar'><label><input type='checkbox' id='rats' checked> mostrar ratsnest</label>"
            "<div class='legend'>%s</div></div>"
            "<div class='grid'>%s</div><dialog><h3></h3><div></div></dialog><script>%s</script></body></html>") % (
        html.escape(name), CSS, html.escape(name), n_all, n_lock, n_all - n_lock, len(cands), legend,
        "".join(cards), JS)
    gallery = os.path.join(out, "gallery.html")
    with open(gallery, "w", encoding="utf-8") as fh:
        fh.write(page)

    summary = {
        "board": os.path.abspath(a.board), "baseline": base_m,
        "candidates": [{"id": c["job"]["id"], "profile": c["job"]["profile"], "init": c["job"]["init"],
                        "seed": c["job"]["seed"], "file": c["job"]["file"], "seconds": c["res"]["seconds"],
                        "illegal_left": c["res"]["illegal_left"], "metrics": c["m"],
                        "board": applied.get(c["job"]["id"], {}).get("board")} for c in cands],
        "seconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)

    print("\nbaseline  idx 100.0  mst %.0f  cross %d  cong %.0f  dec %.2f/%.1f  ov %d  fb %.1f" % (
        base_m["mst"], base_m["crossings"], base_m["cong_peak"], base_m["dec_mean"], base_m["dec_max"],
        base_m["ov_pairs"], base_m["fb_area"]))
    for c in cands:
        m = c["m"]
        print("cand %-3s %-10s %-7s idx %5.1f  mst %.0f  cross %d  cong %.0f  dec %.2f/%.1f  ov %d  fb %.1f" % (
            c["job"]["id"], c["job"]["profile"], c["job"]["init"], m["index"], m["mst"], m["crossings"],
            m["cong_peak"], m["dec_mean"], m["dec_max"], m["ov_pairs"], m["fb_area"]))
    print("\ngallery: %s  (%.0fs total)" % (gallery, summary["seconds"]))


if __name__ == "__main__":
    main()
