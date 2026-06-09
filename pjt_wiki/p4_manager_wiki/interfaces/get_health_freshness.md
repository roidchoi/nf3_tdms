# 인터페이스: 데이터 신선도 조회 중계 API (get_health_freshness.md)

> **Sub Project**: p4_manager  
> **마지막 업데이트**: 2026-06-09 (Task-006)  
> **물리 경로**: `tdms_core/p4_manager/routers/manager.py` (라인 143-172)
> **상태**: ✅ 완료

---

## 1. 개요
각 마켓(KR/US)의 최신 영업일 대비 당일 일봉 수집 완료도(Freshness) 정보를 이종 백엔드로부터 비동기(`httpx`) 중계 조회합니다.

---

## 2. API 규격

### GET `/api/mgr/health/freshness/{market}`
* **Path Parameters**:
  - `market`: `'kr'` (KDMS) 또는 `'us'` (USDMS)
* **요청 예시**:
  `GET /api/mgr/health/freshness/us`
* **출력 형식**:
  - 반환 타입: `dict` (JSON)
  - 응답 상태코드: `200 OK` (하위 서버 에러 시 장애 격리로 `200 OK` 유지하되 `offline: true` 객체 반환)

#### 정상 반환 스키마 (예시)
```json
{
  "status": "GREEN",
  "latest_trading_date": "2026-06-09",
  "total_active_stocks": 3909,
  "collected_daily_count": 3890,
  "daily_coverage_ratio": 0.9951,
  "is_daily_fresh": true
}
```

#### 장애 격리 (Fault Isolation) 발생 시 반환 스키마
하위 백엔드 오프라인 혹은 통신 실패 시, 시스템 전체 장애 전파를 방지하기 위해 다음 폴백 데이터를 200 응답으로 즉시 리턴합니다.
```json
{
  "status": "RED",
  "offline": true,
  "message": "http://p3_usdms:8005/api/health/freshness ConnectError"
}
```
