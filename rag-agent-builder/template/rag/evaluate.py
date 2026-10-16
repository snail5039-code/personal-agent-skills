"""7. 골든셋 평가

retrieval (LLM 없이 검색만 채점, 청킹·검색기 고르기용)
- 검색된 청크의 (파일명, 쪽)이 정답 (파일명, 쪽)과 같으면 정답
- hit@1/3/5, recall@5, MRR, 검색 시간 / 검색 방식: similarity·mmr·bm25·hybrid·agent(에이전트 검색 그대로)

agent (에이전트 또는 기본 RAG로 풀고 채점)
- 답변 정확도: openevals CORRECTNESS_PROMPT로 LLM 채점 (채점 모델은 config.JUDGE_MODEL로 고정)
    답할 수 있는 문제를 보류하면 오답 / 답변 불가 문제(answerable=false)는 보류해야 정답
- 근거 쪽 적중(답에 든 근거 쪽이 정답 쪽인가), 검색 적중(검색한 청크에 정답 쪽이 있었나)
- 잘못된 보류, 답변 불가 보류, 평균 검색 횟수, 평균 시간 -> 전체·분야별·근거 유형별
- 문제마다 바로 저장 -> 끊겨도 다시 실행하면 이어서 (오류 난 문제는 다시 푼다)

골든셋 형식은 스킬의 references/evaluation.md 참고 (여러 문서 정답은 "A.pdf || B.pdf", "3 || 10,11")
정답 위치(target_page_no)를 비우면 파일만 맞으면 적중으로 본다 (쪽이 없는 형식이나 위치를 모를 때)

실행
    python -m rag.evaluate retrieval --golden data/golden_set.csv
    python -m rag.evaluate agent --golden data/golden_set.csv --limit 5     # 5문제로 먼저 확인
    python -m rag.evaluate agent --golden data/golden_set.csv               # 전체
    python -m rag.evaluate agent --golden data/golden_set.csv --mode rag    # 기본 RAG와 비교
    python -m rag.evaluate agent --golden data/golden_set.csv --tag run2    # 같은 설정 한 번 더 (LLM 흔들림 확인)

결과: output/eval/<retrieval|agent>/<골든셋>__<설정>.../report.md, details.jsonl
"""

import argparse
import csv
import re
import time

from rag import config
from rag.common import append_jsonl, norm_name, read_jsonl, write_jsonl

GROUPS = (("domain", "분야별"), ("context_type", "근거 유형별"))


# ---------------- 골든셋 ----------------

def load_golden(path, keep_unanswerable=True):
    """CSV -> 문제 목록. gold = {(정규화 파일명, 쪽 또는 None)}  None = 파일만 맞으면 적중"""
    rows = []
    with open(config.BASE_DIR / path, encoding="utf-8-sig") as f:
        for i, r in enumerate(csv.DictReader(f), start=1):
            answerable = str(r.get("answerable") or "true").strip().lower() != "false"
            if not answerable and not keep_unanswerable:
                continue
            gold = set()
            if answerable:
                names, pages = r["target_file_name"].split("||"), (r.get("target_page_no") or "").split("||")
                for i, name in enumerate(names):
                    nums = re.findall(r"\d+", pages[i] if i < len(pages) else "")
                    gold |= {(norm_name(name), int(p)) for p in nums} or {(norm_name(name), None)}
            rows.append({"qid": r.get("id") or f"q{i:03d}", "domain": r.get("domain", ""),
                         "context_type": r.get("context_type", ""), "question": r["question"],
                         "target_answer": r.get("target_answer", ""), "answerable": answerable, "gold": gold})
    return rows


def is_hit(page, gold):
    """(파일, 쪽)이 정답인가. 정답 쪽이 비어 있으면 파일만 맞으면 된다"""
    return page in gold or (page[0], None) in gold


def any_hit(chunks, gold):
    return any(is_hit((norm_name(c["file_name"]), int(c["page_no"])), gold) for c in chunks)


def gold_labels(q):
    return sorted(f"{f} p.{p}" if p else f for f, p in q["gold"])


