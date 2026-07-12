# -*- coding: utf-8 -*-
"""sim_qbench011_replant_fix.py — 심기 위치·문형 수리 (공개 재현본, 원 파일명 sim_qbench011_replant.py).

배경(파일럿 v1 INVALID의 진단, 정의서 (pppp)): v1 결함 ①심은 v1·v2가 각 세션 블록의 *끝*에
있어 raw 창(마지막 12턴)에 그대로 노출됨(S4 user 턴이 ~7개뿐이라 창 12가 S3까지 닿음) — 이러면
"창 밖" 조건이 성립하지 않아 RAW팔도 정답을 볼 수 있어 측정이 무효화된다. ②v2 문형이 대용어
("이제 7개야" — 무엇이 7개인지 앞 문맥 의존)라 커널의 결정 채택 로직이 "갱신"으로 못 묶는 경우가
있었다(이건 벤치 설계 문제가 아니라 실제 제품 구멍이라 별도 트랙으로 기록하고, 이 벤치는
"later-wins"만 분리해서 잰다).

수리: 심는 위치를 각 세션 블록의 *중간*으로 옮기고(끝이 아니면 raw 창에서 밀려남), v2 문형을
자족형으로 바꾼다("이제 {item} {n2}개야" — 문장 안에서 무엇이 몇 개인지 완결). stores/questions를
제자리에서 재작성한다(결정론 — 같은 questions.jsonl의 gold/distractor는 그대로, store만 바뀜).

사용 순서: sim_qbench011_prep.py 실행 → 이 스크립트 실행 → run_bench.py.
(신선 재현판은 별도 폴더에 seed 43으로 prep을 다시 돌린 뒤 이 로직을 그대로 적용한 것과 동일하다.)
"""
import io
import json
import os
import re
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

QDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_banks", "qbench011")

qs = [json.loads(l) for l in open(os.path.join(QDIR, "questions.jsonl"), encoding="utf-8")]
f2 = {q["msid"]: q for q in qs if q["family"] == "f2_갱신"}

for msid, q in f2.items():
    sp = os.path.join(QDIR, "stores", f"{msid}.jsonl")
    rows = [json.loads(l) for l in open(sp, encoding="utf-8")]
    item, n2 = re.search(r"내 (\S+) 지금", q["q"]).group(1), q["gold"]
    n1 = q["distractor"]
    rows = [r for r in rows if not r.get("planted")]
    s2 = [i for i, r in enumerate(rows) if r["s"] == 2]
    s3 = [i for i, r in enumerate(rows) if r["s"] == 3]
    assert s2 and s3, msid
    v1 = {"t": f"참, 나 요즘 {item} 모으고 있어. 지금까지 {n1}개 모았어.", "s": 2, "planted": True}
    v2 = {"t": f"아 맞다, 이제 {item} {n2}개야. 더 모았거든.", "s": 3, "planted": True}
    rows.insert(s2[len(s2) // 2], v1)                       # S2 중간
    s3b = [i for i, r in enumerate(rows) if r["s"] == 3 and not r.get("planted")]
    rows.insert(s3b[len(s3b) // 2], v2)                     # S3 중간
    with open(sp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"재심기 완료: {len(f2)}개 store (중간 위치·자족 문형)")
