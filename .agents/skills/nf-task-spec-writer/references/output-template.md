# 산출물 템플릿: task-{id}_spec.md

아래 형식을 그대로 사용하여 산출물을 작성합니다.
`{중괄호}` 항목을 실제 내용으로 채워 넣으세요.

**작성 전 필수**: `references/wiki-query-protocol.md`의 Step A~E를 완료하고
아래 선조회 완료 표를 채운 후 Spec 본문을 작성하세요.

---

```markdown
# Task-{ID}: {Task명}

> **Sub Project**: {서브프로젝트폴더명} (예: p2_kdms)
> **PRD 근거**: {이 Task가 커버하는 PRD 요구사항 ID}
> **작성일**: {날짜}
> **의존 Task**: {T-XXX 또는 없음}

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/{서브프로젝트}_wiki/environment.md` | ✅ 확인 |
| {핵심 클래스} 시그니처 | `pjt_wiki/{서브프로젝트}_wiki/interfaces/{파일}.md` | ✅ 확인 |
| DB 스키마 | `pjt_wiki/{서브프로젝트}_wiki/interfaces/schema_{db}.md` | ✅ 확인 |
| {미기록 항목} | 위키 미기록 → `{실제 소스 파일 경로}` 직접 확인 완료 | ⚠️ 직접 확인 |
| {신규 정의 항목} | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

{한 문장으로: 이 Task가 완료되면 무엇이 가능해지는가}

**구현 범위:**
- IN: {이 Task에서 구현하는 것}
- OUT: {이 Task에서 구현하지 않는 것 — 다음 Task 또는 다른 Task}

---

## § 2. 구현 대상

### 신규 생성 파일
- `{절대경로/파일명.py}` — {역할 한 줄}
- `{절대경로/test_파일명.py}` — 테스트

### 수정 대상 파일 (해당 시)
- `{절대경로/파일명.py}` — {현재 기능} → {추가/변경 내용}

---

## § 3. 핵심 인터페이스

구현 Agent가 코드를 작성하기 전에 인터페이스를 먼저 확정합니다.

> 아래 시그니처는 위키 선조회 또는 실제 소스 파일 직접 확인으로 검증된 정보입니다.
> 각 블록 상단에 `[출처]` 주석을 반드시 표기합니다.

```python
# [출처: pjt_wiki/{서브프로젝트}_wiki/interfaces/{파일}.md]
# 또는 [출처: {실제 소스 파일 경로} — 위키 미기록으로 직접 확인]
# 또는 [신규 정의 — 이 Task에서 최초 설계]

class {ClassName}:
    def {메서드명}({파라미터}: {타입}) -> {반환타입}:
        """
        {한 줄 설명}

        Args:
            {파라미터}: {설명}
        Returns:
            {반환값 설명}
        Raises:
            {예외}: {발생 조건}
        """
        ...
```

> **⚠️ 위키 미기록이고 소스 파일도 미존재(신규) 시**: `[신규 정의 — 구현 Agent가 아래 시그니처로 생성]`으로 표기
> **⚠️ 위키에 있어야 하는데 없는 기존 모듈**: 추정 작성 절대 금지. `view_file`로 직접 열어 복사.

---

## § 3a. 기존 기능 보존 (수정 Task에만 작성)

### 보존 인터페이스
- `{기존 함수 시그니처}` — 변경 불가, `{의존 모듈}`에서 사용 중

### 회귀 테스트 케이스
```python
# [Tier 2 — 격리 통합]
def test_{기존기능}_unchanged_after_modification():
    """기존 동작이 수정 후에도 유지됨을 검증"""
    ...
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.
>
> **Tier 안내**:
> - Tier 1 (단위): DB/외부 의존성 없음 — 항상 실행
> - Tier 2 (격리 통합): mocker로 DB/API 대체 — 항상 실행
> - Tier 3 (실제 통합): 실 DB 필요, `@pytest.mark.integration` — `pytest --run-integration`으로만 실행

### 4.1 정상 동작 케이스

```python
# [Tier 1 — 단위] 또는 [Tier 2 — 격리 통합]
def test_{대상}_{조건}_{기대결과}():
    """
    [목적] {이 테스트가 검증하는 것}
    [유도] {이 테스트를 통과하려면 무엇을 구현해야 하는가}
    """
    # Arrange
    {입력 데이터 준비}

    # Act
    result = {함수 호출}

    # Assert
    assert {기대 결과}
