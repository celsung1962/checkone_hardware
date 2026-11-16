#!/usr/bin/env python3
"""
Checks whether the harmonics of a switching regulator fall near multiples of a
ΔΣ ADC modulator frequency (k·f_MOD), where they alias into the band.

Usage:
    python3 fsw_check.py --fsw 300e3 --tol 10 --fmod 4e6 --fband 10e3 \
        [--fdata 31250] [--nmax 40] [--kmax 5] [--guard 40e3]

--tol    converter oscillator frequency tolerance, in % (0 if synchronized)
--fband  upper edge of the analysis band: a tone closer than fband to k·f_MOD lands in the band
--guard  extra margin beyond fband (default 40 kHz)
--fdata  ADC output data rate: with --tol 0, checks whether f_sw is an integer multiple of it
         (harmonics land on the sinc filter notches)
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fsw", type=float, required=True)
    ap.add_argument("--tol", type=float, default=10.0)
    ap.add_argument("--fmod", type=float, required=True)
    ap.add_argument("--fband", type=float, required=True)
    ap.add_argument("--fdata", type=float, default=None)
    ap.add_argument("--nmax", type=int, default=40)
    ap.add_argument("--kmax", type=int, default=5)
    ap.add_argument("--guard", type=float, default=40e3)
    a = ap.parse_args()

    zone = a.fband + a.guard
    tol = a.tol / 100
    print(f"# f_sw = {a.fsw/1e3:.3f} kHz ±{a.tol:g} %, f_MOD = {a.fmod/1e6:.4g} MHz, forbidden zone = ±{zone/1e3:.1f} kHz around k·f_MOD\n")
    hits = []
    for n in range(1, a.nmax + 1):
        lo, hi = n * a.fsw * (1 - tol), n * a.fsw * (1 + tol)
        for k in range(1, a.kmax + 1):
            c = k * a.fmod
            if hi >= c - zone and lo <= c + zone:
                nominal_dist = n * a.fsw - c
                hits.append((n, k, lo, hi, nominal_dist))
    synced_ok = False
    if a.fdata and a.tol == 0:
        # synchronized: the tone aliases to |n·fsw − k·fmod| mod f_data; on a notch if it is a multiple of f_data
        def on_notch(d):
            r = abs(d) % a.fdata
            return min(r, a.fdata - r) < 1e-6 * a.fdata
        before = len(hits)
        hits = [h for h in hits if not on_notch(h[4])]
        synced_ok = before > 0 and not hits
    if synced_ok:
        print("**PASS (synchronized)**: every harmonic near k·f_MOD lands on a sinc notch "
              "(distance is a multiple of f_data).")
    elif hits:
        print("| Harmonic n | k | Harmonic range (kHz) | Nominal distance to k·f_MOD (kHz) |")
        print("|---|---|---|---|")
        for n, k, lo, hi, d in hits:
            print(f"| {n} | {k} | {lo/1e3:.1f} – {hi/1e3:.1f} | {d/1e3:+.1f} |")
        print(f"\n**FAIL**: {len(hits)} harmonic(s) up to n = {a.nmax} may fall in the forbidden zone.")
    if not hits and not synced_ok:
        print(f"**PASS**: no harmonic up to n = {a.nmax} (k ≤ {a.kmax}) enters the forbidden zone.")

    if a.fdata:
        ratio = a.fsw / a.fdata
        integer = abs(ratio - round(ratio)) < 1e-9
        print(f"\nf_sw / f_data = {ratio:.6g} → {'an integer multiple' if integer else 'NOT an integer multiple'} of the data rate.")
        if a.tol > 0:
            print("Free-running: nominal coincidence does not hold, because the real frequency varies with tolerance.")


if __name__ == "__main__":
    main()
