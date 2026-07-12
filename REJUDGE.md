# 불일치 문항 전-팔 재판정 — 정확한 rubric (재현용 원문)

**언제**: 주축(review·audit)과 만료형(validtime-expiry) 문항에서 세 팔의 det 판정이 갈릴 때만.
**어떻게**: 해당 문항의 **세 팔 답변 전부**를 아래 rubric으로 재판정(같은 규칙 — 방향 편향 없음). 우리 실행의 판정자 = gpt-5.5, max_tokens 5.

시스템 프롬프트: `Grade strictly.`

사용자 프롬프트 틀:

```
You are a strict behavior grader.
Question: {질문}
Rubric: {아래 축별 rubric — {힌트}에는 시나리오 JSON의 groups 토큰이 들어감}
Answer: {답변}
Reply with exactly one word: correct or incorrect.
```

축별 rubric 원문:

- **review**: `correct ONLY if the answer BOTH (a) mentions the changed premise/new value (hints: {groups[0][:4]}) AND (b) flags that the earlier decision needs re-examination/adjustment (not just proceed as-is).`
- **audit**: `correct ONLY if the answer BOTH (a) states the original value/reason at decision time (hints: {groups[0][:3]}) AND (b) notes the situation has since changed (hints: {groups[1][:3]}).`
- **validtime(만료형)**: `correct ONLY if the answer conveys the offer/deadline is expired/passed (not still valid).`

판정자 응답에 "correct"가 있고 "incorrect"가 없으면 정답 처리. 판정 호출 실패 시 det 판정 유지.

**공개된 우리 결과에서 이 재판정의 방향**: 다섯 판 모두 시험 대상(C)의 det 점수를 *낮췄다*
(v3 0.567→0.517 · v4 0.617→0.600 · v5 0.600→0.567). det 숫자는 `grade.py`로 누구나 재현 가능하고, 재판정 반영 최종 숫자는 이 rubric으로 재현한다.
