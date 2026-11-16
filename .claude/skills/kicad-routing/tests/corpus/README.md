# Regression corpus — real boards

The synthetic fixtures in `run_tests.js` only contain defects their author already thought of.
The footprint-internal keepout bug survived three releases for exactly that reason: no synthetic
fixture had one. It took a real board, and a user noticing, to find it.

This directory is intentionally **empty of boards**. Point it at your own.

## Use

1. Copy boards in, each with its `.kicad_pro`, plus one `kicad_golden.project.json` for the
   directory. Copies are fine — nothing here is ever modified except `*.expected.json`.

   ```
   tests/corpus/board_a.kicad_pcb
   tests/corpus/board_a.kicad_pro
   tests/corpus/kicad_golden.project.json
   ```

2. Record today's audit as the expectation, once you believe it:

   ```
   python tests/run_corpus.py tests/corpus --record
   ```

3. Run it after any change to the skill:

   ```
   python tests/run_corpus.py tests/corpus
   ```

Drift in FAIL/WARN counts, the FAIL breakdown, or any tracked stat is reported. Drift is not
automatically wrong — if you improved a check, re-record. The point is that it is never silent.

## Choosing boards

Pick ones that differ from each other, not ones that pass. Useful variety: a 2-layer board, a
6-layer board, a board with footprint-internal keepouts, one with footprint-local clearance
overrides, one with differential pairs, one with a BGA. Each covers a branch the synthetic
fixtures do not.

Boards are not committed with the skill — they are yours, often proprietary, and large.
