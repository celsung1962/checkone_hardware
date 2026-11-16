#!/usr/bin/env python3
"""
3rd-order Butterworth anti-aliasing filter = unity-gain Sallen-Key low-pass
(Q = 1) + a real pole in the ADC's differential input RC.

Usage:
    python3 filter_design.py --fc 12000 --fs 31250 --fband 10000 \
        [--rsk 10k] [--rrc 1k] [--series E96|E24] [--points 1000,5000]

--rsk  equal Sallen-Key resistors (R1 = R2)
--rrc  resistor in EACH leg of the differential RC (pole at 1/(2π·2·Rrc·C))
--fs   sample rate (to report Nyquist and the frequency that folds onto fband)

Prints ideal values, values in the chosen series, the resulting response and
an E96 resistor suggestion that puts f0 back on target with E24/E12 capacitors.
"""
import argparse, math

E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]
E12 = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
E96 = [1.00,1.02,1.05,1.07,1.10,1.13,1.15,1.18,1.21,1.24,1.27,1.30,1.33,1.37,1.40,1.43,1.47,1.50,1.54,1.58,1.62,1.65,1.69,1.74,1.78,1.82,1.87,1.91,1.96,2.00,2.05,2.10,2.15,2.21,2.26,2.32,2.37,2.43,2.49,2.55,2.61,2.67,2.74,2.80,2.87,2.94,3.01,3.09,3.16,3.24,3.32,3.40,3.48,3.57,3.65,3.74,3.83,3.92,4.02,4.12,4.22,4.32,4.42,4.53,4.64,4.75,4.87,4.99,5.11,5.23,5.36,5.49,5.62,5.76,5.90,6.04,6.19,6.34,6.49,6.65,6.81,6.98,7.15,7.32,7.50,7.68,7.87,8.06,8.25,8.45,8.66,8.87,9.09,9.31,9.53,9.76]


def parse_eng(s):
    s = str(s).strip().lower().replace("ω", "").replace("ohm", "")
    mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "meg": 1e6}
    for k in ("meg", "p", "n", "u", "µ", "m", "k"):
        if s.endswith(k):
            return float(s[: -len(k)]) * mult[k]
    return float(s)


def snap(x, series):
    d = 10 ** math.floor(math.log10(x))
    cands = [v * d for v in series] + [10 * d]
    return min(cands, key=lambda v: abs(math.log(v / x)))


def eng(x, unit):
    for p, s in ((1e-12, "p"), (1e-9, "n"), (1e-6, "µ"), (1e-3, "m"), (1, ""), (1e3, "k"), (1e6, "M")):
        if abs(x) < p * 1000:
            return f"{x / p:.4g} {s}{unit}"
    return f"{x:.4g} {unit}"


def resp_db(f, f0, q, frc):
    s = 1j * f / f0
    h2 = 1 / (s * s + s / q + 1)
    h1 = 1 / (1 + 1j * f / frc)
    return 20 * math.log10(abs(h2 * h1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fc", type=float, required=True)
    ap.add_argument("--fs", type=float, default=None)
    ap.add_argument("--fband", type=float, default=None, help="upper edge of the band of interest")
    ap.add_argument("--rsk", default="10k")
    ap.add_argument("--rrc", default="1k")
    ap.add_argument("--cseries", choices=["E24", "E12"], default="E24")
    ap.add_argument("--points", default="")
    a = ap.parse_args()
    cs = E24 if a.cseries == "E24" else E12
    R, Rrc, fc = parse_eng(a.rsk), parse_eng(a.rrc), a.fc
    w = 2 * math.pi * fc
    C2 = 1 / (2 * w * R)          # to ground
    C1 = 4 * C2                   # feedback (Q = 1 with equal R)
    Crc = 1 / (w * 2 * Rrc)
    C1e, C2e, Crce = snap(C1, cs), snap(C2, cs), snap(Crc, cs)

    def summary(Rsk, Rr):
        f0 = 1 / (2 * math.pi * Rsk * math.sqrt(C1e * C2e))
        q = math.sqrt(C1e * C2e) / (2 * C2e)
        frc = 1 / (2 * math.pi * 2 * Rr * Crce)
        return f0, q, frc

    print(f"# 3rd-order Butterworth AAF, target fc = {fc:.0f} Hz\n")
    print("| Component | Ideal | Series |")
    print("|---|---|---|")
    print(f"| R1 = R2 (Sallen-Key) | {eng(R,'Ω')} | {eng(R,'Ω')} |")
    print(f"| C1 (feedback) | {eng(C1,'F')} | {eng(C1e,'F')} |")
    print(f"| C2 (to ground) | {eng(C2,'F')} | {eng(C2e,'F')} |")
    print(f"| RC resistor (each leg) | {eng(Rrc,'Ω')} | {eng(Rrc,'Ω')} |")
    print(f"| RC capacitor (differential) | {eng(Crc,'F')} | {eng(Crce,'F')} |")

    f0, q, frc = summary(R, Rrc)
    # E96 resistor correction to put f0 and frc back on target
    Rfix = snap(R * f0 / fc, E96)
    Rrcfix = snap(Rrc * frc / fc, E96)
    print(f"\nWith series values: f0(SK) = {f0:.0f} Hz, Q = {q:.3f}, f(RC) = {frc:.0f} Hz")
    f0b, qb, frcb = summary(Rfix, Rrcfix)
    print(f"E96 suggestion: R_SK = {eng(Rfix,'Ω')}, R_RC = {eng(Rrcfix,'Ω')} → f0 = {f0b:.0f} Hz, Q = {qb:.3f}, f(RC) = {frcb:.0f} Hz")

    pts = [float(x) for x in a.points.split(",") if x.strip()]
    if a.fband:
        pts.append(a.fband)
    if a.fs:
        pts.append(a.fs / 2)
        if a.fband:
            pts.append(a.fs - a.fband)
    pts = sorted(set(pts))
    if pts:
        print("\n| f (Hz) | Series (dB) | With E96 (dB) | Note |")
        print("|---|---|---|---|")
        for f in pts:
            obs = []
            if a.fband and abs(f - a.fband) < 1e-6: obs.append("band edge")
            if a.fs and abs(f - a.fs / 2) < 1e-6: obs.append("Nyquist")
            if a.fs and a.fband and abs(f - (a.fs - a.fband)) < 1e-6: obs.append("folds onto the band edge")
            print(f"| {f:.1f} | {resp_db(f, f0, q, frc):.2f} | {resp_db(f, f0b, qb, frcb):.2f} | {', '.join(obs)} |")
    print("\nNotes: C0G/NP0 capacitors; add the ADC digital filter rejection at the folding frequency; "
          "the RC resistor and the ADC input impedance create a gain error — compute it separately.")


if __name__ == "__main__":
    main()
