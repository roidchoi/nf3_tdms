---
description: task-spec 문서를 기반으로 실제 코드를 TDD 방식으로 구현하는 워크플로우. 사용자가 "T-XXX 구현해", "구현 시작해", "코드 작성해", "task 구현 진행해" 등을 언급하거나, task-spec 파일을 열어둔 채로 구현을 요청하는 모든 상황에서 반드시 이 워크플로우를 따르십시오. spec 없이 구현하라는 요청이더라도, 구현 작업이라면 이 워크플로우의 절차를 준수하십시오.
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
- `[위키 선조회 완료]` 표 (Spec 상단): **⚠️ 직접 확인** 또는 **🆕 신규** 항목이 있으면 아래 0-3 단계에서 즉시 처리한다
- `§ 1 목표`: IN/OUT 범위 명확히 파악 — OUT 항목은 절대 구현하지 않는다
- `§ 2 구현 대상`: 생성할 파일 경로 목록
- `§ 3 핵심 인터페이스`: `[출처]` 주석 확인. `[위키 미기록]` 또는 `[신규 정의]` 표기 항목은 0-3에서 처리
- `§ 4 테스트 케이스`: Tier별 분류(Tier 1/2/3) 파악 — Tier 3(`@pytest.mark.integration`)는 Phase 4b에서 별도 실행
- `§ 5 구현 참고사항`: 가상환경명, requirements.txt, 기술 스택
- `§ 6 완료 기준`: 이 모든 항목이 통과해야 Task 완료

### 0-3. 미확인 인터페이스 선해소 (⚠️ 항목 처리)

Spec의 `[위키 선조회 완료]` 표에서 **⚠️ 직접 확인** 항목이 있거나,
`§ 3 핵심 인터페이스`에 `[위키 미기록 — ... 직접 확인 필요]` 표기가 있으면:

**구현 시작 전에 반드시 해당 소스 파일을 `view_file`로 직접 열어 실제 시그니처를 확인한다.**
추정으로 구현을 진행하면 전체 재작업으로 이어진다.

```
처리 절차:
1. Spec에서 "[위키 미기록]" 또는 "⚠️" 표기 항목 목록 추출
2. 각 항목에 명시된 소스 파일 경로를 view_file로 직접 열기
3. 실제 클래스/함수 시그니처, 파라미터, 반환 타입 확인
4. 확인된 내용을 메모하고 이를 기준으로 구현
5. 위키에 미기록된 내용이라면 구현 완료 후 Phase 5-4에서 위키에 추가
```

> **⚠️ 주의**: 소스 파일도 아직 없는 `[신규 정의]` 항목은 Spec의 인터페이스 명세가 설계 기준이다.
> Spec에 명시된 시그니처를 그대로 따르되, 불명확한 부분은 사용자에게 확인 후 진행한다.

### 0-4. 위키 컨텍스트 조회
`nf-wiki` 스킬을 통해 pjt-wiki에서 관련 컨텍스트를 조회한다.
이미 구현된 유사 모듈이 있으면 패턴을 참조하되, 복사·붙여넣기하지 않는다.

특히 다음을 확인한다:
- `pjt_wiki/00_schema/index.md` → 이 Task와 관련된 기존 인터페이스 문서 위치
- `{서브프로젝트}_wiki/decisions/*.md` → 이미 결정된 아키텍처 방향
- `{서브프로젝트}_wiki/errors/*.md` → 유사 구현에서 발생한 알려진 에러

### 0-5. 가상환경 확인 및 구축
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

## Phase 2: 테스트 코드 먼저 작성 (Test-First / Red)

spec `§ 4 테스트 케이스`의 코드를 **Tier별로 분리하여** 테스트 파일로 옮긴다.

### Tier별 처리 전략

| Tier | 표기 | 처리 방법 |
|---|---|---|
| Tier 1 (단위) | `# [Tier 1 — 단위]` | 그대로 작성, Phase 2에서 즉시 실행 |
| Tier 2 (격리 통합) | `# [Tier 2 — 격리 통합]` | 그대로 작성, Phase 2에서 즉시 실행 |
| Tier 3 (실제 통합) | `@pytest.mark.integration` | 완전히 작성, Phase 4b에서 별도 실행 |

