# -*- coding: utf-8 -*-
"""bench_stale_full_v0.py — public reproduction of the STALE full run (N=400):
A (long-context) vs B (retrieval + premise-check discipline), graded by a 3-provider
majority vote of judges.

WHAT THIS MEASURES
  STALE (arXiv 2605.06527; Wuhan Univ. / CUHK / HKUST, 2026) tests whether a memory
  system honors the *temporal validity* of premises: later turns implicitly invalidate
  earlier state, and a good system must not silently comply with an outdated premise.
  Arm A feeds the trimmed dialogue directly to gpt-4o-mini. Arm B retrieves the top-6
  user turns by embedding similarity and adds a single "check for an outdated premise
  before answering" instruction. Both arms use the SAME backbone (gpt-4o-mini) and the
  SAME three questions per item; the only difference is retrieval + the premise-check
  discipline. Three judges (gpt-5.5, claude-opus-4-8, gemini-3.1-pro-preview) score each
  response with STALE's own judge prompt; the majority (>=2 of 3) is the label. Item-query
  pairs are compared with a two-sided sign test.

HONEST LABELS (must travel with any citation of the results):
  1. B-arm = retrieval + a premise-check instruction, NOT a memory-kernel ledger.
  2. Cross-framework numbers (mem0/Zep/etc.) are copied from the STALE paper — we did NOT
     rerun them. This is an INDIRECT comparison.
  3. Judge = 3-provider majority vote (paper uses a single judge); strictness direction vs
     the paper's judge is unmeasured.
  4. gpt-4o-mini responses only.

------------------------------------------------------------------------------------------
DIFFERENCES FROM THE ORIGINAL (internal) SCRIPT — the load-bearing logic (arm construction,
history trim, judge-prompt call, majority vote, sign test) is byte-for-byte identical to
the run that produced results_n400.jsonl. Only the private plumbing was replaced:

  * Removed hard-coded local absolute paths / a non-ASCII (Korean) user directory. The
    dataset dir and output path now come from env vars / relative paths.
  * `cra.language_cortex.LanguageCortex`  -> a self-contained OpenAI-compatible wrapper
    defined below (same `.generate(system, messages, max_tokens)` / `.embed(list)` API).
    Embeddings use text-embedding-3-small (the model the internal cortex used).
  * `cra.parallel.parallel_map`           -> a ThreadPoolExecutor equivalent (below).
    Parallelism only changes execution order, not per-item logic.
  * `cra_rigor.Prereg`                    -> preregistration text kept as a comment; the
    validity/verdict check is computed inline at the end. `sign_test_p` is byte-identical.
  * `cra_panel._cred_for`                 -> env-var credential/route resolver (below).
  * `Evaluation.judge_prompts.SYSTEM_PROMPT_ALL_IN_ONE_JUDGE` is imported lazily from your
    own STALE checkout (see STALE_REPO_DIR) — the STALE judge prompt is NOT redistributed
    here.

The STALE dataset itself is NOT redistributed. Download it from HF `STALEproj/STALE`
(CC BY 4.0) and place `T1_T2_400_FULL.json` under $STALE_DATA_DIR (default ./data).

PREREGISTRATION (verbatim intent of the original run, for transparency):
  H1: B > A overall AND on dim2 (stale-premise rejection), paired sign test p<0.05.
  H2: gap shrinks / significance vanishes at full scale -> the 10-item pilot was luck.
  H3: excess execution failures or A at ceiling (no discrimination) -> INVALID-SETUP.
  Validity: done >= 90% of N and A_all < 0.95.
  Verdict:  POSITIVE iff B_all > A_all AND B_dim2 > A_dim2 AND sign_p < 0.05.
  Opposite (kept even if POSITIVE): the driver is "premise-check instruction + retrieval",
  NOT the CRA kernel ledger; judges are still LLMs, validated only on gpt-4o-mini outputs;
  no direct comparison to other memory products — "SOTA / beat X" is not licensed.

USAGE
  set OPENAI_API_KEY=...                      # target model + (default) gpt-5.5 judge
  set OPENROUTER_API_KEY=...                  # (default) claude / gemini judges
  set STALE_DATA_DIR=./data                   # holds T1_T2_400_FULL.json (from HF)
  set STALE_REPO_DIR=/path/to/STALE           # holds Evaluation/judge_prompts.py
  set STALE_N=400                             # 100 (default) or 400
  python bench_stale_full_v0.py
"""
import json
import os
import re
import sys
import io
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

