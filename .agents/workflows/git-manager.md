---
name: git-manager
description: 사용자가 소스 관리, 커밋, 브랜치 관리, 푸시, 풀, 클론, 롤백, 충돌 해결 등 Git과 관련된 작업을 요청할 때 반드시 이 워크플로우를 트리거하십시오. GitHub MCP를 사용할 수 없는 환경이므로, 항상 run_command를 사용하여 터미널(Git CLI) 명령으로 직접 실행해야 합니다.
---

# Git 관리 워크플로우 (git-manager)

이 워크플로우는 Git Credential Manager(GCM) 인증을 바탕으로 터미널 명령을 이용해 Git 작업을 직접적이고 일관성 있게 수행하기 위한 가이드입니다. 에이전트는 사용자가 Git 작업을 요청하면 다음의 규칙과 방법론에 따라 터미널 명령(`run_command`)을 실행해야 합니다.

## 1. 기본 동작 원칙
- **터미널 직접 실행**: GitHub MCP 등 외부 서버 도구를 찾지 마십시오. 항상 `run_command` 도구를 사용하여 `git` 명령을 터미널에서 직접 실행하십시오.
- **상태 확인 우선**: 불필요한 오류를 방지하기 위해 작업 전후로 항상 `git status` 또는 `git log -n 3` 명령을 실행하여 현재 상태를 확인하십시오.

## 2. 환경 설정 및 초기화 (Setup & Init)
- **기본 설정 확인**: `git config --list` 명령으로 현재 설정(user.name, user.email)을 확인하고, 필요 시 `git config user.name "이름"`, `git config user.email "이메일"` 명령으로 설정을 지원합니다.
- **초기화 및 원격 연결**:
  - 저장소 초기화: `git init`
  - 필요시 `.gitignore` 파일 생성 (개발 환경에 맞는 템플릿 제안)
  - 원격 저장소 연결: `git remote add origin <URL>`
  - 클론: 지정된 경로에 `git clone <URL> <디렉토리>` 실행

## 3. 브랜치 관리 전략 및 명명 규칙 (Branch Strategy)
- **전략**: `main`(또는 `master`) 브랜치는 배포 가능한 안정적인 상태를 유지해야 합니다. 기능 개발이나 버그 수정은 항상 별도의 작업 브랜치에서 진행합니다.
- **명명 규칙**:
  - 기능 개발: `feat/<기능명>`
  - 버그 수정: `fix/<버그명>`
  - 문서 작업: `docs/<문서명>`
  - 코드 리팩토링: `refactor/<작업명>`
  - (예: `git checkout -b feat/login-system`)

## 4. 커밋 메시지 컨벤션 (Commit Convention)
Angular/Conventional Commits 규칙을 따르되, **모든 내용은 한국어로 작성**합니다.
- **형식**: `<타입>: <한글 제목>` (예: `feat: 사용자 인증 기능 추가`)
- **타입**:
  - `feat`: 새로운 기능 추가
  - `fix`: 버그 수정
  - `docs`: 문서 수정 (예: 위키 업데이트)
  - `style`: 코드 포맷팅, 세미콜론 누락 등 (코드 로직 변경 없음)
  - `refactor`: 코드 리팩토링
  - `test`: 테스트 코드 추가/수정
  - `chore`: 빌드 업무 수정, 패키지 매니저 설정 등
- **작성 규칙 (일관성 유지)**:
  - **제목**: 50자 이내, 명령조보다는 명사형 종결이나 "~함"체 권장 (예: "~ 추가", "~ 수정")
  - **본문**: "왜(Why)"와 "무엇을(What)" 위주로 기술하며, 다음 템플릿을 준수합니다.
    ```
    - 원인: [작업 배경/이유]
    - 내용: [주요 변경 사항]
    ```
  - **실행 명령**: `git commit -m "타입: 제목" -m "- 원인: 내용" -m "- 내용: 내용"`

## 5. 커밋 전 필수 점검 절차 (Pre-Commit Checklist)

구현 완료 후 커밋 시 파일 누락을 방지하기 위해 아래 절차를 **반드시** 따릅니다.

### Step 1: 전체 변경 파일 목록 확인
커밋 전에 반드시 다음 명령으로 변경된 모든 파일을 파악합니다.
`git add`는 아직 하지 말고 확인만 먼저 합니다:

```bash
git status            # Untracked + Modified + Staged 전체 표시
git diff --name-only  # 추적 중인 Modified 파일만 표시
```

### Step 2: 파일 분류 및 처리 결정
확인된 파일들을 다음 기준으로 분류합니다:

| 분류 | 기준 | 처리 |
|------|------|------|
| **당연히 포함** | 현재 세션에서 직접 생성/수정한 코드, 테스트, 문서 | 즉시 `git add` |
| **연관 파일** | 현재 Task의 spec, walkthrough 등 세션과 연관된 문서 | 즉시 `git add` — **누락 시 경고** |
| **무관/미진행 파일** | 이전 세션 잔여물, 다른 Task 파일 등 | 사용자에게 확인 후 결정 |