**Tier 3 conftest 설정 확인**: `tests/conftest.py`에 아래 설정이 없으면 반드시 추가한다.
```python
# tests/conftest.py
def pytest_addoption(parser):
    parser.addoption("--run-integration", action="store_true", default=False)

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-integration"):
        skip = pytest.mark.skip(reason="--run-integration 플래그 없이는 실행 안 됨")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
```

### Red 상태 확인 (Tier 1 + Tier 2만)
```bash
# Tier 3 제외 — 전부 실패해야 정상 (Red 상태 확인)
conda run -n <env_name> pytest <테스트_경로>/ -v -m "not integration"
```

> **왜 먼저 작성하는가?** 테스트가 실패하는 것을 눈으로 확인함으로써,
> 이후 구현이 실제로 그 테스트를 통과시키는 올바른 코드임을 검증할 수 있다.

---

## Phase 3: 모듈별 구현 (Green)

테스트 케이스 순서에 따라 **가장 단순한 모듈부터** 구현한다.
Tier 1 → Tier 2 순으로 통과시키며 진행한다.

### 구현 원칙 (Karpathy 기반)
- 테스트를 통과하는 **최소한의 코드**만 작성한다. 과도한 추상화 금지.
- 하드코딩 금지 — 설정값은 `.env` 또는 생성자 주입 방식으로.
- 각 모듈 구현 후 즉시 해당 모듈의 테스트를 실행하여 Green 확인.

### 구현 중 인터페이스 불일치 발견 시

구현 도중 Spec의 인터페이스가 실제 코드와 다른 것을 발견하면:

1. **Spec이 추정으로 작성된 경우**: 실제 소스 파일을 `view_file`로 열어 올바른 시그니처 확인 후 해당 기준으로 구현
2. **신규 정의인데 Spec이 불명확한 경우**: 사용자에게 즉시 확인 요청 후 진행
3. **발견된 올바른 시그니처**: 구현 완료 후 Phase 5-4에서 nf-wiki에 기록

### 모듈별 구현 → 테스트 → 확인 사이클
```bash
# 특정 테스트 파일만 실행 (Tier 3 제외)
conda run -n <env_name> pytest <테스트_파일> -v -m "not integration"

# 실패한 테스트만 다시 실행
conda run -n <env_name> pytest <테스트_파일> -v --lf -m "not integration"
```

### 필요 시 외부 문서 조회
구현에 라이브러리 API가 필요한 경우 `context7 MCP`를 사용하여 최신 공식 문서를 조회한다.
기억에 의존하지 말고, 특히 DB 관련 라이브러리(psycopg2, SQLAlchemy 등)는 반드시 조회.

---

## Phase 4: 전체 테스트 통과 확인

### Phase 4a: Tier 1 + Tier 2 전체 통과 (All Green)

모든 모듈 구현이 완료되면 Tier 1, 2 전체 테스트를 실행한다.

```bash
# Tier 3 제외 전체 실행
conda run -n <env_name> pytest <테스트_루트>/ -v -m "not integration"
```

전체 통과 확인 후 spec `§ 6 완료 기준`의 해당 체크박스를 검증한다:
- [ ] Tier 1 + Tier 2 테스트 N개 통과
- [ ] editable install 후 `import <패키지>` 성공

### Phase 4b: Tier 3 실제 통합 테스트 (Integration)

> Tier 3 테스트는 실 DB 컨테이너가 기동된 상태에서만 실행한다.
> Spec의 `§ 6 완료 기준`에 Tier 3 통과가 명시된 경우에만 이 단계를 수행한다.

```bash
# DB 컨테이너 기동 확인
docker ps | grep <컨테이너명>

# Tier 3 통합 테스트 실행
conda run -n <env_name> pytest <테스트_루트>/ -v -m "integration" --run-integration
```

Tier 3 실행 전 사용자에게 다음을 안내한다:
```
[Tier 3 통합 테스트 실행 준비]
실 DB 컨테이너({컨테이너명})가 기동되어 있어야 합니다.
지금 실행할까요, 아니면 수동으로 실행하시겠습니까?
```

---

## Phase 5: 완료 처리

### 5-1. pjt_tasks 상태 업데이트
`docs/<subproject>/<subproject>_pjt_tasks.md`에서 해당 Task의 상태를 `진행 중` → `완료`로 변경한다.

