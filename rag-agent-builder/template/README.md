# RAG 에이전트

`data/`의 문서로 질문에 답하는 RAG 에이전트. 근거(파일·쪽)를 함께 답하고, 근거가 부족하면 검색어를 바꿔 다시 찾으며(최대 3회), 끝까지 없으면 답변을 보류한다.

## 준비

```bash
pip install -r requirements.txt
cp .env.example .env      # GOOGLE_API_KEY 넣기 (다른 모델은 .env.example 참고)
```

문서는 `data/<분야>/`에, 골든셋 CSV는 `data/` 바로 아래에 둔다.

## 실행 순서

모든 명령은 이 폴더에서 실행한다. 단계마다 결과가 파일로 남고, 끊겨도 다시 실행하면 이어서 한다.

```bash
python -m rag.extract                 # 1. 추출 -> output/extracted/INDEX.md 에서 미리보기 확인
python -m rag.ocr                     # 2. (선택) 스캔·이미지 OCR
python -m rag.figures                 # 3. (선택) 차트·도식 -> 마크다운 (Vision 모델)
python -m rag.chunk                   # 4. 청킹 -> output/chunks/base_500_60/STATS.md
python -m rag.embed                   # 5. 임베딩 -> vectordb/
python -m rag.embed --query "질문"     #    검색 확인
python -m rag.agent "질문" --show-searches                       # 6. 에이전트에 질문
python -m rag.evaluate retrieval --golden data/<골든셋>.csv       # 7. 검색 평가
python -m rag.evaluate agent --golden data/<골든셋>.csv --limit 5 #    에이전트 평가 (먼저 5문제)
python -m rag.evaluate agent --golden data/<골든셋>.csv --mode rag #    기본 RAG와 비교
python -m rag.make_golden             # (골든셋이 없을 때) 초안 -> 반드시 검수
```

## 구조

| 파일 | 하는 일 |
|---|---|
| `rag/config.py` | 경로·모델·추출/청킹/검색/에이전트 설정 (설정은 여기서만 바꾼다) |
| `rag/common.py` | JSONL·마크다운 표·모델 생성 등 공통 도구 |
| `rag/extract/` | 형식별 추출 (PDF / DOCX·PPTX·XLSX·CSV·HTML·MD·TXT·이미지 / HWP 등은 LibreOffice 변환) |
| `rag/ocr.py`, `rag/figures.py` | 이미지 글자 OCR, 차트·도식 Vision 변환 |
| `rag/chunk.py` | 본문=길이 기준(논문형은 문단), 표=행 단위+헤더 반복, 그림=통째로 |
| `rag/embed.py`, `rag/retriever.py` | Chroma 임베딩, Hybrid(벡터+Kiwi BM25, RRF) + 앞뒤 청크 + 분야 보완 검색 |
| `rag/agent.py` | 에이전트(재검색·보류) / 기본 RAG(1회 검색) |
| `rag/evaluate.py` | 골든셋 평가 (검색 hit·MRR / 에이전트 정답률·근거 적중·보류) |

결과: `output/extracted/`(추출), `output/chunks/`(청크), `output/eval/`(평가 report.md), `output/runs/agent_runs.jsonl`(질문별 실행 기록)
