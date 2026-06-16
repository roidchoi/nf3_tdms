# Interface: Settings & Config (config.py)

> **파일**: `tdms_core/p2_kdms/config.py`
> **클래스**: `Settings(BaseSettings)`
> **관련**: `[[p2_kdms_wiki/interfaces/fastapi_lifespan.md]]`, `[[p1_shared_wiki/interfaces/env_detector.md]]`

---

## 설계 원칙: Layer A / Layer B 이중 구조

```
Layer A — EnvDetector 전용 (p1_shared.utils.env_detector 에서 읽음)
  tdms_env, dev_hostname, server_hostname, dev_ip, server_ip

Layer B — 앱 내부용 (repositories/base.py, main.py 등)
  DEV/SERVER DB 접속 정보, 풀 크기, 로그 레벨
```

---

## 전체 필드 정의

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # Layer A
    tdms_env:        str = ""
    dev_hostname:    str = ""
    server_hostname: str = ""
    dev_ip:          str = ""
    server_ip:       str = ""

    # DEV DB
    dev_kdms_db_user:     str = "roid"
    dev_kdms_db_password: str = ""
    dev_kdms_db_port:     int = 5432
    dev_kdms_db_name:     str = "kdms_db"

    # SERVER DB
    server_kdms_db_user:     str = "roid"
    server_kdms_db_password: str = ""
    server_kdms_db_port:     int = 5432
    server_kdms_db_name:     str = "kdms_db"

    # Layer B
    postgres_user:     str = ""
    postgres_password: str = ""
    db_pool_min:       int = 5
    db_pool_max:       int = 20
    log_level:         str = "INFO"

    # T-011 스케줄링 (중앙화 마이그레이션 변수)
    schedule_kdms_daily_update:     str = "15:40"
    schedule_kdms_financial_update: str = "17:10"
    schedule_kdms_backfill_minute:  str = "10"

settings = Settings(_env_file=".env")
```

---

## .env 파일 변수 목록 (실제 사용 키)

| 변수 | 레이어 | 설명 |
|---|---|---|
| `TDMS_ENV` | A | 환경 식별자 (dev/server) |
| `DEV_HOSTNAME` / `SERVER_HOSTNAME` | A | 호스트명 기반 환경 감지 |
| `DEV_IP` / `SERVER_IP` | A | IP 기반 환경 감지 |
| `DEV_KDMS_DB_PASSWORD` | B | 개발 DB 비밀번호 |
| `SERVER_KDMS_DB_PASSWORD` | B | 서버 DB 비밀번호 |
| `DB_POOL_MIN` / `DB_POOL_MAX` | B | 커넥션 풀 크기 |
| `LOG_LEVEL` | B | 로그 레벨 |
| `SCHEDULE_KDMS_DAILY_UPDATE` | B | 대한민국 시장 일일 가격 수집 배치 시각 (기본: `"15:40"`) |
| `SCHEDULE_KDMS_FINANCIAL_UPDATE` | B | 대한민국 시장 분기 재무 수집 배치 시각 (기본: `"17:10"`) |
| `SCHEDULE_KDMS_BACKFILL_MINUTE` | B | 대한민국 시장 분봉 백필 수기 기동 간격 분 (기본: `"10"`) |

