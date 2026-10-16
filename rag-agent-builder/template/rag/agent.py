"""6. RAG 에이전트 (LangChain create_agent) + 비교용 기본 RAG

RagAgent
- search(query, domain) 툴 -> Retriever.search (Hybrid + 분야 보완 + 앞뒤 청크)
- 근거 판단: 질문의 부분마다 근거가 있는지 judgement에 먼저 쓰고 status를 정한다
- 재검색: 부족하면 검색어를 바꿔 다시. 최초 포함 최대 MAX_SEARCHES회 (ToolCallLimitMiddleware로 강제)
- 보류: 끝까지 근거가 없으면 status="withheld"
BasicRag: 질문 그대로 한 번만 검색하고 바로 답한다 (검색기·모델·답변 형식·규칙은 같고 재검색만 없음)

실행 결과(질문, 답, 근거, 검색어·청크 ID, 검색 횟수, 시간)는 output/runs/agent_runs.jsonl에 저장된다.

실행
    python -m rag.agent "질문"
    python -m rag.agent "질문" --show-searches
    python -m rag.agent "질문" --mode rag
"""

import argparse
import time
import uuid
from datetime import datetime
from typing import Literal, Optional

from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, Field

from rag import config
from rag.common import append_jsonl, chat_model
from rag.retriever import Retriever

JUDGE_RULES = """[근거 판단]
- 질문이 여러 부분(예: 목적과 활동, 금액과 변화율)이면 부분마다 근거가 있는지 따로 확인한다.
- 표·그래프의 수치로 차이·증감률·순위·비교를 계산할 수 있으면 근거가 있는 것으로 본다.
  문서에 비교·결론 문장이 따로 없다는 이유만으로 보류하지 않는다."""

ANSWER_RULES = """[답변]
- 검색 결과에 있는 내용만으로 한국어로 답한다. 추측하거나 문서 밖 지식을 보태지 않는다.
- 질문의 모든 부분에 답한다. 계산했으면 계산에 쓴 수치와 결과를 함께 쓴다.
- 수치는 연도·대상·단위가 질문과 같은 것을 쓴다.
- citations에는 실제로 답에 쓴 근거만 넣는다: chunk_id, file_name, page_no, quote(검색 결과 원문 그대로 짧게).
- judgement에 근거가 충분/부족한 이유를 먼저 쓰고, 그 판단에 맞게 status를 정한다."""


def agent_prompt(domains):
    domain_rule = (f"- 분야가 확실하면 domain({', '.join(domains)})을 지정하고, 애매하면 비워 둔다.\n"
                   if len(domains) > 1 else "")
    return f"""너는 {config.CORPUS_DESCRIPTION}에 근거해서만 답하는 RAG 에이전트다.

[검색]
- 답하기 전에 반드시 search 툴로 문서를 검색한다. 검색은 최초 포함 최대 {config.MAX_SEARCHES}번까지만 할 수 있다.
{domain_rule}
{JUDGE_RULES}
- 부족한 부분이 있으면 그 부분을 찾도록 검색어를 바꿔 다시 검색한다: 핵심어만 남기기,
  동의어·문서에 나올 법한 표현으로 바꾸기, domain을 지정했다면 풀기.
- {config.MAX_SEARCHES}번 검색해도 근거가 없으면 지어내지 말고 status="withheld"로 답변을 보류한다.

{ANSWER_RULES}"""


BASIC_RAG_PROMPT = f"""너는 {config.CORPUS_DESCRIPTION}에 근거해서만 답하는 RAG 어시스턴트다.
아래 검색 결과만 보고 답한다. 다시 검색할 수 없다.

{JUDGE_RULES}
- 검색 결과에 근거가 없으면 지어내지 말고 status="withheld"로 답변을 보류한다.

{ANSWER_RULES}

질문: {{question}}

검색 결과:
{{context}}
"""


class Citation(BaseModel):
    chunk_id: str = Field(description="검색 결과의 chunk_id")
    file_name: str = Field(description="파일명")
    page_no: int = Field(description="쪽 번호")
    quote: str = Field(description="답의 근거가 된 원문 구절 (검색 결과에서 그대로)")


class Answer(BaseModel):
    # 필드 순서대로 생성되므로 judgement를 먼저 쓰고 그에 맞춰 status를 정하게 한다
    judgement: str = Field(description="질문의 부분마다 근거가 충분/부족한지와 그 이유")
    status: Literal["answered", "withheld"] = Field(description="answered=답변, withheld=근거 부족으로 보류")
    answer: str = Field(description="한국어 답변. 보류면 근거를 찾지 못했다는 안내")
    citations: list[Citation] = Field(default_factory=list, description="답에 쓴 근거")


