"""Report the plane pads that have no room for their own via, for the source placement
of a model and for candidate files.

    python via_room_report.py MODEL.json [CAND.json ...]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate as ev  # noqa: E402

model = json.load(open(sys.argv[1], encoding="utf-8"))
m, _ = ev.evaluate(model)
print("%-28s %3d of %d plane pads without via room" % ("source placement", m["via_starved"], m["via_pads"]))
for f in sys.argv[2:]:
    c = json.load(open(f, encoding="utf-8"))
    m, _ = ev.evaluate(model, c.get("placement", c))
    print("%-28s %3d of %d  %s" % (os.path.basename(f), m["via_starved"], m["via_pads"],
                                   " ".join(m["via_starved_list"][:14])))