# ---------------- 요약 표 ----------------

def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def md_table(columns, rows):
    """columns: {키: 표시 이름}, rows: dict 목록"""
    cell = lambda v: "-" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)
    return "\n".join(["| " + " | ".join(columns.values()) + " |", "|" + "---|" * len(columns)]
                     + ["| " + " | ".join(cell(r.get(k)) for k in columns) + " |" for r in rows])


def grouped_tables(rows, summarize, columns):
    """전체 + 분야별 + 근거 유형별 표. summarize(그룹 이름, rows) -> 표 행 목록"""
    md = ["## 전체", "", md_table(columns, summarize("전체", rows)), ""]
    for key, label in GROUPS:
        values = sorted({r[key] for r in rows if r[key]})
        if len(values) > 1:
            md += [f"## {label}", "", md_table(columns, [x for v in values
                                                       for x in summarize(v, [r for r in rows if r[key] == v])]), ""]
    return md


# ---------------- retrieval ----------------

RET_COLUMNS = {"name": "검색", "count": "문제", "hit@1": "hit@1", "hit@3": "hit@3", "hit@5": "hit@5",
               "recall@5": "recall@5", "mrr": "MRR", "ms": "ms"}


def score_retrieval(retrieved, gold):
    pages = [(norm_name(c["file_name"]), int(c["page_no"])) for c in retrieved]
    rel = [is_hit(p, gold) for p in pages]
    first = next((i + 1 for i, x in enumerate(rel) if x), None)
    found = {g for g in gold if any(p == g or (g[1] is None and p[0] == g[0]) for p in pages[:5])}
    return {"hit@1": any(rel[:1]), "hit@3": any(rel[:3]), "hit@5": any(rel[:5]),
            "recall@5": len(found) / len(gold), "mrr": 1 / first if first else 0.0}


def eval_retrieval(args):
    from rag.retriever import STRATEGIES, Retriever
    golden = load_golden(args.golden, keep_unanswerable=False)
    r = Retriever(args.config)
    unknown = {f for q in golden for f, _ in q["gold"]} - {norm_name(x["file_name"]) for x in r.rows}
    if unknown:
        print(f"[경고] 청크에 없는 골든셋 파일명: {sorted(unknown)}")
    find = {s: (lambda q, s=s: getattr(r, s)(q, args.k)) for s in STRATEGIES}
    find["agent"] = lambda q: r.search(q, k=args.k)
    strategies = args.strategies.split(",") if args.strategies else list(find)

    results = []
    for q in golden:
        for s in strategies:
            t0 = time.perf_counter()
            hits = find[s](q["question"])
            results.append({"qid": q["qid"], "strategy": s, "domain": q["domain"], "context_type": q["context_type"],
                            "question": q["question"], "gold": gold_labels(q),
                            "retrieved": [h["chunk_id"] for h in hits], "ms": (time.perf_counter() - t0) * 1000,
                            **score_retrieval(hits, q["gold"])})

    def summarize(name, rows):
        metrics = [m for m in RET_COLUMNS if m not in ("name", "count")]
        return [{"name": f"{name} · {s}", "count": len(rs), **{m: mean(float(x[m]) for x in rs) for m in metrics}}
                for s in strategies if (rs := [x for x in rows if x["strategy"] == s])]

    out = config.EVAL_DIR / "retrieval" / f"{stem(args.golden)}__{args.config}"
    write_jsonl(out / "details.jsonl", results)
    md = [f"# 검색 평가 - {args.golden} / {args.config} / k={args.k}", ""]
    md += grouped_tables(results, summarize, RET_COLUMNS)
    misses = [x for x in results if not x["hit@5"]]
    md += [f"## 놓친 문제 ({len(misses)})", ""] + [
        f"- [{x['strategy']}] {x['qid']} {x['question']}  \n  정답: {', '.join(x['gold'])} / 검색: {', '.join(x['retrieved'][:3])}"
        for x in misses]
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(md_table(RET_COLUMNS, summarize("전체", results)))
    print(f"보고서: {out / 'report.md'}")


