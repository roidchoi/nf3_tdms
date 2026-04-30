# TDMS 통합 프로젝트 PRD (Product Requirements Document)

> **문서명**: `tdms_PRD.md`
> **버전**: v1.0
> **작성일**: 2026-04-28
> **참조 위키**: `pjt_wiki/migration-pjt/`
> **작성 지침**: `docs/parent/tdms_PRD작성지침.md`

---

## 1. 프로젝트 개요

### 1.1 프로젝트 목적

**TDMS (Total Data Management System)**는 한국 및 미국 금융시장 데이터를 체계적으로 수집·관리·제공하는 통합 데이터 관리 플랫폼이다.

기존에 독립적으로 운영되던 두 시스템(`KDMS`, `USDMS`)의 검증된 아키텍처와 운영 중인 데이터베이스를 **그대로 인계받아** 중단 없이 수집을 이어가면서, 코드베이스를 통합·정제하여 유지보수성과 확장성을 획기적으로 개선하는 것이 핵심 목표다.

### 1.2 배경

| 원본 시스템 | 역할 | 참조 소스 |
|---|---|---|
| **KDMS** (nf_p01_kdms v7.0) | 한국 주식시장 데이터 수집·관리 | `migration_pjt/kdms_origin/` |
| **USDMS** (nf_03_usdms v5.0) | 미국 주식시장 데이터 수집·관리 | `migration_pjt/usdms_origin/` |

두 시스템은 현재 **실시간 운영 중**이며, TDMS는 이 데이터를 단절 없이 인계받는 것을 전제로 설계한다.

### 1.3 핵심 제약 조건

1. **데이터 연속성 보장**: 기존 운영 DB(`kdms_db`, `usdms_db`)를 그대로 인계하여 수집 이력의 단절이 없어야 한다.
2. **무중단 인계**: 마이그레이션 과정에서 수집 작업이 멈추는 기간을 최소화해야 한다.
3. **DB 안전성**: 도커 이미지 빌드·업데이트 시 DB 볼륨이 유실되는 기존 사례가 있었다. 강건한 백업·복구 구조를 필수적으로 구현해야 한다.

---

## 2. 서브프로젝트 구성 및 역할

TDMS는 네 개의 독립적인 서브프로젝트로 구성된다.

```
nf3_tdms/
├── p1_shared/     # 공통 모듈 (API 클라이언트, DB 유틸, 로거 등)
├── p2_kdms/       # 한국 시장 데이터 백엔드 (독립 실행 가능)
├── p3_usdms/      # 미국 시장 데이터 백엔드 (독립 실행 가능)
└── p4_manager/    # 통합 관리 UI + 공통 오케스트레이터
```

### 2.1 p2_kdms — 한국 시장 데이터 백엔드

| 항목 | 내용 |
|---|---|
| **참조 원본** | `migration_pjt/kdms_origin/` (KDMS v7.0) |
| **핵심 목표** | 원본 백엔드 기능을 정제·리팩토링하여 구현 |
| **DB 인계** | 기존 `kdms_db` (TimescaleDB, 포트 5432) 그대로 인계 |
| **독립성** | `p3_usdms`, `p4_manager` 없이도 단독 실행 가능 |

**구현 범위 (ref_kdms_wiki 기준)**

- 일일 OHLCV 수집 (KIS / Kiwoom API)
- 주가 수정계수(price_adjustment_factors) 계산 및 관리
- PIT 재무제표 수집 (KIS API)
- 시가총액 수집 (pykrx / KRX)
- 분봉 데이터 수집 (분봉 수집 대상 종목 선정 포함)
- FastAPI 데이터 조회 엔드포인트 (`/data`, `/health`)
- APScheduler 기반 자동화 스케줄

**포트 배정**: DB `5432`, Backend `8000`

---

### 2.2 p3_usdms — 미국 시장 데이터 백엔드

| 항목 | 내용 |
|---|---|
| **참조 원본** | `migration_pjt/usdms_origin/` (USDMS v5.0) |
| **핵심 목표** | 원본 백엔드 기능을 정제·리팩토링하여 구현 |
| **DB 인계** | 기존 `usdms_db` (TimescaleDB, 포트 5435) 그대로 인계 |
| **독립성** | `p2_kdms`, `p4_manager` 없이도 단독 실행 가능 |

