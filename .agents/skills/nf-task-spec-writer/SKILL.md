---
name: nf-task-spec-writer
description: >
  Task 목록(`p{n}_pjt_tasks.md`)의 특정 Task를 구현 명세(`task-{id}_spec.md`)로
  변환하는 스킬. 사용자가 "Task 명세 작성해줘", "T-XXX Spec 만들어줘",
  "구현 명세 써줘", "이 Task 상세화해줘", "구현 시작 전 명세 작성" 등을 언급하거나,
  특정 Task의 구현을 시작하기 직전에 상세 명세가 필요한 모든 상황에서 반드시 이 스킬을 사용하세요.
  Task Planner(nf-task-planner)가 Task 목록을 만든 직후 단계에서도 자동으로 이 스킬을
  제안하세요.
---

# nf-task-spec-writer

Task 목록의 특정 Task를 테스트 케이스 중심 구현 명세(`task-{id}_spec.md`)로 변환하는 스킬입니다.

> 산출물 템플릿은 `references/output-template.md`를 참조하세요.
> 위키 선조회 프로토콜은 `references/wiki-query-protocol.md`를 참조하세요.

---

## § 1. 역할 및 입출력

### 경로 규칙 — 반드시 먼저 확인

작업 시작 전 `docs/` 폴더 하위 디렉토리명을 확인하여 실제 존재하는 경로를 사용합니다.

현재 프로젝트 구조:

```
docs/
├── p1_shared/      → p1_shared_PRD.md 등
├── p2_kdms/        → p2_kdms_PRD.md 등
├── p3_usdms/       → p3_usdms_PRD.md 등
├── p4_manager/     → p4_manager_PRD.md 등
└── parent/         → 상위 PRD
```

경로 패턴: `docs/{서브프로젝트폴더}/` (예: `docs/p2_kdms/`)

> 산출물을 저장할 하위 폴더(`tasks/` 등)가 없으면 **폴더를 맘대로 생성하지 말고**
> 사용자에게 어디에 저장할지 보고 후 진행하세요.

**입력:**
- `docs/{서브프로젝트폴더}/{서브프로젝트폴더}_pjt_tasks.md` (필수, 예: `docs/p2_kdms/p2_kdms_pjt_tasks.md`)
- `docs/{서브프로젝트폴더}/{서브프로젝트폴더}_PRD.md` (필수)
- `docs/{서브프로젝트폴더}/{서브프로젝트폴더}_TRD.md`, `_DB_SCHEMA.md` (선택)
- 이전 완료 Task의 walkthrough 문서 (선택)

**출력:**
- `docs/{서브프로젝트폴더}/task-{id}_spec.md` (단일 산출물)
- 예시: `docs/p2_kdms/task-001_spec.md`

> 만약 해당 서브프로젝트 폴더에 `tasks/` 하위 폴더가 이미 존재하면
> `docs/{서브프로젝트폴더}/tasks/task-{id}_spec.md`로 저장합니다.

**이 스킬의 책임 범위 밖:**
- 실제 테스트 코드 작성 → 구현 Agent
- 실제 구현 → 구현 Agent

---

## § 2. 핵심 원칙: 테스트가 명세다

이 Spec의 목적은 **"무엇을 만들어야 하는가"를 테스트 케이스로 전달**하는 것입니다.

- 테스트 케이스 = 구현 목표의 구체적 표현
- 테스트 케이스 = 완료 기준(DoD)
- 테스트 케이스 = 올바른 구현 방향 유도 장치

구현 Agent는 테스트 케이스를 먼저 코드로 작성한 뒤, 테스트가 통과하도록 구현합니다.
**테스트 케이스의 품질이 구현 결과의 품질을 결정합니다.**

> **황금률**: 인터페이스·변수명·임포트 경로·DB 스키마는 절대 추정으로 작성하지 않습니다.
> 위키에서 확인하거나, 위키에 없으면 실제 소스 파일을 직접 열어 확인합니다.
> 이를 지키지 않은 Spec은 구현 Agent를 잘못된 방향으로 유도하여 전체 재작업을 유발합니다.

---

## § 3. 작업 프로세스

