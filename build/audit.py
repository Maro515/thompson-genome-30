#!/usr/bin/env python3
"""内容監査: 各Dayの密度・話者バランス・note種別・focus項目のカバー率を出す。

  python3 build/audit.py            # 表
  python3 build/audit.py -v         # focus 未カバー語も表示
"""
import json, os, re, sys, unicodedata

ROOT = os.path.dirname(os.path.abspath(__file__))
V = "-v" in sys.argv


def flat_text(d):
    out = [d.get("title", ""), d.get("subtitle", "")]
    out += d.get("goals") or []
    for k in d.get("keywords") or []:
        out += [k.get("term", ""), k.get("en", ""), k.get("def", "")]
    for s in d.get("scenes") or []:
        out.append(s.get("heading", ""))
        for b in s.get("blocks") or []:
            t = b.get("t")
            if t == "talk":
                out.append(b.get("text", ""))
            elif t == "note":
                out += [b.get("title", ""), b.get("body", "")]
            elif t == "list":
                out.append(b.get("title", "") or "")
                out += b.get("items") or []
            elif t == "fig":
                out.append(b.get("caption", "") or "")
                out.append(json.dumps(b.get("data") or {}, ensure_ascii=False))
    out += d.get("summary") or []
    for q in d.get("quiz") or []:
        out += [q.get("q", ""), q.get("explain", "")] + (q.get("choices") or [])
    for c in d.get("cards") or []:
        out += [c.get("q", ""), c.get("a", "")]
    out.append(d.get("next", "") or "")
    return "\n".join(map(str, out))


def focus_terms(focus):
    """focus 文字列から照合用の語を切り出す。括弧内・読点・スラッシュで分割。"""
    s = re.sub(r"[（()）]", "／", focus)
    parts = re.split(r"[／/、,。\s]+", s)
    terms = []
    for p in parts:
        p = p.strip("・:=＝").strip()
        if len(p) < 3:
            continue
        if re.fullmatch(r"[0-9.\-–—]+", p):
            continue
        if p in ("など", "その他", "の原理", "の基礎", "全体", "および"):
            continue
        terms.append(p)
    return terms


def norm(s):
    return unicodedata.normalize("NFKC", s).lower().replace(" ", "")


def covered(term, nt):
    """語が本文に現れているか。長い記述的フレーズは構成要素の8割一致で可とする。"""
    if norm(term) in nt:
        return True
    chunks = [c for c in re.split(r"[のとにをはがへや・=＝:：0-9]+", term) if len(c) >= 2]
    if len(chunks) < 2:
        return False
    hit = sum(1 for c in chunks if norm(c) in nt)
    # 長い記述的フレーズほど逐語一致しないので、構成要素の過半一致で「扱っている」とみなす
    need = 0.8 if len(chunks) == 2 else (0.66 if len(chunks) == 3 else 0.6)
    return hit / len(chunks) >= need


