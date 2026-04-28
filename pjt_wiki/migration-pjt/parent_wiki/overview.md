# Migration PJT 개요 (overview.md)

> **역할**: 이 폴더는 `nf3_tdms` 통합 프로젝트의 **참고(Reference) 소스 저장소**입니다.
> 두 원본 프로젝트(`KDMS`, `USDMS`)를 분석하여, 새 통합 프로젝트(`p1_kdms`, `p2_usdms`, `p3_manager`)의 구현 기준으로 활용합니다.
> **마지막 업데이트**: 2026-04-28

---

## 1. 참고 프로젝트 구성

| 참고 프로젝트 | 원본 저장소 | 역할 | 상태 |
|---|---|---|---|
| `ref_kdms` | `nf_p01_kdms` | 한국 주식시장 데이터 관리 시스템 (원본) | ✅ 클론 완료 |
| `ref_usdms` | `nf_03_usdms` | 미국 주식시장 데이터 관리 시스템 (원본) | ✅ 클론 완료 |

---

## 2. 신규 프로젝트와의 매핑 관계

```
migration_pjt/kdms_origin/ → nf3_tdms 프로젝트의 p1_kdms 구현 참조
migration_pjt/usdms_origin/ → nf3_tdms 프로젝트의 p2_usdms 구현 참조
(공통 아키텍처 패턴) → p3_manager 통합 관리자 구현 참조
```

### 신규 프로젝트 서브 프로젝트 구조 (예정)
| 서브 프로젝트 | 역할 | 참조 원본 |
|---|---|---|
| `p1_kdms` | 한국 시장 데이터 수집/관리 통합 구현 | `migration_pjt/kdms_origin/` |
| `p2_usdms` | 미국 시장 데이터 수집/관리 통합 구현 | `migration_pjt/usdms_origin/` |
| `p3_manager` | 통합 관리 레이어 (공통 스케줄러, 공통 DB, 모니터링) | 두 원본의 공통 패턴 추출 |

---

## 3. 두 원본 프로젝트의 공통 설계 철학

> 이 섹션의 내용은 `p3_manager` 설계 시 핵심 기준이 됩니다.

### 3.1 Point-in-Time (PIT) 원칙
- **정의**: 모든 데이터는 수집 시점(`retrieved_at` 또는 `filed_dt`)을 기록하여 특정 시점의 상태를 재현 가능하게 저장
- **KDMS**: `retrieved_at` 기반 재무제표 버전 관리 → [[ref_kdms_wiki/interfaces/pit_financial_pattern]]
- **USDMS**: `filed_dt` 기반 SEC 공시 기준 PIT → [[ref_usdms_wiki/interfaces/pit_sec_pattern]]

### 3.2 Raw + Factor 분리 아키텍처
- **정의**: 수정 주가를 API에서 받지 않고, Raw 가격과 수정 계수(Factor)를 분리 저장하여 역산
- **KDMS**: `daily_ohlcv(raw)` + `price_adjustment_factors` → 수정주가 계산
- **USDMS**: `us_daily_price(raw)` + `us_price_adjustment_factors` → 수정주가 계산

### 3.3 공통 인프라 (TimescaleDB + FastAPI)
- **DB**: 두 프로젝트 모두 TimescaleDB(PostgreSQL 16) + Hypertable 사용
- **Backend**: FastAPI + Uvicorn (ASGI)
- **차이**: KDMS는 포트 5432/8000, USDMS는 포트 5435/8005로 분리 운영 가능

---

## 4. 지식 그래프 분석 요약 (Graphify)

> 소스: `graphify-out/GRAPH_REPORT.md` (2026-04-28 생성)

- **총 규모**: 124개 파일, 1,066개 노드, 2,480개 관계
- **핵심 God Node**: `DatabaseManager` (243 edges) — 두 프로젝트 전반에 걸친 DB 추상화 레이어
- **주요 커뮤니티**:
  - `USDMS Core & Auditors`: 재무/가치지표 산출 + 데이터 정합성 검증
  - `KDMS Build & Daily Jobs`: 한국 시장 데이터 수집 파이프라인
  - `Brokerage API Integration`: KIS/Kiwoom API 공통 레이어

---

## 5. 물리 경로

```
migration_pjt/
├── kdms_origin/      # KDMS 원본 (git clone: nf_p01_kdms)
└── usdms_origin/     # USDMS 원본 (git clone: nf_03_usdms)
```

상세 구조: [[ref_kdms_wiki/codebase_map]] 및 [[ref_usdms_wiki/codebase_map]] 참조