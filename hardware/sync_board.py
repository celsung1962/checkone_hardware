#!/usr/bin/env python3
"""
Bring hardware/CheckOne/CheckOne.kicad_pcb in line with the rev 1.1 schematic (the scripted "Update PCB from
Schematic" that kicad-cli 10 lacks), keeping S. Zimath's placement. Run with KiCad's Python after gen_checkone.py and
the netlist export:

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/sync_board.py [--dry-run]

For every part of hardware/CheckOne/CheckOne.net (matched by reference, the references are v1's):
  - every footprint is reloaded from its library (KiCad 10 standard or the project library), at the same position,
    rotation and side; that brings the rev 1.1 footprints in (D50 / D51 SOD-123, L1 / L2 maker's land, J11-J18
    corrected outline, U2 / U4-U6 TSSOP-10, test pads 2.0 mm);
  - value, LCSC / Description fields, symbol path, sheet name and file, DNP / BOM / position-file attributes, pad nets.
Board changes of the review (reports/CheckOne/review_2026-11-16.md): J11-J18 3.8 mm toward the board edge (terminal
front 0.95 mm beyond the edge, owner 2026-11-16), LED1-LED4 1.0 mm away from the edge, J2 0.3 mm in x, title
block rev 1.1 and the silkscreen revision text. The board is saved in the KiCad 10 format.
"""
import argparse
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.join(HERE, "CheckOne")
PCB = os.path.join(PRJ, "CheckOne.kicad_pcb")
NET = os.path.join(PRJ, "CheckOne.net")
STD = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "share", "kicad", "footprints")
TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
REPLACE_ALWAYS = {"KF2EDGRC-5.08-4P"}          # project footprints whose library copy changed at rev 1.1
TERMINAL_SHIFT = 3.8                            # mm toward the nearest long edge (review item 2, owner choice)
LED_SHIFT = 1.0                                 # mm away from the edge (review item 8)
J2_SHIFT_X = 0.3                                # mm, J2 (NTC1) courtyard clear of J18 after the terminal fix (item 9)


def sexp(text):
    stack, cur = [], []
    for m in TOK.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return cur[0]


def kids(n, tag):
    return [c for c in n if isinstance(c, list) and c and c[0] == tag]


def val(n, tag, default=""):
    k = kids(n, tag)
    return k[0][1] if k and len(k[0]) > 1 else default


def parse(path):
    root = sexp(open(path, encoding="utf-8").read())
    comps, nets = {}, {}
    for c in kids(kids(root, "components")[0], "comp"):
        props = {val(p, "name"): val(p, "value") for p in kids(c, "property")}
        fields = {}
        for fs in kids(c, "fields"):
            for f in kids(fs, "field"):
                fields[val(f, "name")] = f[2] if len(f) > 2 and isinstance(f[2], str) else ""
        sp = kids(c, "sheetpath")[0]
        comps[val(c, "ref")] = dict(value=val(c, "value"), footprint=val(c, "footprint"), fields=fields, props=props,
                                    tstamps=val(sp, "tstamps"), names=val(sp, "names"), uuid=val(c, "tstamps"))
    for n in kids(kids(root, "nets")[0], "net"):
        for node in kids(n, "node"):
            nets[(val(node, "ref"), val(node, "pin"))] = (val(n, "name"), val(node, "pinfunction"), val(node, "pintype"))
    return comps, nets


