# 멀티세션 품질 벤치 (Multi-Session Quality Bench, "011") — 공개 재현본 v1

작성 2026-07-12 · 문의: 임치영 (chiyoung5104@gmail.com)

> **English abstract.** A benchmark for two *governance* behaviors of conversational memory
> layers, built on real (not synthetic) multi-session Korean chit-chat dialogue: **F1 —
> sequencing** ("which of these two things did I mention first?", answered from outside the
> model's context window) and **F2 — update / later-wins** (a value is stated, then updated
> later; the correct answer is the newer one). This is *not* a recall-parity test — that
> question is already closed by our earlier KU-bench track. Dialogues come from AI Hub's
> licensed "011 everyday-conversation multi-session" corpus; **the corpus and any derived data
> (chains/questions/stores) are excluded from this package** per its license. What is public:
> our generation and execution code (deterministic, seeded), the procedure to acquire the data
> yourself, and the aggregate result numbers. Three arms, same base model (gpt-4o-mini): RAW
> (12-turn window), RAG (batch embedding top-8 retrieval, "most-recent-wins" prompt), and CRA
> (our memory/governance layer — closed product, not re-runnable from this package; a
> `YOUR_LAYER` slot lets you plug in your own). On a **10-superchain main run** (4 real chains
> concatenated per superchain, ~100 turns, question chain outside the RAW window): **F1
> (sequencing, an axis only the layer solved): CRA 0.8 vs RAW 0.2 / RAG 0.3 (Δ+0.5). F2
> (update): CRA 0.9 vs RAG 0.9→1.0 (tie with a strong ledger-style baseline), RAW 0.0.** A
> same-night **fresh reproduction (new seed, zero item overlap)** reproduced F1 exactly (0.8 vs
> 0.2/0.3) and F2 rose to 1.0. Read §5 before citing — the item axes are designed to favor a
> governance layer, the judge for F1 is a mini-tier LLM, and this is a 20-item sample.

## 1. 무엇을 재나

기존 트랙(KU 벤치, `../` 상위 폴더 참조)이 "회상은 RAG와 동급"임을 이미 확인·닫았다. 이 벤치는
회상이 아니라, 여러 세션에 걸친 대화에서 **기억 층이 시간 구조를 다루는 방식**을 잰다:

| 축 | 질문 꼴 | 정답 행동 |
|---|---|---|
| F1 선후 | "「A」 얘기한 거랑 「B」 얘기한 거, 어느 쪽이 먼저였지?" | 실제 발화 순서대로 지목(원장/전사 순서가 gold) |
| F2 갱신 | "내 {물건} 지금 몇 개까지 모았지?" | 나중에 갱신된 값(later-wins) — 옛 값이 섞이면 오답 |

F1은 궤적 거버넌스 벤치의 "시점감사" 축과 동형이며, 이 벤치가 그 축의 **실데이터(합성 시나리오가
아니라 실제 사람 대화)** 판이다. F2는 값 갱신을 실제 대화 흐름 속에 심어 later-wins 판단을
시험한다.

## 2. 재료 — 데이터 vs 코드 (★라이선스 구분)

대화 원문은 AI Hub(공공 데이터 플랫폼, aihub.or.kr)의 **"011.일상대화 한국어 멀티세션 데이터"**
(라이선스: 재배포 금지)에서 왔다. **이 패키지에는 원본 대화·추출된 사슬(chains.jsonl)·문항
은행(questions.jsonl)·store가 전혀 포함돼 있지 않다** — 포함된 것은:

- 데이터 추출·문항 생성 코드(`sim_qbench011_prep.py`) — seed 42로 **결정론적**이라, 같은
  데이터셋 버전에서 실행하면 우리가 쓴 것과 같은 40개 사슬·120개 문항이 재생성된다.
  이것이 우리 재현성의 근거다(원본 재배포가 아니라 절차 재배포).
  ★2026-07-12 발견 기록: 원 작업 지시서는 "S2/S3/S4 zip에 흩어진 세션 파일을 이어붙여야 한다"고
  적었으나, 실측(zip을 직접 까 봄)은 그 반대였다 — `TS_session4.zip`/`VS_session4.zip` 파일
  하나가 세션 1~4 전부를 이미 누적하고 있어 이어붙이기가 불필요했다. 스크립트 주석에 원문 그대로
  남겨뒀다(막히면 원본 대조 원칙).
- 심기 위치·문형 수리 코드(`sim_qbench011_replant_fix.py`) — 파일럿에서 잡힌 측정 결함(§4)의
  교정.
- 실행·채점 코드(`run_bench.py`) — RAW/RAG 팔은 OpenAI API만으로 독립 재현 가능. CRA 자리는
  `YOUR_LAYER`에 자신의 층을 꽂는다(CRA 자체는 비공개 제품).
- 집계 결과 숫자(§3) — 개별 문항 원문 발췌는 라이선스상 공개하지 않는다(궤적 거버넌스 벤치처럼
  답변 전문 jsonl을 공개하는 방식을 이 벤치에는 쓸 수 없다 — 원문에 011 데이터 발췌가 그대로
  포함되기 때문).

