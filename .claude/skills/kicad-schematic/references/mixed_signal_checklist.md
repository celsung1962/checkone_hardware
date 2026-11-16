# Design and review checklist — mixed-signal acquisition (ADC + MCU)

Real pitfalls, each with its reason. Use it when reviewing the brief and every sheet. For each item the accepted answer is "verified, with calculation/source" or "not applicable, because…".

## Contents
1. Clock tree
2. ADC synchronization and reset
3. SPI bus and timing
4. Power and switching frequency
5. MCU: pins, power domains and strapping
6. Analog front-ends
7. Assembly options and reuse
8. Testability

## 1. Clock tree

- **Common root.** If the ADC datasheet requires CLKIN and SCLK to be coherent (many ΔΣ parts do), both must derive from the same PLL. A "cleaner" external oscillator for the ADC breaks that coherence.
- **The MCU crystal is untouchable** when peripherals depend on it (USB, Ethernet, core PLL). Changing its frequency to "make the ADC math work" usually overclocks the CPU or kills USB. Work backwards instead: pick the sample rate that an integer divider allows.
- **Integer divider and duty cycle.** Generate the ADC clock with a timer/PWM with an even period for exactly 50 %; check the minimum t_w(CLH/CLL) with margin. Fractional division creates period jitter.
- **Right generator peripheral.** It must offer a second channel phase-locked to the same timer if the sync pulse will also come from it. Check before choosing (e.g. an LED-PWM channel may not have this).
- **Star fanout** with an LVCMOS buffer, series resistor at the source and on each branch (22–33 Ω), matched branch lengths. The reason is signal integrity and EMI; a few ns of skew are irrelevant for simultaneous sampling at low frequency.
- **Count the outputs**: ADCs + sync flip-flop + test point. A 1:4 buffer is often not enough.

## 2. ADC synchronization and reset

- **Retime the sync pulse** with a flip-flop clocked by CLKIN itself, on the edge opposite to the ADC's sampling edge, to guarantee t_su. Without it the ADC flags resynchronization continuously.
- **Falling edge with a rising-edge flip-flop** (e.g. the LVC1G175 family) needs an inverter on the flip-flop clock — a detail architecture documents usually omit.
- **Reset held at power-on.** Tie the flip-flop CLR to a GPIO with a pull-down: the ADCs stay in reset until firmware releases them, after the clock is stable and t_POR has elapsed. This implements the start-up sequence in hardware, regardless of the MCU state.
- **Shared sync/reset pin**: pulse width decides (sync vs reset). Hardware cannot tell; document the limits in t_CLKIN on the sheet.
- Discard data for the filter settling time after a sync — note it on the sheet.

## 3. SPI bus and timing

- **t_p(SCDO)** (clock → data valid) limits SCLK. Compute the margin at the edge where the MCU samples, including trace delay and the MCU's internal routing (IO MUX vs GPIO matrix). Record the SCLK above which the margin disappears.
- **ADC DVDD** often changes the minimum t_c(SC): a higher DVDD may allow a faster SCLK.
- **Shared bus** only if DOUT goes high-impedance with CS high; check t_p(CSDOZ). Series resistor next to the source of each signal (SCLK/MOSI at the MCU, DOUT at the ADC), no stubs.
- **CS count per SPI controller** varies between controllers of the same MCU — check the SDK before allocating.
- **Bus occupancy**: bits per frame × rate ÷ SCLK; keep headroom for ISR/DMA latency.
- **Undecided read mechanism** (ISR, DMA via an alternative serial peripheral, parallel capture): draw per-ADC local nets, 0 Ω at the junction, extra DOUT lines to spare GPIOs through DNP 0 Ω. Switching becomes an assembly change only.

## 4. Power and switching frequency