def load_fp(fpid, io):
    nick, name = fpid.split(":", 1)
    for lib in (os.path.join(PRJ, nick + ".pretty"), os.path.join(STD, nick + ".pretty")):
        if os.path.isfile(os.path.join(lib, name + ".kicad_mod")):
            fp = io.FootprintLoad(lib, name)
            fp.SetFPID(pcbnew.LIB_ID(nick, name))
            return fp
    sys.exit(f"footprint not found: {fpid}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    comps, nets = parse(NET)
    io = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    board = pcbnew.LoadBoard(PCB)
    byref = {f.GetReference(): f for f in board.GetFootprints()}
    missing = sorted(set(comps) - set(byref))
    extra = sorted(r for r in set(byref) - set(comps))
    if missing:
        sys.exit(f"parts in the schematic but not on the board: {missing}")
    netinfo = {}
    for (_, _), (name, _, _) in nets.items():
        if name not in netinfo:
            ni = board.FindNet(name)
            if ni is None:
                ni = pcbnew.NETINFO_ITEM(board, name)
                board.Add(ni)
            netinfo[name] = ni
    replaced = []
    for ref, c in sorted(comps.items()):
        old = byref[ref]
        old_id = f"{old.GetFPID().GetLibNickname()}:{old.GetFPID().GetLibItemName()}"
        name = c["footprint"].split(":", 1)[1]
        if True:                                # every footprint from its library (KiCad 10 copies, rev 1.1)
            new = load_fp(c["footprint"], io)
            new.SetParent(board)
            board.Add(new)
            if old.IsFlipped():
                new.Flip(new.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
            new.SetPosition(old.GetPosition())
            new.SetOrientation(old.GetOrientation())
            new.SetReference(ref)
            new.Reference().SetPosition(old.Reference().GetPosition())
            new.Reference().SetTextAngle(old.Reference().GetTextAngle())
            new.Reference().SetVisible(old.Reference().IsVisible())
            # 3D models set on the board (EasyEDA models for KiCad-library footprints, e.g. F1) survive the reload
            if old.Models().size() and any("KIPRJMOD" in m.m_Filename for m in old.Models()):
                nm = new.Models()
                while len(nm):
                    nm.pop()
                for m in old.Models():
                    new.Add3DModel(m)
            board.Remove(old)
            replaced.append(f"{ref}: {old_id} -> {c['footprint']}")
            fp = new
        else:
            fp = old
            fp.SetFPID(pcbnew.LIB_ID(*c["footprint"].split(":", 1)))
        fp.SetValue(c["value"])
        for k, v in c["fields"].items():
            if k == "Footprint":
                continue
            fp.SetField(k, v)
            fld = fp.GetField(k)
            if fld is not None:
                fld.SetVisible(False)
                fld.SetLayer(pcbnew.B_Fab if fp.IsFlipped() else pcbnew.F_Fab)
        if c["fields"].get("Description"):
            fp.SetLibDescription(c["fields"]["Description"])
        fp.SetPath(pcbnew.KIID_PATH(c["tstamps"].strip("/") + "/" + c["uuid"]))
        fp.SetSheetname(c["props"].get("Sheetname", ""))
        fp.SetSheetfile(c["props"].get("Sheetfile", ""))
        fp.SetDNP("dnp" in c["props"])
        nobom = "exclude_from_bom" in c["props"] or not c["fields"].get("LCSC")
        fp.SetExcludedFromBOM(nobom)
        fp.SetExcludedFromPosFiles(nobom)
        for pad in fp.Pads():
            hit = nets.get((ref, pad.GetNumber()))
            if hit:
                pad.SetNet(netinfo[hit[0]])
                pad.SetPinFunction(hit[1])
                pad.SetPinType(hit[2])
            else:
                pad.SetNetCode(0)
    # board changes of the review: once, on the v1 board (title block not yet at rev 1.1)
    first = board.GetTitleBlock().GetRevision() != "1.1"
    bb = board.GetBoardEdgesBoundingBox()
    ymid = (bb.GetTop() + bb.GetBottom()) / 2
    moved = []
    for f in board.GetFootprints() if first else []:
        r = f.GetReference()
        p = f.GetPosition()
        if re.fullmatch(r"J1[1-8]", r):
            dy = -TERMINAL_SHIFT if p.y < ymid else TERMINAL_SHIFT
        elif r == "J2":
            dy = 0.0
            f.SetPosition(pcbnew.VECTOR2I(p.x + pcbnew.FromMM(J2_SHIFT_X), p.y))
            moved.append(f"J2 x {J2_SHIFT_X:+.2f} mm")
            continue
        elif r in ("LED1", "LED2", "LED3", "LED4") and p.y > ymid and \
                pcbnew.ToMM(bb.GetBottom() - p.y) < 12:
            dy = -LED_SHIFT
        else:
            continue
        f.SetPosition(pcbnew.VECTOR2I(p.x, p.y + pcbnew.FromMM(dy)))
        moved.append(f"{r} {dy:+.2f} mm")
    for d in board.GetDrawings():
        if isinstance(d, pcbnew.PCB_TEXT) and "rev 1.0" in d.GetText():
            d.SetText(d.GetText().replace("rev 1.0", "rev 1.1"))
    tb = board.GetTitleBlock()
    tb.SetTitle("CheckOne - production test fixture, 8 x 4-20 mA")
    tb.SetRevision("1.1")
    tb.SetDate("2026-11-16")
    tb.SetCompany("AQTech Power Prognostics")
    board.SetTitleBlock(tb)
    board.BuildConnectivity()
    print(f"{len(comps)} parts synced; {len(replaced)} footprints replaced:")
    for x in replaced:
        print("  ", x)
    print("moved:", ", ".join(moved))
    if extra:
        print("on the board only (left as they are):", extra)
    if not a.dry_run:
        pcbnew.SaveBoard(PCB, board)
        print("saved", PCB)


if __name__ == "__main__":
    main()
