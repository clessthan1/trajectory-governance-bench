# -*- coding: utf-8 -*-
"""sim_qbench011_prep.py — 멀티세션 품질 벤치(011) 재료 준비 (2026-07-12, 공개 재현본).

목적: "CRA 층이 세션을 넘는 답변 품질을 올린다"를 재는 벤치의 데이터 준비 단계. 문항 축은
회상이 아니라 ①시점(F1: "언제 얘기했지?") ②갱신(F2: 값이 바뀌었을 때 최신값)이다. 이 스크립트는
재료만 만든다(대화 사슬 추출 + 문항 은행 생성) — RAW/RAG/CRA 3팔 실행은 run_bench.py.

전부 결정론(seed 42)·LLM API 금지·F: 원본 수정 금지(zipfile로 스트리밍 읽기만).

★공개본 안내: BASE_011 아래 경로는 우리 로컬 다운로드 위치다. 이 스크립트를 실행하려면
AI Hub(aihub.or.kr)에서 "011.일상대화 한국어 멀티세션 데이터"를 별도로 신청·수급한 뒤,
BASE_011을 자신의 다운로드 경로로 바꿔야 한다. 이 저장소에는 원본 데이터·추출본·은행
(chains.jsonl/questions.jsonl/stores/*.jsonl)이 포함돼 있지 않다 — AI Hub 라이선스가
재배포를 금지한다. 아래 로직은 seed 42로 결정론적이므로, 같은 데이터셋 버전에서 실행하면
같은 40개 사슬·120개 문항이 재생성된다(재현성의 근거).

★구조 정정(중요, 이전 작업자 sim_aihub_extract.py 코드 주석 및 실측 재확인):
  작업 지시서는 "S2/S3/S4 zip에 같은 multisessionID의 세션별 파일이 흩어져 있어 이어 붙여야
  한다"고 적었으나, 실제 데이터를 열어 재확인한 결과(TS4/VS4 zip 파일 하나를 통째로 까 봄)는
  반대다: TS_session4.zip(= VS_session4.zip) 안의 파일 하나는 그 멀티세션 대화의 세션 1~4
  전부를 sessionInfo 리스트에 "이미 누적"해서 담고 있다(session2 zip에 도달한 대화는 session2
  zip에만, session4까지 간 대화는 session4 zip에만 존재 — zip 간 multisessionID 교집합 실측
  0). 따라서 "S2·S3·S4 파일을 이어 붙이는" 과정 자체가 필요 없다: session4 zip(Training+
  Validation) 파일 하나에서 nthSession 2·3·4에 해당하는 sessionInfo 항목 3개를 그대로 꺼내면
  이미 사슬이다(세션1은 과제 지시대로 사용 안 함 — "세션1 원문은 별도 zip이 없다"는 지시 취지와
  결과적으로 부합: 세션1 데이터는 있지만 이 벤치 사슬에는 안 씀). 이 스크립트는 실측대로 만들며,
  원본 지시서의 "이어 붙이기" 문구는 틀렸다는 점을 README와 최종 보고에 명시한다(블랙박스 원칙
  — 막히면 원본을 대조).

산출 (sim_banks/qbench011/, 로컬 전용 — git·공개 배포 금지):
  chains.jsonl    — 사슬 40개, 원본 그대로(가공 없음)
  stores/{msid}.jsonl — S2·S3 user 발화만(+F2 심기 2줄, planted:true — 이 단계는 v1 파일럿
                       위치/문형이다. 본판·재현판은 replant_fix.py로 교정한 뒤 실행됐다.)
  questions.jsonl — F1(시점)·F2(갱신) 문항
  README_qbench011.md — 통계·표본·심기 규칙(생성 시 실제 데이터 발췌를 포함하므로 로컬 전용 —
                        절대 공개 배포하지 말 것)
"""
import json
import os
import random
import statistics
import zipfile

from kiwipiepy import Kiwi

SEED = 42
# ★로컬 경로 — 자신의 AI Hub 011 다운로드 위치로 바꿀 것
BASE_011 = r"F:\011.일상대화 한국어 멀티세션 데이터\3.개방데이터\1.데이터"
ZIPS_011_S4 = [
    os.path.join(BASE_011, "Training", "01.원천데이터", "TS_session4.zip"),
    os.path.join(BASE_011, "Validation", "01.원천데이터", "VS_session4.zip"),
]

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_banks", "qbench011")
STORES_DIR = os.path.join(OUT_DIR, "stores")