> **핵심 규칙**: `git add <파일1> <파일2>` 방식으로 파일을 개별 명시하면 **Untracked 파일이 빠질 위험**이 있습니다.
> 분류가 끝났다면 `git add docs/ tdms_core/` 처럼 **경로 단위로 추가**하거나 `git add -A`를 사용하여 누락을 방지하십시오.

### Step 3: 미관련 파일 발견 시 사용자 확인 요청
분류 결과 "무관/미진행 파일"이 발견된 경우, 커밋 전 다음 형식으로 사용자에게 확인을 요청합니다:

```
커밋 전 확인 요청

현재 세션(T-XXX)과 직접 관련이 없거나 이번 세션에서 변경되지 않은 파일이 감지되었습니다:

  [미관련 파일 목록]
  - 파일명 1 (이유: ...)
  - 파일명 2 (이유: ...)

선택지:
  A. 이번 커밋에 함께 포함
  B. 별도 커밋으로 분리
  C. 스테이징 제외 (나중에 처리)

어떻게 처리할까요?
```

### Step 4: Task 구현 커밋 시 자동 포함 대상
구현 Task 커밋 시에는 다음 파일들이 포함되었는지 반드시 체크합니다:
- `docs/<subproject>/tasks/task-{id}_spec.md` — 구현 명세서 (Untracked 여부 주의!)
- `docs/<subproject>/tasks/task-{id}_walkthrough.md` — 완료 후 워크스루
- `docs/<subproject>/<subproject>_pjt_tasks.md` — 상태 업데이트 파일

## 6. 병합 및 동기화 (Merge & Sync)
가장 깔끔한 히스토리 관리를 위해 **"Rebase 후 `--no-ff` 병합"**을 기본 전략으로 사용합니다.

- **Pull (원격 브랜치 동기화)**:
  - 현재 작업 브랜치를 최신 상태로 만들 때 꼬임을 방지하기 위해 `--rebase`를 권장합니다. (`git pull origin <브랜치> --rebase`)
- **작업 브랜치를 메인 브랜치로 병합하는 절차**:
  1. 작업 브랜치에서 메인 브랜치의 최신 내용을 가져와 Rebase합니다.
     `git fetch origin`
     `git rebase origin/main` (또는 로컬 main)
  2. Rebase 완료 후 메인 브랜치로 이동합니다.
     `git checkout main`
  3. 작업 브랜치를 `--no-ff` 옵션을 주어 병합하며, **병합 메시지 역시 한국어로 작성**합니다.
     - **형식**: `merge: <브랜치명> 병합 - <주요 작업 요약>`
     - (예: `git merge --no-ff <작업브랜치> -m "merge: feat/login-ui 병합 - 로그인 화면 구현 완료"`)
  4. 원격 저장소에 푸시합니다.
     `git push origin main`

## 7. 문제 발생 대처 가이드 (Troubleshooting & Rollback)
에이전트는 문제가 발생했을 때 당황하지 않고 다음 가이드에 따라 침착하게 해결을 돕습니다.

- **충돌(Conflict) 해결**:
  1. Rebase 또는 Merge 중 충돌이 발생하면 `git status`로 충돌 파일을 확인하고 사용자에게 알립니다.
  2. 에디터 도구(`replace_file_content` 등)를 이용해 파일 내의 충돌 마커(`<<<<<<<`, `=======`, `>>>>>>>`)를 분석하고 알맞게 코드를 수정한 후 저장합니다.
  3. 해결된 파일을 `git add <파일>`로 스테이징합니다.
  4. `git rebase --continue` 또는 `git commit`을 진행하여 병합을 완료합니다.
- **안전한 롤백 (Revert)**:
  - 이미 푸시된 커밋이거나 다른 사람과 협업 중인 경우 `git revert <커밋해시>`를 사용하여 이전 상태로 되돌리는 새로운 커밋을 생성합니다.
- **로컬 히스토리 취소 (Reset)**:
  - 푸시되지 않은 로컬 커밋을 취소할 때 사용합니다.
  - `git reset --soft HEAD~1` (커밋만 취소, 파일 변경사항 및 스테이징 유지)
  - `git reset --hard HEAD~1` (주의: 커밋, 파일 변경사항 모두 삭제)
- **실수 복구 (Reflog)**:
  - 잘못된 Reset이나 Rebase를 복구해야 할 때 `git reflog` 명령을 실행하여 이전 HEAD 상태의 해시를 찾은 뒤, `git reset --hard <해시>`로 복구합니다.

## 8. OS 및 쉘 호환성 가이드 (Compatibility)
- **Windows 환경 주의사항**: 
  - Windows PowerShell 환경에서는 명령어 체이닝 연산자(`&&`)가 작동하지 않을 수 있습니다. (PowerShell 7 미만 버전)
  - **권장 사항**: 모든 Git 명령어는 `run_command`를 통해 **하나씩 개별적으로 실행**하십시오.
  - 복합 명령어가 필요한 경우 연산자(`&&`, `;`)를 사용하기보다 단계별로 나누어 실행하고, 각 단계의 결과를 `git status` 등으로 검증하십시오.
