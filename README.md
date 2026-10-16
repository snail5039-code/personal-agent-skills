# Personal Agent Skills

Codex와 Claude Code에서 쓰는 개인 스킬 모음입니다.

<br>

## 스킬 목록

| 스킬 | 호출 | 하는 일 | 결과물 |
|:---|:---|:---|:---|
| **TIL 정리** | `$til` | 학습 자료를 TIL 형식으로 정리 | 노션 페이지, TIL 마크다운, 티스토리 HTML |
| **자기소개서** | `$cover-letter-writing` | 채용공고와 경험을 연결해 작성 · 첨삭 | 초안 · 첨삭본, 확인 필요 항목, 예상 면접 질문 |
| **RAG 에이전트** | `$rag-agent-builder` | 문서 폴더로 RAG 에이전트 구축 · 평가 | 파이프라인 프로젝트, 평가 리포트 |

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
| 자기소개서 작성 | `$cover-letter-writing 이 채용공고와 제 경험으로 700자 지원동기 써줘` |
| 자기소개서 첨삭 | `$cover-letter-writing 아래 자소서 첨삭하고 예상 면접 질문 5개 알려줘` |
| RAG 에이전트 | `$rag-agent-builder C:\docs 폴더로 RAG 에이전트 만들어줘` |
| RAG 평가 | `$rag-agent-builder data/golden.csv로 평가하고 개선점 알려줘` |

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
