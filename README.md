# Personal Agent Skills

Codex · Claude Code에서 쓰는 개인 스킬 모음.

| 스킬 | 호출 | 하는 일 |
|---|---|---|
| [til](til/SKILL.md) | `$til` | 학습 자료를 노션 · TIL 레포 마크다운 · 티스토리 HTML로 정리 |
| [cover-letter-writing](cover-letter-writing/SKILL.md) | `$cover-letter-writing` | 채용공고와 경험을 연결해 자기소개서 작성 · 첨삭 |
| [rag-agent-builder](rag-agent-builder/SKILL.md) | `$rag-agent-builder` | 문서 폴더로 RAG 에이전트를 만들고 골든셋으로 평가 |

## 설치

```powershell
git clone https://github.com/snail5039-code/personal-agent-skills.git
cd personal-agent-skills
.\install.ps1                            # 전부 설치
.\install.ps1 -Skill rag-agent-builder   # 하나만 설치
```

- 설치 위치: `$env:CODEX_HOME\skills` (없으면 `$HOME\.codex\skills`)
- 같은 이름의 스킬이 있으면 덮어쓰지 않고 건너뛴다
- Claude Code는 스킬 폴더를 `~/.claude/skills/<스킬 이름>`에 복사한다

## 사용 방법

스킬 이름 앞에 `$`를 붙이고 요청을 이어 쓴다. 이름을 안 써도 자동으로 선택될 수 있지만, 확실히 쓰려면 호출명을 붙인다.

### til

```text
$til 오늘 수업 자료(첨부) TIL로 정리해줘
```

- 결과: 노션 페이지, `C:\puh\TIL` 레포용 마크다운, 목차가 있는 티스토리 HTML
- 다른 컴퓨터에서는 TIL 레포를 같은 경로에 두거나 `til/SKILL.md`의 경로를 고친다

### cover-letter-writing

```text
$cover-letter-writing 이 채용공고와 제 경험으로 700자 지원동기 써줘
$cover-letter-writing 아래 자소서 첨삭하고 예상 면접 꼬리질문 5개 알려줘
```

- 문항 의도를 정리하고 결론부터 쓴다
- 주지 않은 경험·수치는 만들지 않고 `[확인 필요]`로 표시한다

### rag-agent-builder

```text
$rag-agent-builder C:\docs\보고서 폴더로 RAG 에이전트 만들고 data/golden.csv로 평가해줘
```

진행 순서:

1. 문서 분석: 형식, 스캔 쪽, 표, 이미지, 2단 논문을 확인하고 필요한 단계를 정한다
2. 프로젝트 생성: `template/`을 복사하고 문서를 `data/<분야>/`에 넣는다
3. 실행: 추출 → (OCR · 차트 변환) → 청킹 → 임베딩 → 에이전트, 단계마다 결과 확인
4. 평가: 골든셋으로 검색 · 답변 정확도 · 보류를 채점하고 개선한다 (골든셋이 없으면 초안 생성 후 검수)

- 지원 형식: PDF, DOCX, PPTX, XLSX, CSV, HTML, MD, TXT, 이미지 (HWP · DOC는 LibreOffice로 PDF 변환)
- 필요: Python 3.13, `GOOGLE_API_KEY` (`.env`에서 OpenAI · Claude 등으로 변경 가능)
- 기본 설정 근거와 실험 결과: [rag-agent-builder/references/decisions.md](rag-agent-builder/references/decisions.md)

## 구조

```text
til/                     SKILL.md, references/ (양식, 티스토리 템플릿)
cover-letter-writing/    SKILL.md, references/ (작성 가이드)
rag-agent-builder/       SKILL.md, scripts/ (문서 분석), references/, template/ (파이프라인 코드)
install.ps1              Codex 설치 스크립트
```