if __name__ == "__main__":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception:
        pass
HERE = os.path.dirname(os.path.abspath(__file__))

MODEL = "gpt-4o-mini"
JUDGES = ["gpt-5.5", "claude-opus-4-8", "gemini-3.1-pro-preview"]
N = int(os.environ.get("STALE_N", "100"))
RAG_K = 6
DATA_DIR = os.environ.get("STALE_DATA_DIR", os.path.join(HERE, "data"))
OUT = os.environ.get("STALE_OUT", os.path.join(HERE, "bench_stale_full_v0_results.jsonl"))
EMB = "text-embedding-3-small"


# --- replacement for cra_panel._cred_for: env-var credential / route resolver -------------
# Judges keep their exact model IDs and the >=2-of-3 majority is unchanged; only the
# transport is env-configurable. Defaults mirror the internal run (gpt-5.5 native OpenAI;
# claude/gemini via OpenRouter). Override any route with STALE_ROUTE_<slug>_{KEY,URL,MODEL}.
_OR_URL = "https://openrouter.ai/api/v1"
_ROUTES = {
    "gpt-4o-mini": {"key_env": "OPENAI_API_KEY", "url": None, "model": "gpt-4o-mini"},
    "gpt-5.5": {"key_env": "OPENAI_API_KEY", "url": None, "model": "gpt-5.5"},
    "claude-opus-4-8": {"key_env": "OPENROUTER_API_KEY", "url": _OR_URL,
                        "model": "anthropic/claude-opus-4.8"},
    "gemini-3.1-pro-preview": {"key_env": "OPENROUTER_API_KEY", "url": _OR_URL,
                               "model": "google/gemini-3.1-pro-preview"},
}


def _cred_for(model):
    r = _ROUTES.get(model, {"key_env": "OPENAI_API_KEY", "url": None, "model": model})
    slug = re.sub(r"[^A-Za-z0-9]", "_", model).upper()
    key = os.environ.get(f"STALE_ROUTE_{slug}_KEY") or os.environ.get(r["key_env"])
    url = os.environ.get(f"STALE_ROUTE_{slug}_URL") or r["url"]
    real = os.environ.get(f"STALE_ROUTE_{slug}_MODEL") or r["model"]
    return key, url, real


# --- replacement for cra.language_cortex.LanguageCortex: OpenAI-compatible wrapper ---------
class LanguageCortex:
    def __init__(self, model, api_key=None, base_url=None):
        if api_key is None and base_url is None:
            key, url, real = _cred_for(model)
            api_key, base_url, model = key, url, real
        self.model = model
        self._cli = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, system, messages, max_tokens=400):
        r = self._cli.chat.completions.create(
            model=self.model, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}] + list(messages))
        return r.choices[0].message.content or ""

    def embed(self, texts):
        r = self._cli.embeddings.create(model=EMB, input=list(texts))
        return [d.embedding for d in r.data]


# --- replacement for cra.parallel.parallel_map --------------------------------------------
def parallel_map(fn, items, workers=4):
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        return list(ex.map(fn, items))


def _cos(u, v):
    s = sum(x * y for x, y in zip(u, v))
    nu = math.sqrt(sum(x * x for x in u)) or 1.0
    nv = math.sqrt(sum(y * y for y in v)) or 1.0
    return s / (nu * nv)


def load_dataset():
    p = os.path.join(DATA_DIR, "T1_T2_400_FULL.json")
    with open(p, encoding="utf-8") as f:
        j = json.load(f)
    rows = j["data"] if isinstance(j, dict) and "data" in j else j
    return rows


