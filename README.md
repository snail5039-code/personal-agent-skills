# Personal Agent Skills

Codex와 Claude Code에서 쓰는 개인 스킬 모음입니다.

<br>

## 스킬 목록

| 스킬 | 호출 | 하는 일 | 결과물 |
|:---|:---|:---|:---|
| **TIL 정리** | `$til` | 학습 자료를 TIL 형식으로 정리 | 노션 페이지, TIL 마크다운, 티스토리 HTML |
| **솔리드 이엔지 학습 기록** | `$solid-eng-til` | 업무 학습 내용을 예시 코드와 함께 네 항목으로 정리 | 지정된 노션 아래 `YYYY.MM.DD (짧은 학습 주제)` 형식의 하위 페이지 |
| **자기소개서** | `$cover-letter-writing` | 채용공고와 경험을 연결해 작성 · 첨삭 | 초안 · 첨삭본, 확인 필요 항목, 예상 면접 질문 |
| **RAG 에이전트** | `$rag-agent-builder` | 문서 폴더로 RAG 에이전트 구축 · 평가 | 파이프라인 프로젝트, 평가 리포트 |
| **한국 채용공고 탐색** | `$korean-job-discovery` | 국내 채용 사이트·기업 채용 페이지에서 공고를 찾고 공식 원문으로 확인 | 공고 목록, 확인한 출처, 남은 확인 사항 |
| **장애 조치 보고서** | `$incident-fix-report` | 장애를 재현·추적해 고치고 그 과정을 보고서로 기록 | 코드 수정 · 회귀 테스트, HTML 보고서, 남은 일 목록 |
| **업무 안내 메일** | `$work-update-email` | 조치·개선 내용을 발주처 담당자용 메일로 정리 | 붙여넣기용 메일 초안, 보내기 전 확인 메모 |

<br>

## 설치

```powershell
git clone https://github.com/snail5039-code/personal-agent-skills.git
cd personal-agent-skills
.\install.ps1
```

| 하고 싶은 것 | 방법 |
|:---|:---|
| 전체 설치 (Codex) | `.\install.ps1` |
| 하나만 설치 (Codex) | `.\install.ps1 -Skill til` |
| Claude Code에서 사용 | 스킬 폴더를 `~/.claude/skills/`에 복사 |

> 설치 위치는 `~/.codex/skills`이며, 같은 이름의 스킬이 있으면 덮어쓰지 않습니다.

<br>

## 사용 방법

`$스킬이름` 뒤에 요청을 이어서 씁니다.

| 스킬 | 이렇게 요청 |
|:---|:---|
| TIL 정리 | `$til 오늘 수업 자료 TIL로 정리해줘` |
| 솔리드 이엔지 학습 기록 | `$solid-eng-til 오늘 공부한 쿠버네티스 Service를 기록해줘` |
| 자기소개서 작성 | `$cover-letter-writing 이 채용공고와 제 경험으로 700자 지원동기 써줘` |
| 자기소개서 첨삭 | `$cover-letter-writing 아래 자소서 첨삭하고 예상 면접 질문 5개 알려줘` |
| RAG 에이전트 | `$rag-agent-builder C:\docs 폴더로 RAG 에이전트 만들어줘` |
| RAG 평가 | `$rag-agent-builder data/golden.csv로 평가하고 개선점 알려줘` |
| 채용공고 탐색 | `$korean-job-discovery 서울 신입 백엔드·AI 에이전트 공고 찾아줘` |
| 장애 조치 | `$incident-fix-report 예약 현황이 계속 실패하는데 원인 찾아서 고쳐줘` |
| 조치 보고서 | `$incident-fix-report 오늘 고친 거 인수인계용 보고서로 정리해줘` |
| 업무 안내 메일 | `$work-update-email 오늘 담당부서 검색 개선한 거 주무관님께 메일로 정리해줘` |

솔리드 이엔지 학습 기록은 지정된 노션 페이지 아래에 `2026.11.20 (쿠버네티스 Service)` 같은 제목으로 만들어요. 본문에는 오늘 배운 내용과 예시 코드, 어려울 수 있는 점, 헷갈린 부분(`없음` 포함), 업무에서 할 수 있는 일을 순서대로 적어요.

<br>

## RAG 에이전트 상세

### 진행 순서

| 단계 | 하는 일 |
|:---:|:---|
| 1 | **문서 분석** · 형식, 스캔, 표, 이미지, 2단 논문 확인 |
| 2 | **프로젝트 생성** · 파이프라인 코드 복사, 필요한 단계만 선택 |
| 3 | **실행** · 추출 → 청킹 → 임베딩 → 에이전트 |
| 4 | **평가** · 골든셋으로 검색 · 답변 정확도 · 보류 채점 |

### 지원 형식

| 구분 | 형식 |
|:---|:---|
| 문서 | PDF, DOCX, PPTX, HWP · DOC (LibreOffice로 변환) |
| 표 | XLSX, CSV |
| 텍스트 | HTML, MD, TXT |
| 이미지 | PNG, JPG 등 (OCR) |

### 준비물

| 항목 | 내용 |
|:---|:---|
| Python | 3.13 |
| API 키 | `GOOGLE_API_KEY` (`.env`에서 OpenAI · Claude로 변경 가능) |
| 선택 | LibreOffice (HWP · DOC 처리 시) |

<br>

## 출처

`korean-job-discovery`는 [Kimhyuntae9665/codex-skill-korean-job-discovery](https://github.com/Kimhyuntae9665/codex-skill-korean-job-discovery)(MIT)를 그대로 가져왔습니다. 원본 라이선스는 `korean-job-discovery/LICENSE`에 있습니다.
