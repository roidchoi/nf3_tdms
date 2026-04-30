# p1_shared PRD — 공통 모듈

> **버전**: v1.1 | **작성일**: 2026-04-29 (보완지침 반영)
> **상위 PRD**: `docs/parent/tdms_PRD.md`
> **사용 주체**: `p2_kdms`, `p3_usdms`, `p4_manager`

---

## 1. 목적 및 범위

`p1_shared/`는 p2·p3·p4 네 서브프로젝트가 **공통으로 사용하는 모듈**을 모아둔 패키지다.

### 설계 원칙
1. **서브프로젝트는 p1_shared에 의존할 수 있으나, p1_shared는 서브프로젝트에 의존하지 않는다.**
2. **인터페이스 우선**: p1_shared 모듈의 public API(메서드 시그니처)를 먼저 정의하고 변경 시 버전 태깅.
3. **독립 테스트 가능**: p1_shared 모듈은 p2·p3 없이 단독으로 단위 테스트 실행 가능해야 한다.
4. **하드코딩 금지**: 모든 설정값(URL, 포트, 경로 등)은 `.env` 또는 생성자 인수로 주입.
5. **DB 관련 구현 시 context7 MCP 필수**: `psycopg2`, `TimescaleDB`, `pg_dump/pg_restore` 등 DB 관련 기능 구현 전 반드시 context7 MCP로 최신 공식 문서를 조회하고 정확한 사용법을 확인한 후 구현한다.

---

## 2. 모듈 구성

```
p1_shared/
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
│   ├── backup_manager.py      # DB 백업·복구·검증 (강건 복원 전략 포함)
│   ├── sync_manager.py        # 🆕 개발PC ↔ 서버PC 양방향 DB 동기화
│   ├── startup_validator.py   # 🆕 Docker 재기동 시 DB 기동 검증 + 조치 안내
│   └── logger.py              # 공통 로거 팩토리 (WebSocket 핸들러 포함)
│
└── utils/
    ├── env_detector.py        # 🆕 PC 환경 자동 감지 (hostname/IP 기반)
    ├── date_utils.py          # 날짜·시장 캘린더 유틸리티
    └── retry.py               # 재시도 데코레이터
```

---

## 3. 모듈 상세 명세

### 3.1 KIS API 코어 (`api/kis_api_core.py`)

#### 배경

KDMS와 USDMS 양쪽에 `kis_rest.py`, `kis_api_core.py`가 각각 독립적으로 구현되어 있다.
동일 KIS 계정을 사용할 경우 **토큰이 중복 발급**되어 API 호출 한도가 낭비된다.
`p1_shared/KisApiCore`로 통합하면 토큰 캐시를 공유하여 이를 방지한다.

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
p2_kdms/collectors/kis_kr_client.py
    └── KisApiCore(token_cache_path="~/.cache/tdms/kis_token.json")
            └── TokenManager.get_valid_token()
                    ├── 캐시 파일 존재 + 유효 → 캐시 반환
                    └── 만료 또는 없음 → issue_new_token() → 캐시 저장

p3_usdms/collectors/kis_us_client.py
    └── KisApiCore(token_cache_path="~/.cache/tdms/kis_token.json")  ← 동일 캐시
            └── TokenManager.get_valid_token()
                    └── 캐시 유효 → 재발급 없이 캐시 반환  ← 토큰 공유
```

#### 서브클래스 패턴

```python
# p2_kdms/collectors/kis_kr_client.py
class KisKrClient(KisApiCore):
    """KIS 한국 시장 전용 엔드포인트."""

    def get_daily_ohlcv(self, stk_cd: str, end_date: str) -> list[dict]:
        """일봉 조회. start_date 무시 특이동작 → end_date 역방향 페이지네이션."""
        ...

    def get_financial_data(self, stk_cd: str) -> dict:
        ...

# p3_usdms/collectors/kis_us_client.py
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

