# Spec 작성을 위한 위키 선조회 프로토콜

> **이 문서의 목적**: Spec 작성 전 반드시 수행해야 하는 위키 조회 절차와
> 정보 미확인 시의 강제 행동 지침을 정의한다.
> SKILL.md의 Step 2에서 이 문서를 읽고 따른다.

---

## 1. 조회 의무 원칙

> **핵심 규칙**: 인터페이스·변수명·임포트 경로·DB 스키마 등 **모든 기술적 사실**은
> 추정(hallucination)으로 작성하지 않는다.
> 위키에서 확인되지 않은 정보는 **실제 소스 파일을 직접 열어서** 확인한다.

이 원칙을 어기는 것은 Spec의 품질 기준을 위반하는 것이다.
추정으로 작성된 Spec은 구현 Agent가 잘못된 방향으로 구현하게 만들어 **전체 재작업**을 유발한다.

---

## 2. 필수 조회 순서 (모든 Spec 작성에 적용)

### Step A: MoC(지식 지도) 파악

```
읽어야 할 파일: pjt_wiki/00_schema/index.md
목적: 어느 서브 위키에 무엇이 기록되어 있는지 전체 지도 파악
```

### Step B: 환경 변수 확인 (`.env` 변수명 오류 방지)

```
읽어야 할 파일:
  - pjt_wiki/{서브프로젝트}_wiki/environment.md
  - pjt_wiki/parent_wiki/environment.md (공통 변수)

확인 항목:
  □ 이 Task에서 사용하는 .env 변수명 전체 목록
  □ Layer A (EnvDetector용) / Layer B (앱 내부용) 구분
  □ 각 변수의 기본값 및 타입
```

**⚠️ 위키에 변수가 기록되지 않은 경우**:
`pjt_wiki/{서브프로젝트}_wiki/environment.md` 파일로 확인 불가 시
→ **즉시 `tdms_core/{서브프로젝트}/.env.example` 파일을 `view_file`로 직접 열어 확인**한다.
추정으로 변수명을 작성하는 것은 절대 금지.

### Step C: 인터페이스 시그니처 확인

```
읽어야 할 파일:
  - pjt_wiki/{서브프로젝트}_wiki/interfaces/*.md (Task 관련 파일 전체)
  - pjt_wiki/p1_shared_wiki/interfaces/*.md (공통 모듈 사용 시)

확인 항목:
  □ 클래스/함수 이름 정확한 표기
  □ 파라미터명, 타입 힌트
  □ 반환 타입
  □ 임포트 경로 (from X.Y.Z import ClassName)
  □ 예외 발생 조건
```

**⚠️ 위키에 인터페이스가 미기록된 경우**:
위키 인터페이스 문서가 없거나 불완전할 때
→ **즉시 해당 소스 파일을 `view_file`로 직접 열어 클래스/함수 시그니처를 확인**한다.

소스 파일 위치 예시:
```
p1_shared 모듈:   tdms_core/p1_shared/p1_shared/{모듈경로}.py
p2_kdms 모듈:     tdms_core/p2_kdms/{모듈경로}.py
p3_usdms 모듈:    tdms_core/p3_usdms/{모듈경로}.py
```

소스 파일 접근도 불가할 경우 (파일이 아직 생성 안 된 신규 Task):
→ Spec 내 해당 항목에 다음 형식으로 명시한다:
```
# [신규 생성 — 이 인터페이스는 이 Task에서 처음 정의됨]
```

### Step D: DB 스키마 확인

```
읽어야 할 파일:
  - pjt_wiki/{서브프로젝트}_wiki/interfaces/schema_{db이름}.md

확인 항목:
  □ 관련 테이블명 (추정 금지)
  □ 컬럼명 및 타입
  □ PRIMARY KEY / UNIQUE CONSTRAINT
  □ ON CONFLICT 전략 (upsert 여부)
```

**⚠️ 스키마 문서가 없거나 최신 아닌 경우**:
→ **`view_file`로 실제 SQL 파일 (`init.sql`, `migrations/*.sql`)을 직접 열어 확인**한다.

