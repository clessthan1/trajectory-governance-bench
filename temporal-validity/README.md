# Temporal validity of premises — an evaluation axis

This folder defines an evaluation **axis** for conversational-memory / agent systems:
the **temporal validity of premises** — how well a system handles *when* a fact or premise
in its memory is true, not merely *whether* it can be recalled. Standard long-term-memory
benchmarks score recall and some temporal *reasoning*; they largely do not score the
decision- and premise-governance behaviors that follow from a fact having a *lifetime*.

We name the axis so it can be measured and argued about directly. It has **four
measurement facets**. Facet (a) and part of (b) are covered by an existing public
benchmark (STALE); (c) and (d) are largely open.

| Facet | One line | Existing coverage |
|---|---|---|
| (a) implicit invalidation | a later turn silently overrides earlier state | **STALE** (measures this) |
| (b) stale-premise rejection | push back on a request that assumes an outdated state | STALE (partial) |
| (c) point-in-time recall | recall the value that was valid *as of* a given time | gap |
| (d) expiry-driven review | a lapse of a validity window becomes a review event with no human prompt | gap |

---

## (a) Implicit invalidation

**Definition.** A later utterance changes a fact without ever saying "forget the old
value." A system with temporal validity must treat the earlier state as superseded when
answering, rather than surfacing whichever value it retrieves first.

**Why it matters (motivation, not proof).** This is the dominant real failure of memory
layers: a user says "I moved to Berlin" ten turns after "I live in Paris," and the system
still answers "Paris." Coding agents show the analogous need — they are expected to *hold*
or flag knowledge that a later commit or config change has invalidated rather than act on
the superseded state.

**Existing benchmarks.** **STALE** measures this directly: each item plants an old value
`M_old`, later introduces `M_new`, and probes whether the model answers from the current
state (its dim1/dim3, across single-hop T1 and propagation T2).

**Protocol sketch.** Plant `M_old` → distractor turns → introduce `M_new` → ask a question
whose correct answer requires the current state. Score whether the response reflects
`M_new` (not `M_old`), with a judge or deterministic marker. Report separately for
single-hop vs propagation (a change that must cascade to a dependent fact is harder).

## (b) Stale-premise rejection

**Definition.** The user's *request itself* presupposes a state that has since changed
("go ahead and ship it at the old price, right?"). The correct behavior is to name the
outdated premise first, then answer from the current state — not to silently comply.

**Why it matters.** Silent compliance with an outdated premise is how a memory layer
launders a stale fact into a wrong action. It is the highest-stakes facet for agents,
because the failure is an *action*, not just a wrong recall.

**Existing benchmarks.** **STALE covers this partially** — its adversarial/premise-driven
dimension (dim2 / PR) is the closest public measure, and in both the paper and our
reproduction it is the weakest cell across all systems. Coverage is partial because the
premise is embedded in the *question*, not in a full downstream *request/plan* the system
must refuse to execute unchanged.

**Protocol sketch.** After an invalidating update, issue a request that bakes in the old
premise. Score two conjuncts: (i) the outdated premise is flagged, and (ii) the answer/plan
uses the current state. Silent compliance fails even if the surface answer is otherwise
fluent.

## (c) Point-in-time recall

**Definition.** Recall the value that was valid *as of* a specified time, not the latest
value — "what was my address **when** I signed the lease?", "why did I decide that at the
time?". This requires keeping the history, not overwriting it.

**Why it matters (motivation, not proof).** The clinical NLP temporal-reasoning literature
repeatedly notes that "as-of" / point-in-time value recall — as opposed to latest-value
recall — is comparatively **underexplored**; medication and status values are inherently
time-indexed, and answering "what was the dose as of date X" is a distinct, harder query
than "what is the dose now." Audit and decision-review settings need the same capability:
reconstructing *why* a past decision was correct given the state *then*.

**Existing benchmarks.** Largely a **gap**. General temporal-reasoning items ask "when did X
happen," but rarely "what was Y's value as of time T." The decision-audit ("why did I decide
that?") variant is, to our knowledge, not covered by standard memory benchmarks.

**Protocol sketch.** Record a value with a validity interval; later change it; then query as
of a past timestamp. Correct = the value valid at that timestamp *and* an acknowledgment
that it has since changed (for the audit variant, juxtapose the reason-then with the
state-now). Latest-value recall is a distractor answer here.

## (d) Expiry-driven review

**Definition.** A fact/premise carries a validity window; when that window lapses, the
*passage of time itself* — with no new human utterance — should become a review event
("the quote you approved expired yesterday; revisit before proceeding").

**Why it matters.** Most systems only react to inputs. Temporal validity means the *absence*
of an event (a deadline passing, a lease ending) is itself information. Without it, a memory
layer confidently serves facts whose "true-until" date is long past.

**Existing benchmarks.** A **gap** — benchmarks are query-driven, so an item that should fire
*because nothing was said* does not fit the standard "ask a question, score the answer"
frame. Some temporal-QA sets touch future/expired facts on the recall side (return the value
true *now*, distinguishing not-yet from already), but not the review-event side.

**Protocol sketch.** Assign a validity window to a premise; advance the clock past it without
a user turn; check whether the system raises a review/expiry event before it is next relied
upon. Score both the fire and its correctness (no false alarms on still-valid premises).

---

## Our public results on this axis (with honest labels)

- **Facet (a) + part of (b) — STALE full run (N=400).** Reproduction package in
  [`../stale-eval/`](../stale-eval/). Long-context vs retrieval+premise-check on gpt-4o-mini,
  3-provider majority judge: **0.109 vs 0.469 overall** (paired sign test B-win 455 : A-win 24,
  p ≈ 2.6e-104). Labels that must travel with this: B-arm = retrieval + a premise-check
  instruction (**not** the CRA kernel ledger); cross-framework numbers are **indirect** (paper
  figures, not rerun); judge is a majority vote whose strictness vs the paper's judge is
  unmeasured; gpt-4o-mini responses only. Details and the four-label block are in the
  stale-eval README.

- **Facet (c) — as-of / decision audit.** On this repository's self-designed 30-trajectory
  set (see the top-level README and `HISTORY.md`), the point-in-time decision-audit question
  ("why did I decide that originally?", requiring the reason-then juxtaposed with the
  state-now) was answered by the governance layer on **17/30** items while the bare-model and
  RAG arms answered **0/30** combined. Honest labels: self-designed stage (we defined the
  axis), synthetic single-session trajectories, one backbone (gpt-4o-mini). This is evidence
  of a behavior retrieval alone does not produce on this stage — **not** a claim of better
  chat quality.

Facets (c) and (d) are only partially instrumented today; closing them is the point of
naming the axis. Sources: STALE (*arXiv 2605.06527*, 2026; data CC BY 4.0, code MIT);
this repository's trajectory-governance bench.