p2·p3 원본 모두 `psycopg2.pool.ThreadedConnectionPool`을 사용하나 패턴이 다르다.
`get_cursor()` context manager 패턴(p3 방식)을 표준으로 채택하여 통일한다.

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

#### 사용 패턴 (p2, p3 공통)

```python
# p2_kdms/repositories/ohlcv_repo.py
from p1_shared.db.connection import DbConnectionPool

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

#### 필수 원칙: 강건 복원 전략

> 과거 경험상 인덱스 생성/테이블 생성 순서 오류로 복원이 실패한 사례가 많았다. 아래 원칙을 반드시 준수한다.

| 원칙 | 내용 |
|---|---|
| **표준 백업 포맷** | `pg_dump -Fc` (스키마+데이터 통합 custom 포맷) 표준 사용 |
| **복원 순서 보장** | `pg_restore --section=pre-data` (테이블) → `--section=data` (데이터) → `--section=post-data` (인덱스/FK) 단계별 적용 |
| **점진적 스키마 반영** | 복원 전 저장된 `init.sql` 기준으로 DB에 누락 컬럼/테이블 차분 적용 |
| **충돌 안전 삽입** | 데이터 복원 시 `--clean --if-exists` 옵션 또는 `ON CONFLICT DO NOTHING` 활용 |
| **복원 전 자동 백업** | `restore()` 호출 시 `pre_backup=True`(기본값)이면 실행 전 현 상태 스냅샷 필수 |

#### Docker 볼륨 실물 파일 경로 명세

> **DB 연결 오류 등 최악의 상황에서도 실물 파일 위치를 통해 데이터 생존 여부를 직접 확인할 수 있다.**

```
# WSL2 환경에서 Docker Desktop의 named volume 실제 저장 경로
# (Docker Desktop for Windows + WSL2 통합 백엔드 기준)

Windows 호스트 접근:
  \\wsl.localhost\docker-desktop-data\data\docker\volumes\
    ├─ kdms_pgdata\_data\
    └─ usdms_pgdata\_data\

WSL2 내부 접근:
  /var/lib/docker/volumes/
    ├─ kdms_pgdata/_data/    ← TimescaleDB의 실제 PostgreSQL 데이터 디렉토리
    └─ usdms_pgdata/_data/

실물 파일 존재 확인 명령:
  # WSL 터미널에서
  ls -la /var/lib/docker/volumes/kdms_pgdata/_data/
  cat /var/lib/docker/volumes/kdms_pgdata/_data/PG_VERSION   # 존재 = 정상 볼륨
