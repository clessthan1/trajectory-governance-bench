# STALE reproduction package (N=400)

A public, self-contained reproduction of our STALE full run: **A (long-context) vs
B (retrieval + premise-check discipline)**, same backbone (gpt-4o-mini), graded by a
**3-provider majority vote** of judges. STALE measures whether a system honors the
*temporal validity* of premises — when a later turn implicitly invalidates earlier
state, does the model still silently comply with the stale premise?

> STALE: *arXiv 2605.06527* (Wuhan University / CUHK / HKUST, 2026). Dataset
> `STALEproj/STALE` on Hugging Face (CC BY 4.0); STALE code MIT.

## Result (399/400 completed; 1 execution failure dropped)

| | A (long-context) | B (retrieval + premise-check) |
|---|---|---|
| **Overall** | **0.109** | **0.469** |
| dim1 (explicit probing) | 0.208 | 0.551 |
| dim2 (stale-premise rejection) | 0.000 | 0.378 |
| dim3 (implicit task) | 0.118 | 0.476 |
| T1 (single-hop) | 0.147 | 0.597 |
| T2 (propagation) | 0.070 | 0.340 |

Paired item-query sign test (two-sided): **B-win 455 vs A-win 24, p ≈ 2.6e-104**.
Preregistered verdict (computed by code): **POSITIVE** — B > A overall *and* on dim2,
sign-test p < 0.05.

Both arms fail dim2 at the long-context baseline (A dim2 = 0.000), reproducing the
paper's Finding that premise-driven bias (PR) is the weakest cell across systems.

Per-item, per-judge verdicts and (truncated) model answers are in
[`results_n400.jsonl`](results_n400.jsonl). Each row: `uid`, `type`, `{a,b}_dim{1,2,3}`
(majority labels), `{a,b}_per` (each judge's per-dim pass), `{a,b}_ans` (model responses,
≤350 chars).

## The four mandatory labels (must travel with any citation)

1. **B-arm = retrieval + a premise-check instruction, NOT the CRA kernel ledger.** B is
   top-6 embedding retrieval over user turns plus one instruction to flag an outdated
   premise before answering. The kernel-ledger arm (C) was excluded from this run and did
   not beat B in our earlier internal versions. This table is **not** evidence that "the
   CRA kernel wins" — it is evidence that "the minimal discipline of our layer is useful on
   this axis."
2. **Indirect comparison (same stage, different execution).** Cross-framework numbers below
   are copied from the STALE paper; **we did not rerun mem0 / Zep / etc.** Direct-comparison
   standing would require running those adapters ourselves. "SOTA / beat X" is not licensed.
3. **Judge difference.** The paper uses a single judge (Gemini-3.1-flash-lite). We use a
   3-provider majority (gpt-5.5, claude-opus-4-8, gemini-3.1-pro-preview) with the paper's
   judge prompt verbatim. The majority switch was made to curb a single judge's leniency;
   **the strictness direction vs the paper's judge is unmeasured** — assume ±several pp on
   absolute values.
4. **gpt-4o-mini responses only.** All target responses are from one backbone.

## Indirect comparison to paper-reported numbers