### 5-2. Walkthrough 작성
`docs/<subproject>/tasks/task-{id}_walkthrough.md`를 생성한다.

포함 내용:
- 구현한 파일 목록 및 각 파일의 역할
- 설계상 주요 결정사항 (왜 이렇게 구현했는지)
- 테스트 결과 요약: Tier 1/2 N개 통과, Tier 3 N개 통과(실행한 경우)
- 다음 Task(의존 관계) 진행 시 주의사항
- 구현 중 발견된 Spec과 실제 코드 간 차이점 (있는 경우)

### 5-3. nf-wiki 업데이트 [신규]

이 Task 구현을 통해 새로 확인하거나 생성된 기술적 사실을 nf-wiki에 반드시 기록한다.
다음 중 해당하는 항목을 `nf-wiki` [업데이트 모드]로 처리한다:

- **새로 구현한 클래스/함수 시그니처** → `{서브프로젝트}_wiki/interfaces/` 에 개별 문서 생성/수정
- **구현 중 발견한 올바른 `.env` 변수명** (Spec이 추정이었던 경우) → `environment.md` 수정
- **구현 중 결정한 아키텍처 선택** → `decisions/` 에 기록
- **구현 중 만난 에러와 해결법** → `errors/` 에 기록
- **DB 스키마 변경** → `interfaces/schema_*.md` 수정

> Spec의 `[위키 선조회 완료]` 표에서 `⚠️ 직접 확인` 항목은 이 단계에서
> 위키 문서로 공식화하여 다음 Spec 작성 시 재조회 불필요하게 한다.

### 5-4. Git 커밋
변경된 모든 파일을 커밋한다.

```bash
git add <구현파일들> <테스트파일들> docs/<변경문서들>
git commit -m "feat(<서브프로젝트>): T-{id} <Task명> 구현 완료" \
           -m "- 구현: <파일 목록 요약>" \
           -m "- 테스트: Tier1+2 N개 / Tier3 N개 통과"
```

---

## 단계별 요약 체크리스트

```
Phase 0: 사전 준비
  [ ] karpathy-guidelines 숙지
  [ ] spec 전체 읽기 (§1~§6)
  [ ] Spec [위키 선조회 완료] 표의 ⚠️ 항목 → 실제 소스 파일 view_file로 확인
  [ ] Spec § 3의 [위키 미기록] 항목 → 실제 소스 파일 view_file로 확인
  [ ] nf-wiki에서 관련 컨텍스트 조회 (decisions, errors 포함)
  [ ] 가상환경 확인/구축

Phase 1: 환경 파일 생성
  [ ] requirements.txt 생성
  [ ] pyproject.toml 생성
  [ ] __init__.py 파일들 생성
  [ ] 의존성 설치 완료

Phase 2: 테스트 먼저 작성 (Red)
  [ ] conftest.py에 --run-integration 옵션 추가 (Tier 3 있는 경우)
  [ ] Tier 1 + Tier 2 테스트 파일 작성 (spec § 4 기준)
  [ ] Tier 3 통합 테스트 파일 작성 (pass 없이 완전하게)
  [ ] pytest -m "not integration" 실행 — Tier 1+2 전부 실패 확인 (Red)

Phase 3: 모듈 구현 (Green)
  [ ] Tier 1 테스트 순서로 단순 모듈부터 구현
  [ ] Tier 2 테스트 순서로 통합 로직 구현
  [ ] 인터페이스 불일치 발견 시 즉시 실제 파일 확인 (추정 금지)

Phase 4: 전체 검증
  Phase 4a — Tier 1 + Tier 2
  [ ] pytest -m "not integration" 전체 통과
  [ ] spec § 6 완료 기준 해당 항목 통과
  Phase 4b — Tier 3 (실 DB 필요, 해당 시)
  [ ] DB 컨테이너 기동 확인
  [ ] pytest -m "integration" --run-integration 전체 통과

Phase 5: 완료 처리
  [ ] pjt_tasks.md 상태 업데이트
  [ ] walkthrough.md 작성 (Tier별 테스트 결과 포함)
  [ ] nf-wiki 업데이트 (새 인터페이스, 에러, 결정사항 기록)
  [ ] git 커밋
```