## 3. 프로토콜

- **사슬 40개**: 011 세션2·3·4 데이터에서 발화합 40~200인 대화만 골라(seed 42, 9,089개 후보 중
  40개) 결정론 추출. 사슬 하나는 ~48턴으로 짧아(맨 모델도 다 봄 — §4 참조) 그대로는 "창 밖" 조건이
  안 선다.
- **슈퍼사슬**: 사슬 4개를 한 사용자의 시간순 대화로 이어붙여(~100턴대) 창 압박과 주제 간섭을
  만든다. 문항은 **첫 사슬**에서 뽑아 질문 시점엔 ~턴 100개 앞(RAW 12턴 창 밖 강제).
  F1은 첫 사슬 vs 셋째 사슬의 사실을 짝지어 순서를 묻고(제시 순서는 슈퍼사슬마다 교대 — 위치
  편향 방지), F2는 첫 사슬에 심은 v1→v2(later-wins)를 묻는다.
- **3팔, 같은 모델(gpt-4o-mini)**: RAW(최근 12턴 창) · RAG(전 발화 배치 임베딩 top-8 +
  "최신 우선" 프롬프트 — B6, KU 벤치와 같은 시장 기준선) · CRA(제품의 장부+전사검색+시간 주석
  부품을 그대로 조립).
- **채점**: F2=결정적(정답 숫자 포함 ∧ 옛 값 미포함). F1=LLM 판정(먼저 지목한 쪽이 gold와
  일치하면 정답) — ★판정자는 **mini급 모델**(생성 팔과 동일 gpt-4o-mini)이다. 궤적 거버넌스
  벤치(v5)가 쓴 gpt-5.5 강한 판정자와 다르다 — §5 한계에 명시.
- **측정 유효성 게이트**: 심은 F2 값이 RAW 창(12턴) 안에 노출되면 그 문항은 무효(창-노출률로
  집계·기준 초과 시 INVALID-SETUP). 표본 미달(n_f1<8 또는 n_f2<8)·전팔 동점도 무효.
- **판정 기준(사전등록, 코드로 계산)**: POSITIVE iff `F1: cra − max(raw,rag) ≥ 0.3` **그리고**
  `F2: cra ≥ max(raw,rag) − 0.1`(강한 기준선과 동급이면 충분 — F2는 "이긴다"가 아니라 "안 진다"
  기준).

## 4. 파일럿 이력 (5판 — 실패 3회가 설계를 교정한 과정, 전부 정직 공개)

| 판 | 무엇을 했나 | 결과 |
|---|---|---|
| 파일럿 v1(사슬 단위, N=5) | 첫 시도 — 세션 블록 끝에 값 심기 | **INVALID** — 심은 v2가 RAW 창 안에 그대로 노출(측정 무효) + 대용어 갱신("이제 7개야")을 커널이 갱신으로 못 묶는 제품 구멍 발견(별도 트랙 등록) |
| 재심기(replant) 후 재판정 | 심기 위치·문형 수리 | **INVALID (근본 원인 확정)** — 011 사슬 자체가 ~50턴으로 짧아 어느 위치에 심어도 RAW 창이 닿거나 맨 모델이 전체를 봄 = "CRA 값은 궤적·기억 스케일에서 난다"는 기존 결론의 실데이터 재확인 |
| 재설계: 슈퍼사슬(사슬 4개 연결) 파일럿(N=3, 평균 98턴) | 창 압박·주제 간섭 조건 확보 | 측정은 성립(창-노출 0)했지만 **정직 NEGATIVE**: F2는 RAG(B6) 3/3 vs CRA 2/3, F1은 전팔 저조 — 개선 표적 3개 특정(①구어 값-사슬 채택 미스 ②선후 질문 트리거 갭 ③검색 발췌에 순서 정보 없음) |
| 표적 수리 → **본판**(N=10) | §3 프로토콜대로 실행 | **POSITIVE** — §3 아래 표 |
| **신선 재현판**(같은 날 밤, 새 seed·본판과 문항 0 중복) | 표본 요행 배제 확인 | **POSITIVE, 재현 확인** — §3 아래 표 |

수리 3건의 내용(정직 기록 — 셋 중 하나는 "제품엔 이미 있었다"는 결론이었다):
1. **값-사슬 채택**: 진단해보니 제품 커널 자체는 정상이었다 — 실패 원인은 벤치의 CRA팔 조립이
   제품보다 허술했던 것(수리는 코드가 아니라 조립 방식).
2. **선후 문형**: 전사 검색 부품에 "선후 판단 경로"를 신설(순번 정렬 + 인용 문자열 직대조) —
   이건 실제 제품 코드 수리였다.
3. **순서 각인**: 제품에는 이미 있었다(검색 발췌에 [지난 기록 순번·날짜] 주석) — 벤치의 CRA팔을
   제품이 실제로 쓰는 부품으로 교체했을 뿐.

## 5. 우리 결과

**본판**(슈퍼사슬 10개, 평균 102턴, 문항 20 = F1 10 + F2 10):