N_CHAINS = 40
UTT_SUM_MIN, UTT_SUM_MAX = 40, 200

ITEMS = ["우표", "엽서", "배지", "병뚜껑", "티켓"]
N1_LIST = [3, 5, 7, 9, 12]
GAP_LIST = [4, 6, 8]

NEG_MORPH = {
    ("않", "VX"), ("없", "VA"), ("아니", "VCN"), ("못", "MAG"), ("안", "MAG"),
}

kiwi = Kiwi()


def who_of(speaker):
    return "user" if speaker == "speaker1" else "other"


def load_candidates():
    """TS4+VS4 zip을 훑어 msid별 사슬(세션2·3·4 dialog) 후보를 만든다."""
    cands = {}  # msid -> {2:[{"who","t"}...], 3:[...], 4:[...]}
    for zpath in ZIPS_011_S4:
        with zipfile.ZipFile(zpath) as z:
            names = sorted(n for n in z.namelist() if n.endswith(".txt"))
            for name in names:
                obj = json.loads(z.read(name).decode("utf-8"))
                mid = obj.get("multisessionInfo", {}).get("multisessionID", "")
                if not mid or mid in cands:
                    continue  # 실측상 TS4/VS4 간 msid 중복 없음(방어적으로만 skip)
                sess_map = {}
                for sess in obj.get("sessionInfo", []):
                    nth = str(sess.get("nthSession"))
                    if nth not in ("2", "3", "4"):
                        continue
                    utts = []
                    for d in sess.get("dialog", []):
                        utt = d.get("utterance")
                        if not utt:
                            continue
                        utts.append({"who": who_of(d.get("speaker")), "t": utt})
                    sess_map[int(nth)] = utts
                if not all(k in sess_map for k in (2, 3, 4)):
                    continue  # 세션4까지 안 간 대화(이 파일 집합엔 원래 없어야 정상)
                total = sum(len(sess_map[k]) for k in (2, 3, 4))
                if UTT_SUM_MIN <= total <= UTT_SUM_MAX:
                    cands[mid] = sess_map
    return cands


def is_fact_candidate(utt_text):
    """F1 시점 문항용 '구체 사실 발화' 판정: NNG>=2·길이10~60·물음표 없음·부정 없음·#@없음."""
    t = utt_text.strip()
    if "#@" in t:
        return False
    if not (10 <= len(t) <= 60):
        return False
    if "?" in t:
        return False
    toks = kiwi.tokenize(t)
    nng = sum(1 for x in toks if x.tag == "NNG")
    if nng < 2:
        return False
    if any((x.form, x.tag) in NEG_MORPH for x in toks):
        return False
    return True


def pick_f1_candidates(sess_map):
    """S2·S3 user 발화 중 사실 후보를 최대 2개(세션 다양성 우선) 고른다. (msid, session)순 결정론."""
    pools = {}
    for s in (2, 3):
        pool = [u["t"] for u in sess_map[s] if u["who"] == "user" and is_fact_candidate(u["t"])]
        pools[s] = pool
    picks = []  # [(session, fact_text)]
    if pools[2]:
        picks.append((2, pools[2][0]))
    if pools[3]:
        picks.append((3, pools[3][0]))
    if len(picks) < 2:
        leftovers = [(2, u) for u in pools[2][1:]] + [(3, u) for u in pools[3][1:]]
        for s, u in leftovers:
            if len(picks) >= 2:
                break
            picks.append((s, u))
    return picks[:2]


def build_plant_lines(idx):
    item = ITEMS[idx % len(ITEMS)]
    n1 = N1_LIST[idx % len(N1_LIST)]
    gap = GAP_LIST[idx % len(GAP_LIST)]
    n2 = n1 + gap
    v1 = f"참, 나 요즘 {item} 모으고 있어. 지금까지 {n1}개 모았어."
    v2 = f"{item} 얘기하니까 생각났는데, 이제 {n2}개야."
    return item, n1, n2, v1, v2


