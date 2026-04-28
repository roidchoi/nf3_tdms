# shared PRD — 공통 모듈

> **버전**: v1.0 | **작성일**: 2026-04-28
> **상위 PRD**: `docs/parent/tdms_PRD.md`
> **사용 주체**: `p1_kdms`, `p2_usdms`, `p3_manager`

---

## 1. 목적 및 범위

`shared/`는 p1·p2·p3 세 서브프로젝트가 **공통으로 사용하는 모듈**을 모아둔 패키지다.

### 설계 원칙
1. **서브프로젝트는 shared에 의존할 수 있으나, shared는 서브프로젝트에 의존하지 않는다.**
2. **인터페이스 우선**: shared 모듈의 public API(메서드 시그니처)를 먼저 정의하고 변경 시 버전 태깅.
3. **독립 테스트 가능**: shared 모듈은 p1·p2 없이 단독으로 단위 테스트 실행 가능해야 한다.
4. **하드코딩 금지**: 모든 설정값(URL, 포트, 경로 등)은 `.env` 또는 생성자 인수로 주입.

---

## 2. 모듈 구성

```
shared/
├── api/
│   ├── kis_api_core.py        # KIS API 코어 (토큰 캐시 공유)
│   ├── kiwoom_api_core.py     # Kiwoom API 코어 (KR 전용)
│   └── token_manager.py       # 토큰 캐시 파일 관리
│
├── db/
│   ├── connection.py          # 커넥션 풀 팩토리 + get_cursor()
│   └── exceptions.py          # DB 관련 공통 예외
│
├── ops/
│   ├── backup_manager.py      # DB 백업·복구·검증
│   └── logger.py              # 공통 로거 팩토리 (WebSocket 핸들러 포함)
│
└── utils/
    ├── date_utils.py          # 날짜·시장 캘린더 유틸리티
    └── retry.py               # 재시도 데코레이터
```

---

## 3. 모듈 상세 명세

### 3.1 KIS API 코어 (`api/kis_api_core.py`)

#### 배경

KDMS와 USDMS 양쪽에 `kis_rest.py`, `kis_api_core.py`가 각각 독립적으로 구현되어 있다.
동일 KIS 계정을 사용할 경우 **토큰이 중복 발급**되어 API 호출 한도가 낭비된다.
`shared/KisApiCore`로 통합하면 토큰 캐시를 공유하여 이를 방지한다.

#### 인터페이스

```python
class KisApiCore:
    """KIS REST API 클라이언트 기반 클래스."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        is_mock: bool = False,
        token_cache_path: str = "~/.cache/tdms/kis_token.json",
    ): ...

    def get_headers(self, tr_id: str, extra: dict = {}) -> dict:
        """유효한 토큰이 포함된 요청 헤더 반환. 만료 시 자동 갱신."""
        ...

    def request(
        self, method: str, path: str, params: dict = {}, body: dict = {}
    ) -> dict:
        """KIS API 요청 실행. 401 응답 시 토큰 자동 갱신 후 1회 재시도."""
        ...

    @property
    def base_url(self) -> str:
        """실전/모의 투자 URL 자동 선택."""
        ...
```

#### 토큰 캐시 공유 흐름

```
p1_kdms/collectors/kis_kr_client.py
    └── KisApiCore(token_cache_path="~/.cache/tdms/kis_token.json")
            └── TokenManager.get_valid_token()
                    ├── 캐시 파일 존재 + 유효 → 캐시 반환
                    └── 만료 또는 없음 → issue_new_token() → 캐시 저장

p2_usdms/collectors/kis_us_client.py
    └── KisApiCore(token_cache_path="~/.cache/tdms/kis_token.json")  ← 동일 캐시
            └── TokenManager.get_valid_token()
                    └── 캐시 유효 → 재발급 없이 캐시 반환  ← 토큰 공유
```

#### 서브클래스 패턴

```python
# p1_kdms/collectors/kis_kr_client.py
class KisKrClient(KisApiCore):
    """KIS 한국 시장 전용 엔드포인트."""

    def get_daily_ohlcv(self, stk_cd: str, end_date: str) -> list[dict]:
        """일봉 조회. start_date 무시 특이동작 → end_date 역방향 페이지네이션."""
        ...

    def get_financial_data(self, stk_cd: str) -> dict:
        ...

# p2_usdms/collectors/kis_us_client.py
class KisUsClient(KisApiCore):
    """KIS 미국 시장 전용 엔드포인트."""

    def get_us_daily_ohlcv(self, ticker: str, end_date: str) -> list[dict]:
        ...
```