```

#### 인터페이스

```python
class BackupManager:
    """TimescaleDB pg_dump 기반 백업·복구·검증 관리자."""

    def __init__(
        self,
        container_name: str,      # Docker 컨테이너명 (예: "p2_kdms_db")
        db_name: str,              # DB명 (예: "kdms_db")
        db_user: str,
        backup_dir: str,           # 백업 파일 저장 디렉토리
        volume_name: str,          # Docker 볼륨명 (예: "kdms_pgdata") ← 경로 확인용
    ): ...

    def backup(self, tag: str = "manual") -> Path:
        """
        pg_dump -Fc 실행 후 .dump 파일 저장.
        파일명: {backup_dir}/{tag}/checkpoint_{YYYYMMDD_HHMMSS}.dump
        완료 후 verify() 자동 호출.
        """
        ...

    def verify(self, dump_path: Path) -> bool:
        """
        pg_restore --list 로 dump 파일 헤더 파싱.
        확인 항목:
          1. 예상 테이블 존재 여부
          2. Hypertable 설정 존재 여부
          3. dump 파일 크기 > 0 byte
        """
        ...

    def restore(
        self,
        dump_path: Path,
        pre_backup: bool = True,
        section_order: bool = True,  # pre-data → data → post-data 단계 적용
    ) -> bool:
        """
        강건 복원 실행.
        1. pre_backup=True 시 복원 전 현 상태 스냅샷 생성
        2. section_order=True 시 pre-data → data → post-data 순서대로 적용
           (인덱스/FK 생성 순서 방지 난수 해결)
        """
        ...

    def check_volume_exists(self) -> dict:
        """
        Docker 볼륨 실물 파일 존재 여부 확인.
        Returns: {"volume_path": str, "exists": bool, "pg_version": str|None, "size_bytes": int}
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
python -m p1_shared.ops.backup_manager backup --target kdms --tag daily

# 검증
python -m p1_shared.ops.backup_manager verify \
  --file backups/kdms/daily/checkpoint_20260428_030000.dump

# 복구 (순서 보장 + 사전 백업)
python -m p1_shared.ops.backup_manager restore \
  --target kdms \
  --file backups/kdms/pre_update/checkpoint_20260428_150000.dump

# 볼륨 실물 파일 확인
python -m p1_shared.ops.backup_manager check-volume --target kdms

# 이력 조회
python -m p1_shared.ops.backup_manager list --target kdms
```

---

### 3.6 공통 로거 (`ops/logger.py`)

#### 배경

KDMS 원본에 `log_utils.py` (WebSocket 큐 핸들러)가 있다. p2·p3·p4 모두 동일한 로깅 설정을 공유해야 p4_manager에서 통합 로그를 수집할 수 있다.

#### 인터페이스

```python
def get_logger(name: str, ws_queue: asyncio.Queue | None = None) -> logging.Logger:
    """
    공통 로거 팩토리.
    - Rich 콘솔 핸들러 (컬러 출력)
    - 파일 핸들러 (logs/{name}_{date}.log, rotate daily)
    - WebSocket 큐 핸들러 (ws_queue 제공 시, p4_manager 실시간 스트리밍용)
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

### 3.9 환경 감지 모듈 (`utils/env_detector.py`)

#### 배경

개발PC(WSL2)와 서버PC(WSL2+Docker)가 동일한 코드베이스를 사용하므로, 실행 환경을 자동으로 감지하여 적절한 `.env` 프로파일을 적용해야 한다. 수동 설정 오류를 방지하고 환경별 자동 분기를 지원한다.

#### 인터페이스

```python
class EnvDetector:
    """hostname/IP 기반 실행 환경 자동 감지 및 .env 프로파일 로더."""

    KNOWN_HOSTS = {
        # .env 에 등록된 PC 식별 정보
        # 예: {"dev-pc": {"hostname": "ROID-DEV", "ip_prefix": "192.168.1."}, ...}
    }

    def detect(self) -> Literal["dev", "server", "unknown"]:
        """
        현재 실행 PC를 감지한다.
        감지 순서:
          1. 환경변수 TDMS_ENV 명시적 지정 (최우선)
          2. hostname 매칭 (.env의 DEV_HOSTNAME, SERVER_HOSTNAME)
          3. IP 주소 대역 매칭 (.env의 DEV_IP_PREFIX, SERVER_IP_PREFIX)
          4. 감지 실패 시 "unknown" 반환 후 경고 로그
        """
        ...

    def load_env_profile(self) -> dict:
        """
        감지된 환경에 맞는 설정 반환.
        - DB 접속 정보 (host, port, db_name, user, password)
        - API 키 세트
        - 백업/동기화 경로
        """
        ...

    def get_peer_host(self) -> str:
        """
        동기화 상대방 PC의 IP 반환.
        dev 환경이면 server IP, server 환경이면 dev IP.
        """
        ...
```

#### `.env` 환경 설정 예시

```bash
# 환경 감지 설정
TDMS_ENV=                          # 명시 지정 시 자동 감지 무시 (dev / server)
DEV_HOSTNAME=ROID-DEV              # 개발PC hostname
SERVER_HOSTNAME=ROID-SERVER        # 서버PC hostname
DEV_IP=192.168.1.10                # 개발PC IP
SERVER_IP=192.168.1.20             # 서버PC IP

# 환경별 DB 접속 (dev 기준)
DEV_KDMS_DB_HOST=localhost
DEV_KDMS_DB_PORT=5432
SERVER_KDMS_DB_HOST=192.168.1.20   # 동기화 시 서버PC 접근용
SERVER_KDMS_DB_PORT=5432
```

