#!/usr/bin/env python
"""stop_rule.py - the stop rule for scripted finishing runs (lesson L30, Vladimir Duk, ServiceOne D133, 2026-10-22).

A scripted run is estimated before it starts and watched while it runs. After the first CHECK_AFTER attempts (default
10) or CHECK_MINUTES (default 30), the run stops when fewer than MIN_RATE of the attempts were kept (default 1 in 5),
or when the projected time for the attempts left exceeds the budget agreed with the designer (default 60 min). The
driver then reports what it kept and hands the rest to the interactive router with a list of ends. Grinding on is
wasted time and tokens: ServiceOne D133 spent 3.5 h for 5 kept routes out of 74 attempts.

Module API (system Python, no pcbnew):
    rule = StopRule(budget_min=60, min_rate=0.2, check_after=10, check_minutes=30)
    print(rule.estimate(n_items, attempts_per_item=1.5, minutes_per_attempt=0.5))   # before the run
    rule.attempt(kept)                     # after every attempt
    why = rule.should_stop(items_left)     # None, or the reason to stop
    rule.summary()
Drivers take --budget MIN, --min-keep-rate R and --no-stop-rule (experiments only).

Self-test: python stop_rule.py --selftest
"""
import sys
import time


class StopRule:
    def __init__(self, budget_min=60.0, min_rate=0.2, check_after=10, check_minutes=30.0, clock=time.monotonic):
        self.budget = float(budget_min)
        self.min_rate = float(min_rate)
        self.check_after = int(check_after)
        self.check_minutes = float(check_minutes)
        self.clock = clock
        self.t0 = clock()
        self.tried = 0
        self.kept = 0

    @classmethod
    def from_argv(cls, argv, **kw):
        """--budget MIN, --min-keep-rate R from a driver's argument list; None with --no-stop-rule."""
        if '--no-stop-rule' in argv:
            return None
        opt = lambda n, d: argv[argv.index(n) + 1] if n in argv and argv.index(n) + 1 < len(argv) else d
        return cls(budget_min=float(opt('--budget', kw.pop('budget_min', 60))),
                   min_rate=float(opt('--min-keep-rate', kw.pop('min_rate', 0.2))), **kw)

    def minutes(self):
        return (self.clock() - self.t0) / 60.0

    def estimate(self, n_items, attempts_per_item=1.0, minutes_per_attempt=0.5):
        m = n_items * attempts_per_item * minutes_per_attempt
        return ('estimate: %d item(s) x %.1f attempt(s) x %.1f min = %.0f min (budget %.0f min)%s' % (
            n_items, attempts_per_item, minutes_per_attempt, m, self.budget,
            ' - over budget: agree a budget with the designer or run a sample first' if m > self.budget else ''))

    def attempt(self, kept):
        self.tried += 1
        self.kept += 1 if kept else 0

    def should_stop(self, items_left=0):
        t = self.minutes()
        if t > self.budget:
            return 'budget of %.0f min spent (%.0f min, %d of %d kept)' % (self.budget, t, self.kept, self.tried)
        if self.tried < self.check_after and t < self.check_minutes:
            return None
        if self.tried and self.kept / self.tried < self.min_rate:
            return 'keep rate %d of %d (%.0f %%) is below %.0f %% after %.0f min' % (
                self.kept, self.tried, 100.0 * self.kept / self.tried, 100 * self.min_rate, t)
        if self.tried and items_left:
            proj = t + items_left * t / self.tried
            if proj > self.budget:
                return 'projected %.0f min for %d item(s) left exceeds the %.0f min budget' % (
                    proj, items_left, self.budget)
        return None

    def summary(self):
        return 'stop rule: %d of %d attempt(s) kept in %.0f min (budget %.0f min, minimum keep rate %.0f %%)' % (
            self.kept, self.tried, self.minutes(), self.budget, 100 * self.min_rate)


def _selftest():
    now = [0.0]
    clock = lambda: now[0] * 60.0
    ok = 0
    r = StopRule(budget_min=60, clock=clock)
    for _ in range(9):
        r.attempt(False)
    assert r.should_stop(50) is None; ok += 1                         # fewer than 10 attempts, under 30 min
    r.attempt(False)
    assert 'keep rate' in r.should_stop(50); ok += 1                  # 0 of 10
    r = StopRule(budget_min=60, clock=clock)
    for i in range(10):
        r.attempt(i % 2 == 0)
    now[0] = 10.0
    assert r.should_stop(10) is None; ok += 1                         # 5 of 10, 10 min, 10 left -> 20 min projected
    assert 'projected' in r.should_stop(100); ok += 1                 # 100 left -> 110 min projected
    now[0] = 61.0
    assert 'budget' in r.should_stop(0); ok += 1
    now[0] = 0.0
    r = StopRule(budget_min=60, clock=clock)
    now[0] = 62.0
    assert 'budget' in r.should_stop(0); ok += 1
    assert StopRule.from_argv(['b.kicad_pcb', '--no-stop-rule']) is None; ok += 1
    s = StopRule.from_argv(['b.kicad_pcb', '--budget', '15', '--min-keep-rate', '0.5'])
    assert s.budget == 15 and s.min_rate == 0.5; ok += 1
    assert 'over budget' in StopRule(budget_min=10).estimate(40, 1, 0.5); ok += 1
    print('stop_rule self-test: %d passed' % ok)


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        _selftest()
    else:
        sys.stdout.write(__doc__)
