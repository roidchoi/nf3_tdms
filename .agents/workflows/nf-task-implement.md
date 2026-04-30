---
description: task-spec 문서를 기반으로 실제 코드를 구현하는 워크플로우. 사용자가 "T-XXX 구현해", "구현 시작해", "코드 작성해", "task 구현 진행해" 등을 언급하거나, task-spec 파일을 열어둔 채로 구현을 요청하는 모든 상황에서 반드시 이 워크플로우를 따르십시오. spec 없이 구현하라는 요청이더라도, 구현 작업이라면 이 워크플로우의 절차를 준수하십시오.
---

# NF Task Implement 워크플로우

`task-{id}_spec.md`를 기반으로 실제 코드를 TDD 방식으로 구현하는 표준 절차입니다.

---

## Phase 0: 사전 준비 (Pre-flight)

구현 시작 전 반드시 아래 순서로 준비한다.

### 0-1. Karpathy 가이드라인 숙지
`/karpathy-guidelines` 워크플로우를 먼저 읽고 핵심 원칙(단순성 우선, 외과적 수정, 목표 기반 실행)을 내면화한다.

### 0-2. Spec 파일 전체 읽기
대상 `task-{id}_spec.md`의 **모든 섹션**을 빠짐없이 읽는다.

확인해야 할 항목:
- `§ 1 목표`: IN/OUT 범위 명확히 파악 — OUT 항목은 절대 구현하지 않는다
- `§ 2 구현 대상`: 생성할 파일 경로 목록
- `§ 4 테스트 케이스`: 테스트 코드를 먼저 작성하기 위한 핵심 정보
- `§ 5 구현 참고사항`: 가상환경명, requirements.txt, 기술 스택
- `§ 6 완료 기준`: 이 모든 항목이 통과해야 Task 완료

### 0-3. 필요 정보 사전 확보
`nf-wiki` 스킬을 통해 pjt-wiki에서 관련 컨텍스트를 먼저 조회한다.
이미 구현된 유사 모듈이 있으면 패턴을 참조하되, 복사·붙여넣기하지 않는다.

### 0-4. 가상환경 확인 및 구축
`/tdms-env-policy` 워크플로우를 기준으로:

```bash
# 환경 존재 여부 확인
conda env list | grep <env_name>

# 없으면 생성
conda create -n <env_name> python=3.12 -y

# 의존성 설치 (requirements.txt가 이미 있는 경우)
conda run -n <env_name> uv pip install -r <경로>/requirements.txt
```

> **핵심 규칙**: 에이전트 터미널에서 `conda activate`는 비대화형 셸에서 동작하지 않는다.
> 모든 명령은 반드시 `conda run -n <env_name> <명령>` 형식으로 실행한다.

---

## Phase 1: 환경 파일 생성

spec `§ 2`에서 파악한 파일 목록 중 **설정 파일**을 먼저 생성한다.

생성 순서:
1. `requirements.txt` — 의존성 목록 (spec `§ 5` 기준)
2. `pyproject.toml` — 패키지 메타데이터 정의
3. `__init__.py` — 패키지 루트 초기화 (필요 시 `__version__` 포함)
4. 서브패키지 `__init__.py` 파일들 (db/, utils/, ops/ 등)

파일 생성 후 즉시 환경 구축을 완료한다:
```bash
conda run -n <env_name> uv pip install -r requirements.txt
conda run -n <env_name> uv pip install -e <패키지_루트_경로>/
```

---

## Phase 2: 테스트 코드 먼저 작성 (Test-First)

spec `§ 4 테스트 케이스`의 코드를 **그대로** 테스트 파일로 옮긴다.
테스트는 아직 구현이 없으므로 실행하면 전부 실패(`FAILED` 또는 `ImportError`)해야 정상이다.

```bash
# 테스트 실행 — 전부 실패해야 정상 (Red 상태 확인)
conda run -n <env_name> pytest <테스트_경로>/ -v
```

