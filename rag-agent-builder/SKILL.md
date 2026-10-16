---
name: rag-agent-builder
description: 사용자가 준 문서(PDF·DOCX·PPTX·XLSX·CSV·HWP/HWPX·HTML·MD·TXT·이미지)를 분석해 그 문서에 맞는 한국어 RAG 에이전트 파이프라인(추출 → 청킹 → 임베딩 → 하이브리드 검색 → 재검색·보류하는 에이전트 → 골든셋 평가)을 만들고 돌려 본다. "RAG 만들어줘", "문서로 질의응답 에이전트", "골든셋으로 평가", "검색 성능 개선" 같은 요청에 사용한다. 단순 RAG 개념 설명에는 사용하지 않는다.
---

# RAG 에이전트 만들기

`template/`의 검증된 파이프라인(rag_agent_practice에서 59개 PDF·309문제로 실험해 정한 기본값)을 사용자 문서에 맞춰 설치·조정하고 실행한다. 문서를 먼저 분석해서 **필요한 단계만** 넣고, 단계마다 결과를 눈으로 확인한 뒤 다음으로 넘어간다.

## 진행 순서

### 1. 요청 확인
다음이 없으면 짧게 묻는다. 기본값이 있으면 기본값으로 진행하고 알린다.
- 문서 위치 (필수)와 프로젝트를 만들 위치 (기본: 문서 폴더 옆 `rag-agent/`)
- 골든셋 유무 (없으면 초안을 만들어 검수받는다)
- 모델: 기본 Google Gemini (`GOOGLE_API_KEY`). OpenAI·Claude 등을 원하면 `.env`의 `LLM_PROVIDER`·`EMBEDDING_PROVIDER`로 바꾼다

### 2. 문서 분석 → 계획
```bash
python <스킬 경로>/scripts/profile_docs.py <문서 폴더> --out <프로젝트>/output
```
`PROFILE.md`를 읽고 아래를 정해 사용자에게 계획을 보여 준다. 사용자가 확인하면 진행한다.

| 프로파일 결과 | 결정 |
|---|---|
| 스캔 쪽·깨진 글자·큰 이미지·이미지 파일이 있음 | `rag.ocr` 넣기 |
| 차트·도식에 답이 있을 법함 (큰 이미지, 벡터 그림 많은 쪽) | `rag.figures` 넣기 (Vision 모델 비용 → 먼저 `--limit 5`로 품질 확인) |
| 둘 다 없음 | `ocr.py`·`figures.py`와 OCR 패키지를 빼고 설치 |
| HWP·DOC·PPT 등 | LibreOffice로 PDF 변환 (없으면 설치 안내 또는 PDF로 저장 요청. HWPX는 본문 글자만이라도 읽힘) |
| 2단 논문형 PDF | `PARAGRAPH_MODE="auto"`가 문단 단위로 자름 (그대로) |
| 분야가 섞여 있음 | `data/<분야>/`로 나눠 넣기 → 에이전트가 domain을 지정해 검색 |
| 영어 위주 | BM25 토크나이저(`retriever.BM25Search.tokenize`)를 공백·소문자 기반으로 |

### 3. 프로젝트 만들기
1. `template/`을 프로젝트 위치로 복사한다. 이미 있는 파일은 덮어쓰지 않고 차이를 보고한다.
2. 문서를 `data/<분야>/`에 복사한다 (원본은 옮기지 않는다). 골든셋 CSV는 `data/` 바로 아래에 둔다.
3. 계획에서 뺀 단계의 모듈과 `requirements.txt` 항목을 지운다. 필요한 형식의 선택 패키지만 남긴다.
4. `rag/config.py`의 `CORPUS_DESCRIPTION`을 문서 내용에 맞게 쓴다 (에이전트 프롬프트에 들어간다). 다른 값은 근거가 있을 때만 바꾼다.
5. `.env.example` → `.env`. API 키는 사용자가 직접 넣게 안내하고, 키 값을 대화에 옮겨 적지 않는다.
6. `pip install -r requirements.txt` (가상환경 권장).