def main():
    plan = json.load(open(os.path.join(ROOT, "plan.json"), encoding="utf-8"))
    rows, problems = [], []
    for pd in plan["days"]:
        fp = os.path.join(ROOT, "days", "day%02d.json" % pd["day"])
        if not os.path.exists(fp):
            problems.append("Day %2d: MISSING FILE" % pd["day"])
            continue
        d = json.load(open(fp, encoding="utf-8"))
        blocks = [b for s in d.get("scenes") or [] for b in s.get("blocks") or []]
        talks = [b for b in blocks if b.get("t") == "talk"]
        notes = [b for b in blocks if b.get("t") == "note"]
        figs = [b for b in blocks if b.get("t") == "fig"]
        who = {}
        for b in talks:
            who[b.get("who")] = who.get(b.get("who"), 0) + 1
        txt = flat_text(d)
        nt = norm(txt)
        terms = focus_terms(pd["focus"])
        miss = [t for t in terms if not covered(t, nt)]
        cov = 100 * (len(terms) - len(miss)) / max(1, len(terms))
        rows.append(dict(
            day=pd["day"], chars=len(txt), sc=len(d.get("scenes") or []), tk=len(talks),
            fg=len(figs), nt_=len(notes), qz=len(d.get("quiz") or []), cd=len(d.get("cards") or []),
            kw=len(d.get("keywords") or []), sm=len(d.get("summary") or []), cs=len(d.get("cases") or []),
            cov=cov, miss=miss, who=who,
            kinds=sorted({b.get("kind") for b in figs}),
            nkinds=sorted({b.get("kind") for b in notes}),
        ))
        p = "Day %2d" % pd["day"]
        if len(txt) < 11000:
            problems.append(f"{p}: thin ({len(txt)} chars < 11000)")
        if len(talks) < 30:
            problems.append(f"{p}: only {len(talks)} talk blocks (<30)")
        if len(figs) < 3:
            problems.append(f"{p}: only {len(figs)} figures (<3)")
        if "analogy" not in {b.get("kind") for b in notes}:
            problems.append(f"{p}: no analogy note")
        if len(d.get("quiz") or []) < 5:
            problems.append(f"{p}: only {len(d.get('quiz') or [])} quiz items")
        if len(d.get("cards") or []) < 6:
            problems.append(f"{p}: only {len(d.get('cards') or [])} cards")
        if who.get("hikari", 0) < 8:
            problems.append(f"{p}: hikari speaks only {who.get('hikari',0)}x (<8)")
        for k in ("kirihara", "sora", "haru"):
            if who.get(k, 0) < 2:
                problems.append(f"{p}: {k} speaks only {who.get(k,0)}x")
        ans = [q.get("answer") for q in d.get("quiz") or []]
        if ans and len(set(ans)) == 1:
            problems.append(f"{p}: every quiz answer is index {ans[0]}")
        if cov < 55:
            problems.append(f"{p}: focus coverage {cov:.0f}% — missing {len(miss)}/{len(terms)}")

    print("day chars  sc  tk  fg  nt  qz  cd  kw  sm  cs  focus%  figure kinds")
    print("(focus% は plan.json の focus 語句が本文に現れるかの目安。長い記述句は逐語一致しないため過小に出る)")
    print("-" * 96)
    for r in rows:
        print("%3d %5d %3d %3d %3d %3d %3d %3d %3d %3d %3d  %5.0f%%  %s" % (
            r["day"], r["chars"], r["sc"], r["tk"], r["fg"], r["nt_"], r["qz"], r["cd"],
            r["kw"], r["sm"], r["cs"], r["cov"], ",".join(r["kinds"])))
    if rows:
        tot = sum(r["chars"] for r in rows)
        print("-" * 96)
        print("days=%d  total=%s chars  avg=%d  figures=%d  quiz=%d  cards=%d" % (
            len(rows), f"{tot:,}", tot // len(rows), sum(r["fg"] for r in rows),
            sum(r["qz"] for r in rows), sum(r["cd"] for r in rows)))
        allkinds = {}
        for r in rows:
            for k in r["kinds"]:
                allkinds[k] = allkinds.get(k, 0) + 1
        print("figure kind usage:", ", ".join(f"{k}×{v}" for k, v in sorted(allkinds.items(), key=lambda x: -x[1])))
        allw = {}
        for r in rows:
            for k, v in r["who"].items():
                allw[k] = allw.get(k, 0) + v
        print("speaker totals:", ", ".join(f"{k}={v}" for k, v in sorted(allw.items(), key=lambda x: -x[1])))

    print()
    if problems:
        print("---- %d problems ----" % len(problems))
        for x in problems:
            print(" *", x)
    else:
        print("no problems.")
    if V:
        for r in rows:
            if r["miss"]:
                print("\nDay %2d missing focus terms (%d):" % (r["day"], len(r["miss"])))
                print("   " + " / ".join(r["miss"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