def format_results(chunks):
    """검색 결과 -> LLM이 읽을 텍스트"""
    return "\n\n".join(f"[{i}] chunk_id={c['chunk_id']} | {c['file_name']} p.{c['page_no']} ({c['content_type']})\n{c['text']}"
                       for i, c in enumerate(chunks, start=1)) or "검색 결과 없음"


def search_record(query, domain, chunks):
    """검색 한 번의 기록. 앞뒤 청크를 붙였으면 LLM이 실제로 본 청크를 모두 남긴다"""
    ids = [cid for c in chunks for cid in c.get("chunk_ids", [c["chunk_id"]])] if chunks is not None else []
    return {"query": query, "domain": domain, "blocked": chunks is None, "chunk_ids": ids}


class BaseRunner:
    mode = ""

    def __init__(self, name=config.DEFAULT_CONFIG, model=None, **retriever_options):
        self.config_name = name
        self.model_name = model or config.LLM_MODEL
        self.retriever = Retriever(name, **retriever_options)
        self.llm = chat_model(self.model_name)

    def ask(self, question, save=True):
        t0 = time.time()
        answer, searches = self.run(question)
        result = {
            "run_id": uuid.uuid4().hex[:12], "time": datetime.now().isoformat(timespec="seconds"),
            "mode": self.mode, "model": self.model_name, "config": self.config_name, "question": question,
            "status": answer.status if answer else "error",
            "answer": answer.answer if answer else "",
            "judgement": answer.judgement if answer else "",
            "citations": [c.model_dump() for c in answer.citations] if answer else [],
            "n_searches": sum(not s["blocked"] for s in searches), "searches": searches,
            "retrieved_chunk_ids": sorted({cid for s in searches for cid in s["chunk_ids"]}),
            "elapsed_sec": round(time.time() - t0, 2),
        }
        if save:
            append_jsonl(config.RUNS_DIR / "agent_runs.jsonl", result)
        return result

    def run(self, question):
        """-> (Answer, [검색 기록])"""
        raise NotImplementedError


class RagAgent(BaseRunner):
    mode = "agent"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from langchain.agents import create_agent
        from langchain.agents.middleware import ToolCallLimitMiddleware
        from langchain_core.tools import tool
        retriever = self.retriever

        @tool(response_format="content_and_artifact")
        def search(query: str, domain: Optional[str] = None):
            """문서에서 질문의 근거를 검색한다.

            Args:
                query: 검색어 (질문 그대로 또는 핵심어)
                domain: 분야. 애매하면 비워 둔다
            """
            chunks = retriever.search(query, domain=domain)
            return format_results(chunks), chunks  # 본문은 LLM에게, 청크 목록은 artifact로 기록에

        self.agent = create_agent(
            model=self.llm, tools=[search], system_prompt=agent_prompt(retriever.domains),
            middleware=[ToolCallLimitMiddleware(tool_name="search", run_limit=config.MAX_SEARCHES)],
            response_format=Answer,
        )

    def run(self, question):
        state = self.agent.invoke({"messages": [{"role": "user", "content": question}]})
        return state.get("structured_response"), extract_searches(state["messages"])


class BasicRag(BaseRunner):
    mode = "rag"

    def run(self, question):
        chunks = self.retriever.search(question)
        answer = self.llm.with_structured_output(Answer).invoke(
            BASIC_RAG_PROMPT.format(question=question, context=format_results(chunks)))
        return answer, [search_record(question, None, chunks)]


def extract_searches(messages):
    """메시지 기록에서 search 호출(검색어·domain)과 결과 청크를 순서대로 뽑는다.
    호출 횟수 제한에 걸린 호출은 실행되지 않아 artifact가 없다 -> blocked"""
    calls = [tc for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls or [] if tc["name"] == "search"]
    artifacts = {m.tool_call_id: getattr(m, "artifact", None) for m in messages if isinstance(m, ToolMessage)}
    return [search_record(tc["args"].get("query", ""), tc["args"].get("domain"), artifacts.get(tc["id"]))
            for tc in calls]


RUNNERS = {"agent": RagAgent, "rag": BasicRag}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--mode", choices=RUNNERS, default="agent")
    parser.add_argument("--show-searches", action="store_true")
    args = parser.parse_args()
    r = RUNNERS[args.mode]().ask(args.question)
    print(f"\n[{r['status']}] {r['answer']}\n\n근거 판단: {r['judgement']}")
    for c in r["citations"]:
        print(f"  - {c['file_name']} p.{c['page_no']} ({c['chunk_id']}): {c['quote'][:80]}")
    print(f"검색 {r['n_searches']}회 / {r['elapsed_sec']}초")
    if args.show_searches:
        for i, s in enumerate(r["searches"], start=1):
            print(f"  검색{i}: {s['query']} (domain={s['domain']}){' [제한 초과로 차단]' if s['blocked'] else ''}")
            for cid in s["chunk_ids"][:8]:
                print(f"      {cid}")


if __name__ == "__main__":
    main()