Same-backbone (GPT-4o-mini) anchoring: the paper's long-context baseline is 8.7%, our
reproduction is 10.9% (~2 pp apart, same failure shape: PR near-zero, T2 < T1). On that
anchor, our B-arm (46.8%, six-cell average per the paper's Table 2 format) sits above every
GPT-4o-mini-backbone memory framework reported in the paper — but this is an **indirect**
comparison (see labels 2 and 3).

| System (backbone) | Source | T1 SR | T1 PR | T1 IPA | T2 SR | T2 PR | T2 IPA | Overall |
|---|---|---|---|---|---|---|---|---|
| GPT-4o-mini long-context* | paper | 30.0% | 0.0% | 11.0% | 9.5% | 0.0% | 1.5% | 8.7% |
| **A: GPT-4o-mini long-context (ours)** | ours | 29.5% | 0.0% | 14.5% | 12.1% | 0.0% | 9.0% | **10.9%** |
| Zep (4o-mini) | paper | 10.0% | 0.0% | 19.0% | 3.0% | 1.0% | 3.0% | 6.0% |
| A-mem (4o-mini) | paper | 13.5% | 0.0% | 7.5% | 8.0% | 0.0% | 1.5% | 5.1% |
| LiCoMemory (4o-mini) | paper | 15.5% | 0.5% | 22.5% | 1.5% | 1.5% | 4.0% | 7.6% |
| mem-0 (4o-mini) | paper | 17.0% | 1.0% | 22.0% | 3.5% | 0.0% | 6.5% | 8.3% |
| LightMem (4o-mini) | paper | 52.5% | 1.0% | 23.5% | 21.5% | 0.5% | 7.5% | 17.8% |
| **B: retrieval + premise-check (4o-mini, ours)** | ours | 69.0% | 50.0% | 60.0% | 41.2% | 25.6% | 35.2% | **46.8%** |
| (ref) Gemini-3.1-pro long-context | paper | 92.0% | 30.0% | 71.0% | 69.0% | 14.0% | 55.0% | 55.2% |
| (ref) CUPMEM = paper prototype (4o-mini) | paper | 91.0% | 78.0% | 32.0% | 89.0% | 75.0% | 43.0% | 68.0% |

\* The paper's context-window-limited, evidence-preserving-truncation model. Our A arm applies
the same-intent trim (evidence sessions preserved).

**How to read it, honestly.** B at 46.8% is above the paper's strongest reported framework
(LightMem 17.8%) and below the paper prototype (CUPMEM 68.0%) and Gemini-3.1-pro long-context
(55.2%). The paper itself validates the *same family* of fix — an explicit premise-check — via
CUPMEM. Our result is an independent data point that this fix recovers a large share of the
gap with just "retrieval + one instruction," without an elaborate state schema. It is not a
claim of better chat quality, and (label 2) not a direct win over any named product.

### Consistency anchors (supporting the indirect comparison)
- Same-backbone long-context baseline: paper 8.7% vs ours 10.9% (~2 pp, same shape). A large
  reproduction drift would make this closeness unlikely. Largest cell deviation is T2 IPA
  (ours 9.0% vs paper 1.5%) — trim/judge differences may concentrate there.
- Paper Finding (premise-driven bias is pervasive; PR weakest) ↔ our dim2 = 0 at baseline.
- Paper Finding (T2 propagation harder) ↔ our T2 < T1 across arms.

## Reproduce

Dependencies: `pip install openai tiktoken`.

1. **Data** — download `T1_T2_400_FULL.json` from HF `STALEproj/STALE` (CC BY 4.0) into
   `./data/` (not redistributed here).
2. **Judge prompt** — point `STALE_REPO_DIR` at your local STALE checkout (the directory
   containing `Evaluation/judge_prompts.py`; STALE code is MIT — not redistributed here).
3. **Keys** — `OPENAI_API_KEY` (target model + gpt-5.5 judge) and `OPENROUTER_API_KEY`
   (claude / gemini judges, by default). Any judge route is overridable with
   `STALE_ROUTE_<slug>_{KEY,URL,MODEL}`.
4. **Run**:
   ```
   set STALE_N=400
   set STALE_DATA_DIR=./data
   set STALE_REPO_DIR=/path/to/STALE
   python bench_stale_full_v0.py
   ```

The arm construction, history trim, judge-prompt call, majority vote, and sign test are
byte-for-byte identical to the run that produced `results_n400.jsonl`; only the private
plumbing (LLM client, parallel map, preregistration harness, credential resolver) was
replaced with self-contained equivalents. See the header of `bench_stale_full_v0.py` for
the full diff.
