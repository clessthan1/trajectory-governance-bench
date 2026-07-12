# -*- coding: utf-8 -*-
"""grade.py — 궤적 거버넌스 벤치 재채점기(독립 실행·API 0).

공개된 원본 답변(results/*.jsonl)을 시나리오의 결정적 마커로 *다시* 채점해 집계를 재현한다.
저장된 ok 필드를 믿지 않고 답변 원문에서 재계산 — 채점 검증이 목적.

사용:  python grade.py scenarios_v5_fresh.json results/wm_traj_gov_v5_results.jsonl

주의: 이 재채점은 결정적(det) 판정만이다. 우리 최종 숫자는 여기에 "팔 간 판정이 갈린 문항의
전-팔 LLM 재판정"(README의 rubric, gpt-5.5)을 얹은 것이며, 다섯 판 모두 재판정이 CRA(C) 점수를
det보다 *낮췄다*(관대 편향 없음). det/최종 둘 다 HISTORY.md에 표기.
"""
import io
import json
import math
import re
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass


def norm(s):
    return re.sub(r"[\s\.,!?'\"‘’“”~…()\[\]]+", "", str(s).lower())


def judge(ans, groups, forb):
    a = norm(ans)
    if any(norm(t) in a for t in forb):
        return False
    return all(any(norm(t) in a for t in g) for g in groups)


def main(scen_path, res_path):
    trajs = json.load(open(scen_path, encoding="utf-8"))
    qmap = {(t["tid"], q["qid"]): q for t in trajs for q in t["qs"]}
    rows, seen = [], set()
    for line in open(res_path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if "error" in r or (r["tid"], r["qid"]) in seen or (r["tid"], r["qid"]) not in qmap:
            continue
        seen.add((r["tid"], r["qid"]))
        q = qmap[(r["tid"], r["qid"])]
        for arm in ("a", "b", "c"):
            r[arm]["ok"] = judge(r[arm]["ans"], q["groups"], q.get("forb", []))
        r["axis"] = q["axis"]
        rows.append(r)
    main_r = [r for r in rows if r["axis"] in ("review", "audit")]
    aux = [r for r in rows if r["axis"] in ("past", "premise", "validtime")]
    rec = [r for r in rows if r["axis"] == "recall"]
    print(f"문항 {len(rows)} (주축 {len(main_r)}·보조 {len(aux)}·대조 {len(rec)}) — det 재채점\n")
    acc = {}
    for arm in ("a", "b", "c"):
        acc[arm] = round(sum(r[arm]["ok"] for r in main_r) / max(1, len(main_r)), 3)
    print(f"주축: A {acc['a']} · B {acc['b']} · C {acc['c']} · Δ(C-max) "
          f"{round(acc['c'] - max(acc['a'], acc['b']), 3):+}")
    for label, rs in (("보조", aux), ("대조 회상", rec)):
        print(f"{label}: " + " · ".join(
            f"{arm.upper()} {round(sum(r[arm]['ok'] for r in rs) / max(1, len(rs)), 3)}"
            for arm in ("a", "b", "c")))
    n10 = sum(1 for r in main_r if r["c"]["ok"] and not r["b"]["ok"])
    n01 = sum(1 for r in main_r if r["b"]["ok"] and not r["c"]["ok"])
    n = n10 + n01
    p = sum(math.comb(n, k) for k in range(n10, n + 1)) / (2 ** n) if n else 1.0
    print(f"대응쌍(C vs B, 주축): C만 {n10} · B만 {n01} · 방향 이항 p={round(p, 5)}")
    by = {}
    for r in rows:
        by.setdefault(r["axis"], []).append(r)
    for ax, rs in sorted(by.items()):
        print(f"  [{ax}] " + " · ".join(
            f"{arm.upper()} {sum(r[arm]['ok'] for r in rs)}/{len(rs)}" for arm in ("a", "b", "c")))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