def main():
    os.makedirs(STORES_DIR, exist_ok=True)

    cands = load_candidates()
    n_cand = len(cands)
    cand_totals = sorted(sum(len(v[k]) for k in (2, 3, 4)) for v in cands.values())
    print(f"[후보] 세션4까지 도달·발화합 {UTT_SUM_MIN}~{UTT_SUM_MAX} 사슬 후보: {n_cand}개")

    sorted_msids = sorted(cands.keys())
    rng = random.Random(SEED)
    sampled = rng.sample(sorted_msids, N_CHAINS)
    sampled.sort()  # 출력 순서 결정론 고정(내부 sample() 순서에 안 묶이게)

    chains_path = os.path.join(OUT_DIR, "chains.jsonl")
    questions_path = os.path.join(OUT_DIR, "questions.jsonl")

    chain_lens = []
    n_f1 = n_f2 = 0
    f1_samples = []
    f2_samples = []

    with open(chains_path, "w", encoding="utf-8") as fc, \
         open(questions_path, "w", encoding="utf-8") as fq:
        for idx, msid in enumerate(sampled):
            sess_map = cands[msid]
            total_utt = sum(len(sess_map[k]) for k in (2, 3, 4))
            chain_lens.append(total_utt)

            # 1) chains.jsonl — 원본 그대로(가공 없음)
            chain_rec = {
                "msid": msid,
                "sessions": [
                    {"s": s, "utts": sess_map[s]} for s in (2, 3, 4)
                ],
            }
            fc.write(json.dumps(chain_rec, ensure_ascii=False) + "\n")

            # 2) F1 시점 문항 (사슬당 최대 2개)
            f1_picks = pick_f1_candidates(sess_map)
            for gold_session, fact in f1_picks:
                head = fact.strip()[:20]
                q = f"내가 「{head}…」 얘기한 게 몇 번째 세션이었지?"
                rec = {"msid": msid, "family": "f1_시점", "fact": fact,
                       "q": q, "gold_session": gold_session}
                fq.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_f1 += 1
                if len(f1_samples) < 5:
                    f1_samples.append(rec)

            # 3) F2 갱신 심기 + 문항
            item, n1, n2, v1, v2 = build_plant_lines(idx)
            f2_rec = {"msid": msid, "family": "f2_갱신", "q": f"내 {item} 지금 몇 개까지 모았지?",
                       "gold": str(n2), "distractor": str(n1)}
            fq.write(json.dumps(f2_rec, ensure_ascii=False) + "\n")
            n_f2 += 1
            if len(f2_samples) < 5:
                f2_samples.append({**f2_rec, "v1": v1, "v2": v2})

            # 4) store 재료 — S2·S3 user 발화만 + 심기 2줄
            store_path = os.path.join(STORES_DIR, f"{msid}.jsonl")
            with open(store_path, "w", encoding="utf-8") as fs:
                for s in (2, 3):
                    for u in sess_map[s]:
                        if u["who"] != "user":
                            continue
                        fs.write(json.dumps({"t": u["t"], "s": s}, ensure_ascii=False) + "\n")
                    plant = v1 if s == 2 else v2
                    fs.write(json.dumps({"t": plant, "s": s, "planted": True}, ensure_ascii=False) + "\n")

    # README(로컬 전용 — 실제 데이터 발췌 포함이므로 절대 공개 배포하지 말 것)
    readme_path = os.path.join(OUT_DIR, "README_qbench011_LOCAL_ONLY.md")
    lens_sorted = sorted(chain_lens)
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# qbench011 재료 — 로컬 전용(실제 데이터 발췌 포함 — 재배포 금지)\n\n")
        f.write(f"- 후보(세션4까지 도달·발화합 {UTT_SUM_MIN}~{UTT_SUM_MAX}): {n_cand:,}개 msid, "
                f"그중 seed {SEED}로 {N_CHAINS}개 추출.\n")
        f.write(f"- 선별 40개 발화합(세션2+3+4): min={min(lens_sorted)} "
                f"median={statistics.median(lens_sorted)} max={max(lens_sorted)} "
                f"mean={statistics.mean(lens_sorted):.1f}\n")
        f.write(f"- 문항: F1={n_f1} F2={n_f2} 합계={n_f1 + n_f2}\n")

    print(f"[완료] 사슬 {len(sampled)}개 -> {chains_path}")
    print(f"[완료] 문항 F1={n_f1} F2={n_f2} 합계={n_f1+n_f2} -> {questions_path}")
    print(f"[완료] store {len(sampled)}개 -> {STORES_DIR}")
    print(f"[완료] 로컬 전용 README -> {readme_path} (재배포 금지)")


if __name__ == "__main__":
    main()
