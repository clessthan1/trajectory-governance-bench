# 궤적 거버넌스 벤치 (Trajectory Governance Bench) — 공개 재현본 v1

작성 2026-07-11 · 문의: 임치영 (chiyoung5104@gmail.com)

> **English abstract.** A benchmark for *governance behaviors* of conversational memory layers —
> not recall QA. Each item is a dialogue *trajectory*: facts → a casual decision that references
> them → 12 distractor turns → a premise-weakening update → 4 questions (decision re-review,
> decision audit "why did I decide that?", one of past-state/false-premise/valid-time, and a
> recall control with false-alarm check). Three arms share the same model (gpt-4o-mini):
> A = bare model with a 12-turn window, B = RAG (top-6 embedding retrieval), C = the memory
> layer under test. Deterministic marker grading; arm-discordant items re-judged across all arms
> by a stronger LLM; paired binomial test. On a **fresh, never-before-run 30-trajectory set**,
> the CRA layer scored **0.567 vs 0.217 (RAG) and 0.033 (bare)** on the governance axes
> (Δ+0.350, paired p=0.0001) with **zero recall loss and zero false alarms**. This measures
> "behaviors a layer produces that retrieval alone does not" — it is *not* a claim of better
> chat quality.

## 1. 무엇을 재나

시간이 흐르고 전제가 바뀌는 대화 궤적에서, 기억 층이 내는 **거버넌스 행동**:

| 축 | 질문 꼴 | 정답 행동 |
|---|---|---|
| ★재검토 표면화 | (전제 갱신 후) "그 건 그대로 진행하지?" | 바뀐 값을 들어 결정 재검토를 표명 |
| ★시점 감사 | "애초에 왜 그렇게 하기로 했었지?" | 당시 근거 **와** 지금 달라진 상태를 병치 |
| 과거-상태 | "처음엔 얼마였지?" | 갱신 전 값 |
| 전제 부인 | (말한 적 없는 대상) "내 햄스터 이름 뭐였지?" | 바꿔치기 없이 없다고 답함 |
| 유효시간 | (미래/만료 사실) "지금 어디 살아?" | 아직/이미를 가려 현재 참인 값 |
| 대조(FRR) | 평범한 회상 | 정답 + 불필요한 재검토·부인 0 |

기존 장기기억 벤치(LongMemEval 등)는 회상·시간추론 축을 재고, **결정-의존·감사 축은 재지 않는다** — 이 벤치가 그 빈 무대다.

## 2. 프로토콜

- **궤적 골격**: 값 사실(2~3) → 그 사실을 참조한 casual 결정 → 방해 12턴 → 결정을 약화시키는 값 갱신 → 질문 4개. 30궤적 = 주축 60문항 + 보조 30 + 대조 30.
- **3팔, 같은 모델(gpt-4o-mini)·같은 질문**: A 맨 모델(창 12턴 — 현실 챗앱 절단 모사) · B RAG(전 턴 임베딩 top-6) · C 시험 대상 층.
- **채점**: 결정적 마커(값 토큰 any-of 그룹의 전부 충족 + 금지어) → **팔 간 판정이 갈린 문항만 전-팔 LLM 재판정**(gpt-5.5, 행동 rubric: 재검토="바뀐 값 인용 그리고 재검토 표명 둘 다", 감사="당시 값 그리고 달라진 지금 둘 다") — 전 팔 동일 규칙이라 방향 편향 없음.
- **판정 4조건(사전등록)**: 주축 C−max(A,B) ≥ +0.25 **그리고** 대조 오발동 FRR ≤ 0.1 **그리고** 회상 동급(B−C ≤ 0.15) **그리고** 대응쌍 방향 이항 p < 0.05.

## 3. 우리 결과 (원본 답변 전문이 results/에 있음)

**신선 확인판**(scenarios_v5_fresh — 새로 작성한 30궤적, 수정 없이 1회):

| | 맨 모델 | RAG | CRA 층 |
|---|---|---|---|
| 주축(재검토+시점감사 60) | 0.033 | 0.217 | **0.567** (Δ+0.350) |
| 시점감사만 | 0/30 | 0/30 | **17/30** |
| 대조 회상 / 오발동 | 0.0 | 1.0 | **1.0 / 0.0** |
| 대응쌍(C vs B) | | 5 | **26** (p=0.0001) |

- det(결정적 채점만) 숫자와 최종(재판정 반영) 숫자를 둘 다 공개한다 — **다섯 판 모두 재판정이 C 점수를 낮췄다**(v5: 0.600→0.567). 판정 관대함이 시험 대상 편으로 작동한 적 없음.
- 전체 5판 이력(사전등록 음성 2·경계 1·양성 2)은 `HISTORY.md`.
- 정직 한계: 유효시간 축에서 C 5/7 < B 7/7(신선 문형 2건이 결정적 어법 사전 밖).

## 4. 재현 방법 (3단계)

1. **채점 검증(무API)**: `python grade.py scenarios_v5_fresh.json results/wm_traj_gov_v5_results.jsonl` — 공개된 원본 답변을 마커로 재채점해 det 집계가 재현되는지 확인.
2. **베이스라인 재실행**: `python run_baselines.py scenarios_v5_fresh.json my.jsonl` (OPENAI_API_KEY 필요) → `grade.py`로 채점.
3. **당신의 층을 C로**: `run_baselines.py`의 `YOUR_LAYER(turns, question)`에 자기 기억/거버넌스 층을 꽂아 같은 조건 비교.

CRA(C팔) 자체는 비공개 제품이라 이 패키지로 재실행할 수 없다 — 대신 **우리 실행의 원본 답변 전문을 공개**해 채점을 검증할 수 있게 했고, C 자리는 누구의 층이든 꽂을 수 있게 열어뒀다.

## 5. 한계 (전부 명시)

- 자체 설계 무대다(측정 축을 우리가 정의). 완화: 사전등록·결정적 채점·원본 전문 공개·이 패키지.
- 합성 시나리오·한 모델(gpt-4o-mini)·단일 세션 시간축. 실사용 검증은 별도 트랙.
- 주장 범위: **"이 거버넌스 행동들은 검색만으로는 안 나온다"** — "더 좋은 챗봇"이라는 주장이 아니다(회상 축은 RAG와 동급이 우리 결과다).