### 4. 단계별 실행과 검수
모든 명령은 프로젝트 폴더에서 실행한다. 단계마다 표시한 것을 확인하고 문제가 있으면 다음 단계로 넘어가지 않는다.

| 단계 | 명령 | 확인할 것 |
|---|---|---|
| 추출 | `python -m rag.extract` | `output/extracted/INDEX.md`: 오류 0, 스캔형 수가 예상과 맞는지. 미리보기 2~3개를 열어 표·읽기 순서·머리말 제거 확인 |
| OCR (선택) | `python -m rag.ocr` | 미리보기에서 OCR 글자 품질, "Vision 대기" 수 |
| 그림 (선택) | `python -m rag.figures --limit 5` → 확인 후 `python -m rag.figures` | 차트 값·도식 관계가 원본 PNG와 맞는지 |
| 청킹 | `python -m rag.chunk` | `STATS.md`의 종류별 개수·길이, `preview/`에서 표 헤더 반복·문단 끊김 |
| 임베딩 | `python -m rag.embed` 후 `--query "문서에 있는 질문"` | 검색 결과가 맞는 문서·쪽인지 |
| 에이전트 | `python -m rag.agent "질문" --show-searches` | 답·근거 쪽·검색 횟수, 문서에 없는 질문은 보류하는지 |

추출 품질이 나쁘면 [파이프라인 구조](references/pipeline.md)의 확장 방법을 따라 해당 추출기만 고친다.

### 5. 골든셋
[평가 가이드](references/evaluation.md)의 CSV 형식을 따른다.
- 사용자 골든셋이 있으면 열 이름을 이 형식에 맞춘다 (원본은 보존하고 변환본을 따로 저장).
- 없으면 `python -m rag.make_golden --per-group 2`로 초안을 만들고, **사용자에게 검수를 요청한다**. 문서에 없는 질문(answerable=false) 3~5개도 넣는다. 검수되지 않은 초안으로 낸 점수는 "초안 기준"이라고 밝힌다.

### 6. 평가와 개선
```bash
python -m rag.evaluate retrieval --golden data/<골든셋>.csv                 # 검색만 (LLM 비용 없음)
python -m rag.evaluate agent --golden data/<골든셋>.csv --limit 5           # 먼저 5문제
python -m rag.evaluate agent --golden data/<골든셋>.csv                     # 전체 (끊겨도 이어서)
python -m rag.evaluate agent --golden data/<골든셋>.csv --mode rag          # 기본 RAG와 비교
```
`report.md`의 실패 사례를 [결정 근거와 튜닝](references/decisions.md)의 증상별 조치표로 진단하고 한 번에 하나씩 바꿔 다시 평가한다. LLM 답은 같은 설정에서도 1~2%p 흔들리므로 비슷한 결과는 `--tag run2`로 한 번 더 돌려 비교한다.

## 코드 원칙
- 설정값은 `rag/config.py`에만, 여러 단계가 쓰는 도구는 `rag/common.py`에만 둔다. 같은 로직을 두 파일에 복사하지 않는다.
- 새 문서 형식은 `rag/extract/formats.py`에 함수 하나를 추가하고 `EXTRACTORS`에 등록한다. 결과는 반드시 같은 페이지 dict 형식이어야 한다 (청킹 이후 단계는 형식을 모른다).
- 단계마다 결과를 파일로 남기고(JSONL·미리보기 md·report.md), 다시 실행하면 이어서 하도록 유지한다.
- 프롬프트를 바꾸면 `config.PROMPT_VERSION`을 올린다 (평가 결과 폴더가 섞이지 않게).
- 주석·docstring은 템플릿처럼 한국어로, 파일 맨 위에 규칙·흐름·실행 방법을 쓴다.

## 마무리 보고
- 만든 위치와 포함한/뺀 단계, 그 이유
- 단계별 결과 수치 (문서·쪽·청크 수, 검색 hit@5·MRR, 에이전트 정답률·잘못된 보류·답변 불가 보류·평균 검색·시간)
- 확인하지 못한 것 (예: 골든셋 미검수, Vision 단계 생략, LibreOffice 없음)
- 다음 개선 후보 1~3개