**구현 범위 (ref_usdms_wiki 기준)**

- 티커 마스터 동기화 (SEC EDGAR, CIK 중심)
- 일봉 OHLCV 수집 (KIS 미국 주식 래퍼)
- XBRL 재무 데이터 파싱·표준화 (SEC EDGAR → us_standard_financials)
- PIT 기반 가치평가 지표 산출 (PER/PBR/EV-EBITDA, merge_asof 패턴)
- 재무 비율 산출 (ROE/ROA/ROIC 등)
- 수집 차단 목록 관리 (BlacklistManager)
- FastAPI 데이터 조회 엔드포인트
- 일일 루틴 오케스트레이터 (Step 1~6)

**포트 배정**: DB `5435`, Backend `8005`

---

### 2.3 p4_manager — 통합 관리 레이어

| 항목 | 내용 |
|---|---|
| **참조 원본** | KDMS frontend (Vue 3) + 두 시스템의 공통 관리 패턴 |
| **핵심 목표** | p2, p3를 모두 통합 모니터링·관리하는 단일 UI 및 오케스트레이터 |
| **독립성** | p2, p3가 실행 중일 때 연결; 단독으로는 의미 없음 |

**구현 범위**

- **통합 대시보드**: p2(KR), p3(US) 양쪽의 태스크 상태, 로그, 헬스 지표를 하나의 화면에서 표시
- **통합 스케줄 관리**: 두 시스템의 스케줄을 한 곳에서 조회·수정
- **통합 데이터 익스플로러**: KR/US 데이터를 시장별로 탭 전환하여 조회
- **통합 헬스 모니터링**: 데이터 신선도, 갭 탐지, 마일스톤을 시장별로 통합 표시
- **WebSocket 실시간 로그**: p2, p3 각각의 실행 로그를 탭으로 분리하여 실시간 스트리밍
- **백업·복구 관리 UI**: DB 백업 실행, 복구 절차, 상태 이력을 UI에서 관리

**포트 배정**: Frontend `80` (Nginx), Backend API `8010`

---

## 3. 서브프로젝트 간 관계 다이어그램

```
┌─────────────────────────────────────────┐
│              p4_manager                  │
│   (통합 UI + 오케스트레이션 레이어)         │
│                                          │
│  [KR Dashboard] [US Dashboard]           │
│  [Schedule]     [Health]                 │
│  [Backup/Restore UI]                     │
└──────────┬───────────────┬──────────────┘
           │ REST API 호출  │ REST API 호출
           ▼               ▼
┌──────────────┐   ┌──────────────────┐
│  p2_kdms     │   │  p3_usdms        │
│  (Backend)   │   │  (Backend)       │
│              │   │                  │
│ FastAPI:8000 │   │ FastAPI:8005     │
└──────┬───────┘   └────────┬─────────┘
       │                    │
       ▼                    ▼
┌──────────────┐   ┌──────────────────┐
│  kdms_db     │   │  usdms_db        │
│  (Port 5432) │   │  (Port 5435)     │
│  TimescaleDB │   │  TimescaleDB     │
└──────────────┘   └──────────────────┘
       ↑                    ↑
       │                    │
┌──────────────────────────────────────┐
│         p1_shared/ 공통 모듈          │
│  KIS API Core, Kiwoom Core,          │
│  DB Util, Logger, Backup Manager     │
└──────────────────────────────────────┘
```

---

## 4. 공통 아키텍처 원칙

### 4.1 Point-in-Time (PIT) 데이터 원칙

두 시스템 모두 **특정 시점의 투자자 관점**을 재현할 수 있어야 한다. 미래 데이터가 과거 분석에 혼입되는 Look-ahead Bias를 원천 차단한다.

| 시스템 | PIT Key | 적용 대상 |
|---|---|---|
| p2_kdms | `retrieved_at` (TIMESTAMPTZ) | financial_statements, financial_ratios |
| p3_usdms | `filed_dt` (DATE) | us_financial_facts, us_standard_financials, us_share_history |