# ---------------- agent ----------------

AGENT_COLUMNS = {"name": "그룹", "count": "문제", "answer_acc": "정답률", "citation_hit": "근거 쪽 적중",
                 "retrieval_hit": "검색 적중", "false_withhold": "잘못된 보류", "unans_withheld": "답변 불가 보류",
                 "avg_searches": "평균 검색", "avg_sec": "평균 초"}


def make_judge():
    from openevals.llm import create_llm_as_judge
    from openevals.prompts import CORRECTNESS_PROMPT
    from rag.common import chat_model
    return create_llm_as_judge(prompt=CORRECTNESS_PROMPT, judge=chat_model(config.JUDGE_MODEL, max_retries=6),
                               feedback_key="answer_correct")


def grade(judge, q, run, by_id):
    """-> {correct, judge_comment, citation_hit, retrieval_hit}"""
    withheld = run["status"] == "withheld"
    if not q["answerable"]:
        return {"correct": withheld, "judge_comment": "답변 불가 문제: " + ("보류함" if withheld else "답을 지어냄"),
                "citation_hit": None, "retrieval_hit": None}
    if withheld:
        correct, comment = False, "답할 수 있는 문제인데 보류함"
    else:
        res = judge(inputs=q["question"], outputs=run["answer"], reference_outputs=q["target_answer"])
        correct, comment = bool(res["score"]), res["comment"]
    searched = [by_id[cid] for cid in run["retrieved_chunk_ids"] if cid in by_id]
    return {"correct": correct, "judge_comment": comment,
            "citation_hit": any_hit(run["citations"], q["gold"]), "retrieval_hit": any_hit(searched, q["gold"])}


def summarize_agent(name, rows):
    ans = [r for r in rows if r["answerable"]]
    unans = [r for r in rows if not r["answerable"]]
    return {"name": name, "count": len(rows),
            "answer_acc": mean(r["correct"] for r in ans),
            "citation_hit": mean(r["citation_hit"] for r in ans),
            "retrieval_hit": mean(r["retrieval_hit"] for r in ans),
            "false_withhold": mean(r["status"] == "withheld" for r in ans),
            "unans_withheld": mean(r["status"] == "withheld" for r in unans),
            "avg_searches": mean(r["n_searches"] for r in rows),
            "avg_sec": mean(r["elapsed_sec"] for r in rows)}


FAILURES = {
    "답했는데 오답 - 검색은 정답 쪽을 찾음 (답변·프롬프트 문제)":
        lambda r: r["answerable"] and r["status"] == "answered" and not r["correct"] and r["retrieval_hit"],
    "답했는데 오답 - 검색도 못 찾음 (검색·청킹 문제)":
        lambda r: r["answerable"] and r["status"] == "answered" and not r["correct"] and not r["retrieval_hit"],
    "잘못된 보류": lambda r: r["answerable"] and r["status"] == "withheld",
    "답변 불가 문제에 답함": lambda r: not r["answerable"] and r["status"] != "withheld",
}