```
Step 1: Task 파악
         └─ p{n}_pjt_tasks.md에서 대상 Task 정보 및 구현 범위 요약 확인

Step 2: 위키 선조회 [필수 — 건너뛰기 금지]
         └─ references/wiki-query-protocol.md를 읽고 절차를 따른다
         └─ 조회 완료 체크리스트를 채운다
         └─ 미기록 항목은 실제 소스 파일을 view_file로 직접 확인한다

Step 3: 요구사항 분석
         └─ PRD에서 이 Task가 커버하는 요구사항 추출
         └─ TRD·DB_SCHEMA에서 기술 제약 확인 (있는 경우)
         └─ Step 2에서 확인한 위키 정보와 통합

Step 4: 테스트 케이스 설계 (핵심 작업)
         └─ 정상 동작 케이스 (happy path)
         └─ 경계값 및 예외 처리 케이스
         └─ 기존 기능 보존 케이스 (수정 Task인 경우)
         └─ 각 케이스에 검증 계층(Tier) 표기
         └─ 각 케이스가 "올바른 구현 방향"을 유도하는지 검토

Step 5: Spec 작성 (references/output-template.md 형식 사용)
         └─ 위키 선조회 완료 표를 Spec 상단에 포함

Step 6: 사용자 검토 요청

Step 7: 최종 승인 후 저장
```

**Step 6 검토 요청 시 반드시 포함할 내용:**

```
[Task-{id} Spec 초안]
테스트 케이스 {N}개를 작성했습니다.

[위키 선조회 결과]
- 확인 완료: {확인된 인터페이스/변수 목록}
- 직접 확인(소스 파일): {위키 미기록으로 소스 파일 직접 열어 확인한 항목}
- 신규 정의: {이 Task에서 처음 설계하는 인터페이스}

[설계 판단 확인]
1. {테스트 케이스 설계에서 판단이 필요했던 사항}
2. {Tier 3(실제 통합) 테스트 포함 여부 및 이유}

[확인 요청]
- 테스트 케이스가 구현 의도를 충분히 유도하는가?
- 누락된 케이스가 있는가?
- 인터페이스(함수명, 파라미터)가 의도와 일치하는가?
```

---

## § 4. 테스트 케이스 설계 원칙

### 4.1 검증 계층(Tier) — 모든 테스트 케이스에 반드시 표기

테스트 케이스는 다음 세 계층 중 하나로 분류합니다.
분류는 테스트 케이스 요약 표의 `계층` 컬럼에 명시합니다.

| 계층 | 설명 | 실행 조건 | 기본 실행 |
|---|---|---|---|
| **Tier 1: 단위** | DB·외부 의존성 Zero. 순수 Python 로직만 검증 | 항상 | ✅ |
| **Tier 2: 격리 통합** | DB·API·외부 서비스를 `mocker`로 대체 | 항상 | ✅ |
| **Tier 3: 실제 통합** | 실 DB 컨테이너 또는 실제 API 연결 필요 | `--run-integration` 플래그 | ❌ (기본 제외) |

**Tier 3 작성 규칙**:
- `@pytest.mark.integration` 마커를 반드시 부여합니다
- `pass`로 남기는 것은 **절대 금지** — 실제 검증 내용을 완전히 작성합니다
- conftest.py에 `--run-integration` 옵션 없이는 skip하는 설정을 포함하도록 지시합니다
- Tier 3는 "실제 DB에 연결했을 때 올바르게 동작하는가"를 검증하는 핵심 안전망입니다

**나쁜 예 (절대 금지)**:
```python
def test_refresh_adjusted_ohlcv_batch_executes_cte(mocker):
    # mock cursor 및 execute를 이용해 테스트 작성
    pass  # ← 이것은 테스트가 아님. 의미 없는 placeholder.
```

**좋은 예**:
```python
@pytest.mark.integration
def test_refresh_adjusted_ohlcv_batch_writes_to_physical_table(real_pool):
    """
    [Tier 3 — 실제 DB 필요: pytest --run-integration으로만 실행]
    [목적] refresh_adjusted_ohlcv_batch 실행 후 daily_ohlcv_adjusted 테이블에
           실제 행이 쓰여지는지 검증.
    """
    repo = OhlcvRepo(pool=real_pool)
    rows = repo.refresh_adjusted_ohlcv_batch(
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 31)
    )
    assert rows > 0
    with real_pool.get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM daily_ohlcv_adjusted")
        count = cur.fetchone()[0]
    assert count > 0
```

### 4.2 케이스 구성 기준

**모든 Task에 포함:**

| 케이스 유형 | Tier | 목적 | 예시 |
|---|---|---|---|
| 정상 동작 (happy path) | Tier 1 또는 2 | 주요 기능이 올바르게 동작 | 유효한 입력 → 예상 출력 |
| 경계값 | Tier 1 | 극단적 입력에서의 동작 | 빈 데이터, 최소/최대값 |
| 예외/오류 처리 | Tier 1 | 잘못된 입력에서의 동작 | None 입력, 타입 오류 |
| 실제 통합 | Tier 3 | 실 DB/API에서의 동작 보장 | 실제 행 수 확인 |

