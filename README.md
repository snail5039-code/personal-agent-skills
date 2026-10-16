# Personal Agent Skills

Codex와 Claude Code에서 쓰는 개인 스킬 모음입니다.

<br>

## 스킬 목록

| 스킬 | 하는 일 |
|---|---|
| `til` | 학습 자료를 TIL 형식으로 정리 |
| `cover-letter-writing` | 자기소개서 작성과 첨삭 |
| `rag-agent-builder` | 문서로 RAG 에이전트 만들기 |

<br>

## 설치

```powershell
git clone https://github.com/snail5039-code/personal-agent-skills.git
cd personal-agent-skills
.\install.ps1
```

특정 스킬만 설치할 때

```powershell
.\install.ps1 -Skill til
```

> Codex 스킬 폴더(`~/.codex/skills`)에 설치됩니다.
> Claude Code는 스킬 폴더를 `~/.claude/skills`에 복사해서 씁니다.

<br>

## 사용 방법

스킬 이름 앞에 `$`를 붙이고, 이어서 요청을 씁니다.

```text
$스킬이름 요청 내용
```

<br>

### til

학습 자료를 세 가지 형태로 한 번에 정리합니다.

```text
$til 오늘 수업 자료 TIL로 정리해줘
```

**결과**

- 노션 페이지
- TIL 레포 마크다운 (`C:\puh\TIL`)
- 티스토리 HTML (목차 포함)

<br>

### cover-letter-writing

채용공고와 내 경험을 연결해 자기소개서를 쓰거나 고칩니다.

```text
$cover-letter-writing 이 채용공고와 제 경험으로 700자 지원동기 써줘
```

```text
$cover-letter-writing 아래 자소서 첨삭하고 예상 면접 질문 5개 알려줘
```

**결과**

- 초안 또는 첨삭본
- 사실 확인이 필요한 부분
- 예상 면접 꼬리질문

<br>

### rag-agent-builder

문서 폴더를 주면 RAG 에이전트를 만들고 평가까지 합니다.

```text
$rag-agent-builder C:\docs 폴더로 RAG 에이전트 만들어줘
```

**진행 순서**

1. 문서 분석 — 형식, 스캔, 표, 이미지 확인
2. 프로젝트 생성 — 파이프라인 코드 복사
3. 실행 — 추출 → 청킹 → 임베딩 → 에이전트
4. 평가 — 골든셋으로 정확도 채점

**지원 형식**

PDF, DOCX, PPTX, XLSX, CSV, HTML, MD, TXT, 이미지, HWP(LibreOffice 필요)

**준비물**

- Python 3.13
- `GOOGLE_API_KEY` (다른 모델로 변경 가능)