- **A ΔΣ ADC repeats its response at multiples of f_MOD.** Switching tones near k·f_MOD alias straight into the band. Rule:
  - prefer converters with a SYNC input, synchronized by the MCU at an **integer multiple of the output data rate** (harmonics near k·f_MOD then land on the sinc notches);
  - without SYNC: fixed f_sw (no spread spectrum) and a script proving that the harmonics, **including oscillator tolerance**, stay away from k·f_MOD. With ±10 % tolerance, high harmonics sweep hundreds of kHz — free-running is rarely provable. Use `scripts/fsw_check.py`.
  - this also applies to the MCU core buck.
- **Dedicated analog rail** (low-noise LDO) for AVDD; sequencing that never applies a signal to an input before its rail is up (chained enables or power-good).
- Capacitors mandated by the datasheet (e.g. an internal-LDO CAP pin) with the exact value and the right ground; never tie that pin to a rail.
- A presence LED per rail and a PWR_FLAG on every on-board rail.

## 5. MCU: pins, power domains and strapping

- **High-speed peripherals on the IO MUX** (direct path) when available; the GPIO matrix adds delay.
- **A low-power core** only sees GPIOs of its own domain: signals it supervises (DRDY, wake) go to those pins.
- **Strapping**: nothing that forces a level during the reset sampling window; BOOT button on the boot-mode pin; beware of strap pins reused by a PHY (the PHY must be high-impedance during reset).
- **Alternate-function conflicts** (SD, RMII, SPI on overlapping pin sets): build the complete table and report conflicts instead of resolving them.
- Pins with default functions (USB, JTAG) must be released by register if reused — note it.
- Follow the MCU vendor's hardware design guidelines for power domains, core DC-DC, crystal, reset RC and unused interfaces.

## 6. Analog front-ends

- **ADC absolute input range** (not only the differential range): if it accepts voltages below ground, a ground-referenced bipolar signal enters without a level shift.
- **Usable full scale** with headroom (e.g. 1.0 V out of 1.2 V ≈ 1.6 dB) for overload and tolerances.
- **Fault current**: with op-amps on bipolar rails, the ADC input RC resistor must limit the current below the datasheet maximum at worst-case saturation; check the absolute voltage too.
- **ADC input impedance** × RC resistors → gain error; compute and record it (calibration compensates, but it must be known).
- **AAF**: 3rd-order Butterworth = unity-gain Sallen-Key with Q = 1 + a real pole in the ADC input RC. E96/E24 values with the response recomputed (`scripts/filter_design.py`); C0G throughout the path. Record the loss at the band edge and the rejection at the frequency that folds into the band.
- **AC coupling at low frequency**: for a loss ≤ X dB at f_min, f_c = f_min·√(10^(X/10) − 1). Film capacitor (not X7R: piezoelectric and lossy). Long time constant → fast-settle circuit at power-up.
- **Current-excited sensors** (e.g. IEPE accelerometers): compliance ≥ bias + swing; per-channel switchable source if the board will be reused; monitor the bias node for cable diagnostics.
- **4–20 mA loop**: precision burden resistor, swing up to the maximum fault current within full scale; reverse and overcurrent protection.
- **Zero-drift (chopper) op-amps** are great at DC; on wideband AC channels, check noise and chopping artifacts before using them.
- Input protection: TVS + series resistor, sized for the worst field voltage.

## 7. Assembly options and reuse

- If the hardware may serve another application (another standard, another sensor range), provide **two assembly options** on the same layout: parts exclusive to each option marked by variant/DNP. Examples: divider with an offset resistor for a unipolar range, switchable current source, spare channels conditioned as generic inputs.
- Identical channel sheets: one multi-instance file (one fix applies to all) versus one copy per instance (the pattern of some references) — decide and record it as a deviation from the reference if needed.

## 8. Testability

- Test points on every clock (at the IC pin), on sync before and after retiming, on DRDY, on rails.
- Coaxial (U.FL) test points on high-resolution channel inputs for noise measurements.
- DNP 0–10 pF footprints on clocks for edge tuning on the bench.
- A note on the root sheet listing the bench measurements that validate the critical decisions.