> **왜 먼저 작성하는가?** 테스트가 실패하는 것을 눈으로 확인함으로써,
> 이후 구현이 실제로 그 테스트를 통과시키는 올바른 코드임을 검증할 수 있다.

---

## Phase 3: 모듈별 구현 (Green)

테스트 케이스 순서에 따라 **가장 단순한 모듈부터** 구현한다.

### 구현 원칙 (Karpathy 기반)
- 테스트를 통과하는 **최소한의 코드**만 작성한다. 과도한 추상화 금지.
- 하드코딩 금지 — 설정값은 `.env` 또는 생성자 주입 방식으로.
- 각 모듈 구현 후 즉시 해당 모듈의 테스트를 실행하여 Green 확인.

### 모듈별 구현 → 테스트 → 확인 사이클
```bash
# 특정 테스트 파일만 실행하여 빠르게 피드백
conda run -n <env_name> pytest <테스트_파일> -v

# 실패한 테스트만 다시 실행
conda run -n <env_name> pytest <테스트_파일> -v --lf
```

### 필요 시 외부 문서 조회
구현에 라이브러리 API가 필요한 경우 `context7 MCP`를 사용하여 최신 공식 문서를 조회한다.
기억에 의존하지 말고, 특히 DB 관련 라이브러리(psycopg2, SQLAlchemy 등)는 반드시 조회.

---

## Phase 4: 전체 테스트 통과 확인 (All Green)

모든 모듈 구현이 완료되면 전체 테스트 스위트를 실행한다.

```bash
# 전체 테스트 실행
conda run -n <env_name> pytest <테스트_루트>/ -v

# 커버리지 확인 (선택)
conda run -n <env_name> pytest <테스트_루트>/ -v --tb=short
```

spec `§ 6 완료 기준`의 모든 체크박스를 순서대로 검증한다:
- [ ] 전체 테스트 N개 통과
- [ ] editable install 후 `import <패키지>` 성공
- [ ] 기타 spec에 명시된 검증 항목

---

## Phase 5: 완료 처리

### 5-1. pjt_tasks 상태 업데이트
`docs/<subproject>/<subproject>_pjt_tasks.md`에서 해당 Task의 상태를 `진행 중` → `완료`로 변경한다.

### 5-2. Walkthrough 작성
`docs/<subproject>/tasks/task-{id}_walkthrough.md`를 생성한다.

포함 내용:
- 구현한 파일 목록 및 각 파일의 역할
- 설계상 주요 결정사항 (왜 이렇게 구현했는지)
- 테스트 결과 요약 (N개 통과)
- 다음 Task(의존 관계) 진행 시 주의사항

### 5-3. Git 커밋
변경된 모든 파일을 커밋한다.

```bash
git add <구현파일들> <테스트파일들> docs/<변경문서들>
git commit -m "feat(<서브프로젝트>): T-{id} <Task명> 구현 완료" \
           -m "- 구현: <파일 목록 요약>" \
           -m "- 테스트: N개 전체 통과"
```

---

## 단계별 요약 체크리스트

```
Phase 0: 사전 준비
  [ ] karpathy-guidelines 숙지
  [ ] spec 전체 읽기 (§1~§6)
  [ ] nf-wiki에서 관련 컨텍스트 조회
  [ ] 가상환경 확인/구축

Phase 1: 환경 파일 생성
  [ ] requirements.txt 생성
  [ ] pyproject.toml 생성
  [ ] __init__.py 파일들 생성
  [ ] 의존성 설치 완료

Phase 2: 테스트 먼저 작성 (Red)
  [ ] 테스트 파일 작성 (spec § 4 기준)
  [ ] pytest 실행 — 전부 실패 확인

Phase 3: 모듈 구현 (Green)
  [ ] 모듈별 구현 → 개별 테스트 통과 반복

Phase 4: 전체 검증
  [ ] 전체 테스트 N개 통과
  [ ] spec § 6 완료 기준 전체 통과

Phase 5: 완료 처리
  [ ] pjt_tasks.md 상태 업데이트
  [ ] walkthrough.md 작성
  [ ] git 커밋
```