**수정 Task에 추가:**

| 케이스 유형 | Tier | 목적 |
|---|---|---|
| 기존 기능 회귀 | Tier 1 또는 2 | 수정 후에도 기존 동작이 유지됨을 보장 |

### 4.3 테스트명 규칙

`test_{대상}_{조건}_{기대결과}` 형식을 사용합니다.

```python
# 올바른 테스트명 예시
def test_calculate_return_with_valid_prices_returns_float(): ...
def test_calculate_return_with_empty_df_raises_value_error(): ...
def test_save_portfolio_stores_to_db_and_returns_id(): ...
```

### 4.4 구현 방향 유도 체크

각 테스트 케이스 작성 후 스스로 확인합니다:
- 이 테스트를 통과시키기 위해 자연스럽게 어떤 코드가 나오는가?
- 그 코드가 우리가 원하는 구현인가?
- 테스트를 편법으로 통과시키는 방법이 있다면 추가 케이스로 막을 수 있는가?

### 4.5 나쁜 테스트 케이스

- `test_it_works()` — 검증 대상 불명확
- 구현 내부 로직을 직접 테스트 — 인터페이스가 아닌 구현 종속
- 한 케이스에 여러 검증 — 실패 원인 파악 어려움
- `pass`만 있는 테스트 — 아무것도 검증하지 않는 무의미한 placeholder

---

## § 5. 복잡도 초과 시 Task 분할 제안

명세 작성 중 아래 신호가 발견되면 Task 분할을 사용자에게 제안합니다.

**분할 필요 신호:**
- 테스트 케이스가 15개를 초과
- 서로 다른 계층(DB 저장 + 알고리즘 + API)을 동시에 테스트해야 함
- 테스트 케이스 간 의존성이 복잡하게 얽힘

**분할 제안 형식:**

```
[복잡도 초과 감지]
Task-{id}의 테스트 케이스가 {N}개로 한 세션에 과도합니다.

[제안 분할]
- Task-{id}-A: {범위A} — 테스트 {N}개
- Task-{id}-B: {범위B} — 테스트 {N}개

p{n}_pjt_tasks.md 조정이 필요합니다. 진행할까요?
```

---

## § 6. 완료 기준 체크리스트

**위키 선조회 완료:**
- [ ] `references/wiki-query-protocol.md`를 읽고 절차를 따랐는가?
- [ ] 조회 완료 표가 Spec 상단에 포함되었는가?
- [ ] 위키 미기록 항목은 실제 소스 파일을 `view_file`로 직접 확인했는가?

**인터페이스 정확성:**
- [ ] 모든 임포트 경로가 위키 또는 실제 소스 파일 기준인가?
- [ ] `.env` 변수명이 `environment.md` 또는 `.env.example` 기준인가?
- [ ] DB 테이블명·컬럼명이 스키마 문서 또는 실제 SQL 파일 기준인가?
- [ ] 추정으로 작성한 인터페이스가 없는가?

**테스트 케이스 충분성:**
- [ ] 정상 동작 케이스가 주요 기능을 모두 커버하는가?
- [ ] 경계값/예외 케이스가 포함되었는가?
- [ ] 수정 Task인 경우 회귀 케이스가 있는가?
- [ ] Tier 3(실제 통합) 테스트가 `pass`로 남겨지지 않았는가?
- [ ] 테스트 케이스가 PRD 요구사항과 매핑되는가?

**테스트 케이스 유도력:**
- [ ] 각 테스트를 통과시키면 자연스럽게 올바른 구현이 나오는가?
- [ ] 테스트만 보고 인터페이스(함수명, 파라미터, 반환값)를 파악할 수 있는가?

**명세 명확성:**
- [ ] Task 목표가 한 문장으로 이해되는가?
- [ ] IN/OUT Scope가 명확한가?
- [ ] 구현 Agent가 별도 질문 없이 작업 시작 가능한가?
- [ ] 모든 파일 경로가 절대 경로인가?

**완료 후 전달 형식:**

```
[Task-{ID} Spec 완료]
✅ docs/p{n}/tasks/task-{id}_spec.md

[위키 선조회 결과]
- 확인 완료: {N}개 항목
- 소스 파일 직접 확인: {N}개 항목
- 신규 정의: {N}개 항목

[테스트 케이스 요약]
- Tier 1 단위: {N}개
- Tier 2 격리 통합: {N}개
- Tier 3 실제 통합: {N}개
- 총 {N}개 — 전체 통과 시 Task 완료
```