> 상세 패턴: `pjt_wiki/migration-pjt/ref_kdms_wiki/interfaces/pit_financial_pattern.md`
> 상세 패턴: `pjt_wiki/migration-pjt/ref_usdms_wiki/interfaces/pit_sec_pattern.md`

### 4.2 Raw + Factor 분리 수정주가 원칙

API가 제공하는 수정주가를 신뢰하지 않는다. **원본 가격(Raw)과 수정 계수(Factor)를 분리 저장**하고 필요 시 역산한다.

| 시스템 | Raw 테이블 | Factor 테이블 | 비고 |
|---|---|---|---|
| p2_kdms | `daily_ohlcv` | `price_adjustment_factors` | KIS/Kiwoom 이원화 관리 |
| p3_usdms | `us_daily_price` | `us_price_adjustment_factors` | Adj/Close 비율 저장 |

> 상세 패턴: `pjt_wiki/migration-pjt/ref_kdms_wiki/interfaces/price_adjustment_factor.md`

### 4.3 공통 인프라 스택

```
DB:       TimescaleDB (PostgreSQL 16) + Hypertable
Backend:  FastAPI + Uvicorn (ASGI)
Infra:    Docker + Docker Compose
p1_shared:   Python 3.12, conda 환경
```

### 4.4 코드 품질 원칙

- **유지보수 우선**: 기존에 검증된 로직은 최대한 보존하되, 가독성·유지보수성·확장성을 위해 리팩토링을 적극 수행한다.
- **구현 방향 통일**: 양 시스템의 유사 기능(수집, 팩터 계산, 헬스체크 등)은 서로를 참조해 더 강건한 쪽의 구조를 표준으로 채택한다.
- **원자적 모듈**: 단일 책임 원칙(SRP)을 준수하여 모듈 단위 테스트와 독립 실행이 가능하도록 구성한다.

---

## 5. 공통 모듈 설계 (p1_shared/)

p2와 p3가 독립 실행 가능한 구조를 유지하면서도, 중복 구현을 피하기 위해 다음 컴포넌트는 `p1_shared/` 공통 모듈로 관리한다.

### 5.1 공통화 대상

| 모듈 | 원본 위치 | 공통화 이유 |
|---|---|---|
| `KisApiCore` | `kdms_origin/collectors/kis_rest.py` + `usdms_origin/backend/collectors/kis_api_core.py` | 동일 KIS API를 양쪽에서 중복 구현. **접근 토큰 캐시를 공유**해야 효율적 |
| `KiwoomApiCore` | `kdms_origin/collectors/kiwoom_rest.py` | p2 전용이지만 p1_shared에 배치하여 향후 확장성 확보 |
| `KisUsWrapper` | `usdms_origin/backend/collectors/kis_us_wrapper.py` | 미국 주식 KIS 래퍼 (p3 전용이지만 p1_shared 배치) |
| `DbUtil` | `db_manager.py` (양쪽) | 커넥션 풀 생성, `get_cursor()` 컨텍스트 매니저 패턴 통일 |
| `LoggerFactory` | `kdms_origin/log_utils.py` | WebSocket 핸들러 포함, 공통 로깅 설정 |
| `BackupManager` | `usdms_origin/ops/run_db_checkpoint.py` 기반 | DB 백업·복구 절차 표준화 |

### 5.2 KIS API 토큰 공유 전략

```
p1_shared/api/kis_api_core.py
  └── KisApiCore
        ├── TokenManager (파일 캐시: ~/.cache/tdms/kis_token.json)
        │     ├── is_valid() → 유효 시 캐시 반환
        │     └── issue_new_token() → 갱신 후 캐시 저장
        └── RateLimiter (초당 호출 제한)

p2_kdms/collectors/kis_kr_client.py  → KisApiCore 상속, KR 전용 엔드포인트
p3_usdms/collectors/kis_us_client.py → KisApiCore 상속, US 전용 엔드포인트
```

> **핵심**: 토큰 캐시 파일을 공유하면 p2와 p3가 같은 KIS 계정을 사용할 때 불필요한 토큰 재발급을 방지하고 API 호출 제한에 여유를 확보한다.

---