def norm_item(row):
    it = dict(row)
    for k in ("probing_queries", "haystack_session", "timestamps"):
        if isinstance(it.get(k), str):
            it[k] = json.loads(it[k])
    return it


def format_haystack(sessions, timestamps):
    out = ""
    for idx, session in enumerate(sessions):
        if not session:
            continue
        ts = f" [Time: {timestamps[idx]}]" if timestamps and idx < len(timestamps) else ""
        out += f"\n=== Session {idx + 1}{ts} ===\n"
        for turn in session:
            role = "User" if turn.get("role") == "user" else "Assistant"
            out += f"{role}: {turn.get('content', '')}\n"
    return out


_ENC = None


def _ntok(text):
    global _ENC
    if _ENC is None:
        import tiktoken
        _ENC = tiktoken.get_encoding("o200k_base")
    return len(_ENC.encode(text))


INPUT_TOKEN_LIMIT = 128000 - 6500 - 512


def trim_history(it, dim_key, query, seed):
    import copy as _copy
    import random as _random
    rng = _random.Random(seed)
    sessions = _copy.deepcopy(it["haystack_session"])
    tss = _copy.deepcopy(it.get("timestamps") or [])
    idx_old, idx_new = it["relevant_session_index"]

    def toks():
        return _ntok(format_haystack(sessions, tss) + str(query)) + 60

    cur = toks()
    if cur <= INPUT_TOKEN_LIMIT:
        return sessions, tss
    for _ in range(min(2, idx_old)):
        if cur <= INPUT_TOKEN_LIMIT:
            break
        sessions.pop(0)
        if tss:
            tss.pop(0)
        idx_old -= 1
        idx_new -= 1
        cur = toks()
    for _ in range(min(2, len(sessions) - 1 - idx_new)):
        if cur <= INPUT_TOKEN_LIMIT:
            break
        sessions.pop()
        if tss:
            tss.pop()
        cur = toks()
    middle = list(range(idx_old + 1, idx_new))
    while cur > INPUT_TOKEN_LIMIT and middle:
        di = rng.choice(middle)
        sessions.pop(di)
        if tss and di < len(tss):
            tss.pop(di)
        idx_new -= 1
        middle = list(range(idx_old + 1, idx_new))
        cur = toks()
    return sessions, tss


def baseline_answer(cortex, history_text, query, dim_key):
    if dim_key == "dim3_query":
        sysp = ("You are a helpful assistant. Review the following conversation history "
                "with the user, then respond to the user's latest query directly.")
        userp = f"[Conversation History]\n{history_text}\n\n[Latest Query]\n{query}"
    else:
        sysp = ("You are a helpful assistant. Review the following conversation history "
                "with the user, then accurately answer the question.")
        userp = f"[Conversation History]\n{history_text}\n\n[Question]\n{query}"
    return cortex.generate(sysp, [{"role": "user", "content": userp}], max_tokens=400)


PREMISE_CHECK = ("\nBefore answering, check whether the user's question or request PRESUPPOSES any "
                 "state that your sources show has since changed or been invalidated. If it does, "
                 "point out the outdated premise first, then answer according to the CURRENT state. "
                 "Do not silently comply with an outdated premise.")


def judge_user_prompt(it, responses):
    q = it["probing_queries"]
    return f"""
[Ground Truth Context]
- M_old: "{it['M_old']}"
- M_new: "{it['M_new']}"
- Hidden Logic: {it['explanation']}

--------------------------------------------------
[Dimension 1: Explicit Probing]
Question 1: {q['dim1_query']}
Target Model Response 1: {responses['dim1']}

--------------------------------------------------
[Dimension 2: Adversarial Robustness]
Question 2: {q['dim2_query']}
Target Model Response 2: {responses['dim2']}

--------------------------------------------------
[Dimension 3: Implicit Task]
Question 3: {q['dim3_query']}
Target Model Response 3: {responses['dim3']}
"""


_CORTEX = {}
_CLOCK = threading.Lock()