---

### 3.2 Kiwoom API 코어 (`api/kiwoom_api_core.py`)

#### 인터페이스

```python
class KiwoomApiCore:
    """Kiwoom REST API 클라이언트 (한국 시장 전용)."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        token_cache_path: str = "~/.cache/tdms/kiwoom_token.json",
    ): ...

    def get_headers(self) -> dict:
        """유효한 토큰이 포함된 헤더 반환. 자동 갱신."""
        ...

    def request(self, method: str, path: str, params: dict = {}) -> dict:
        ...
```

- 원본: `kdms_origin/collectors/kiwoom_rest.py` (400+ lines) 기반
- 토큰 캐시를 `TokenManager`로 분리하여 인스턴스 공유 문제 해결

---

### 3.3 토큰 매니저 (`api/token_manager.py`)

```python
class TokenManager:
    """파일 기반 API 토큰 캐시 관리자."""

    def __init__(self, cache_path: str, token_type: str): ...

    def get_valid_token(self) -> str | None:
        """유효한 토큰 반환. 없거나 만료 시 None."""
        ...

    def save_token(self, token: str, expires_at: datetime): ...

    def is_valid(self) -> bool:
        """토큰 유효성 확인 (만료 5분 전을 만료로 처리)."""
        ...
```

---

### 3.4 DB 커넥션 (`db/connection.py`)

#### 배경

p1·p2 원본 모두 `psycopg2.pool.ThreadedConnectionPool`을 사용하나 패턴이 다르다.
`get_cursor()` context manager 패턴(p2 방식)을 표준으로 채택하여 통일한다.

#### 인터페이스

```python
from contextlib import contextmanager

class DbConnectionPool:
    """ThreadedConnectionPool 래퍼."""

    def __init__(self, dsn: str, min_conn: int = 5, max_conn: int = 20): ...

    @contextmanager
    def get_cursor(self, autocommit: bool = False):
        """
        커넥션 풀에서 커넥션 획득 → 커서 yield → 자동 반환.
        예외 발생 시 rollback 후 커넥션 반환.

        Usage:
            with pool.get_cursor() as cur:
                cur.execute("SELECT ...")
        """
        conn = self._pool.getconn()
        try:
            if autocommit:
                conn.autocommit = True
            with conn.cursor() as cur:
                yield cur
            if not autocommit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def close_all(self): ...
```

#### 사용 패턴 (p1, p2 공통)

```python
# p1_kdms/repositories/ohlcv_repo.py
from shared.db.connection import DbConnectionPool

class OhlcvRepo:
    def __init__(self, pool: DbConnectionPool):
        self._pool = pool

    def upsert_daily(self, records: list[dict]) -> int:
        with self._pool.get_cursor() as cur:
            cur.executemany(
                "INSERT INTO daily_ohlcv ... ON CONFLICT DO UPDATE ...",
                records
            )
            return cur.rowcount
```

---

### 3.5 백업 매니저 (`ops/backup_manager.py`)

#### 배경

도커 이미지 업데이트 시 DB 볼륨 유실 사례가 있었다. 백업·복구 절차를 표준화하여 어느 시스템에서도 동일하게 실행 가능하도록 한다.

#### 인터페이스

```python
class BackupManager:
    """TimescaleDB pg_dump 기반 백업·복구·검증 관리자."""

    def __init__(
        self,
        container_name: str,      # Docker 컨테이너명 (예: "p1_kdms_db")
        db_name: str,              # DB명 (예: "kdms_db")
        db_user: str,
        backup_dir: str,           # 백업 파일 저장 디렉토리
    ): ...

    def backup(self, tag: str = "manual") -> Path:
        """
        pg_dump 실행 후 .dump 파일 저장.
        파일명: {backup_dir}/{tag}/checkpoint_{YYYYMMDD_HHMMSS}.dump
        완료 후 verify() 자동 호출.
        """
        ...

    def verify(self, dump_path: Path) -> bool:
        """pg_restore --list 로 dump 파일 헤더 파싱. 예상 테이블 존재 여부 확인."""
        ...

    def restore(self, dump_path: Path, pre_backup: bool = True) -> bool:
        """
        pg_restore 실행.
        pre_backup=True 시 복구 전 자동 백업 실행 (안전 장치).
        """
        ...

    def list_backups(self, tag: str | None = None) -> list[BackupInfo]:
        """저장된 백업 파일 목록 반환 (생성일시, 태그, 크기, 검증 상태)."""
        ...

    def cleanup_old(self, retain_daily: int = 30, retain_weekly: int = 12):
        """보관 정책에 따라 오래된 백업 파일 삭제."""
        ...
```