def eval_agent(args):
    from langsmith import tracing_context
    from rag.agent import RUNNERS
    golden = load_golden(args.golden)
    if args.ids:
        golden = [q for q in golden if q["qid"] in args.ids.split(",")]
    golden = golden[:args.limit or None]

    model = args.model or config.LLM_MODEL
    opts = f"nb{args.neighbors}" + ("_fb" if args.domain_fallback else "") + f"_{config.PROMPT_VERSION}"
    name = "__".join([stem(args.golden), args.config, model, opts + ("_rag" if args.mode == "rag" else "")]
                     + ([args.tag] if args.tag else []))
    out = config.EVAL_DIR / "agent" / name
    details = out / "details.jsonl"
    if args.fresh:
        details.unlink(missing_ok=True)
    done = {r["qid"]: r for r in read_jsonl(details)}
    todo = [q for q in golden if q["qid"] not in done or "error" in done[q["qid"]]]
    print(f"{args.golden}: {len(golden)}문제 / 이미 채점 {len(golden) - len(todo)} / 이번에 {len(todo)}")

    if todo:
        runner = RUNNERS[args.mode](args.config, model, neighbors=args.neighbors, domain_fallback=args.domain_fallback)
        judge = make_judge()
        for i, q in enumerate(todo, start=1):
            row = {k: q[k] for k in ("qid", "domain", "context_type", "question", "target_answer", "answerable")}
            row["gold"] = gold_labels(q)
            try:
                with tracing_context(enabled=False):  # 평가 중에는 LangSmith로 보내지 않는다 (호출이 많다)
                    run = runner.ask(q["question"], save=False)
                    row.update({k: run[k] for k in ("status", "answer", "judgement", "citations", "n_searches",
                                                    "searches", "retrieved_chunk_ids", "elapsed_sec")})
                    row.update(grade(judge, q, run, runner.retriever.by_id))
                mark = "O" if row["correct"] else "X"
            except Exception as e:  # 한 문제 실패로 멈추지 않게 기록하고 다음 실행 때 다시 푼다
                row["error"] = f"{type(e).__name__}: {e}"
                mark = "오류 " + row["error"][:80]
            append_jsonl(details, row)
            print(f"  [{i}/{len(todo)}] {q['qid']} {mark}", flush=True)

    done = {r["qid"]: r for r in read_jsonl(details)}
    rows = [done[q["qid"]] for q in golden if q["qid"] in done and "error" not in done[q["qid"]]]
    if not rows:
        return print("채점된 문제가 없습니다.")
    md = [f"# 에이전트 평가 - {name}", "", f"- 채점 모델 {config.JUDGE_MODEL}. 정답률·적중률·잘못된 보류는 답할 수 있는 문제 기준", ""]
    md += grouped_tables(rows, lambda n, rs: [summarize_agent(n, rs)], AGENT_COLUMNS)
    md += ["## 실패 사례", ""]
    for label, cond in FAILURES.items():
        cases = [r for r in rows if cond(r)]
        md += [f"### {label} ({len(cases)})", ""] + [
            f"- **{r['qid']}** {r['question']}  \n  정답: {r['target_answer'][:150]}  \n"
            f"  답[{r['status']}, 검색 {r['n_searches']}회]: {r['answer'][:150]}  \n  채점: {r['judge_comment'][:200]}"
            for r in cases] + [""]
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(md_table(AGENT_COLUMNS, [summarize_agent("전체", rows)]))
    print(f"오류로 빠진 문제 {len(golden) - len(rows)}개 (다시 실행하면 이어서) / 보고서: {out / 'report.md'}")


def stem(path):
    return re.sub(r"\.csv$", "", path.replace("\\", "/").rsplit("/", 1)[-1])


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd in ("retrieval", "agent"):
        p = sub.add_parser(cmd)
        p.add_argument("--golden", required=True, help="BASE_DIR 기준 골든셋 CSV 경로")
        p.add_argument("--config", default=config.DEFAULT_CONFIG)
    ret = sub.choices["retrieval"]
    ret.add_argument("--k", type=int, default=config.TOP_K)
    ret.add_argument("--strategies", help="쉼표로 구분 (기본: similarity,mmr,bm25,hybrid,agent)")
    ag = sub.choices["agent"]
    ag.add_argument("--mode", choices=("agent", "rag"), default="agent")
    ag.add_argument("--model", help="문제 푸는 모델 (채점 모델은 고정)")
    ag.add_argument("--limit", type=int)
    ag.add_argument("--ids", help="풀 문제 id (쉼표로 구분)")
    ag.add_argument("--fresh", action="store_true", help="이전 결과를 지우고 처음부터")
    ag.add_argument("--tag", help="같은 설정을 다시 돌릴 때 결과 폴더 뒤에 붙일 이름")
    ag.add_argument("--neighbors", type=int, default=config.NEIGHBORS)
    ag.add_argument("--no-domain-fallback", dest="domain_fallback", action="store_false")
    args = parser.parse_args()
    (eval_retrieval if args.cmd == "retrieval" else eval_agent)(args)


if __name__ == "__main__":
    main()
