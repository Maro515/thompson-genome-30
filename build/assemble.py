#!/usr/bin/env python3
"""build/shell.html + build/days/dayNN.json + build/plan.json -> index.html (single file, offline).

使い方:  python3 build/assemble.py
"""
import json, os, re, sys, unicodedata

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(os.path.dirname(ROOT), "index.html")

CHAR_KEYS = {"hikari", "kirihara", "sora", "haru", "rasen", "narr"}
FIG_KINDS = {"flow", "compare", "table", "stack", "pedigree", "formula", "seq", "bars", "svg"}
NOTE_KINDS = {"clinical", "analogy", "pitfall", "exam", "deep"}


def fail(msg):
    print("ERROR: " + msg)
    return 1


def validate_block(b, p):
    errs = []
    t = b.get("t")
    if t == "talk":
        if b.get("who") not in CHAR_KEYS:
            errs.append(f"{p}: unknown speaker {b.get('who')!r}")
        if not b.get("text"):
            errs.append(f"{p}: empty talk text")
    elif t == "note":
        if b.get("kind") not in NOTE_KINDS:
            errs.append(f"{p}: unknown note kind {b.get('kind')!r}")
        if not b.get("body"):
            errs.append(f"{p}: empty note body")
    elif t == "fig":
        if b.get("kind") not in FIG_KINDS:
            errs.append(f"{p}: unknown fig kind {b.get('kind')!r}")
        dd = b.get("data") or {}
        k = b.get("kind")
        if k == "table":
            head = dd.get("head") or []
            for r in dd.get("rows") or []:
                if head and len(r) != len(head):
                    errs.append(f"{p}: table row width {len(r)} != head {len(head)}")
        if k == "pedigree":
            ids = {n.get("id") for n in dd.get("nodes") or []}
            if not ids:
                errs.append(f"{p}: pedigree without nodes")
            for u in dd.get("unions") or []:
                for x in (u.get("p") or []) + (u.get("kids") or []):
                    if x not in ids:
                        errs.append(f"{p}: pedigree union refers to unknown node {x!r}")
        if k == "seq":
            seq = dd.get("seq") or ""
            for m in dd.get("marks") or []:
                if not (0 <= int(m.get("i", -1)) < len(seq)):
                    errs.append(f"{p}: seq mark index out of range")
        for need, key in (("bars", "bars"), ("flow", "steps"), ("compare", "cols"), ("stack", "layers")):
            if k == need and not dd.get(key):
                errs.append(f"{p}: {need} without {key}")
    elif t == "list":
        if not b.get("items"):
            errs.append(f"{p}: list without items")
    else:
        errs.append(f"{p}: unknown block type {t!r}")
    return errs


def validate(d, plan_day):
    errs = []
    p = f"Day {d.get('day')}"
    for k in ("day", "part", "chapter", "pages", "title"):
        if not d.get(k):
            errs.append(f"{p}: missing {k}")
    if d.get("day") != plan_day["day"]:
        errs.append(f"{p}: day mismatch vs plan")
    if len(d.get("scenes") or []) < 3:
        errs.append(f"{p}: needs >=3 scenes (got {len(d.get('scenes') or [])})")
    if len(d.get("quiz") or []) < 4:
        errs.append(f"{p}: needs >=4 quiz items")
    if len(d.get("cards") or []) < 4:
        errs.append(f"{p}: needs >=4 cards")
    if len(d.get("keywords") or []) < 5:
        errs.append(f"{p}: needs >=5 keywords")
    if len(d.get("summary") or []) < 4:
        errs.append(f"{p}: needs >=4 summary lines")
    for q in d.get("quiz") or []:
        n = len(q.get("choices") or [])
        if n < 3:
            errs.append(f"{p}: quiz choices <3")
        if not isinstance(q.get("answer"), int) or not (0 <= q["answer"] < n):
            errs.append(f"{p}: quiz answer index out of range: {q.get('answer')}")
        if not q.get("explain"):
            errs.append(f"{p}: quiz without explain")
    for si, sc in enumerate(d.get("scenes") or []):
        if not sc.get("heading"):
            errs.append(f"{p}: scene {si} without heading")
        for b in sc.get("blocks") or []:
            errs += validate_block(b, p)
    for c in d.get("cases") or []:
        if not isinstance(c.get("no"), int) or not (1 <= c["no"] <= 49):
            errs.append(f"{p}: case no out of range: {c.get('no')}")
    return errs


