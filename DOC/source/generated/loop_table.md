| Loop current | Shunt voltage | ADS1115 code (+-4.096 V) | Meaning (NAMUR NE43) |
|---|---|---|---|
| 3.6 mA | 0.432 V | 3456 | below: open loop |
| 4.0 mA | 0.480 V | 3840 | zero of the range |
| 12.0 mA | 1.440 V | 11520 | mid scale |
| 20.0 mA | 2.400 V | 19200 | full scale |
| 21.0 mA | 2.520 V | 20160 | above: short circuit |
| 22.0 mA | 2.640 V | 21120 |  |

Source: `calc/checkone_budget.py` item 1 (120 ohm shunt, LSB 125.0 uV = 1.04 uA per count; input filter 4.7 k / 10 nF 3.4 kHz).