#### 백업 파일 구조

```
backups/
├── kdms/
│   ├── daily/
│   │   └── checkpoint_20260428_030000.dump
│   ├── weekly/
│   │   └── checkpoint_20260421_030000.dump
│   └── pre_update/
│       └── checkpoint_20260428_150000.dump   ← 업데이트 직전 수동 백업
└── usdms/
    └── (동일 구조)
```

#### CLI 사용법

```bash
# 백업 실행
python -m shared.ops.backup_manager backup --target kdms --tag daily

# 검증
python -m shared.ops.backup_manager verify \
  --file backups/kdms/daily/checkpoint_20260428_030000.dump

# 복구
python -m shared.ops.backup_manager restore \
  --target kdms \
  --file backups/kdms/pre_update/checkpoint_20260428_150000.dump

# 이력 조회
python -m shared.ops.backup_manager list --target kdms
```

---

### 3.6 공통 로거 (`ops/logger.py`)

#### 배경

KDMS 원본에 `log_utils.py` (WebSocket 큐 핸들러)가 있다. p1·p2·p3 모두 동일한 로깅 설정을 공유해야 p3_manager에서 통합 로그를 수집할 수 있다.

#### 인터페이스

```python
def get_logger(name: str, ws_queue: asyncio.Queue | None = None) -> logging.Logger:
    """
    공통 로거 팩토리.
    - Rich 콘솔 핸들러 (컬러 출력)
    - 파일 핸들러 (logs/{name}_{date}.log, rotate daily)
    - WebSocket 큐 핸들러 (ws_queue 제공 시, p3_manager 실시간 스트리밍용)
    """
    ...

class WebSocketQueueHandler(logging.Handler):
    """asyncio.Queue에 로그 레코드를 넣는 핸들러."""

    def __init__(self, queue: asyncio.Queue): ...
    def emit(self, record: logging.LogRecord): ...
```

---

### 3.7 날짜·시장 유틸리티 (`utils/date_utils.py`)

```python
def is_kr_trading_day(date: date) -> bool:
    """한국 주식시장 영업일 여부 (공휴일 포함 확인)."""
    ...

def is_us_trading_day(date: date) -> bool:
    """미국 주식시장 영업일 여부."""
    ...

def get_kr_trading_days(start: date, end: date) -> list[date]:
    """기간 내 한국 영업일 목록."""
    ...

def get_us_trading_days(start: date, end: date) -> list[date]:
    """기간 내 미국 영업일 목록."""
    ...

def last_kr_trading_day(reference: date | None = None) -> date:
    """기준일 이전 마지막 한국 영업일."""
    ...

def last_us_trading_day(reference: date | None = None) -> date:
    """기준일 이전 마지막 미국 영업일."""
    ...
```

---

### 3.8 재시도 데코레이터 (`utils/retry.py`)

```python
def retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    지수 백오프 재시도 데코레이터.

    Usage:
        @retry(max_attempts=3, delay_seconds=1.0, exceptions=(requests.Timeout,))
        def fetch_data():
            ...
    """
    ...

def async_retry(...):
    """비동기 함수용 재시도 데코레이터."""
    ...
```

---

## 4. 설치 및 사용 방법

### 4.1 프로젝트 내 패키지로 참조

`shared/`는 별도 PyPI 패키지로 배포하지 않고, 각 서브프로젝트에서 **상대 경로 또는 editable install**로 참조한다.

```
nf3_tdms/
├── shared/
│   ├── __init__.py
│   └── pyproject.toml        # 패키지 정의
│
├── p1_kdms/
│   └── requirements.txt      # "-e ../shared" 항목 포함
└── p2_usdms/
    └── requirements.txt      # "-e ../shared" 항목 포함
```