```

### 4.2 경계값 케이스

```python
# [Tier 1 — 단위]
def test_{대상}_with_empty_input_{기대결과}():
    """[목적] 빈 입력에 대한 처리"""
    ...

def test_{대상}_with_minimum_valid_input_{기대결과}():
    """[목적] 최소 유효 입력에서의 동작"""
    ...
```

### 4.3 예외/오류 처리 케이스

```python
# [Tier 1 — 단위]
def test_{대상}_with_none_input_raises_value_error():
    """[목적] None 입력 시 ValueError 발생"""
    import pytest
    with pytest.raises(ValueError, match="{에러 메시지 패턴}"):
        {함수 호출}(None)
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest

@pytest.mark.integration
def test_{대상}_with_real_db_{기대결과}(real_pool):
    """
    [목적] 실제 DB 연결 상태에서 {기능}이 올바르게 동작하는지 검증.
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    [유도] {이 테스트를 통과하려면 무엇을 구현해야 하는가}
    """
    # Arrange
    {실제 DB 데이터 준비 또는 전제 조건}

    # Act
    result = {함수 호출(real_pool 사용)}

    # Assert — 실제 DB 상태를 검증하는 구체적 assertion
    assert result {기대값}
    # 필요 시 실제 DB 직접 조회로 이중 검증
    with real_pool.get_cursor() as cur:
        cur.execute("{검증 쿼리}")
        row = cur.fetchone()
    assert row {기대값}
```

> **conftest.py에 반드시 포함할 설정**:
> ```python
> # tests/conftest.py
> def pytest_addoption(parser):
>     parser.addoption("--run-integration", action="store_true", default=False)
>
> def pytest_collection_modifyitems(config, items):
>     if not config.getoption("--run-integration"):
>         skip = pytest.mark.skip(reason="--run-integration 플래그 없이는 실행 안 됨")
>         for item in items:
>             if "integration" in item.keywords:
>                 item.add_marker(skip)
> ```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_{...}` | Tier 1 | 정상 | {검증 내용} |
| 2 | `test_{...}` | Tier 1 | 경계값 | {검증 내용} |
| 3 | `test_{...}` | Tier 1 | 예외 | {검증 내용} |
| 4 | `test_{...}` | Tier 2 | 격리 통합 | {검증 내용} |
| 5 | `test_{...}` | Tier 3 | 실제 통합 | {실 DB에서의 검증 내용} |
| N | `test_{...}` | Tier 2 | 회귀 | {기존 기능 유지} |

**총 {N}개 테스트 — 전체 통과 시 Task 완료**
*(Tier 3는 `pytest --run-integration` 실행 시에만 포함)*

---

## § 5. 구현 참고사항

구현 Agent가 테스트를 통과시키는 과정에서 참고할 기술 정보입니다.
이 섹션은 구현 방법을 지시하지 않으며, 참고용으로만 활용합니다.

- **기술 스택**: {언어, 주요 라이브러리 및 버전 — environment.md에서 확인}
- **위키 참조 링크**:
  - `pjt_wiki/{서브프로젝트}_wiki/interfaces/{파일}.md` — {참조할 내용}
  - `pjt_wiki/p1_shared_wiki/interfaces/{파일}.md` — {참조할 내용}
- **관련 문서**: `{경로}` — {참조할 섹션}
- **주의사항**: {알려진 기술적 제약이나 함정}
- **데이터 구조**: {핵심 데이터 형태 — 필요한 경우만}

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 테스트 전체 통과
- [ ] 기존 테스트(있는 경우) 전체 통과 — 회귀 없음
- [ ] `{서브프로젝트폴더}_pjt_tasks.md`의 Task-{ID} 상태를 `완료`로 업데이트
      (예: `docs/p2_kdms/p2_kdms_pjt_tasks.md`)
- [ ] `docs/{서브프로젝트폴더}/task-{id}_walkthrough.md` 작성
```