## 6. DB 안전성 및 백업·복구 아키텍처

### 6.1 문제 정의

도커 이미지 빌드·업데이트 시 TimescaleDB 볼륨이 의도치 않게 재초기화되는 사례가 발생한 바 있다. 이는 운영 데이터의 치명적 유실로 이어질 수 있으므로, 다층 방어 구조를 설계한다.

### 6.2 방어 계층 설계

#### Layer 1: 볼륨 보호 (Docker 설정)

```yaml
# docker-compose.yml 원칙
volumes:
  kdms_pgdata:
    external: true   # ← 핵심: docker-compose down 시 볼륨 삭제 안 됨
  usdms_pgdata:
    external: true

# 볼륨 생성은 최초 1회만 수동으로 수행
# docker volume create kdms_pgdata
# docker volume create usdms_pgdata
```

> `external: true` 볼륨은 `docker-compose down -v` 명령으로도 **삭제되지 않는다**.

#### Layer 2: 업데이트 전 자동 백업 (Makefile / 업데이트 스크립트)

```bash
# ops/update.sh — 업데이트 전 반드시 실행
#!/bin/bash
set -e
echo "[1/4] Pre-update backup..."
python p1_shared/ops/backup_manager.py --target all --tag pre_update

echo "[2/4] Verifying backup..."
python p1_shared/ops/backup_manager.py --verify-last

echo "[3/4] Pulling new image..."
docker-compose pull

echo "[4/4] Restarting services..."
docker-compose up -d
```

#### Layer 3: 자동 정기 백업 (Cron)

```
# crontab: 매일 새벽 3시 백업
0 3 * * * /path/to/tdms/ops/backup_manager.py --target all --tag daily
```

#### Layer 4: 백업 파일 보관 정책

```
backups/
├── kdms/
│   ├── daily/          # 최근 30일 보관 (자동 만료)
│   ├── weekly/         # 최근 12주 보관
│   └── pre_update/     # 업데이트 직전 백업 (수동 삭제 전까지 보관)
└── usdms/
    └── (동일 구조)
```

#### Layer 5: 복구 절차 표준화

```bash
# ops/restore.sh — 특정 백업으로 복구
python p1_shared/ops/backup_manager.py --restore \
  --target kdms \
  --file backups/kdms/pre_update/checkpoint_20260428_030000.dump

# 복구 후 무결성 검증
python p2_kdms/ops/run_diagnostics.py
```

### 6.3 백업 검증 의무화

백업이 성공적으로 생성되었더라도 **복원 가능한 형태인지 검증**해야 한다.

```
BackupManager.verify_last()
  └→ pg_restore --list 로 dump 파일 헤더 파싱
  └→ 예상 테이블 목록과 대조
  └→ 검증 실패 시 즉시 알림 (콘솔 출력 + 로그 기록)
```

---

## 7. 데이터베이스 인계 절차

기존 운영 DB를 중단 없이 신규 프로젝트로 인계한다. 상세 절차는 각 서브프로젝트 PRD에 기술하되, 공통 원칙은 다음과 같다.

### 공통 인계 원칙

1. **백업 선행**: 인계 전 반드시 `BackupManager`로 전체 덤프 생성 및 검증
2. **스키마 호환 확인**: 신규 스키마가 기존 테이블 구조와 호환되는지 `audit_schema.py` 수준의 검사 선행
3. **볼륨 재사용**: 기존 Docker 볼륨(`kdms_pgdata`, `usdms_pgdata`)을 신규 compose 파일에서 `external: true`로 연결
4. **수집 재개 검증**: 인계 후 일일 루틴 1회 실행 결과를 통해 데이터 연속성 확인

---

## 8. 운영 스케줄 설계

| 시간 (KST) | 대상 | 작업 |
|---|---|---|
| 17:10 (월~금) | p2_kdms | 일일 OHLCV + 팩터 + 시총 동기화 |
| 09:00 (토) | p2_kdms | PIT 재무 데이터 업데이트 |
| 10:20 (토) | p2_kdms | 분봉 백필 + 시총 갭 복구 |
| 07:00 (화~토) | p3_usdms | 일일 루틴 (Step 1~6: Master Sync → Market Data → Financial → Valuation) |
| 03:00 (매일) | p1_shared | DB 자동 백업 (p2, p3 모두) |

