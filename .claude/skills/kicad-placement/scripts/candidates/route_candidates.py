"""Route placement candidates with Freerouting and score the routed boards.

Run with KiCad's Python:

    kicad-python route_candidates.py OUT_DIR --ids 02,09,01 [--baseline] [--passes 40] [--timeout 1800]

OUT_DIR is the folder written by run_placement.py. Each candidate board in
OUT_DIR/boards/cand_<id>/ is routed in place (route_freerouting.py keeps a
.bak_prerouting next to it). --baseline also routes a bare copy of the source board
(current placement, tracks removed) in OUT_DIR/boards/atual/, with the same budget, so
the candidates are compared with the manual placement on equal terms.

The routing itself is the kicad-routing skill's route_freerouting.py; this script only
runs the candidates side by side and collects the numbers into OUT_DIR/routing.json.
The boards are for comparison: no stitching, repair or audit is done here.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def routing_scripts():
    """kicad-routing scripts folder: $KICAD_ROUTING_SCRIPTS, else the sibling skill in the same skills folder as
    this one (the project's own copy), else ~/.claude/skills. The sibling comes first so the candidates are routed
    with the routing version the project carries, not an older global copy."""
    cands = [os.environ.get("KICAD_ROUTING_SCRIPTS", ""),
             os.path.join(HERE, "..", "..", "..", "kicad-routing", "scripts"),
             os.path.join(os.path.expanduser("~"), ".claude", "skills", "kicad-routing", "scripts")]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "route_freerouting.py")):
            return os.path.normpath(c)
    return None


SKILL = routing_scripts()
KICAD_CLI = os.path.join(os.path.dirname(sys.executable), "kicad-cli.exe")


def measure(board_path):
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    length = 0.0
    vias = 0
    segs = 0
    per_layer = {}
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            vias += 1
        else:
            segs += 1
            ln = t.GetLength() / 1e6
            length += ln
            name = b.GetLayerName(t.GetLayer())
            per_layer[name] = per_layer.get(name, 0.0) + ln
    return {"track_mm": round(length, 1), "vias": vias, "segments": segs,
            "per_layer_mm": {k: round(v, 1) for k, v in sorted(per_layer.items())}}


def prepare(board_path):
    """Make a candidate copy ready for the router: bare, and without placement rule
    areas. KiCad's Specctra export writes EVERY rule area as a full keepout, even one
    that forbids nothing, so a placement region left on the board closes its whole area
    to the router (measured on GapOne_CON: every net of the ISO_LOOP domain unrouted)."""
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    rooms = [z for z in b.Zones() if z.GetIsRuleArea() and z.GetPlacementAreaEnabled()
             and not (z.GetDoNotAllowTracks() or z.GetDoNotAllowVias() or z.GetDoNotAllowPads()
                      or z.GetDoNotAllowZoneFills() or z.GetDoNotAllowFootprints())]
    names = [z.GetZoneName() for z in rooms]
    tracks = list(b.GetTracks())
    for z in rooms:
        b.Delete(z)
    for t in tracks:
        b.Delete(t)
    pcbnew.SaveBoard(board_path, b)
    return names, len(tracks)


def drc(board_path, out_json):
    cmd = [KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-all", "--output", out_json, board_path]
    subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(out_json):
        return None
    with open(out_json, encoding="utf-8") as fh:
        d = json.load(fh)
    by = {}
    for v in d.get("violations", []):
        key = "%s:%s" % (v.get("severity", "?"), v.get("type", "?"))
        by[key] = by.get(key, 0) + 1
    return {"unconnected": len(d.get("unconnected_items", [])),
            "errors": sum(n for k, n in by.items() if k.startswith("error:")),
            "warnings": sum(n for k, n in by.items() if k.startswith("warning:")),
            "by_type": dict(sorted(by.items(), key=lambda kv: -kv[1]))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--ids", required=True, help="comma-separated candidate ids, e.g. 02,09,01")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--passes", type=int, default=40)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=1, help="boards routed at the same time")
    ap.add_argument("--score-only", action="store_true", help="do not route; only measure the boards")
    a = ap.parse_args()
    if not SKILL:
        sys.exit("kicad-routing skill not found: install it next to kicad-placement (.claude/skills/kicad-routing) "
                 "or in ~/.claude/skills, or set KICAD_ROUTING_SCRIPTS to its scripts folder")
    print(f"kicad-routing scripts: {SKILL}")

    out = os.path.abspath(a.out)
    with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
        summary = json.load(fh)
    src = summary["board"]
    stem = os.path.splitext(os.path.basename(src))[0]
    golden = os.path.join(os.path.dirname(src), "kicad_golden.project.json")

    jobs = []
    for cid in [s for s in a.ids.split(",") if s]:
        jobs.append({"id": cid, "dir": os.path.join(out, "boards", "cand_%s" % cid)})
    if a.baseline:
        bdir = os.path.join(out, "boards", "atual")
        if not os.path.exists(os.path.join(bdir, stem + ".kicad_pcb")):
            sys.path.insert(0, HERE)
            import apply_placement
            apply_placement.apply(src, {}, bdir)
        jobs.append({"id": "atual", "dir": bdir})

    for j in jobs:
        j["board"] = os.path.join(j["dir"], stem + ".kicad_pcb")
        if not os.path.exists(j["board"]):
            raise SystemExit("no board for candidate %s: %s" % (j["id"], j["board"]))
        if os.path.exists(golden):
            shutil.copy2(golden, os.path.join(j["dir"], "kicad_golden.project.json"))
        j["rdir"] = os.path.join(j["dir"], "route")
        os.makedirs(j["rdir"], exist_ok=True)

    if not a.score_only:
        for j in jobs:
            names, removed = prepare(j["board"])
            print("prepared %s: removed placement areas %s and %d old tracks" % (j["id"], names, removed), flush=True)
        # Freerouting is memory-hungry: four at once exhausted a 32 GB machine, so the
        # default is one board at a time.
        t0 = time.time()
        pending = list(jobs)
        running = []
        while pending or running:
            while pending and len(running) < a.parallel:
                j = pending.pop(0)
                cmd = [sys.executable, os.path.join(SKILL, "route_freerouting.py"), j["board"],
                       "--auto-clearance", "--auto-rules", "--passes", str(a.passes),
                       "--timeout", str(a.timeout), "--threads", str(a.threads), "--outdir", j["rdir"]]
                j["log"] = open(os.path.join(j["rdir"], "route.log"), "w", encoding="utf-8")
                j["t0"] = time.time()
                j["proc"] = subprocess.Popen(cmd, stdout=j["log"], stderr=subprocess.STDOUT)
                running.append(j)
                print("started %s" % j["id"], flush=True)
            time.sleep(5)
            for j in list(running):
                if j["proc"].poll() is not None:
                    j["secs"] = round(time.time() - j["t0"])
                    j["log"].close()
                    running.remove(j)
                    print("finished %s: exit %d after %ds" % (j["id"], j["proc"].returncode, j["secs"]), flush=True)
        print("routing done in %.0fs" % (time.time() - t0), flush=True)

    # keep the results of earlier runs for boards not handled this time
    results = []
    rpath = os.path.join(out, "routing.json")
    if os.path.exists(rpath):
        with open(rpath, encoding="utf-8") as fh:
            results = [r for r in json.load(fh) if r["id"] not in {j["id"] for j in jobs}]
    for j in jobs:
        r = {"id": j["id"], "board": j["board"]}
        if "proc" in j:
            r["router_exit"] = j["proc"].returncode
            r["router_seconds"] = j["secs"]
        rep = os.path.join(j["rdir"], "route_report.json")
        pr = subprocess.run([sys.executable, os.path.join(SKILL, "route_report.py"), j["board"], "--json", rep,
                             "--quiet"], capture_output=True, text=True)
        r["route_report_exit"] = pr.returncode
        if os.path.exists(rep):
            with open(rep, encoding="utf-8") as fh:
                r["route_report"] = json.load(fh)
        r.update(measure(j["board"]))
        r["drc"] = drc(j["board"], os.path.join(j["rdir"], "drc.json"))
        results.append(r)
        d = r["drc"] or {}
        print("%-6s vias %4d  track %7.0f mm  unconnected %s  drc errors %s" % (
            r["id"], r["vias"], r["track_mm"], d.get("unconnected"), d.get("errors")), flush=True)
    with open(os.path.join(out, "routing.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)


if __name__ == "__main__":
    main()
