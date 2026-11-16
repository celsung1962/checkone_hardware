# JLCPCB parts summary - CheckOne rev 1.1

Query: 2026-11-16 17:27, jlcpcb.com parts library API and lcsc.com product API (catalog data in `parts.csv`).

| Class | Distinct lines | Parts per board |
|---|---|---|
| Basic | 17 | 82 |
| Preferred | 5 | 22 |
| Extended | 14 | 46 |

THT parts are bought from LCSC and hand-soldered (CLAUDE.md 4.1): DC-005-A200, KF2EDGRC-5.08-4P, B2B-XH-A, PZ254V-11-04P, BS-02-A1AJ006.

## Preferred / Extended lines and why

| LCSC | Part | Class | Qty/board | JLCPCB stock | Reason |
|---|---|---|---|---|---|
| C46550417 | JVJ50V220M10x10 | Extended | 6 | 155472 | 220 uF 50 V electrolytic bulk (input, filter, buck); no Basic part at 50 V |
| C19077578 | SMBJ24A | Preferred | 1 | 48400 | Preferred: input TVS 24 V (D5) |
| C18198337 | 1812L160/30GR | Extended | 1 | 15697 | input PTC 1.6 A 1812 (D5); no Basic resettable fuse at this rating |
| C720557 | DC-005-A200 | Extended | 1 | 80177 | DC jack (D5), THT, hand-soldered |
| C20415548 | FCH1040-680M | Extended | 2 | 1498 | 68 uH 10x10 power inductor (pi filter, buck); no Basic inductor at this value and current |
| C5334068 | AO4485 | Extended | 1 | 17760 | P-MOSFET soft start (D5); no Basic part with this Vds / Rds(on) |
| C49851 | INA226AIDGSR | Extended | 1 | 62990 | INA226 current / voltage monitor (D2); no Basic equivalent |
| C2925443 | SMAJ5.0A | Preferred | 8 | 97659 | Preferred: loop input TVS 5 V (D7) |
| C7420333 | BAT54S | Preferred | 10 | 441293 | Preferred: ADC input clamp (D7) |
| C516070 | JK-SMD0805-020-30V | Extended | 8 | 377248 | channel PTC 200 mA 0805 (D7); no Basic resettable fuse at this rating |
| C441238 | KF2EDGRC-5.08-4P | Extended | 8 | 6339 | channel terminal (D8), THT, hand-soldered |
| C2989146 | TC0625B1200T5J | Extended | 8 | 2222 | 120 ohm 0.1 % 25 ppm loop shunt (D1); precision part, no Basic; LCSC store stock 0 on the query date; JLCPCB stock 2222 |
| C158012 | B2B-XH-A(LF)(SN) | Extended | 2 | 481977 | NTC connector JST XH, THT, hand-soldered |
| C37593 | ADS1115IDGSR | Extended | 3 | 8682 | ADS1115 16-bit ADC (D2); no Basic equivalent |
| C964745 | BS-02-A1AJ006 | Extended | 1 | 24230 | CR2032 holder, THT, hand-soldered |
| C7502705 | BAT54W | Preferred | 2 | 97390 | Preferred: RTC supply OR diodes |
| C668611 | 1.25-4P LT | Extended | 3 | 40293 | display I2C / 5 V connector (D4); no Basic 1.25 mm connector |
| C2691448 | PZ254V-11-04P | Extended | 1 | 893296 | external display header (D4), THT, hand-soldered |
| C7440 | PCF8563T/5,518 | Preferred | 1 | 91830 | Preferred: PCF8563 RTC (D2) |

## Stock notes

- C25804 0603WAF1002T5E: JLCPCB stock 42000084
- C1017 GZ2012D601TF: not listed in the LCSC store on the query date (JLCPCB library only)
- C2989146 TC0625B1200T5J: JLCPCB stock 2222
- JLCPCB stock below 10 x a 5-board batch: none