| | RAW | RAG(B6) | CRA 층 |
|---|---|---|---|
| F1 선후 (층 유일 축) | 0.2 | 0.3 | **0.8** (Δ+0.5) |
| F2 갱신 (동급 방어 축) | 0.0 | 1.0 | **0.9** |
| 창-노출률 | | | 0 |

**신선 재현판**(같은 밤, 새 seed·본판과 사슬 0 중복, 슈퍼사슬 10개):

| | RAW | RAG(B6) | CRA 층 |
|---|---|---|---|
| F1 선후 | 0.2 | 0.3 | **0.8** (본판과 동일 — 요행 아님) |
| F2 갱신 | — | — | **1.0** |

**사용 가능한 서술(한정 준수)**: "창 밖·주제 간섭 조건에서, 발화 선후를 묻는 질문은 층만 풀고
(0.8 vs RAW 0.2/RAG 0.3), 값 갱신(later-wins)은 최신-우선 원장 기준선과 동급이다." — **전면
우위 주장이 아니다.** RAW의 F2=0.0은 "창 밖에 심긴 값은 창 기반 방식이 원천적으로 못 본다"는
창 압박 자체의 증거이지 RAG 대비 CRA의 우위 증거가 아니다.

## 6. 재현 방법

1. **데이터 신청**: AI Hub(aihub.or.kr)에서 "011.일상대화 한국어 멀티세션 데이터" 다운로드
   신청(공공기관 절차 — 무료·심사 있음). 승인 후 `TS_session4.zip`/`VS_session4.zip`을 받는다.
2. **재료 생성**: `sim_qbench011_prep.py`의 `BASE_011`을 자신의 다운로드 경로로 바꾸고 실행
   (`pip install kiwipiepy`) → `sim_banks/qbench011/`에 사슬·문항·store 생성(로컬 전용, 커밋
   금지). 이어서 `python sim_qbench011_replant_fix.py`로 심기 수리 적용.
3. **실행**: `OPENAI_API_KEY` 설정 후 `python run_bench.py --n 10` — RAW/RAG 팔이 재현되고
   집계·판정이 출력된다. 자신의 기억/거버넌스 층을 시험하려면 `run_bench.py`의 `YOUR_LAYER`에
   구현을 꽂는다(입력: 시간순 사용자 발화 리스트 `turns`, 질문 `question` / 출력: 답변 문자열).

CRA(우리 층) 자체는 비공개 제품이라 이 패키지로 재실행할 수 없다 — 궤적 거버넌스 벤치 공개본과
같은 정책이다. 대신 절차 전체(추출→수리→실행→채점)를 코드로 공개해 방법론을 검증할 수 있게 했고,
CRA 자리는 누구의 층이든 꽂을 수 있게 열어뒀다.

## 7. 한계 (정직 라벨 — 전부 명시)

- **소표본**: 본판·재현판 각 20문항(F1 10 + F2 10). 궤적 거버넌스 벤치(60주축 문항)보다 작다.
- **합성 심기(F2)**: F2의 갱신 값 자체는 실제 대화에 없던 것을 결정론 규칙으로 심었다(대화의
  나머지는 전부 실사람 발화). F1은 심기 없이 실제 발화 순서를 그대로 쓴다.
- **문항 축이 층에 유리하게 설계됨**: F1(선후)·F2(갱신) 모두 구조화된 시간 장부가 유리한 축으로
  우리가 고른 것이다 — "층이 잘하는 축에서 이긴다"의 확인이지 전면 우위 주장이 아니다.
- **B6는 강한 기준선**: RAG 비교 대상(B6)은 "최신 값 우선" 프롬프트가 이미 박힌 원장형 RAG다 —
  시장의 평범한(무원장) RAG보다 유리한 비교이며, F2에서 CRA는 이걸 **이기지 못하고 동급**이다.
- **F1 판정자는 mini급 LLM**: 궤적 거버넌스 벤치(v5)가 쓴 gpt-5.5 강한 판정자와 달리, 생성 팔과
  같은 gpt-4o-mini가 채점한다 — 판정 관대함 검증이 별도로 이뤄지지 않았다.
- **한 모델·한 언어**: gpt-4o-mini·한국어 대화만. 파일럿 실패 3회(§4)가 보여주듯 사슬 길이(짧으면
  축이 안 선다)에 결과가 민감하다 — 011보다 긴/짧은 멀티세션 데이터에서 재현되는지는 미검.
- **주장 범위**: "특정 시간-구조 질문(선후·갱신)에서 이 층은 검색만으로는 안 나오는 행동을
  낸다" — "전반적으로 더 좋은 답변을 한다"가 아니다.

## 8. 라이선스 고지

- 011 데이터의 저작권·이용권은 AI Hub 및 원 제공기관에 있다. 이 저장소는 원본·추출본·파생
  문항 은행을 포함하지 않으며, 재배포하지 않는다.
- 공개된 코드(`sim_qbench011_prep.py`, `sim_qbench011_replant_fix.py`, `run_bench.py`)는
  우리가 작성한 것으로, 자유롭게 검토·재현·수정할 수 있다.
- 이 README의 집계 결과 숫자는 원 데이터의 저작물성 있는 표현을 포함하지 않는 통계치다.