---

### 3.10 DB 동기화 매니저 (`ops/sync_manager.py`)

#### 배경

개발PC와 서버PC(로컬 네트워크 SSH 접근 가능)가 각각 독립 DB를 운영하므로, 기능 추가나 초기 인계 시 양방향 동기화 기능이 필요하다.

#### 동기화 모드

| 모드 | 용도 | 내부 구현 |
|---|---|---|
| `full` | 초기 인계, 스키마 대규모 변경 후 재정렬 | `pg_dump -Fc` → SSH 전송(rsync) → `pg_restore --clean` |
| `diff` | 주기적 일상 동기화 (Hypertable 시계열 특성 활용) | `pg_dump --table=T --where="dt > since"` → SSH → `pg_restore --data-only` |
| `table` | 특정 테이블 핀포인트 갱신 | `pg_dump -t <table>` → SSH → UPSERT |

#### ⚠️ Full 동기화 안전 검증 (FullSyncSafetyChecker)

> **Full 동기화는 대상 DB의 기존 데이터를 전체 교체하는 매우 위험한 작업이다.**
> 방향 설정 실수 시 운영 DB 데이터가 영구 유실될 수 있으므로, 반드시 아래 안전 검증을 통과해야 실행된다.

```python
class FullSyncSafetyChecker:
    """Full 동기화 실행 전 소스/대상 DB 비교 안전 검증기."""

    ANOMALY_CONDITIONS = [
        "대상 DB 크기 >= 소스 DB 크기 × 0.8  →  대상이 더 크면 방향 오류 의심",
        "대상 DB 데이터 최신일 > 소스 DB 데이터 최신일  →  대상이 더 최신",
        "소스 DB 크기 == 0 또는 접속 불가  →  소스 유효성 오류",
        "소스·대상 DB명 불일치  →  타깃 DB 오지정 의심",
    ]

    def compare(
        self,
        source_dsn: str,
        target_dsn: str,
        db_name: str,
        key_tables: list[str],   # 커버리지 비교할 핵심 테이블 목록
    ) -> SyncSafetyReport:
        """
        1. pg_database_size() 로 소스·대상 DB 크기 비교
        2. 핵심 테이블의 MIN(dt)/MAX(dt) 비교 → 데이터 커버리지 기간 비교
        3. 이상 조건 해당 시 SyncSafetyReport.is_safe = False + 경고 메시지 생성
        """
        ...

    def confirm_with_user(self, report: SyncSafetyReport) -> bool:
        """
        비정상 상황 감지 시:
          1. 소스/대상 DB 크기, 최신일, 커버리지 기간을 표로 출력
          2. 경고 메시지 출력
          3. "CONFIRM-FULL-SYNC" 문자열 직접 입력 요구
          4. 30초 타임아웃 내 미입력 시 자동 취소
        Returns: True(사용자 확인 완료) / False(취소 또는 타임아웃)
        """
        ...
```

#### 인터페이스

```python
class SyncManager:
    """개발PC ↔ 서버PC 양방향 DB 동기화 관리자."""

    def __init__(
        self,
        env_detector: EnvDetector,
        backup_manager: BackupManager,
        ssh_user: str,             # SSH 접속 계정
        ssh_key_path: str,         # SSH 키 경로 (.env 로 주입)
    ): ...

    def sync(
        self,
        source: Literal["dev", "server"],
        target: Literal["dev", "server"],
        target_db: Literal["kdms", "usdms"],
        mode: Literal["full", "diff", "table"],
        tables: list[str] | None = None,  # mode="table" 시 지정
        since: date | None = None,        # mode="diff" 시 기준일
        dry_run: bool = False,            # True 시 실제 전송 없이 계획만 출력
    ) -> SyncResult: ...
```

