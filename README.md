# Personal Agent Skills

개인적으로 사용하는 Codex/Claude 호환 스킬 모음이다.

## 포함된 스킬

- `til`: 학습 자료를 Notion, TIL 저장소 Markdown, Tistory HTML 형식으로 정리한다.

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
```

`til` 스킬은 현재 `C:\puh\TIL` 경로와 개인 Notion 페이지를 사용하도록 설정되어 있다. 다른 컴퓨터에서는 TIL 저장소를 같은 위치에 두거나 `til/SKILL.md`의 고정 경로를 수정한다.