def _judge_system_prompt():
    """Lazily import STALE's judge prompt from your own STALE checkout so this module
    imports without the STALE repo present. Set STALE_REPO_DIR to the STALE directory
    that contains Evaluation/judge_prompts.py."""
    repo = os.environ.get("STALE_REPO_DIR")
    if repo and repo not in sys.path:
        sys.path.insert(0, repo)
    from Evaluation.judge_prompts import SYSTEM_PROMPT_ALL_IN_ONE_JUDGE
    return SYSTEM_PROMPT_ALL_IN_ONE_JUDGE


def get_cortex(model):
    with _CLOCK:
        if model not in _CORTEX:
            _CORTEX[model] = LanguageCortex(model=model)
        return _CORTEX[model]


def grade_majority(it, responses):
    """3-provider majority vote. Returns ({dim: bool}, {judge: {dim: bool}})."""
    sysp = _judge_system_prompt()
    per = {}
    for jm in JUDGES:
        cx = get_cortex(jm)
        raw = cx.generate(sysp,
                          [{"role": "user", "content": judge_user_prompt(it, responses)}],
                          max_tokens=800)
        m = re.search(r"\{.*\}", str(raw), re.S)
        j = json.loads(m.group(0)) if m else {}
        per[jm] = {f"dim{i}": bool(j.get(f"dim{i}_eval", {}).get("pass", False)) for i in (1, 2, 3)}
    maj = {f"dim{i}": sum(per[jm][f"dim{i}"] for jm in JUDGES) >= 2 for i in (1, 2, 3)}
    return maj, per


def run_item(it):
    uid = it["uid"]
    t0 = time.time()
    try:
        cortex = LanguageCortex(model=MODEL)
        sessions, tss = it["haystack_session"], it.get("timestamps")
        user_turns = []
        for idx, session in enumerate(sessions):
            ts = tss[idx] if tss and idx < len(tss) else ""
            for turn in session:
                c = str(turn.get("content", "")).strip()
                if turn.get("role") == "user" and len(c) >= 4:
                    user_turns.append(f"[{ts}] {c}" if ts else c)
        out = {"uid": uid, "type": it.get("type"), "user_turns": len(user_turns)}

        A = {}
        for i in (1, 2, 3):
            k = f"dim{i}_query"
            query = it["probing_queries"][k]
            tsess, ttss = trim_history(it, k, query, seed=uid)
            A[f"dim{i}"] = str(baseline_answer(cortex, format_haystack(tsess, ttss), query, k))

        vecs = []
        bs = 128
        plain = [t[:1000] for t in user_turns]
        for i in range(0, len(plain), bs):
            vecs.extend(cortex.embed(plain[i:i + bs]))
        B = {}
        for i in (1, 2, 3):
            query = it["probing_queries"][f"dim{i}_query"]
            qv = cortex.embed([query])[0]
            ranked = sorted(zip(user_turns, vecs), key=lambda x: _cos(qv, x[1]), reverse=True)[:RAG_K]
            ctx = "\n".join(f"- {t[:600]}" for t, _v in ranked)
            B[f"dim{i}"] = str(cortex.generate(
                "You are a helpful assistant. Below are records retrieved from past conversations "
                "(timestamps = time order). Answer accurately based on them." + PREMISE_CHECK,
                [{"role": "user", "content": f"[Retrieved records]\n{ctx}\n\n[Question]\n{query}"}],
                max_tokens=400))

        amaj, aper = grade_majority(it, A)
        bmaj, bper = grade_majority(it, B)
        for i in (1, 2, 3):
            out[f"a_dim{i}"], out[f"b_dim{i}"] = amaj[f"dim{i}"], bmaj[f"dim{i}"]
        out["a_per"], out["b_per"] = aper, bper
        out["a_ans"] = {k: v[:350] for k, v in A.items()}
        out["b_ans"] = {k: v[:350] for k, v in B.items()}
        out["sec"] = round(time.time() - t0, 1)
        _append(out)
        return out
    except Exception as ex:
        out = {"uid": uid, "error": f"{type(ex).__name__}: {ex}", "sec": round(time.time() - t0, 1)}
        _append(out)
        return out


_LOCK = threading.Lock()