#### Full 동기화 실행 흐름

```
[사용자 호출] sync(source="dev", target="server", mode="full")
    │
    ▼
[1] FullSyncSafetyChecker.compare()
    ├── 소스 DB 크기: 12.3 GB
    ├── 대상 DB 크기:  0.1 GB  ← 정상 (소스가 훨씬 큼)
    └── 커버리지: 소스 2020-01~현재 / 대상 없음 → 안전
    │
    ▼ (이상 감지 시)
[2] 경고 출력 + 재확인 요구
    ⚠ WARNING: 대상 DB가 소스보다 큽니다. 방향을 재확인하세요.
    소스(dev) kdms_db 크기: 0.5 GB | 최신일: 2026-01-10
    대상(server) kdms_db 크기: 12.3 GB | 최신일: 2026-04-29
    계속하려면 "CONFIRM-FULL-SYNC" 를 입력하세요 (30초 타임아웃):
    │
    ▼ (안전 확인 완료 또는 사용자 재확인 통과)
[3] 대상 PC 사전 백업 (BackupManager.backup(tag="pre_sync"))
    │
    ▼
[4] 소스 pg_dump -Fc → rsync → 대상 pg_restore (section_order=True)
    │
    ▼
[5] StartupValidator.validate() 로 복원 결과 검증
```

#### CLI 사용법

```bash
# 개발PC → 서버PC full 동기화 (kdms)
python -m p1_shared.ops.sync_manager sync \
  --source dev --target server --db kdms --mode full

# 서버PC → 개발PC diff 동기화 (usdms, 2026-04-01 이후)
python -m p1_shared.ops.sync_manager sync \
  --source server --target dev --db usdms --mode diff --since 2026-04-01

# 특정 테이블만 동기화
python -m p1_shared.ops.sync_manager sync \
  --source server --target dev --db usdms \
  --mode table --tables us_ticker_master us_daily_price

# 계획만 확인 (dry-run)
python -m p1_shared.ops.sync_manager sync \
  --source dev --target server --db kdms --mode full --dry-run
```

---

### 3.11 DB 기동 검증기 (`ops/startup_validator.py`)

#### 배경

Docker 이미지 재생성 또는 Docker Desktop 재실행 시, DB 볼륨이 정상 연결되었는지·기존 데이터가 정상 로드되었는지 자동으로 검증하고, 문제 발생 시 구체적인 조치 방법을 안내한다.

#### 인터페이스

```python
class StartupValidator:
    """Docker 재기동 시 DB 연결·데이터 정합성 자가 검증기."""

    def validate(
        self,
        db_name: Literal["kdms", "usdms"],
        expected_tables: list[str],       # 존재해야 할 핵심 테이블 목록
        min_row_counts: dict[str, int],   # 테이블별 최소 예상 행 수
    ) -> ValidationReport:
        """
        검증 항목:
          1. DB 접속 가능 여부 (psycopg2 연결 테스트)
          2. 핵심 테이블 존재 여부
          3. 각 테이블 행 수 >= 최소 예상치
          4. Docker 볼륨 실물 파일 존재 여부 (BackupManager.check_volume_exists())
          5. Hypertable 청크 상태 (timescaledb_information.chunks)
        """
        ...

    def print_report(self, report: ValidationReport):
        """
        검증 결과를 사람이 읽기 쉬운 형태로 출력.
        실패 항목에는 구체적인 조치 방법 안내 포함.

        출력 예시:
          ✅ DB 접속: 정상
          ✅ 테이블 존재: daily_ohlcv, minute_ohlcv, ... (9/9)
          ❌ 행 수 부족: daily_ohlcv 현재 0행 (예상: 1,000,000행 이상)
             → 조치: Docker 볼륨 경로 확인 후 pg_restore 실행
             → 볼륨 경로: /var/lib/docker/volumes/kdms_pgdata/_data/
             → 복구 명령: python -m p1_shared.ops.backup_manager restore --target kdms
        """
        ...
```