> p2(KR 시장: 15:30 마감)과 p3(US 시장: 05:00 KST 마감)의 실행 시간대가 분리되어 서버 부하 충돌이 없다.

---

## 9. 서브프로젝트별 PRD 참조

각 서브프로젝트의 상세 구현 사항은 아래 PRD 문서에 기술한다.

| 서브프로젝트 | PRD 문서 경로 | 상태 |
|---|---|---|
| p2_kdms | `docs/p2_kdms/p2_kdms_PRD.md` | ⬜ 미작성 |
| p3_usdms | `docs/p3_usdms/p3_usdms_PRD.md` | ⬜ 미작성 |
| p4_manager | `docs/p4_manager/p4_manager_PRD.md` | ⬜ 미작성 |
| p1_shared | `docs/p1_shared/p1_shared_PRD.md` | ⬜ 미작성 |

각 PRD 문서는 다음 항목을 포함한다:
- 상세 기능 명세 (API 엔드포인트, DB 스키마 변경사항)
- 리팩토링 대상 및 방향 (원본 대비 개선점)
- 구현 단계(Phase) 계획
- 테스트 전략

---

## 10. 비기능 요구사항

### 10.1 가용성
- p2, p3 각각 **독립적으로 장애 격리** 가능. 한쪽 장애가 다른 쪽에 영향 없음.
- 일일 스케줄 작업 실패 시 다음 실행 주기에 자동 재시도 또는 갭 복구 수행.

### 10.2 확장성
- 향후 추가 시장(예: p5_jp_dms — 일본 시장)을 추가할 때 `p1_shared/` 모듈을 재사용하고 동일 패턴으로 서브프로젝트를 확장할 수 있는 구조.
- `p4_manager`는 새로운 서브프로젝트 추가 시 설정 파일(YAML)에 엔드포인트를 등록하는 방식으로 확장 가능.

### 10.3 유지보수성
- 모든 하드코딩된 설정값은 `.env` 또는 YAML 설정 파일로 외부화.
- `p1_shared/` 공통 모듈의 변경이 p2, p3의 동작을 의도치 않게 변경하지 않도록 **버전 태깅** 또는 인터페이스 분리 적용.
- 운영 스크립트(`ops/`)는 단일 진입점으로 통합하여 사람이 암기할 수 없어도 `Makefile` 또는 `ops/help.sh`로 전체 명령을 확인할 수 있도록 한다.

### 10.4 관찰성 (Observability)
- 모든 일일 루틴은 실행 결과를 `logs/` 폴더에 날짜별로 기록.
- 이상징후 감지 시 로그에 명확한 ERROR 레벨 기록 (p4_manager에서 집계 가능).
- WebSocket 실시간 로그는 p4_manager UI에서 확인.

---

## 11. 개방적 질문 (각 서브프로젝트 PRD 작성 시 결정 필요)

| 번호 | 질문 | 결정 필요 주체 |
|---|---|---|
| Q1 | KIS API 계정이 p2/p3 공유인가, 별도인가? (토큰 캐시 공유 여부에 직접 영향) | 운영자 |
| Q2 | p4_manager가 p2/p3에 직접 DB 접근할 것인가, REST API만 사용할 것인가? | 아키텍처 결정 |
| Q3 | 분봉 데이터(minute_ohlcv)는 p2에서 계속 수집할 것인가? (스토리지 비용 vs 활용도) | 운영자 |
| Q4 | USDMS의 KIS US Wrapper는 계속 사용할 것인가, yfinance로 교체할 것인가? | p3 PRD에서 결정 |
| Q5 | 백업 파일을 원격 저장소(NAS, S3 등)에 자동 전송할 것인가? | 운영자 |

---

*이 문서는 TDMS 프로젝트의 최상위 PRD로, 각 서브프로젝트 PRD 작성의 기준 문서로 활용한다.*
*각 서브프로젝트의 구체적 구현 사항(API 명세, 스키마 DDL, Phase 계획 등)은 해당 PRD에 상세히 기술한다.*