def _append(row):
    with _LOCK:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def sign_test_p(wins_b, wins_a):
    """Two-sided sign test (exact binomial, p=0.5)."""
    n = wins_b + wins_a
    if n == 0:
        return 1.0
    k = max(wins_b, wins_a)
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


if __name__ == "__main__":
    rows = load_dataset()
    items = [norm_item(r) for r in rows]
    t1 = sorted([it for it in items if str(it.get("type")) == "T1"], key=lambda x: x["uid"])[:N // 2]
    t2 = sorted([it for it in items if str(it.get("type")) == "T2"], key=lambda x: x["uid"])[:N - N // 2]
    chosen = t1 + t2
    done_ok = {}
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            try:
                r = json.loads(line)
                if "error" not in r:
                    done_ok[r["uid"]] = r
            except Exception:
                pass
    todo = [it for it in chosen if it["uid"] not in done_ok]
    print(f"STALE full {len(chosen)} items (T1 {len(t1)} / T2 {len(t2)} / done {len(done_ok)} / "
          f"todo {len(todo)}) · model {MODEL} · judges (majority) {JUDGES}\n")
    if todo:
        workers = int(os.environ.get("STALE_WORKERS", "4"))
        parallel_map(run_item, todo, workers=min(workers, len(todo)))

    okr, seen = [], set()
    uids = {it["uid"] for it in chosen}
    for line in open(OUT, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("uid") in uids and r["uid"] not in seen and "error" not in r:
            okr.append(r); seen.add(r["uid"])
    res = {"n": len(chosen), "done": len(okr)}
    wins_b = wins_a = 0
    for arm in ("a", "b"):
        for i in (1, 2, 3):
            hits = sum(1 for r in okr if r.get(f"{arm}_dim{i}"))
            res[f"{arm}_dim{i}"] = round(hits / max(1, len(okr)), 3)
        allhits = sum(sum(1 for i in (1, 2, 3) if r.get(f"{arm}_dim{i}")) for r in okr)
        res[f"{arm}_all"] = round(allhits / max(1, 3 * len(okr)), 3)
    for r in okr:
        for i in (1, 2, 3):
            a, b = bool(r.get(f"a_dim{i}")), bool(r.get(f"b_dim{i}"))
            if b and not a:
                wins_b += 1
            elif a and not b:
                wins_a += 1
    res["wins_b"], res["wins_a"] = wins_b, wins_a
    res["sign_p"] = round(sign_test_p(wins_b, wins_a), 6)
    # per-type breakdown
    for tp in ("T1", "T2"):
        sub = [r for r in okr if r.get("type") == tp]
        for arm in ("a", "b"):
            allh = sum(sum(1 for i in (1, 2, 3) if r.get(f"{arm}_dim{i}")) for r in sub)
            res[f"{arm}_{tp}"] = round(allh / max(1, 3 * len(sub)), 3)
    fails = len(chosen) - len(okr)
    print(f"completed {len(okr)}/{len(chosen)} (failed {fails})")
    print(f"overall — A long-context {res['a_all']} · B (retrieval+premise-check) {res['b_all']} | "
          f"dim1 {res['a_dim1']}/{res['b_dim1']} · dim2 {res['a_dim2']}/{res['b_dim2']} · "
          f"dim3 {res['a_dim3']}/{res['b_dim3']}")
    print(f"T1: {res.get('a_T1')}/{res.get('b_T1')} · T2: {res.get('a_T2')}/{res.get('b_T2')} | "
          f"pairs B-win {wins_b} · A-win {wins_a} · p={res['sign_p']}")
    print()
    # inline verdict (was cra_rigor.Prereg.report)
    valid = res["done"] >= int(res["n"] * 0.9) and res["a_all"] < 0.95
    if not valid:
        verdict = "INVALID-SETUP (completion <90% or baseline at ceiling)"
    elif res["b_all"] > res["a_all"] and res["b_dim2"] > res["a_dim2"] and res["sign_p"] < 0.05:
        verdict = "POSITIVE"
    else:
        verdict = "NEGATIVE"
    print(f"validity={'PASS' if valid else 'FAIL'}  verdict={verdict}")