#### FastAPI lifespan 연동 패턴

```python
# p2_kdms/main.py
from contextlib import asynccontextmanager
from p1_shared.ops.startup_validator import StartupValidator

@asynccontextmanager
async def lifespan(app: FastAPI):
    validator = StartupValidator(pool=db_pool)
    report = validator.validate(
        db_name="kdms",
        expected_tables=["daily_ohlcv", "stock_info", "price_adjustment_factors"],
        min_row_counts={"daily_ohlcv": 1_000_000, "stock_info": 2_000},
    )
    validator.print_report(report)
    if not report.is_healthy:
        logger.critical("DB 기동 검증 실패 — 위 조치 안내를 확인하세요.")
    yield
```

---

## 4. 설치 및 사용 방법

### 4.1 프로젝트 내 패키지로 참조

`p1_shared/`는 별도 PyPI 패키지로 배포하지 않고, 각 서브프로젝트에서 **상대 경로 또는 editable install**로 참조한다.

```
nf3_tdms/
├── p1_shared/
│   ├── __init__.py
│   └── pyproject.toml        # 패키지 정의
│
├── p2_kdms/
│   └── requirements.txt      # "-e ../p1_shared" 항목 포함
└── p3_usdms/
    └── requirements.txt      # "-e ../p1_shared" 항목 포함
```

```toml
# p1_shared/pyproject.toml
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
pip install -e ../p1_shared
```

### 4.2 Docker 멀티스테이지 빌드에서 공유

```dockerfile
# p2_kdms/backend.Dockerfile
FROM python:3.12-slim AS base

# shared 모듈 복사 후 설치
COPY ../p1_shared /app/p1_shared
RUN pip install -e /app/p1_shared

# p2 의존성 설치
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . /app/p2_kdms
WORKDIR /app/p2_kdms
```

---

## 5. 버전 관리 정책

shared 모듈은 p2·p3가 모두 의존하므로 **하위 호환성** 유지가 필수다.

| 변경 유형 | 버전 업 | 절차 |
|---|---|---|
| 버그 수정 | Patch (1.0.x) | 테스트 통과 후 즉시 배포 |
| 기능 추가 (하위 호환) | Minor (1.x.0) | 기존 인터페이스 유지, 새 메서드 추가 |
| 인터페이스 변경 (breaking) | Major (x.0.0) | p2·p3 동시 업데이트 계획 수립 후 적용 |

---

## 6. 테스트 전략

```
p1_shared/tests/
├── test_token_manager.py      # 토큰 캐시 유효성 확인, 갱신 트리거
├── test_db_connection.py      # get_cursor() 정상 동작, 예외 시 rollback
├── test_backup_manager.py     # dump 파일 생성, 헤더 검증, 보관 정책, 볼륨 경로 확인
├── test_env_detector.py       # 호스트명/IP 감지, .env 프로파일 로드
├── test_sync_manager.py       # safety checker 이상 감지, dry-run, diff 필터
├── test_startup_validator.py  # 테이블 존재, 행 수 검증, 볼륨 확인
├── test_date_utils.py         # 한국/미국 영업일 계산 정확성
└── test_retry.py              # 재시도 횟수, 백오프 간격
```

```bash
# p1_shared 단독 테스트 실행
cd p1_shared
pytest tests/ -v
```

---

## 7. 구현 단계 (Phase)

### Phase 1 — 핵심 인프라 (p2·p3 구현 착수 전 필수)
- [ ] `utils/env_detector.py`: PC 환경 자동 감지 + .env 프로파일 분기
- [ ] `db/connection.py`: `get_cursor()` context manager
- [ ] `ops/logger.py`: 공통 로거 팩토리 + WebSocket 핸들러
- [ ] `utils/retry.py`: 재시도 데코레이터 (동기/비동기)
- [ ] `pyproject.toml` 패키지 설정 + editable install 검증

