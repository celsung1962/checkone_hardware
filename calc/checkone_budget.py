#!/usr/bin/env python3
"""CheckOne v1 (import 2026-11-16): the numbers of the description checked against the v1 schematic.

  1. loop measurement: ADS1115 resolution per channel, shunt voltage, highest readable current, input filter;
  2. NTC inputs: divider voltage over the range, the 1 uF filter;
  3. fault "+24 V on Iin": current pushed into the 3V3A rail through the BAT54S clamp (not in the description);
  4. power budget of the 24 V supply.
Inputs marked ASSUMED are not in the description or in a datasheet on disk (docs/datasheets is still empty).
Run: python calc/checkone_budget.py
"""
import math

# 1. loop measurement (description 3, 5.2; schematic sheet canais / adcs)
R_SHUNT = 120.0          # ohm, 0.1 %
ADC_FSR = 4.096          # V, ADS1115 PGA +-4.096 V
ADC_BITS = 16
VDD_A = 3.3              # V, 3V3A (XC6206P332 + 10 ohm / 1 uF)
VF_BAT54S = 0.3          # V, ASSUMED clamp forward voltage at low current
R_SERIES, C_IN = 1e3, 10e-9

# 2. NTC (description 5.3)
NTC_R25, NTC_B, R_DIV, C_NTC = 100e3, 3950.0, 10e3, 1e-6

# 3. fault +24 V on Iin (description 5.2 / 9: SMAJ5.0A clamp 6.4 V in 5.2, 7.4 V in 9)
V_CLAMP_IIN = (6.4, 7.4)
I_3V3_LOAD = 3e-3        # A, ASSUMED total load of +3V3 / 3V3A (3 x ADS1115, INA226, RTC, LED3 via 1 k, pull-ups)
R_SERIES_ALT = 4.7e3     # ohm, proposed series resistor (review 2026-11-16, O4)
Z_DIFF, Z_CM = 15e6, 6e6  # ohm, ADS1115 at FSR +-4.096 V: differential 15 M (datasheet table), common mode ~6 M (text)

# 4. power budget
V_BUS = 24.0
I_SENSOR = 0.075         # A per sensor, ASSUMED (the mock-up data of the screen design uses 75 mA per sensor)
N_CH = 8
I_DISPLAY_5V = 0.4       # A at 5 V, ASSUMED (CYD backlight on; the description says "some hundred mA" for the 4.3")
ETA_BUCK = 0.85          # ASSUMED XL1509 efficiency at this load
I_SUPPLY = 2.0           # A, minimum supply rating (description 3)


def ntc_r(t_c):
    return NTC_R25 * math.exp(NTC_B * (1 / (t_c + 273.15) - 1 / 298.15))


def main():
    lsb = ADC_FSR / 2 ** (ADC_BITS - 1)
    print('1. Loop measurement')
    print(f'   ADS1115 LSB {lsb * 1e6:.1f} uV -> {lsb / R_SHUNT * 1e6:.2f} uA per count (description: ~1 uA)')
    for i in (0.0036, 0.004, 0.020, 0.021, 0.022):
        print(f'   {i * 1e3:4.1f} mA -> {i * R_SHUNT:.3f} V on the shunt')
    print(f'   highest readable current: input limited to VDD {VDD_A} V -> {VDD_A / R_SHUNT * 1e3:.1f} mA '
          f'(the +-4.096 V range is never reached; clamp starts near {(VDD_A + VF_BAT54S) / R_SHUNT * 1e3:.1f} mA)')
    print(f'   input filter 1 k / 10 nF: {1 / (2 * math.pi * R_SERIES * C_IN) / 1e3:.1f} kHz (description: ~16 kHz)')

    print('2. NTC inputs (10 k to 3V3A, NTC to GND)')
    for t in (-20, 25, 80, 140, 150):
        r = ntc_r(t)
        v = VDD_A * r / (r + R_DIV)
        print(f'   {t:4d} degC: R {r / 1e3:8.2f} k, V {v:.3f} V, {v / VDD_A * 100:5.1f} % of 3V3A')
    rth = 1 / (1 / R_DIV + 1 / NTC_R25)
    print(f'   1 uF filter at 25 degC: Rth {rth / 1e3:.2f} k -> {1 / (2 * math.pi * rth * C_NTC):.1f} Hz '
          f'(description: ~17 Hz)')

    print('3. +24 V wired to Iin: current into 3V3A through the series R and the BAT54S upper diode, per channel')
    z_in = 1 / (1 / Z_DIFF + 1 / Z_CM)
    for rs in (R_SERIES, R_SERIES_ALT):
        for vc in V_CLAMP_IIN:
            inj = (vc - VDD_A - VF_BAT54S) / rs
            print(f'   R {rs / 1e3:.1f} k, Iin clamped at {vc} V -> {inj * 1e3:.2f} mA into 3V3A (assumed rail load '
                  f'{I_3V3_LOAD * 1e3:.0f} mA): ' + ('the XC6206 cannot sink it, 3V3A / +3V3 rise until the PTC trips'
                                                    if inj > I_3V3_LOAD else 'absorbed by the load'))
        print(f'   R {rs / 1e3:.1f} k: gain error from the ADS1115 input impedance (~{z_in / 1e6:.1f} M) '
              f'{rs / z_in * 100:.3f} % (removed by the per-channel gain calibration); input filter '
              f'{1 / (2 * math.pi * rs * C_IN) / 1e3:.1f} kHz')

    print('4. Power budget')
    p_sens = V_BUS * I_SENSOR * N_CH
    i_buck_in = 5.0 * I_DISPLAY_5V / ETA_BUCK / V_BUS
    tot = I_SENSOR * N_CH + i_buck_in
    print(f'   sensors {N_CH} x {I_SENSOR * 1e3:.0f} mA = {I_SENSOR * N_CH:.2f} A ({p_sens:.1f} W); display via buck '
          f'{i_buck_in * 1e3:.0f} mA at 24 V; total {tot:.2f} A of {I_SUPPLY:.1f} A ({tot / I_SUPPLY * 100:.0f} %)')


if __name__ == '__main__':
    main()
