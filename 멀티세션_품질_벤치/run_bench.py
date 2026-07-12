# -*- coding: utf-8 -*-
"""run_bench.py — 멀티세션 품질 벤치(011) 독립 재현 러너 (공개 재현본).

원 실행은 우리 내부 CRA 제품 코드(cra.kernel/cra.language_cortex/cra_timeline/cra_transcript 등)
로 돌렸다 — 그 부품들은 CRA 자체(비공개 제품)라 이 패키지에 포함하지 않는다(궤적 거버넌스 벤치
공개본과 같은 정책). 이 스크립트는 OpenAI API만으로 RAW팔·RAG팔을 재현하고, CRA 자리는
YOUR_LAYER(turns, question)에 자신의 기억/거버넌스 층을 꽂을 수 있게 열어뒀다.

★RAG팔에 관한 문서화된 단순화: 원 실행(B6 클래스, test_b6_governance.py)은 대화가 진행되는
동안 매 턴마다 응답까지 생성하며 로그를 쌓았다(비용이 크고, 최종 점수엔 로그 임베딩만 필요).
이 재현본은 결과-동등한 단순화판이다 — 전체 발화를 한 번에 배치 임베딩해두고, 질문마다
top-k(k=8) 코사인 유사도로 검색해 "최신 값을 우선하라"는 같은 시스템 프롬프트로 1회 생성한다.
검색+최신-우선 로직은 원본과 동일하다.

무엇을 재는지·프로토콜·우리 결과·한계는 README.md를 먼저 읽을 것 — 이 벤치는 회상 동급 시험이
아니라 ①F1 선후(시점감사의 실데이터 판) ②F2 갱신(later-wins)의 거버넌스 축이다.

사용 순서:
  1) sim_qbench011_prep.py   (AI Hub 011 데이터 필요 — README §5 신청 안내)
  2) sim_qbench011_replant_fix.py
  3) python run_bench.py [--qdir sim_banks/qbench011] [--n 10] [--model gpt-4o-mini]

OPENAI_API_KEY 필요. 문항 수(N=10 슈퍼사슬 기준 F1 10 + F2 10 = 20)만큼 생성 호출이 들고,
RAG팔 준비에 슈퍼사슬당 배치 임베딩 1회(발화 수만큼의 토큰)가 든다 — 데이터가 없으면 이 스크립트는
그 자체로는 실행할 수 없다(재현 절차 검증용 코드 공개이지, 데이터 재배포가 아니다).
"""
import argparse
import io
import json
import math
import os
import re
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

from openai import OpenAI

WINDOW = 12
RAG_K = 8
EMB_MODEL = "text-embedding-3-small"


# ── CRA 자리 — 당신의 기억/거버넌스 층. None을 반환하면 건너뛴다(RAW/RAG만 채점). ──
def YOUR_LAYER(turns, question):
    return None


