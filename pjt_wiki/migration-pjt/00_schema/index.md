# Migration PJT 지식 지도 (index.md)

> **역할**: `migration_pjt/` 참조 프로젝트 전체 지식의 네비게이션 허브
> **마지막 업데이트**: 2026-04-28
> **Graphify 분석**: `graphify-out/GRAPH_REPORT.md` (2026-04-28, 1,066 nodes, 2,480 edges)

---

## 📌 빠른 참조

| 목적 | 문서 |
|---|---|
| 두 프로젝트 전체 개요 및 관계 | [[parent_wiki/overview]] |
| KDMS 코드 구조 전체 | [[ref_kdms_wiki/codebase_map]] |
| USDMS 코드 구조 전체 | [[ref_usdms_wiki/codebase_map]] |
| KDMS DB 스키마 | [[ref_kdms_wiki/interfaces/db_schema]] |
| USDMS DB 스키마 | [[ref_usdms_wiki/interfaces/db_schema]] |

---

## 🗂️ 지식 구조 (Graphify 커뮤니티 기반)

### Cluster A: 공통 인프라 & 철학
> 두 프로젝트가 공유하는 설계 패턴 — `p3_manager` 설계의 핵심 기반

| 문서 | 요약 | 상태 |
|---|---|---|
| [[parent_wiki/overview]] | 두 참조 프로젝트 역할, 신규 프로젝트 매핑 | ✅ |
| [[ref_kdms_wiki/interfaces/pit_financial_pattern]] | KDMS PIT 재무 패턴 (`retrieved_at` 기반) | ✅ |
| [[ref_usdms_wiki/interfaces/pit_sec_pattern]] | USDMS PIT SEC 패턴 (`filed_dt` + merge_asof) | ✅ |
| [[ref_kdms_wiki/interfaces/price_adjustment_factor]] | Raw + Factor 분리 수정주가 패턴 (공통) | ✅ |
| [[ref_usdms_wiki/decisions/coexistence_with_kdms]] | KDMS-USDMS 공존 아키텍처 (포트 분리) | ✅ |

### Cluster B: KDMS (한국 시장) 참조
> `p1_kdms` 구현 시 주요 참조

| 문서 | 요약 | 상태 |
|---|---|---|
| [[ref_kdms_wiki/codebase_map]] | KDMS 전체 파일 구조 + 역할 | ✅ |
| [[ref_kdms_wiki/environment]] | KDMS 기술 스택 + 환경 변수 | ✅ |
| [[ref_kdms_wiki/interfaces/db_schema]] | KDMS 9개 핵심 테이블 DDL | ✅ |

### Cluster C: USDMS (미국 시장) 참조
> `p2_usdms` 구현 시 주요 참조

| 문서 | 요약 | 상태 |
|---|---|---|
| [[ref_usdms_wiki/codebase_map]] | USDMS 전체 파일 구조 + 일일 루틴 | ✅ |
| [[ref_usdms_wiki/environment]] | USDMS 기술 스택 + 운영 환경 | ✅ |
| [[ref_usdms_wiki/interfaces/db_schema]] | USDMS 10개 핵심 테이블 DDL | ✅ |

---

## 🔑 God Nodes (핵심 추상화 - Graphify 분석 결과)

> 이 컴포넌트들은 신규 프로젝트에서 최우선으로 재설계해야 할 핵심입니다.

| Node | Edges | 위치 | 역할 |
|---|---|---|---|
| `DatabaseManager` | 243 | 두 프로젝트 모두 | DB 추상화 레이어 (풀링 + 쿼리) |
| `KisREST` | 78 | kdms_origin/collectors/ | KIS API 클라이언트 |
| `get_cursor()` | 69 | db_manager.py | DB 커서 컨텍스트 매니저 |
| `KiwoomREST` | 63 | kdms_origin/collectors/ | Kiwoom API 클라이언트 |
| `SECClient` | 36 | usdms_origin/backend/collectors/ | SEC EDGAR API 래퍼 |
| `BlacklistManager` | 27 | usdms_origin/backend/utils/ | 수집 차단 목록 관리 |
| `MasterSync` | 24 | usdms_origin/backend/collectors/ | SEC 티커 동기화 |

---

## 🕳️ 지식 갭 (Knowledge Gaps - Graphify 분석 결과)

> 추가 문서화가 필요한 영역

| 갭 | 항목 | 우선순위 |
|---|---|---|
| KDMS KIS API 날짜 동작 특이점 | `start_date` 무시, `end_date` 역방향 페이지네이션 | 높음 |
| USDMS XBRL 파서 8-K Gap 한계 | Known Constraint - Blacklist로 방어 | 중간 |
| Frontend (Vue 3) 컴포넌트 구조 | Community 12~14가 실제로는 백엔드 로직과 혼재 | 낮음 |

---

## 📝 업데이트 로그

| 날짜 | 내용 |
|---|---|
| 2026-04-28 | 최초 초기화 — migration_pjt/ (KDMS + USDMS) 참조 위키 구축. Graphify 지식 그래프 연동 |