### Phase 2 — API 클라이언트 통합
- [ ] `api/token_manager.py`: 파일 기반 토큰 캐시
- [ ] `api/kis_api_core.py`: KIS 토큰 공유 코어
- [ ] `api/kiwoom_api_core.py`: Kiwoom 코어
- [ ] p2·p3에서 기존 `kis_rest.py`, `kiwoom_rest.py` 교체 테스트

### Phase 3 — 운영 도구
- [ ] `ops/backup_manager.py`: 백업·복구·검증·비로미 벼륨 경로 명세 (강건 복원 포함)
- [ ] `ops/startup_validator.py`: Docker 재기동 시 DB 기동 검증 + 조치 안내
- [ ] `utils/date_utils.py`: 한국/미국 영업일 유틸리티
- [ ] CLI 진입점 (`python -m p1_shared.ops.backup_manager`)
- [ ] p4_manager 백업 서비스 연동 테스트

### Phase 4 — DB 동기화 도구
- [ ] `ops/sync_manager.py`: full/diff/table 3가지 모드 구현
- [ ] `FullSyncSafetyChecker`: 크기 비교 + 커버리지 분석 + 사용자 재확인 로직
- [ ] kdms 초기 인계: 개발PC → 서버PC full 동기화 검증
- [ ] usdms 초기 인계: 서버PC → 개발PC full 동기화 검증

---

## 8. 알려진 이슈 및 주의사항

| 이슈 | 내용 | 대응 |
|---|---|---|
| KIS 계정 공유 여부 | p2·p3가 동일 계정이어야 토큰 캐시 공유 효과 있음 | 운영자 확인 필요 (tdms_PRD Q1) |
| Docker 내 캐시 경로 | 컨테이너마다 `~/.cache/` 경로가 다름 → 토큰 공유 불가 | 캐시 경로를 볼륨으로 마운트하거나 Redis 등 공유 저장소 사용 고려 |
| psycopg2 스레드 안전성 | `ThreadedConnectionPool`은 스레드 안전하나, 커넥션 자체는 스레드 공유 금지 | `get_cursor()` 사용 시 커넥션을 스레드 경계 밖으로 전달 금지 |
| p1_shared 인터페이스 변경 | p2·p3 동시에 영향 → 한쪽만 업데이트 시 버전 불일치 | Major 변경 시 p2·p3 동시 배포 계획 필수 |
| **kdms DB 유실 현황** | 서버PC kdms DB 유실 상태. 개발PC DB를 소스로 하여 서버PC로 full 동기화 후 Backfill 진행 | Phase 4: kdms 인계 절차 수행 (`sync --source dev --target server --mode full`) |
| **full 동기화 방향 오설 위험** | 소스/대상 방향 실수 시 운영 DB 데이터 영구 유실 가능 | `FullSyncSafetyChecker` 필수 통과 조건: 크기 비교 + 커버리지 확인 + `CONFIRM-FULL-SYNC` 재확인 |
| SSH 키 관리 | `sync_manager`의 SSH 키 경로를 `.env`에 주입. Git 커밋 절대 금지 | `SSH_KEY_PATH=~/.ssh/tdms_sync_rsa` (`.gitignore`에 포함) |
| usdms 서버 동기화 | 서버PC usdms DB 정상 수집 중. 개발PC에 제일 먼저 full 동기화 후 이후 diff로 이상 없음 | Phase 4: usdms 인계 절차 수행 (`sync --source server --target dev --mode full`) |

---

*p2_kdms 상세: `docs/p2_kdms/p2_kdms_PRD.md`*
*p3_usdms 상세: `docs/p3_usdms/p3_usdms_PRD.md`*
*p4_manager 상세: `docs/p4_manager/p4_manager_PRD.md`*
