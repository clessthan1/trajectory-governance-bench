# -*- coding: utf-8 -*-
"""run_baselines.py — 궤적 거버넌스 벤치 베이스라인 러너(독립 실행).

A팔(맨 모델·창 12턴)과 B팔(RAG·전 턴 임베딩 top-6)을 OpenAI 호환 API로 재실행하고,
C 자리에는 *당신의 기억/거버넌스 층*을 꽂을 수 있다(YOUR_LAYER 구현 — 기본은 건너뜀).

사용:  OPENAI_API_KEY 설정 후
       python run_baselines.py scenarios_v5_fresh.json my_results.jsonl
채점:  python grade.py scenarios_v5_fresh.json my_results.jsonl

프로토콜(우리 실행과 동일): 모델 gpt-4o-mini · A 창=마지막 12턴 · B k=6(text-embedding-3-small)
· 질문은 궤적 상태에 독립적으로 각각 던짐 · max_tokens 180.
"""
import io
import json
import math
import os
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

from openai import OpenAI

MODEL = "gpt-4o-mini"
EMB = "text-embedding-3-small"
WINDOW, RAG_K = 12, 6
cli = OpenAI()


def gen(system, user):
    r = cli.chat.completions.create(model=MODEL, max_tokens=180, messages=[
        {"role": "system", "content": system}, {"role": "user", "content": user}])
    return r.choices[0].message.content or ""


def embed(texts):
    r = cli.embeddings.create(model=EMB, input=texts)
    return [d.embedding for d in r.data]


def cos(u, v):
    s = sum(x * y for x, y in zip(u, v))
    return s / ((math.sqrt(sum(x * x for x in u)) or 1) * (math.sqrt(sum(y * y for y in v)) or 1))


def YOUR_LAYER(turns, question):
    """C 자리 — 당신의 기억/거버넌스 층. turns(사용자 발화 시간순)를 먹이고 question에 답하라.
    None을 반환하면 C팔은 건너뛴다(A/B만 기록)."""
    return None


def main(scen_path, out_path):
    trajs = json.load(open(scen_path, encoding="utf-8"))
    out = open(out_path, "a", encoding="utf-8")
    for tj in trajs:
        turns = tj["turns"]
        vecs = embed([t[:500] for t in turns])
        for q in tj["qs"]:
            qv = embed([q["q"]])[0]
            ranked = sorted(zip(range(len(turns)), turns, vecs),
                            key=lambda x: cos(qv, x[2]), reverse=True)[:RAG_K]
            hits = sorted([(i, t) for i, t, _v in ranked])
            ans_a = gen("당신은 개인 비서다. 아래는 사용자와의 최근 대화 기록이다(오래된 앞부분은 "
                        "잘려 없음).\n[최근 대화]\n"
                        + "\n".join(f"- \"{t}\"" for t in turns[-WINDOW:])
                        + "\n기록에 근거해 짧고 정확하게 한국어로 답하라.", q["q"])
            ans_b = gen("당신은 개인 비서다. 아래는 과거 대화에서 질문과 관련해 검색된 발췌다"
                        "(턴 번호=시간순).\n[검색 발췌]\n"
                        + "\n".join(f"- [턴 {i+1}] \"{t}\"" for i, t in hits)
                        + "\n기록에 근거해 짧고 정확하게 한국어로 답하라.", q["q"])
            ans_c = YOUR_LAYER(turns, q["q"])
            row = {"tid": tj["tid"], "qid": q["qid"], "axis": q["axis"], "q": q["q"],
                   "a": {"ans": ans_a[:300], "ok": None},
                   "b": {"ans": ans_b[:300], "ok": None},
                   "c": {"ans": (ans_c or "")[:300], "ok": None}}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            print(tj["tid"], q["qid"], "완료")
    out.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
