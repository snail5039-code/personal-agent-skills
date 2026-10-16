# 파이프라인 구조

## 폴더

```
<프로젝트>/
├─ .env                     API 키·모델 (git 제외)
├─ requirements.txt
├─ data/
│   ├─ <분야>/...           문서 (분야 폴더 이름 = domain)
│   └─ <골든셋>.csv         data/ 바로 아래 csv는 문서로 읽지 않는다
├─ rag/
│   ├─ config.py            경로·모델·추출/청킹/검색/에이전트 설정 (설정은 여기만)
│   ├─ common.py            JSONL·마크다운 표·LLM/임베딩 모델·파일명 정규화
│   ├─ extract/
│   │   ├─ __init__.py      1. 형식별 추출기 고르기 -> 페이지 JSONL + 미리보기  (python -m rag.extract)
│   │   ├─ pdf.py           PDF: 여백·표·2단·이미지 후보·스캔 판정
│   │   └─ formats.py       DOCX·PPTX·XLSX/CSV·HTML·MD/TXT·이미지·LibreOffice 변환
│   ├─ ocr.py               2. (선택) 이미지 영역 OCR + 이미지 속 표 복원
│   ├─ figures.py           3. (선택) 차트·도식 찾기 -> Vision 모델로 마크다운 -> 반영
│   ├─ chunk.py             4. 콘텐츠 종류별 청킹
│   ├─ embed.py             5. Chroma 임베딩 (이어서 실행)
│   ├─ retriever.py         검색기 (similarity·mmr·bm25·hybrid + 에이전트 검색)
│   ├─ agent.py             6. RAG 에이전트 / 기본 RAG
│   ├─ evaluate.py          7. 골든셋 평가 (retrieval / agent)
│   └─ make_golden.py       (선택) 골든셋 초안
├─ output/
│   ├─ extracted/           jsonl/, preview/, INDEX.md, images/, figures/
│   ├─ chunks/<설정>/       chunks.jsonl, STATS.md, preview/
│   ├─ eval/                retrieval/, agent/ (report.md, details.jsonl)
│   └─ runs/                agent_runs.jsonl (질문마다 실행 기록)
└─ vectordb/                Chroma + BM25 캐시 (다시 만들 수 있음, git 제외)
```

## 데이터 계약

단계 사이에는 이 형식만 주고받는다. 새 형식·새 단계도 이 형식을 지킨다.

### 페이지 dict (`output/extracted/jsonl/<분야>/<파일명><확장자>.jsonl`, 한 줄 = 한 위치)

```json
{"file_name": "보고서.pdf", "domain": "finance", "source_path": "data/finance/보고서.pdf",
 "render_path": "data/finance/보고서.pdf", "total_pages": 12,
 "page_no": 3, "unit": "page", "page_type": "text|mixed|scan|empty|error", "columns": 1, "char_count": 1520,
 "blocks": [ ... ]}
```

- `page_no`: 근거 위치 번호. PDF는 물리 쪽(1부터), 슬라이드·시트·섹션은 그 순번 (`unit`에 단위)
- `render_path`: OCR·그림 단계가 렌더링할 PDF/이미지. 없으면(null) 그 단계 대상이 아니다

| block `content_type` | 필드 | 만드는 곳 | 청킹 |
|---|---|---|---|
| `text` | text, bbox(PDF만) | pdf, formats | 길이 기준 또는 문단 |
| `markdown` | text | formats (md·txt) | 표는 행 단위, 나머지 길이 기준 |
| `table` | headers, rows, footnotes, text | pdf, formats | 행 단위 + 헤더·각주 반복 |
| `image` | image_id, bbox, needs_vision, text, ocr_*, vision_method | pdf, formats(이미지) -> ocr, figures | OCR/Vision 글자를 마크다운 규칙으로. `[이미지]` 사진은 버림 |
| `figure` | figure_kind, figure_id, image_path, text | figures | 그림 하나 = 한 청크 |

### 청크 (`output/chunks/<설정>/chunks.jsonl`)

```json
{"chunk_id": "finance/보고서.pdf/p003/c01", "text": "...",
 "metadata": {"file_name": "보고서.pdf", "domain": "finance", "page_no": 3, "unit": "page",
              "page_type": "text", "content_type": "text|table|image_text|figure", "doc_type": "general|paragraph", "method": "..."}}
```

- `chunk_id` = `<분야>/<jsonl 이름>/p<쪽 3자리>/c<순서 2자리>`: 검색기가 같은 쪽 앞뒤 청크를 이 형식으로 찾는다. 바꾸면 `retriever.with_neighbors`도 고친다
- 청크는 위치(쪽)를 넘지 않는다 → 근거 쪽이 정확하다

## 확장 방법

| 하고 싶은 것 | 고칠 곳 |
|---|---|
| 새 문서 형식 | `extract/formats.py`에 `xxx_pages(path) -> [page dict]` 추가, `EXTRACTORS`에 확장자 등록. 쪽 개념이 없으면 `sections()`로 나눈다 |
| PDF 머리말·꼬리말이 남음/본문이 잘림 | `config.MARGIN` (미리보기로 확인) |
| 특정 PDF 표가 깨짐 | `config.MIN_TABLE_TEXT_RATIO`, 또는 `pdf.extract_tables`의 판정 |
| 문단 단위로 자를 문서 지정 | `config.PARAGRAPH_FILES` / `PARAGRAPH_MODE` |
| 모델 바꾸기 | `.env`의 `LLM_PROVIDER`·`LLM_MODEL`·`EMBEDDING_PROVIDER`·`EMBEDDING_MODEL` (langchain-openai 등 패키지 추가). 임베딩을 바꾸면 `vectordb/` 삭제 후 `rag.embed` |
| 리랭커 추가 | `Retriever.search`에서 hybrid 후보를 fetch_k개 받아 재정렬 후 k개 → `evaluate retrieval`의 `agent` 전략으로 비교 |
| 툴 추가 (계산기·웹검색 등) | `RagAgent.__init__`의 tools에 추가. 툴이 여러 개로 늘면 그때 슈퍼바이저 구조 검토 |
| 영어 문서 | `BM25Search.tokenize`를 공백·소문자 기반으로 |