def validate_episode(e, plan):
    errs = []
    p = "Episode part %s" % e.get("part")
    part = next((x for x in plan["parts"] if x["no"] == e.get("part")), None)
    if not part:
        return [p + ": unknown part"]
    lo, hi = part["days"]
    if e.get("afterDay") != hi:
        errs.append(f"{p}: afterDay {e.get('afterDay')} should be {hi} (last day of the part)")
    for k in ("title", "blocks"):
        if not e.get(k):
            errs.append(f"{p}: missing {k}")
    if len(e.get("blocks") or []) < 12:
        errs.append(f"{p}: only {len(e.get('blocks') or [])} blocks (<12)")
    talks = [b for b in e.get("blocks") or [] if b.get("t") == "talk"]
    if len(talks) < 15:
        errs.append(f"{p}: only {len(talks)} talk blocks (<15)")
    for b in e.get("blocks") or []:
        errs += validate_block(b, p)
    for c in e.get("connects") or []:
        if not (lo <= c.get("day", -1) <= hi):
            errs.append(f"{p}: connects to Day {c.get('day')} outside this part ({lo}-{hi})")
    return errs


def main():
    plan = json.load(open(os.path.join(ROOT, "plan.json"), encoding="utf-8"))
    shell = open(os.path.join(ROOT, "shell.html"), encoding="utf-8").read()

    days, missing, errs = [], [], []
    for pd in plan["days"]:
        fp = os.path.join(ROOT, "days", "day%02d.json" % pd["day"])
        if not os.path.exists(fp):
            missing.append(pd["day"])
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception as e:
            errs.append("Day %d: JSON parse error: %s" % (pd["day"], e))
            continue
        d = {k: v for k, v in d.items() if k not in ("ch", "sections", "focus")}
        d["day"] = pd["day"]
        d["part"] = pd["part"]
        d.setdefault("chapter", pd["chapter"])
        d.setdefault("pages", pd["pages"])
        errs += validate(d, pd)
        days.append(d)

    days.sort(key=lambda x: x["day"])

    episodes = []
    for part in plan["parts"]:
        fp = os.path.join(ROOT, "episodes", "ep%d.json" % part["no"])
        if not os.path.exists(fp):
            continue
        try:
            e = json.load(open(fp, encoding="utf-8"))
        except Exception as ex:
            errs.append("Episode %d: JSON parse error: %s" % (part["no"], ex))
            continue
        errs += validate_episode(e, plan)
        episodes.append(e)
    episodes.sort(key=lambda x: x.get("part", 0))

    # inject PARTS from plan
    parts_js = json.dumps(
        [{"no": p["no"], "t": p["t"], "days": p["days"], "note": p["note"]} for p in plan["parts"]],
        ensure_ascii=False,
    )
    shell = re.sub(r"const PARTS = \[.*?\n\];", "const PARTS = " + parts_js + ";", shell, count=1, flags=re.S)
    if "const PARTS = [{" not in shell:
        errs.append("PARTS injection failed")

    data_js = json.dumps(days, ensure_ascii=False, separators=(",", ":"))
    marker = "const DAYS = /*__DAYS__*/[];"
    if marker not in shell:
        return fail("DAYS marker not found in shell.html")
    shell = shell.replace(marker, "const DAYS = " + data_js + ";")

    ep_marker = "const EPISODES = /*__EPISODES__*/[];"
    if ep_marker not in shell:
        return fail("EPISODES marker not found in shell.html")
    shell = shell.replace(ep_marker, "const EPISODES = " + json.dumps(episodes, ensure_ascii=False, separators=(",", ":")) + ";")

    if errs:
        print("---- validation problems (%d) ----" % len(errs))
        for e in errs[:80]:
            print(" *", e)
        if len(errs) > 80:
            print(" ... and %d more" % (len(errs) - 80))

    open(OUT, "w", encoding="utf-8").write(shell)
    chars = sum(len(json.dumps(d, ensure_ascii=False)) for d in days)
    print("built %s  (%d days + %d episodes, %.0f KB html, avg %d chars/day)" % (
        os.path.basename(OUT), len(days), len(episodes), os.path.getsize(OUT) / 1024, chars / max(1, len(days))))
    if missing:
        print("missing days:", ", ".join(map(str, missing)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
