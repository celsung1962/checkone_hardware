#!/usr/bin/env python3
"""
Generate the CheckOne schematic, rev 1.1 (root + 6 A4 sheets), with hardware/schgen.py in the GapOne V2 style:
section title boxes, wired decoupling, local labels inside a sheet, a SHEET PORTS block for the inter-sheet nets,
notes that cite the datasheet figure and the calc/ script of every value. The generator is the master copy of
hardware/CheckOne/*.kicad_sch: do not hand-edit them.

Circuit: the v1 design of S. Zimath (gerador/design.py, update 2026-11-16 10:56) with the changes of
reports/CheckOne/review_2026-11-16.md, decided by the owner on 2026-11-16 ("aplique todas as mudancas"):
  1 D50 / D51 BAT54W on SOD-123;  3 L1 / L2 on the maker's FCH1040 land;  4 R6 0 ohm fitted, D4 SS34 DNP (CYD);
  5 R111-R181 4.7 k (fault current into +3.3VA);  6 power flags;  7 ADS1115 / INA226 on TSSOP-10_3x3mm_P0.5mm;
  10 test pads 2.0 mm;  11 values = part numbers;  12 rev 1.1, 2026-11-16;  13 English sheet names.
References are v1's, so the board keeps its placement (hardware/sync_board.py).

Run:  python hardware/build_symbol_lib.py ; python hardware/gen_checkone.py ; python hardware/sync_board.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import schgen as sg  # noqa: E402

BOARD = "CheckOne"
sg.set_project(BOARD)
P = BOARD

R0603, C0603, C0805 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_0805_2012Metric"
R1206 = "Resistor_SMD:R_1206_3216Metric"
TP_FP = "TestPoint:TestPoint_Pad_D2.0mm"
# key -> (symbol, value, footprint, LCSC, description). Codes: S. Zimath's v1 (JLCPCB catalog, description DS 8.1),
# R111-R181 4.7 k from the same list (C23162), R110-R180 his 25 ppm update (C2989146).
PART = {
    "R:10k": ("R", "10k", R0603, "C25804", "Resistor 10 kohm 1% 0603"),
    "R:4.7k": ("R", "4.7k", R0603, "C23162", "Resistor 4.7 kohm 1% 0603"),
    "R:1k": ("R", "1k", R0603, "C21190", "Resistor 1 kohm 1% 0603"),
    "R:1.5k": ("R", "1.5k", R0603, "C22843", "Resistor 1.5 kohm 1% 0603"),
    "R:10": ("R", "10", R0603, "C22859", "Resistor 10 ohm 1% 0603"),
    "R:0": ("R", "0", R0603, "C21189", "Resistor 0 ohm 0603"),
    "R:100m": ("R", "100m", R1206, "C25334", "Resistor 100 mohm 1% 1206 (Uniroyal 1206W4F100LT5E)"),
    "R:120 0.1%": ("R", "120 0.1%", R1206, "C2989146",
                   "Resistor 120 ohm 0.1% 25 ppm/K thin film 1206 (TC series) - loop shunt"),
    "C:100nF": ("C", "100nF", C0603, "C14663", "Capacitor 100 nF 50 V X7R 0603"),
    "C:10nF": ("C", "10nF", C0603, "C57112", "Capacitor 10 nF 50 V X7R 0603"),
    "C:1uF": ("C", "1uF", C0805, "C28323", "Capacitor 1 uF 50 V X7R 0805 (CL21B105KBFNNNE)"),
    "C:22pF": ("C", "22pF", C0603, "C1653", "Capacitor 22 pF 50 V C0G 0603"),
    "C:220uF": ("C_Polarized", "220uF", "Capacitor_SMD:CP_Elec_10x10.5", "C46550417",
                "Aluminium electrolytic 220 uF 50 V 10 x 10 (JVJ50V220M10x10)"),
    "L:FCH1040": ("L", "FCH1040-680M", f"{P}:L_Fangcheng_FCH1040", "C20415548",
                  "Power inductor 68 uH, molded 11.5 x 10.5 mm (Fangcheng FCH1040-680M)"),
    "FB:GZ2012": ("FerriteBead_Small", "GZ2012D601TF", "Inductor_SMD:L_0805_2012Metric", "C1017",
                  "Ferrite bead 600 ohm at 100 MHz, 500 mA, 0805 (Sunlord)"),
    "F:1.6A": ("Polyfuse", "1812L160/30GR", "Fuse:Fuse_1812_4532Metric", "C18198337", "PTC fuse 1.6 A hold, 30 V, 1812"),
    "F:200mA": ("Polyfuse", "JK-SMD0805-020-30V", "Fuse:Fuse_0805_2012Metric", "C516070",
                "PTC fuse 0.2 A hold, 0.5 A trip, 30 V, 0805 (Jinrui)"),
    "Y:32k": ("Crystal", "Q13FC13500004", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", "C32346",
              "Crystal 32.768 kHz 12.5 pF, FC-135 3.2 x 1.5 (Epson)"),
    "BT": ("Battery_Cell", "BS-02-A1AJ006", f"{P}:BS-02-A1AJ006", "C964745", "CR2032 holder, THT (MYOUNG); cell bought loose"),
    "J:DC": ("Barrel_Jack_Switch", "DC-005-A200", f"{P}:DC-005-A200", "C720557",
             "DC jack 5.5 x 2.1 mm, centre +, THT (XUNPU)"),
    "J:XH": ("Conn_01x02", "B2B-XH-A", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", "C158012",
             "JST XH 2-pin vertical, THT - NTC input"),
    "J:MX125": ("Conn_01x04", "1.25-4P LT", "Connector_Molex:Molex_PicoBlade_53398-0471_1x04-1MP_P1.25mm_Vertical", "C668611",
                "MX1.25 4-pin vertical SMD (SHOU HAN, PicoBlade 53398 compatible) - display cable"),
    "J:EXT": ("Conn_01x04", "PZ254V-11-04P", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "C2691448",
              "Pin header 1 x 4 2.54 mm, THT (XFCN) - external 4.3 in display"),
    "J:TERM": ("Conn_01x04", "KF2EDGRC-5.08-4P", f"{P}:KF2EDGRC-5.08-4P", "C441238",
               "Pluggable terminal header 4-pin 5.08 mm, right angle, closed sides (Kefa) - plug KF2EDGK-5.08-4P"),
}


def fields(key, dnp=False):
    sym, val, fp, lcsc, desc = PART[key]
    return dict(lib_id=f"{P}:{sym}", value=val, dnp=dnp, fields={"Footprint": fp, "LCSC": lcsc, "Description": desc,
                                                                  "Datasheet": "~"})


def part(sh, key, ref, at, rotation=0, dnp=False, **kw):
    f = fields(key, dnp)
    p = sh.place(f.pop("lib_id"), ref, at, rotation=rotation, **f, **kw)
    if key == "C:220uF" and rotation in (0, 180):
        p.field_pos = {"Reference": (6.35, -1.27), "Value": (6.35, 1.27)}
    return p


def ic(sh, name, ref, at, **kw):
    return sh.place(f"{P}:{name}", ref, at, **kw)


POWER_NETS = ("GND", "+5V", "+3.3V", "+3.3VA", "+24V_SENS", "+5V_DISP", "V24_F")


def two(sh, p, n1, n2, stub=2.54):
    for pin, net in (("1", n1), ("2", n2)):
        if net in POWER_NETS:
            sh.power(p, pin, net, stub=stub)
        else:
            sh.label(p, pin, net)


def section(sh, title, at, width=None):
    S = sg.S
    w = width or round(len(title) * 1.75 + 10.16, 2)
    sh.items.append([S("text_box"), title, [S("exclude_from_sim"), S("no")], [S("at"), at[0], at[1], 0],
                     [S("size"), w, 6.35], [S("margins"), 0.9525, 0.9525, 0.9525, 0.9525],
                     [S("stroke"), [S("width"), 0.254], [S("type"), S("solid")], [S("color"), 72, 72, 200, 1]],
                     [S("fill"), [S("type"), S("none")]],
                     [S("effects"), [S("font"), [S("size"), 2.0, 2.0], [S("bold"), S("yes")], [S("color"), 0, 0, 194, 1]],
                      [S("justify"), S("top")]],
                     [S("uuid"), sg.U(f"{sh.name}/section/{title}")]])


def name(sh, point, net, angle=0, kind="local", shape="bidirectional"):
    """Net name written on an existing wire (no stub): the label's anchor sits on the wire and its text runs along
    it (owner 2026-11-16: no lines that go nowhere). kind global also puts the net in the SHEET PORTS block."""
    S = sg.S
    x, y = sg.snap(point[0]), sg.snap(point[1])
    if kind != "local":
        sh.hier.setdefault(net, shape)
    sh.items.append([S("label"), net, [S("at"), x, y, angle], [S("fields_autoplaced"), S("yes")],
                     sg.font(justify="left bottom"), [S("uuid"), sg.U(f"{sh.name}/name/{net}/{x}/{y}")]])


def pwr_flag(sh, n, at, net):
    f = sh.place("power:PWR_FLAG", f"#FLG{sh.tag}{n:02d}", at, value="PWR_FLAG")
    if net in POWER_NETS:
        sh.power(f, "1", net, stub=2.54)
    else:
        sh.label(f, "1", net)
    return f


def testpoint(sh, ref, at, net, kind="local"):
    tp = sh.place(f"{P}:TestPoint", ref, at, value="TP",
                  fields={"Footprint": TP_FP, "Description": "Test pad 2.0 mm, bottom side", "LCSC": "", "Datasheet": "~"})
    tp.field_pos = {"Reference": (3.81, -2.54), "Value": None}
    if net in POWER_NETS:
        sh.power(tp, "1", net, stub=2.54)
    else:
        sh.label(tp, "1", net, kind=kind)
    return tp


def drop(sh, point, key, ref, direction="down", end=None, pin1="1", dnp=False, gap=2.54):
    p, far = sh.drop(point, ref=ref, direction=direction, end=end, pin1=pin1, gap=gap, **fields(key, dnp))
    if key == "C:220uF" and direction in ("down", "up"):     # polarized body is wider: texts further out
        p.field_pos = {"Reference": (6.35, -1.27), "Value": (6.35, 1.27)}
    return p, far


def span(sh, a, b, key, ref, pin1="1", dnp=False):
    return sh.span(a, b, ref=ref, pin1=pin1, **fields(key, dnp))


def chain_led(sh, top, rkey, rref, lref, rail):
    """Rail -> resistor -> green LED -> GND, drawn down from `top`."""
    sh.pwr(top, rail)
    _, far = drop(sh, top, rkey, rref, gap=0)
    led, end = sh.drop(far, f"{P}:KT-0805G", lref, direction="down", gap=0, pin1="2", end="GND")
    return led


# ------------------------------------------------------------------------------------------------ sheets ----
def sheet_power_input():
    sh = sg.Sheet("Power_Input", "Power_Input.kicad_sch", "CheckOne - 24 V input, protection, soft start, filter",
                  paper="A4", comments=("24 V +-5 %, hot plug: PTC, TVS, SS34, P-MOSFET soft start, pi filter",
                                        "Description 5.1; review 2026-11-16"))
    section(sh, "24 V input and protection", (15.24, 22.86))
    j1 = part(sh, "J:DC", "J1", (25.4, 63.5))
    j1.field_pos = {"Reference": (0, -7.62), "Value": (0, 7.62)}
    vin = sh.pt(j1, "1")
    y = vin[1]
    sh.power_bus(j1, ["3", "2"], "GND", stub=2.54)
    span(sh, vin, (58.42, y), "F:1.6A", "F1")
    name(sh, vin, "VIN_RAW")
    sh.drop((58.42, y), f"{P}:SMBJ24A", "D1", direction="down", pin1="1", end="GND")
    name(sh, (59.69, y), "VIN_F")
    sh.span((58.42, y), (83.82, y), f"{P}:SS34", "D2", pin1="2")
    sh.wire((83.82, y), (134.62, y))
    name(sh, (76.2, y), "VIN_S")
    _, far = drop(sh, (91.44, y), "R:10k", "R1")
    sh.drop(far, f"{P}:KT-0805G", "LED1", direction="down", pin1="2", end="GND")
    drop(sh, (101.6, y), "C:100nF", "C1", end="GND")
    pwr_flag(sh, 1, (40.64, 78.74), "GND")

    # soft start: Q1 source on VIN_S; R2 || C2 source-gate, R3 gate-GND, R4 + (C3 || C4) gate-drain, all wired
    section(sh, "Soft start (hot plug)", (101.6, 22.86))
    q1 = ic(sh, "AO4485", "Q1", (134.62, 71.12))
    q1.field_pos = {"Reference": (8.89, -10.16), "Value": (8.89, -7.62)}
    q1.used.update({"2", "3", "6", "7", "8"})
    sh.wire((134.62, y), sh.pt(q1, "1"))
    g = sh.pt(q1, "4")
    d = sh.pt(q1, "5")
    sh.wire(g, (106.68, g[1]))
    span(sh, (111.76, y), (111.76, g[1]), "C:220uF", "C2")            # + on the source (VIN_S)
    span(sh, (121.92, y), (121.92, g[1]), "R:4.7k", "R2")
    drop(sh, (106.68, g[1]), "R:10k", "R3", end="GND", gap=0)
    name(sh, (113.03, g[1]), "SS_GATE")
    _, r4 = drop(sh, (124.46, g[1]), "R:1k", "R4")
    yc3, yc4 = 86.36, 96.52
    sh.wire(r4, (124.46, yc4))
    name(sh, (124.46, 92.71), "SS_CGD", angle=90)
    span(sh, (124.46, yc3), (144.78, yc3), "C:1uF", "C3")
    span(sh, (124.46, yc4), (144.78, yc4), "C:1uF", "C4")
    sh.wire((144.78, yc4), (144.78, d[1]))

    section(sh, "Pi filter 68 uH (about 41 Hz)", (154.94, 22.86))
    sh.wire(d, (172.72, d[1]))
    sh.wire((193.04, d[1]), (233.68, d[1]))
    name(sh, (146.05, d[1]), "V24_D")
    drop(sh, (154.94, d[1]), "C:220uF", "C5", end="GND")
    drop(sh, (167.64, d[1]), "C:1uF", "C6", end="GND")
    span(sh, (172.72, d[1]), (193.04, d[1]), "L:FCH1040", "L1")
    drop(sh, (200.66, d[1]), "C:220uF", "C7", end="GND")
    drop(sh, (213.36, d[1]), "C:1uF", "C8", end="GND")
    drop(sh, (223.52, d[1]), "C:100nF", "C9", end="GND")
    sh.pwr((233.68, d[1]), "V24_F")
    pwr_flag(sh, 2, (241.3, 86.36), "V24_F")

    sh.note("Input chain per description 5.1 (S. Zimath, v1): PTC 1.6 A -> SMBJ24A (VBR 26.7-29.5 V) -> SS34 reverse-polarity "
            "diode -> 24 V LED -> soft start -> pi filter. Supply 24 V +-5 %, 25.2 V max: above it the SMBJ24A conducts (DS 9).\n"
            "Soft start (hot plug, owner meeting 2026-11-16): R2 4.7 k / R3 10 k hold VGS at -7.7 V (24 V) and -12.4 V at the TVS clamp, "
            "inside the AO4485 +-20 V; C2 220 uF G-S (+ on the source) keeps the MOSFET off while the plug settles, ~0.2 s delay; "
            "C3 + C4 (2 uF) with R4 1 k set the ~20 ms ramp, 1-1.8 A peak into ~1.3 mF (ngspice, DS 5.1 / 9; netlists not in the "
            "hand-over, G-1). R4 is essential: without it the cable ringing couples to the gate.\n"
            "Pi filter: 2 x (220 uF + 1 uF) around L1 68 uH (FCH1040, maker's land, review item 3), corner ~41 Hz; drop ~0.16 V.",
            (15.24, 142.24), size=(154.94, 25.4), style="calc")
    sh.note("Layout (v1 LEIA-ME 3): D1 at the DC jack; between D2 and Q1 only C1; copper area on the Q1 drain.",
            (15.24, 170.18), size=(154.94, 6.35))
    return sh


def sheet_power_rails():
    sh = sg.Sheet("Power_Rails", "Power_Rails.kicad_sch", "CheckOne - 5 V buck, display 5 V, sensor-bus monitor, 3.3 V",
                  paper="A4", comments=("XL1509-5.0 buck, display 5 V, INA226 sensor bus, XC6206 3.3 V, 3.3VA",
                                        "Description 5.1, 5.5; review 2026-11-16 items 4, 6"))
    sh.ports_at = (241.3, 15.24)
    # row 1: 5 V buck (left), 3.3 V LDO and 3.3VA (right)
    section(sh, "5 V buck (XL1509-5.0)", (15.24, 22.86))
    u1 = ic(sh, "XL1509-5.0E1", "U1", (66.04, 45.72))
    u1.field_pos = {"Reference": (-10.16, -6.35), "Value": (2.54, -6.35)}
    vin = sh.pt(u1, "1")
    sh.wire(vin, (17.78, vin[1]))
    sh.pwr((17.78, vin[1]), "V24_F")
    drop(sh, (22.86, vin[1]), "C:220uF", "C10", end="GND")
    drop(sh, (35.56, vin[1]), "C:1uF", "C11", end="GND")
    sh.power(u1, "4", "GND", stub=5.08)
    sh.power(u1, "5", "GND")
    u1.used.update({"6", "7", "8"})
    out = sh.pt(u1, "2")
    sh.wire(out, (99.06, out[1]))
    name(sh, out, "BUCK_SW")
    sh.drop((91.44, out[1]), f"{P}:SS34", "D3", direction="down", pin1="1", end="GND")
    span(sh, (99.06, out[1]), (119.38, out[1]), "L:FCH1040", "L2")
    sh.wire((119.38, out[1]), (139.7, out[1]))
    drop(sh, (124.46, out[1]), "C:220uF", "C12", end="GND")
    sh.pwr((134.62, out[1]), "+5V")
    fb = sh.pt(u1, "3")
    sh.wire(fb, (86.36, fb[1]), (86.36, 66.04), (134.62, 66.04), (134.62, out[1]))
    _, far = drop(sh, (139.7, out[1]), "R:1.5k", "R5", gap=0)
    sh.drop(far, f"{P}:KT-0805G", "LED2", direction="down", pin1="2", end="GND")
    pwr_flag(sh, 1, (106.68, 55.88), "+5V")

    section(sh, "3.3 V (XC6206) and analog 3.3VA", (147.32, 22.86))
    u3 = ic(sh, "XC6206P332MR", "U3", (182.88, 45.72))
    vi = sh.pt(u3, "3")
    sh.wire(vi, (152.4, vi[1]))
    sh.pwr((152.4, vi[1]), "+5V")
    drop(sh, (162.56, vi[1]), "C:1uF", "C15", end="GND")
    sh.power(u3, "1", "GND", stub=2.54)
    vo = sh.pt(u3, "2")
    sh.wire(vo, (226.06, vo[1]))
    drop(sh, (198.12, vo[1]), "C:1uF", "C16", end="GND")
    drop(sh, (208.28, vo[1]), "C:100nF", "C18", end="GND")
    _, far = drop(sh, (218.44, vo[1]), "R:1k", "R8")
    sh.drop(far, f"{P}:KT-0805G", "LED3", direction="down", pin1="2", end="GND")
    sh.pwr((223.52, vo[1]), "+3.3V")
    span(sh, (226.06, vo[1]), (246.38, vo[1]), "R:10", "R9")
    sh.wire((246.38, vo[1]), (259.08, vo[1]))
    drop(sh, (251.46, vo[1]), "C:1uF", "C17", end="GND")
    sh.pwr((259.08, vo[1]), "+3.3VA")
    pwr_flag(sh, 2, (266.7, 55.88), "+3.3VA")

    # row 2: display 5 V (left), INA226 (right)
    section(sh, "Display 5 V (CYD: R6 fitted, D4 DNP)", (15.24, 76.2))
    y = 96.52
    sh.pwr((22.86, y), "+5V")
    sh.wire((22.86, y), (30.48, y))
    sh.span((30.48, y), (50.8, y), f"{P}:SS34", "D4", pin1="2", dnp=True)
    sh.wire((33.02, y), (33.02, y + 10.16))
    span(sh, (33.02, y + 10.16), (48.26, y + 10.16), "R:0", "R6")
    sh.wire((48.26, y + 10.16), (48.26, y))
    sh.wire((50.8, y), (55.88, y))
    name(sh, (49.53, y), "5V_D")
    sh.wire((55.88, y), (55.88, y + 10.16))
    span(sh, (55.88, y), (76.2, y), "FB:GZ2012", "FB1")
    span(sh, (55.88, y + 10.16), (76.2, y + 10.16), "FB:GZ2012", "FB2")
    sh.wire((76.2, y + 10.16), (76.2, y))
    sh.wire((76.2, y), (83.82, y))
    sh.pwr((83.82, y), "+5V_DISP")
    pwr_flag(sh, 3, (93.98, 104.14), "+5V_DISP")

    # INA226: Kelvin shunt R7 || R13 wired to IN+ (V24_F side) and IN- / VBUS (+24V_SENS side); C13 at VS; I2C
    # pull-ups R11 / R12 on its SDA / SCL
    section(sh, "Sensor-bus monitor (INA226, 0x40)", (116.84, 76.2))
    u2 = ic(sh, "INA226AIDGSR", "U2", (180.34, 111.76))
    u2.field_pos = {"Reference": (5.08, -12.7), "Value": (12.7, 15.24)}
    inp, inn, vbus = sh.pt(u2, "10"), sh.pt(u2, "9"), sh.pt(u2, "8")
    yt, yb = 91.44, 116.84
    sh.wire(inp, (160.02, inp[1]), (160.02, yt), (134.62, yt))
    sh.pwr((134.62, yt), "V24_F")
    sh.wire(inn, (157.48, inn[1]), (157.48, yb), (127.0, yb))
    sh.wire(vbus, (162.56, vbus[1]), (162.56, inn[1]))
    span(sh, (139.7, yt), (139.7, yb), "R:100m", "R7")
    span(sh, (149.86, yt), (149.86, yb), "R:100m", "R13")
    sh.pwr((127.0, yb), "+24V_SENS")
    drop(sh, (132.08, yb), "C:220uF", "C14", end="GND")
    pwr_flag(sh, 4, (121.92, 99.06), "+24V_SENS")
    vs = sh.pt(u2, "6")
    sh.wire(vs, (vs[0], 86.36))
    sh.pwr((vs[0], 86.36), "+3.3V")
    c13, _ = drop(sh, (vs[0], 91.44), "C:100nF", "C13", direction="left", end="GND")
    c13.field_pos = {"Reference": (0, -3.81), "Value": (0, -6.35)}
    sh.power(u2, "7", "GND", stub=2.54)
    sh.power_bus(u2, ["1", "2"], "GND", stub=5.08)
    sh.nc(u2, "3")
    sda, scl = sh.pt(u2, "4"), sh.pt(u2, "5")
    sh.wire(sda, (210.82, sda[1]))
    sh.wire(scl, (226.06, scl[1]))
    drop(sh, (200.66, sda[1]), "R:4.7k", "R11", direction="up", end="+3.3V")
    drop(sh, (215.9, scl[1]), "R:4.7k", "R12", direction="up", end="+3.3V")
    name(sh, (210.82, sda[1]), "SDA", kind="global")
    name(sh, (226.06, scl[1]), "SCL", kind="global")

    # row 3: test pads
    section(sh, "Test pads (bottom side)", (15.24, 127.0))
    for i, (ref, net) in enumerate((("TP1", "+24V_SENS"), ("TP2", "+5V"), ("TP3", "+3.3V"), ("TP4", "+3.3VA"),
                                    ("TP5", "SDA"), ("TP6", "SCL"), ("TP7", "GND"), ("TP8", "GND"))):
        testpoint(sh, ref, (22.86 + i * 10.16, 149.86), net, kind="global")
    sh.note("XL1509-5.0 per its datasheet typical application (L 68 uH / 2 A, Schottky SS34, ON/OFF low = on, FB to the 5 V "
            "output): 5 V +-4 % (4.8-5.2 V), 150 kHz. Layout (v1 LEIA-ME 4): C10 / C11 at VIN, loop U1-D3-L2-C12 short.\n"
            "Display 5 V (review item 4): the CYD's own LDO needs ~4.4 V; through the SS34 it would get 4.3-4.5 V, so R6 0 ohm is "
            "fitted and D4 is DNP. D4 only with the JC3248W535; with R6 do not plug the display's USB while the fixture is powered.\n"
            "INA226: 50 mohm (R7 || R13), 81.92 mV full scale = 1.64 A; measures the sensor bus only (C-13). VS on +3.3V, not 3.3VA "
            "(review: its digital current stays off the analog rail). Kelvin: R7 / R13 side by side, sense from the pad centres.\n"
            "3.3VA = +3.3V through R9 10 ohm / C17 1 uF: ADS1115 x 3 and the NTC dividers (calc/checkone_budget.py).",
            (15.24, 167.64), size=(157.48, 27.94), style="calc")
    return sh


def sheet_channels(name, chans):
    sh = sg.Sheet(name, f"{name}.kicad_sch", f"CheckOne - loop channels CH{chans[0]}-CH{chans[-1]}", paper="A4",
                  comments=("Per channel: PTC, bead, terminal; Iin -> 120 ohm to GND; 4.7 k, BAT54S, 10 nF",
                            "Description 5.1, 5.2; review 2026-11-16 item 5"))
    sh.ports_at = (241.3, 15.24)
    for i, n in enumerate(chans):
        channel_full(sh, n, 15.24 + i * 55.88)
    sh.note("Loop input (description 5.2): sensor outputs are isolated, Iin -> R1n0 120 ohm 0.1 % 25 ppm -> GND, Iout = GND. "
            "2.40 V at 20 mA, 2.52 V at 21 mA; ADS1115 +-4.096 V: 1.04 uA per count, readable to ~27.5 mA (calc 1). "
            "SMAJ5.0A clamps a +24 V wiring error at 6.4-7.4 V until the channel PTC trips.\n"
            "R1n1 4.7 k (rev 1.1, review item 5; v1 1 k): +24 V on Iin pushes 0.6-0.8 mA into +3.3VA through the BAT54S instead of "
            "2.8-3.8 mA, which the XC6206 cannot sink; filter 4.7 k / 10 nF = 3.4 kHz; gain error 0.11 % from the ADS1115 input "
            "impedance, removed by the per-channel calibration (calc/checkone_budget.py item 3).\n"
            "Terminal pins: 1 +24, 2 GND, 3 Iin, 4 Iout (= GND), same on all eight (D8). Layout: 100 nF at the terminal pins; "
            "short shunt return to GND.", (15.24, 160.02), size=(157.48, 33.02), style="calc")
    return sh


def channel_full(sh, n, x0):
    """One loop channel in a 55.88 mm column from x0 (refs as v1: F1n, FB1n, C1n0, J1n, R1n0, D1n, R1n1, D2n, C1n1)."""
    out, iin, ain = f"CH{n}_OUT", f"CH{n}_IIN", f"CH{n}_AIN"
    section(sh, f"CH{n}", (x0, 17.78), width=17.78)
    # terminal, pins down: 1 +24, 2 GND, 3 Iin, 4 Iout = GND
    j = part(sh, "J:TERM", f"J1{n}", (x0 + 40.64, 43.18), rotation=90)
    j.field_pos = {"Reference": (-10.16, 0), "Value": (0, -7.62)}
    p1, p2, p3, p4 = (sh.pt(j, k) for k in "1234")
    sh.power(j, "2", "GND", stub=2.54)
    sh.power(j, "4", "GND", stub=2.54)
    # supply path: +24V_SENS -> PTC -> bead -> terminal pin 1, 100 nF at the terminal
    top = (x0 + 5.08, 35.56)
    sh.pwr(top, "+24V_SENS")
    _, a = drop(sh, top, "F:200mA", f"F1{n}", gap=0)
    _, b = drop(sh, a, "FB:GZ2012", f"FB1{n}", gap=2.54)
    yo = 63.5
    sh.wire(b, (b[0], yo), (p1[0], yo), p1)
    drop(sh, (x0 + 17.78, yo), "C:100nF", f"C1{n}0", end="GND")
    name(sh, (x0 + 20.32, yo), out)
    # loop input: pin 3 -> node -> R1n0 120 ohm and D1n SMAJ5.0A to GND, R1n1 4.7 k -> AIN
    yi = 81.28
    sh.wire(p3, (p3[0], yi), (x0 + 5.08, yi))
    name(sh, (x0 + 19.05, yi), iin)
    drop(sh, (x0 + 5.08, yi), "R:120 0.1%", f"R1{n}0", gap=0, end="GND")
    sh.drop((x0 + 17.78, yi), f"{P}:SMAJ5.0A", f"D1{n}", direction="down", pin1="1", end="GND")
    _, r_end = drop(sh, (x0 + 30.48, yi), "R:4.7k", f"R1{n}1")
    ya = 101.6
    sh.wire(r_end, (r_end[0], ya), (x0 + 50.8, ya))
    d = sh.place(f"{P}:BAT54S", f"D2{n}", (x0 + 40.64, ya + 7.62), rotation=180)
    d.field_pos = {"Reference": (0, 5.08), "Value": (0, 7.62)}
    sh.wire(sh.pt(d, "3"), (x0 + 40.64, ya))
    sh.power(d, "1", "GND", stub=2.54)
    sh.power(d, "2", "+3.3VA", stub=2.54)
    drop(sh, (x0 + 50.8, ya), "C:10nF", f"C1{n}1", end="GND", gap=0)
    name(sh, (x0 + 31.75, ya), ain, kind="global", shape="output")
    return d


def sheet_adc_ntc():
    sh = sg.Sheet("ADC_NTC", "ADC_NTC.kicad_sch", "CheckOne - A/D converters (3 x ADS1115) and NTC inputs", paper="A4",
                  comments=("U4 0x48 CH1-4, U5 0x49 CH5-8, U6 0x4A NTC1 / 3.3VA / NTC2",
                            "Description 5.2, 5.3, 5.5; calc items 1, 2"))
    sh.ports_at = (241.3, 15.24)
    for k, (ref, cref, at, addr, base) in enumerate((("U4", "C40", (45.72, 55.88), "GND", 1),
                                                     ("U5", "C41", (45.72, 121.92), "+3.3VA", 5))):
        section(sh, f"Loop ADC {ref} (0x{0x48 + k:02X}) - CH{base}-CH{base + 3}", (15.24, at[1] - 33.02))
        u = ic(sh, "ADS1115IDGSR", ref, at)
        for i, pin in enumerate(("4", "5", "6", "7")):
            sh.label(u, pin, f"CH{base + i}_AIN", kind="global", shape="input")
        sh.power(u, "8", "+3.3VA", stub=2.54)
        sh.power(u, "3", "GND", stub=2.54)
        if addr == "GND":
            sh.power(u, "1", "GND", stub=2.54)
        else:                                              # ADDR to VDD: wired out beyond the I2C label texts
            pa = sh.pt(u, "1")
            sh.wire(pa, (pa[0] + 20.32, pa[1]))
            sh.pwr((pa[0] + 20.32, pa[1]), addr)
        sh.nc(u, "2")
        sh.label(u, "9", "SDA", kind="global")
        sh.label(u, "10", "SCL", kind="global")
        c = part(sh, "C:100nF", cref, (at[0] + 22.86, at[1] - 15.24))
        two(sh, c, "+3.3VA", "GND")
    section(sh, "NTC inputs and NTC ADC U6 (0x4A)", (99.06, 22.86))
    u6 = ic(sh, "ADS1115IDGSR", "U6", (226.06, 93.98))
    sh.label(u6, "4", "NTC1_ADC")
    sh.label(u6, "6", "NTC2_ADC")
    for pin, net in (("5", "+3.3VA"), ("7", "GND")):      # AIN1 reads the divider supply, AIN3 unused (grounded)
        pp = sh.pt(u6, pin)
        sh.wire(pp, (pp[0] - 22.86, pp[1]))
        sh.pwr((pp[0] - 22.86, pp[1]), net)
    sh.power(u6, "8", "+3.3VA", stub=2.54)
    sh.power(u6, "3", "GND", stub=2.54)
    sh.label(u6, "1", "SDA", kind="global")
    sh.nc(u6, "2")
    sh.label(u6, "9", "SDA", kind="global")
    sh.label(u6, "10", "SCL", kind="global")
    c = part(sh, "C:100nF", "C42", (248.92, 78.74))
    two(sh, c, "+3.3VA", "GND")
    for k in range(2):
        x0, y0 = 104.14, 48.26 + k * 50.8
        jref, node, adc = ("J2", "J3")[k], f"NTC{k + 1}", f"NTC{k + 1}_ADC"
        sh.text(f"NTC{k + 1} - {'front window, probe to 150 C' if k == 0 else 'inside the enclosure'}", (x0, y0 - 12.7))
        j = part(sh, "J:XH", jref, (x0 + 2.54, y0 + 15.24), mirror="y")
        j.field_pos = {"Reference": (0, -5.08), "Value": (0, 7.62)}
        p1 = sh.pt(j, "1")
        sh.power(j, "2", "GND", stub=2.54)
        nx = x0 + 20.32
        sh.wire(p1, (nx + 20.32, p1[1]))
        sh.pwr((nx, y0), "+3.3VA")
        sh.span((nx, y0), (nx, p1[1]), ref=f"R4{k}0", **fields("R:10k"))
        drop(sh, (x0 + 15.24, p1[1]), "C:1uF", f"C4{k}3", end="GND")
        name(sh, (nx + 1.27, p1[1]), node)
        sh.span((nx + 20.32, p1[1]), (nx + 35.56, p1[1]), ref=f"R4{k}1", **fields("R:1k"))
        a = (nx + 35.56, p1[1])
        sh.wire(a, (nx + 60.96, p1[1]))
        d = sh.place(f"{P}:BAT54S", f"D4{k}", (nx + 45.72, p1[1] + 7.62), rotation=180)
        d.field_pos = {"Reference": (0, 5.08), "Value": (0, 7.62)}
        sh.wire(sh.pt(d, "3"), (nx + 45.72, p1[1]))
        sh.power(d, "1", "GND", stub=2.54)
        sh.power(d, "2", "+3.3VA", stub=2.54)
        drop(sh, (nx + 55.88, p1[1]), "C:10nF", f"C4{k}4", end="GND", gap=0)
        name(sh, (nx + 60.96, p1[1]), adc)
    sh.note("ADS1115 (TI SBAS444): single-ended, PGA +-4.096 V, 128 SPS; ADDR to GND 0x48, VDD 0x49, SDA 0x4A; ALERT/RDY "
            "unused (polled); 100 nF at VDD. Ratiometric NTC: U6 AIN1 reads the 3.3VA that feeds the dividers.\n"
            "NTC 100 k B3950, 10 k divider from 3.3VA: 3.00 V at 25 C, 0.55 V at 150 C; 1 uF at the connector, ~17.5 Hz with the "
            "divider (calc/checkone_budget.py item 2). Input protection as the loops: 1 k, BAT54S, 10 nF.",
            (15.24, 160.02), size=(157.48, 30.48), style="calc")
    return sh


def sheet_display_rtc():
    sh = sg.Sheet("Display_RTC", "Display_RTC.kicad_sch", "CheckOne - display connectors, RTC, mounting holes", paper="A4",
                  comments=("CYD / JC3248W535 or external JC4880P443C, one at a time; PCF8563 + CR2032",
                            "Description 5.4, 7.4, 7.5; review 2026-11-16 item 1"))
    sh.ports_at = (241.3, 15.24)
    section(sh, "Display connectors (one display at a time)", (15.24, 15.24))
    specs = (("J4", "J:MX125", "J_PWR - P1 of the CYD / JC3248W535", (("1", "+5V_DISP"), ("2", None), ("3", None), ("4", "GND"))),
             ("J5", "J:MX125", "J_I2C_CYD - CN1 of the CYD", (("1", "GND"), ("2", "SCL"), ("3", "SDA"), ("4", "DISP_3V3"))),
             ("J6", "J:MX125", "J_I2C_JC - P4 of the JC3248W535", (("1", "GND"), ("2", "DISP_3V3"), ("3", "SDA"), ("4", "SCL"))),
             ("J7", "J:EXT", "J_EXT - 4.3 in JC4880P443C by cable", (("1", "+5V_DISP"), ("2", "GND"), ("3", "SDA"), ("4", "SCL"))))
    for i, (ref, key, title, pins) in enumerate(specs):
        x, y = 40.64 + (i % 2) * 63.5, 40.64 + (i // 2) * 35.56
        sh.text(title, (x - 5.08, y - 12.7))
        j = part(sh, key, ref, (x + 5.08, y))
        j.field_pos = {"Reference": (0, -6.35), "Value": (0, 10.16)}
        for pin, net in pins:
            if net is None:
                sh.nc(j, pin)
            elif net in POWER_NETS and ((net == "GND" and pin == "4") or (net != "GND" and pin == "1")):
                sh.power(j, pin, net, stub=5.08)           # outer pin: the symbol points away from the others
            elif net in POWER_NETS:                        # inner pin: wired out beyond the label texts
                pp = sh.pt(j, pin)
                sh.wire(pp, (pp[0] - 22.86, pp[1]))
                sh.pwr((pp[0] - 22.86, pp[1]), net)
            else:
                sh.label(j, pin, net, kind="global" if net in ("SDA", "SCL") else "local", stub=5.08)
    section(sh, "Display 3.3 V indicator", (15.24, 91.44))
    r10 = part(sh, "R:1k", "R10", (30.48, 121.92))
    sh.label(r10, "1", "DISP_3V3")
    led, _ = sh.drop(sh.pt(r10, "2"), f"{P}:KT-0805G", "LED4", direction="down", gap=2.54, pin1="2", end="GND")

    section(sh, "Real-time clock (PCF8563, 0x51)", (149.86, 15.24))
    u7 = ic(sh, "PCF8563T", "U7", (200.66, 50.8))
    osci, osco = sh.pt(u7, "1"), sh.pt(u7, "2")
    y1 = sh.place(f"{P}:Crystal", "Y1", (172.72, 50.8), rotation=270, value=PART["Y:32k"][1],
                  fields={"Footprint": PART["Y:32k"][2], "LCSC": PART["Y:32k"][3], "Description": PART["Y:32k"][4], "Datasheet": "~"})
    ya, yb = sh.pt(y1, "1"), sh.pt(y1, "2")
    sh.wire(osci, (ya[0], osci[1]), ya) if ya[1] < yb[1] else sh.wire(osci, (yb[0], osci[1]), yb)
    sh.wire(osco, (yb[0], osco[1]), yb) if ya[1] < yb[1] else sh.wire(osco, (ya[0], osco[1]), ya)
    c50 = part(sh, "C:22pF", "C50", (162.56, 40.64))
    sh.label(c50, "1", "OSCI")
    sh.power(c50, "2", "GND", stub=2.54)
    name(sh, (176.53, osci[1]), "OSCI")
    sh.power(u7, "4", "GND", stub=2.54)
    sh.label(u7, "5", "SDA", kind="global")
    sh.label(u7, "6", "SCL", kind="global")
    sh.nc(u7, "3")
    sh.nc(u7, "7")
    vdd = sh.pt(u7, "8")
    sh.wire(vdd, (vdd[0], 30.48), (226.06, 30.48))
    name(sh, (201.93, 30.48), "VRTC")
    c51 = part(sh, "C:100nF", "C51", (226.06, 40.64))
    sh.wire((226.06, 30.48), sh.pt(c51, "1"))
    sh.power(c51, "2", "GND", stub=2.54)
    section(sh, "RTC supply: 3.3 V or CR2032 (BAT54W, SOD-123)", (149.86, 76.2))
    y = 99.06
    d50 = sh.place(f"{P}:BAT54W", "D50", (180.34, y))
    d51 = sh.place(f"{P}:BAT54W", "D51", (180.34, y + 12.7))
    for d, a_net in ((d50, "+3.3V"), (d51, None)):
        sh.label(d, "1", "VRTC")
        if a_net:
            sh.power(d, "2", a_net, stub=2.54)
        else:
            sh.label(d, "2", "VBAT")
    bt = part(sh, "BT", "BT1", (165.1, 134.62))
    bt.field_pos = {"Reference": (7.62, -1.27), "Value": (12.7, 1.27)}
    sh.label(bt, "1", "VBAT")
    sh.power(bt, "2", "GND", stub=2.54)
    f = sh.place("power:PWR_FLAG", f"#FLG{sh.tag}02", (210.82, 104.14), value="PWR_FLAG")
    sh.label(f, "1", "VRTC")
    section(sh, "Mounting holes", (15.24, 144.78))
    for i in range(8):
        h = sh.place(f"{P}:MountingHole", f"H{i + 1}", (22.86 + i * 12.7, 160.02),
                     value="M3 board" if i < 4 else "M3 display spacer",
                     fields={"Footprint": "MountingHole:MountingHole_3.2mm_M3", "LCSC": "", "Description":
                             "M3 hole, board fixing (115 x 80 mm)" if i < 4 else "M3 hole, CYD spacer (87 x 49 mm, to confirm O5)",
                             "Datasheet": "~"})
        h.field_pos = {"Reference": (0, -3.81), "Value": None}
    sh.note("Displays (description 7.4, 7.5): one at a time - both are I2C masters on this bus. The 3.3 V pins of J5 / J6 only "
            "light LED4 (3V3D). J4 TX / RX unconnected. The display's ESP32 is the processor (no MCU on the board).\n"
            "PCF8563T (NXP): 32.768 kHz FC-135 12.5 pF, C50 22 pF on OSCI (OSCO has its internal capacitor); INT and CLKOUT unused. "
            "Supply OR by D50 / D51 BAT54W - SOD-123 (C7502705; v1 had SOT-323 pads, review item 1).",
            (15.24, 170.18), size=(157.48, 22.86), style="calc")
    return sh


def main():
    sheets = [sheet_power_input(), sheet_power_rails(), sheet_channels("Channels_1_4", (1, 2, 3, 4)),
              sheet_channels("Channels_5_8", (5, 6, 7, 8)), sheet_adc_ntc(), sheet_display_rtc()]
    owner = {}
    for sh in sheets:
        missing = sh.check_all_pins_used()
        if missing:
            sys.exit(f"{sh.name}: unconnected pins {missing}")
        for p in sh.parts:
            if p.ref.startswith("#"):
                continue
            if p.ref in owner:
                sys.exit(f"duplicate reference {p.ref} on {sh.name} and {owner[p.ref]}")
            owner[p.ref] = sh.name
    ru, tree = sg.root_sheet(
        sheets, "CheckOne - production test fixture, 8 x 4-20 mA", paper="A4", ymax=(190.5, 154.94), gap=5.08,
        comments=("CheckOne main board, rev 1.1", "v1 S. Zimath; rev 1.1 review reports/CheckOne/review_2026-11-16.md",
                  "Owner: Celso Souza; brief CLAUDE.md"),
        notes=[("BLOCK DIAGRAM - DC jack 24 V -> Power_Input (PTC, TVS, reverse diode, soft start, pi filter) -> V24_F -> "
                "Power_Rails: INA226 shunt -> +24V_SENS -> Channels (8 x PTC, bead, terminal; Iin -> 120 ohm -> ADC) ; "
                "XL1509 +5V -> XC6206 +3.3V -> 3.3VA ; +5V -> display 5 V. ADC_NTC: 3 x ADS1115 on I2C. Display_RTC: display "
                "connectors (the display's ESP32 is the master), PCF8563 + CR2032.", (220.98, 27.94), (63.5, 38.1)),
               ("REVISION 1.1 (2026-11-16): v1 of S. Zimath (schematic and placement, not fabricated) redrawn in the GapOne "
                "style with the review changes: BAT54W SOD-123, DC jack slots (his fix), terminal outline 8.4 mm deep and terminals "
                "3.8 mm toward the edge, FCH1040 maker's land, R6 fitted / D4 DNP, R1n1 4.7 k, power flags, TSSOP-10 links, test "
                "pads 2.0 mm, part numbers as values, English names.", (220.98, 68.58), (63.5, 38.1))])
    out = os.path.join(HERE, BOARD)
    sg.write(tree, os.path.join(out, f"{BOARD}.kicad_sch"))
    for sh in sheets:
        sg.write(sh.sexp(ru), os.path.join(out, sh.filename))
    print(f"written root + {len(sheets)} sheets: " + ", ".join(sh.filename for sh in sheets))


if __name__ == "__main__":
    main()
