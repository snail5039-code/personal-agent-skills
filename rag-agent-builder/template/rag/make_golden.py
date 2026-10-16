"""(골든셋이 없을 때) 청크에서 골든셋 초안을 만든다 -> 반드시 사람이 검수한 뒤 평가에 쓴다.

- 분야 × 콘텐츠 종류(text/table/image_text/figure)마다 고르게 청크를 뽑아 LLM이 문제·정답·근거 구절을 만든다
- 근거가 그 청크 하나로 맞다/틀리다 판단되는 구체적인 질문만 (정답 쪽 = 그 청크의 쪽)
- 답변 불가 문제(answerable=false)는 만들지 않는다 -> 문서에 없는 질문을 사람이 3~5개 직접 추가한다
- 결과: data/goldenset_draft.csv (target_page_no = 추출 단계의 위치 번호: PDF 쪽, 슬라이드, 시트, 섹션) (검수 후 이름을 바꿔 쓴다. 이미 있으면 덮어쓰지 않는다)

실행
    python -m rag.make_golden --per-group 2
"""

import argparse
import csv
import random

from pydantic import BaseModel, Field

from rag import config
from rag.common import chat_model, read_jsonl

COLUMNS = ["id", "domain", "question", "target_answer", "evidence", "target_file_name", "target_page_no",
           "context_type", "answerable", "source"]
CONTEXT_TYPE = {"text": "paragraph", "table": "table", "image_text": "image", "figure": "image"}

PROMPT = """아래는 한국어 문서의 한 부분이다. RAG 평가용 문제 하나를 만든다.
- 이 부분만 보고 정답을 맞다/틀리다로 판단할 수 있는 구체적인 질문 (주제·연도·대상을 넣어 다른 문서와 헷갈리지 않게)
- 질문에 파일명·쪽 번호를 쓰지 않는다 (실제 사용자처럼 묻는다). 예/아니오로 끝나는 질문은 만들지 않는다
- 정답은 이 부분에 있는 사실·수치만으로. evidence에는 정답 근거 원문을 그대로 짧게
- 목차·표지·참고문헌·정보가 없는 조각이면 usable=false

파일: {file_name} p.{page_no}
---
{text}
"""


class Draft(BaseModel):
    usable: bool = Field(description="문제를 만들 만한 내용이 있으면 true")
    question: str = ""
    target_answer: str = ""
    evidence: str = ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=config.DEFAULT_CONFIG)
    parser.add_argument("--per-group", type=int, default=2, help="분야 × 콘텐츠 종류마다 몇 문제")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = config.DATA_DIR / "goldenset_draft.csv"
    if out.exists():
        raise SystemExit(f"{out}가 이미 있습니다. 검수 중인 파일을 덮어쓰지 않도록 이름을 바꾸거나 지운 뒤 실행하세요.")
    chunks = [c for c in read_jsonl(config.CHUNK_DIR / args.config / "chunks.jsonl") if len(c["text"]) >= 150]
    groups = {}
    for c in chunks:
        groups.setdefault((c["metadata"]["domain"], c["metadata"]["content_type"]), []).append(c)
    rng = random.Random(args.seed)
    llm = chat_model(config.LLM_MODEL, max_retries=6).with_structured_output(Draft)

    rows = []
    for (domain, ct), items in sorted(groups.items()):
        made = 0
        for c in rng.sample(items, len(items)):
            if made >= args.per_group:
                break
            m = c["metadata"]
            d = llm.invoke(PROMPT.format(file_name=m["file_name"], page_no=m["page_no"], text=c["text"]))
            if not d.usable or not d.question:
                continue
            made += 1
            rows.append({"id": f"draft-{len(rows) + 1:03d}", "domain": domain, "question": d.question,
                         "target_answer": d.target_answer, "evidence": d.evidence, "target_file_name": m["file_name"],
                         "target_page_no": m["page_no"], "context_type": CONTEXT_TYPE.get(ct, ct),
                         "answerable": "true", "source": "draft"})
            print(f"  {rows[-1]['id']} [{domain}/{ct}] {d.question}", flush=True)

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)}문제 -> {out}\n검수: 질문이 구체적인지, 정답·쪽이 맞는지 확인하고 답변 불가 문제를 추가하세요.")


if __name__ == "__main__":
    main()