```
SQL 파일 위치:
  tdms_core/p1_shared/p1_shared/db/{서브프로젝트}_origin/init.sql
  tdms_core/{서브프로젝트}/migrations/*.sql
```

### Step E: 기술 의사결정 확인

```
읽어야 할 파일:
  - pjt_wiki/{서브프로젝트}_wiki/decisions/*.md

목적:
  □ 이 Task와 관련된 아키텍처 결정 사항 파악
  □ 이미 결정된 방향에 반하는 Spec 작성 방지
```

---

## 3. 조회 결과 Spec 반영 규칙

### ✅ 확인된 정보

위키 또는 소스 파일에서 직접 확인한 정보는 출처를 주석으로 표기:

```python
# [출처: pjt_wiki/p1_shared_wiki/interfaces/db_connection_pool.md]
class DbConnectionPool:
    def __init__(self, dsn: str, min_conn: int = 5, max_conn: int = 20) -> None: ...
    def get_cursor(self, autocommit: bool = False): ...
    def close_all(self) -> None: ...
```

```python
# [출처: pjt_wiki/p2_kdms_wiki/environment.md — Layer B]
# .env 변수: DEV_KDMS_DB_PASSWORD, SERVER_KDMS_DB_PASSWORD
```

### ❌ 미확인 정보 처리 (추정 작성 절대 금지)

위키에도 없고 소스 파일도 아직 없는 경우(신규 정의):

```python
# [신규 정의 — 이 Task에서 최초 설계. 구현 Agent가 아래 시그니처로 생성할 것]
def new_function(param: str) -> int:
    ...
```

위키에 있어야 하는데 누락된 경우(기존 기능인데 문서화 안 됨):

```
[⚠️ 위키 미기록 — 구현 전 반드시 확인 필요]
파일: tdms_core/p2_kdms/repositories/ohlcv_repo.py
확인 방법: view_file로 OhlcvRepo 클래스 전체 시그니처 직접 확인
추정 작성 금지 — 위 파일을 열어 실제 메서드명/파라미터를 복사할 것
```

---

## 4. 서브프로젝트별 위키 조회 파일 우선순위

| 서브프로젝트 | 환경 문서 | 인터페이스 문서 | 스키마 문서 |
|---|---|---|---|
| p1_shared | `p1_shared_wiki/environment.md` | `p1_shared_wiki/interfaces/*.md` | — |
| p2_kdms | `p2_kdms_wiki/environment.md` | `p2_kdms_wiki/interfaces/*.md` | `p2_kdms_wiki/interfaces/schema_kdms_db.md` |
| p3_usdms | `p3_usdms_wiki/environment.md` | `p3_usdms_wiki/interfaces/*.md` | `p3_usdms_wiki/interfaces/schema_*.md` |
| p4_manager | `p4_manager_wiki/environment.md` | `p4_manager_wiki/interfaces/*.md` | — |

p1_shared 모듈을 사용하는 모든 Task는 **항상** `p1_shared_wiki/interfaces/`를 먼저 확인한다.

---

## 5. 조회 완료 선언 형식

Spec 작성 시작 전 다음 체크리스트를 채우고 Spec 상단에 첨부한다:

```
## [위키 선조회 완료 — {날짜}]

| 항목 | 확인 파일 | 상태 |
|---|---|---|
| .env 변수명 | `p2_kdms_wiki/environment.md` | ✅ 확인 |
| DbConnectionPool 시그니처 | `p1_shared_wiki/interfaces/db_connection_pool.md` | ✅ 확인 |
| OhlcvRepo 시그니처 | `p2_kdms_wiki/interfaces/ohlcv_repo.md` | ✅ 확인 |
| daily_ohlcv 스키마 | `p2_kdms_wiki/interfaces/schema_kdms_db.md` | ✅ 확인 |
| 수정주가 설계 결정 | `p2_kdms_wiki/decisions/dec-002_price_adjustment_dual_strategy.md` | ✅ 확인 |
| FactorRepo 시그니처 | 위키 미기록 | ⚠️ `tdms_core/p2_kdms/repositories/factor_repo.py` 직접 확인 완료 |
```

이 표를 채우지 않고 Spec 작성을 시작하는 것은 프로토콜 위반이다.
