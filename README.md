# Personal Agent Skills

개인적으로 사용하는 Codex/Claude 호환 스킬 모음이다.

## 포함된 스킬

- `til`: 학습 자료를 Notion, TIL 저장소 Markdown, Tistory HTML 형식으로 정리한다.
- `cover-letter-writing`: 채용공고와 실제 경험을 연결해 한국어 자기소개서를 작성하고 첨삭한다.
- `rag-agent-builder`: 문서 폴더를 분석해 추출·청킹·임베딩·하이브리드 검색·재검색 에이전트·골든셋 평가까지 갖춘 RAG 파이프라인을 만든다.

## 스킬 호출

Codex에서 스킬 이름 앞에 `$`를 붙여 호출한다.

- 자기소개서 스킬: `$cover-letter-writing`
- TIL 스킬: `$til`
- RAG 에이전트 스킬: `$rag-agent-builder`

자기소개서 작성 예시:

```text
$cover-letter-writing 이 채용공고와 제 경험을 바탕으로 700자 지원동기를 작성해줘.
```

자기소개서 첨삭 예시:

```text
$cover-letter-writing 아래 자기소개서를 첨삭하고, 사실 확인이 필요한 부분과 예상 면접 꼬리질문 5개를 알려줘.
```

RAG 에이전트 만들기 예시:

```text
$rag-agent-builder C:\docs\보고서 폴더의 문서로 RAG 에이전트를 만들고 data/golden.csv로 평가해줘.
```

스킬 이름을 쓰지 않아도 요청 내용에 따라 자동 선택될 수 있지만, 확실히 적용하려면 위 호출명을 명시한다.

## Codex에 설치

PowerShell에서 다음 명령을 실행한다.

```powershell
.\install.ps1
```

기본 설치 위치는 `$env:CODEX_HOME\skills`이며, `CODEX_HOME`이 없으면 `$HOME\.codex\skills`를 사용한다. 이미 같은 이름의 스킬이 있으면 덮어쓰지 않는다.

## 수동 설치

필요한 스킬 폴더를 Codex의 `skills` 폴더 아래에 복사한다.

```text
personal-agent-skills/til
→ ~/.codex/skills/til

personal-agent-skills/cover-letter-writing
→ ~/.codex/skills/cover-letter-writing

personal-agent-skills/rag-agent-builder
→ ~/.codex/skills/rag-agent-builder
```

`til` 스킬은 현재 `C:\puh\TIL` 경로와 개인 Notion 페이지를 사용하도록 설정되어 있다. 다른 컴퓨터에서는 TIL 저장소를 같은 위치에 두거나 `til/SKILL.md`의 고정 경로를 수정한다.

`rag-agent-builder` 스킬은 `template/`을 새 프로젝트로 복사해 쓴다. 파이프라인 실행에는 Python 3.13과 `template/requirements.txt`의 패키지, 기본 모델 사용 시 `GOOGLE_API_KEY`가 필요하다. HWP·DOC 등은 LibreOffice가 있으면 PDF로 변환해 처리한다.