# ── 1) 재료 적재(순수 로직 — 원 sim_qbench011_super.py의 load/chain_turns/build_supers와 동일) ──
def load(qdir):
    chains = {}
    with open(os.path.join(qdir, "chains.jsonl"), encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            chains[c["msid"]] = c
    qs = [json.loads(l) for l in open(os.path.join(qdir, "questions.jsonl"), encoding="utf-8")]
    return chains, qs


def chain_turns(qdir, chains, msid):
    turns = [json.loads(l)["t"] for l in
             open(os.path.join(qdir, "stores", f"{msid}.jsonl"), encoding="utf-8")]
    s4 = next((s for s in chains[msid]["sessions"] if s["s"] == 4), None)
    if s4:
        turns += [u["t"] for u in s4["utts"] if u["who"] == "user" and u["t"].strip()]
    return turns


def build_supers(qdir, chains, qs, n_super):
    """사슬 4개를 시간순으로 이어붙여 슈퍼사슬을 만든다(~100턴대 — 창 압박·주제 간섭 실재).
    문항은 첫 사슬(F2)과 첫·셋째 사슬(F1, 제시 순서는 슈퍼사슬마다 교대해 위치 편향 방지)."""
    msids = sorted(chains.keys())
    supers = []
    for gi in range(min(n_super, len(msids) // 4)):
        group = msids[gi * 4:(gi + 1) * 4]
        turns = []
        for m in group:
            turns += chain_turns(qdir, chains, m)
        first = group[0]
        probes = []
        f2 = next((q for q in qs if q["msid"] == first and q["family"] == "f2_갱신"), None)
        if f2:
            probes.append(f2)
        fa = [q for q in qs if q["msid"] == first and q["family"] == "f1_시점"]
        fb = [q for q in qs if q["msid"] == group[2] and q["family"] == "f1_시점"]
        if fa and fb:
            a, b = fa[0]["fact"][:18], fb[0]["fact"][:18]
            pair = (a, b) if gi % 2 == 0 else (b, a)
            probes.append({"family": "f1_선후",
                           "q": (f"내가 「{pair[0]}…」 얘기한 거랑 「{pair[1]}…」 얘기한 거, "
                                 "어느 쪽이 먼저였지?"),
                           "gold_first": a, "gold_later": b})
        supers.append({"sid": gi, "turns": turns, "probes": probes})
    return supers


# ── 2) 팔 구현 ──
class Cortex:
    def __init__(self, cli, model):
        self.cli, self.model = cli, model

    def generate(self, system, user, max_tokens=160):
        r = self.cli.chat.completions.create(
            model=self.model, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content or ""

    def embed(self, texts):
        r = self.cli.embeddings.create(model=EMB_MODEL, input=texts)
        return [d.embedding for d in r.data]


def cos(u, v):
    s = sum(x * y for x, y in zip(u, v))
    return s / ((math.sqrt(sum(x * x for x in u)) or 1) * (math.sqrt(sum(y * y for y in v)) or 1))


def rag_answer(cortex, turns, question):
    """B6 결과-동등 단순화판(모듈 docstring 참조): 배치 임베딩 1회 + top-k(8) 검색 + 최신-우선 프롬프트."""
    vecs = cortex.embed([t[:500] for t in turns]) if turns else []
    qv = cortex.embed([question])[0]
    ranked = sorted(zip(range(len(turns)), turns, vecs), key=lambda x: cos(qv, x[2]), reverse=True)[:RAG_K]
    hits = sorted([(i, t) for i, t, _v in ranked])
    sysm = ("You are an assistant with a memory log of what the user told you (retrieved below, "
            "may include OUTDATED values). If values CONFLICT, use the MOST RECENT one the user stated "
            "(turn number = time order). If the answer is not in memory, say you have no record — do "
            "not guess.\nRETRIEVED MEMORY:\n"
            + "\n".join(f"- [턴 {i+1}] \"{t}\"" for i, t in hits))
    return cortex.generate(sysm, question)


def raw_answer(cortex, turns, question):
    ctx = "\n".join(f"사용자: {t}" for t in turns[-WINDOW:])
    sysm = ("당신은 개인 비서다. 아래는 사용자와의 최근 대화다(오래된 앞부분은 잘려 없음).\n"
            "[최근 대화]\n" + ctx + "\n기록에 근거해 짧고 정확하게 한국어로 답하라.")
    return cortex.generate(sysm, question)


def score_f2(resp, gold, distractor):
    r = str(resp or "")
    nums = re.findall(r"\d+", r)
    return 1 if (gold in nums and distractor not in nums) else 0


def judge_f1(cortex, probe, resp):
    """★한계: 우리 실행의 F1 판정자는 궤적 거버넌스 벤치(v5)의 gpt-5.5 재판정과 달리 mini급
    모델(생성 팔과 동일 MODEL)이다 — README §5 정직 라벨 참조."""
    sysm = ("당신은 엄격한 채점자다. 질문은 두 발화 중 어느 쪽이 먼저였는지 묻는다. "
            "응답이 '먼저'로 지목한 쪽이 GOLD_FIRST와 같으면 YES, 아니면(반대·모름·회피 포함) NO만 출력.")
    msg = (f"질문: {probe['q']}\nGOLD_FIRST(먼저인 발화): 「{probe['gold_first']}」\n"
           f"다른 발화: 「{probe['gold_later']}」\n응답: {resp}\nYES or NO:")
    out = cortex.generate(sysm, msg, max_tokens=4) or ""
    return 1 if "yes" in out.lower() else 0


def run_super(cortex, qdir, sp):
    turns, probes = sp["turns"], sp["probes"]
    if not probes:
        return []
    f2p = next((p for p in probes if p["family"] == "f2_갱신"), None)
    item = re.search(r"내 (\S+) 지금", f2p["q"]).group(1) if f2p else None
    v_in_window = bool(item) and any(item in t and "개" in t for t in turns[-WINDOW:])

    out = []
    for p in probes:
        ans_raw = raw_answer(cortex, turns, p["q"])
        ans_rag = rag_answer(cortex, turns, p["q"])
        ans_cra = YOUR_LAYER(turns, p["q"])
        row = {"sid": sp["sid"], "family": p["family"], "v_in_window": v_in_window}
        if p["family"] == "f2_갱신":
            for arm, a in (("raw", ans_raw), ("rag", ans_rag)):
                row[arm] = score_f2(a, p["gold"], p["distractor"])
            row["cra"] = score_f2(ans_cra, p["gold"], p["distractor"]) if ans_cra is not None else None
        else:
            for arm, a in (("raw", ans_raw), ("rag", ans_rag)):
                row[arm] = judge_f1(cortex, p, a)
            row["cra"] = judge_f1(cortex, p, ans_cra) if ans_cra is not None else None
        row["ans"] = {"raw": str(ans_raw)[:70], "rag": str(ans_rag)[:70],
                       "cra": (str(ans_cra)[:70] if ans_cra is not None else None)}
        out.append(row)
    return out


# ── 3) 집계 + 사전등록 기준(코드 — 우리 본판·재현판에서 쓴 것과 동일, 정의서 (qqqq) 원문) ──
def verdict(agg, have_cra):
    if agg["n_f1"] < 8 or agg["n_f2"] < 8 or agg["v_in_window_rate"] > 0.2:
        return "INVALID-SETUP", "표본 미달 또는 창-노출 발생 — 결과 아님, 재진단할 것"
    if agg["f1"]["raw"] == agg["f1"]["rag"] and have_cra and agg["f1"].get("cra") == agg["f1"]["raw"]:
        return "INVALID-SETUP", "F1 전팔 동점 — 측정이 팔을 차별하지 못함"
    if not have_cra:
        return "N/A", "YOUR_LAYER가 비어 있음(CRA 자리 미채움) — RAW/RAG 숫자만 참고, 자신의 층을 꽂은 뒤 재실행할 것"
    ok = (agg["f1"]["cra"] - max(agg["f1"]["raw"], agg["f1"]["rag"]) >= 0.3
          and agg["f2"]["cra"] >= max(agg["f2"]["raw"], agg["f2"]["rag"]) - 0.1)
    return ("POSITIVE" if ok else "NEGATIVE",
            "F1: cra-max(raw,rag)>=0.3  AND  F2: cra>=max(raw,rag)-0.1 (사전등록 기준, 본판·재현판 불변)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdir", default=os.path.join("sim_banks", "qbench011"))
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--model", default="gpt-4o-mini")
    args = ap.parse_args()

    cli = OpenAI()
    cortex = Cortex(cli, args.model)

    chains, qs = load(args.qdir)
    supers = build_supers(args.qdir, chains, qs, args.n)
    print(f"슈퍼사슬 {len(supers)}개 · 평균 턴 "
          f"{sum(len(s['turns']) for s in supers)//max(len(supers),1)}")

    res = []
    for sp in supers:
        res += run_super(cortex, args.qdir, sp)
        print(f"  sid={sp['sid']} 완료")

    f1 = [r for r in res if r["family"] == "f1_선후"]
    f2 = [r for r in res if r["family"] == "f2_갱신"]
    have_cra = any(r["cra"] is not None for r in res)

    def avg(rows, arm):
        vals = [r[arm] for r in rows if r.get(arm) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    agg = {"n_f1": len(f1), "n_f2": len(f2),
           "v_in_window_rate": round(sum(1 for r in f2 if r["v_in_window"]) / max(len(f2), 1), 2),
           "f1": {a: avg(f1, a) for a in ("raw", "rag", "cra")},
           "f2": {a: avg(f2, a) for a in ("raw", "rag", "cra")}}
    v, why = verdict(agg, have_cra)

    print("\n" + "=" * 50)
    print(json.dumps(agg, ensure_ascii=False, indent=2))
    print(f"판정: {v}  ({why})")
    print("=" * 50)


if __name__ == "__main__":
    main()