```toml
# shared/pyproject.toml
[project]
name = "tdms-shared"
version = "1.0.0"
dependencies = [
    "psycopg2-binary>=2.9",
    "requests>=2.32",
    "python-dotenv>=1.1",
]
```

```bash
# 각 서브프로젝트 환경에서 shared 설치
pip install -e ../shared
```

### 4.2 Docker 멀티스테이지 빌드에서 공유

```dockerfile
# p1_kdms/backend.Dockerfile
FROM python:3.12-slim AS base

# shared 모듈 복사 후 설치
COPY ../shared /app/shared
RUN pip install -e /app/shared

# p1 의존성 설치
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . /app/p1_kdms
WORKDIR /app/p1_kdms
```

---

## 5. 버전 관리 정책

shared 모듈은 p1·p2가 모두 의존하므로 **하위 호환성** 유지가 필수다.

| 변경 유형 | 버전 업 | 절차 |
|---|---|---|
| 버그 수정 | Patch (1.0.x) | 테스트 통과 후 즉시 배포 |
| 기능 추가 (하위 호환) | Minor (1.x.0) | 기존 인터페이스 유지, 새 메서드 추가 |
| 인터페이스 변경 (breaking) | Major (x.0.0) | p1·p2 동시 업데이트 계획 수립 후 적용 |

---

## 6. 테스트 전략

```
shared/tests/
├── test_token_manager.py      # 토큰 캐시 유효성 확인, 갱신 트리거
├── test_db_connection.py      # get_cursor() 정상 동작, 예외 시 rollback
├── test_backup_manager.py     # dump 파일 생성, 헤더 검증, 보관 정책
├── test_date_utils.py         # 한국/미국 영업일 계산 정확성
└── test_retry.py              # 재시도 횟수, 백오프 간격
```

```bash
# shared 단독 테스트 실행
cd shared
pytest tests/ -v
```

---

## 7. 구현 단계 (Phase)

### Phase 1 — 핵심 인프라 (p1·p2 구현 착수 전 필수)
- [ ] `db/connection.py`: `get_cursor()` context manager
- [ ] `ops/logger.py`: 공통 로거 팩토리 + WebSocket 핸들러
- [ ] `utils/retry.py`: 재시도 데코레이터 (동기/비동기)
- [ ] `pyproject.toml` 패키지 설정 + editable install 검증

### Phase 2 — API 클라이언트 통합
- [ ] `api/token_manager.py`: 파일 기반 토큰 캐시
- [ ] `api/kis_api_core.py`: KIS 토큰 공유 코어
- [ ] `api/kiwoom_api_core.py`: Kiwoom 코어
- [ ] p1·p2에서 기존 `kis_rest.py`, `kiwoom_rest.py` 교체 테스트

### Phase 3 — 운영 도구
- [ ] `ops/backup_manager.py`: 백업·복구·검증·보관 정책
- [ ] `utils/date_utils.py`: 한국/미국 영업일 유틸리티
- [ ] CLI 진입점 (`python -m shared.ops.backup_manager`)
- [ ] p3_manager 백업 서비스 연동 테스트

---

## 8. 알려진 이슈 및 주의사항

| 이슈 | 내용 | 대응 |
|---|---|---|
| KIS 계정 공유 여부 | p1·p2가 동일 계정이어야 토큰 캐시 공유 효과 있음 | 운영자 확인 필요 (tdms_PRD Q1) |
| Docker 내 캐시 경로 | 컨테이너마다 `~/.cache/` 경로가 다름 → 토큰 공유 불가 | 캐시 경로를 볼륨으로 마운트하거나 Redis 등 공유 저장소 사용 고려 |
| psycopg2 스레드 안전성 | `ThreadedConnectionPool`은 스레드 안전하나, 커넥션 자체는 스레드 공유 금지 | `get_cursor()` 사용 시 커넥션을 스레드 경계 밖으로 전달 금지 |
| shared 인터페이스 변경 | p1·p2 동시에 영향 → 한쪽만 업데이트 시 버전 불일치 | Major 변경 시 p1·p2 동시 배포 계획 필수 |

---

*p1_kdms 상세: `docs/p1_kdms/p1_kdms_PRD.md`*
*p2_usdms 상세: `docs/p2_usdms/p2_usdms_PRD.md`*
*p3_manager 상세: `docs/p3_manager/p3_manager_PRD.md`*
