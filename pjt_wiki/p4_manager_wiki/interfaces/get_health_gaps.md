# 인터페이스: 데이터 갭 검출 및 정규화 중계 API (get_health_gaps.md)

> **Sub Project**: p4_manager  
> **마지막 업데이트**: 2026-06-09 (Task-006)  
> **물리 경로**: `tdms_core/p4_manager/routers/manager.py` (라인 174-230)
> **상태**: ✅ 완료

---

## 1. 개요
각 마켓(KR/US)의 데이터 누락 갭 정보를 수집하여 **P4 정규화 구조(Normalization)**로 단일화 매핑하여 반환합니다.
한국(KDMS)은 미수집 분봉 종목 리스트(`missing_stocks`), 미국(USDMS)은 누락 갭 항목 수(`gaps_count`)로 상이하게 응답하던 포맷을 통합 인터페이스 규격으로 결합합니다.

---

## 2. API 규격

### GET `/api/mgr/health/gaps/{market}`
* **Query Parameters**:
  - `start_date` (string, 옵션)
  - `end_date` (string, 옵션)
* **요청 예시**:
  `GET /api/mgr/health/gaps/kr?start_date=2026-06-01`
* **출력 형식**:
  - 반환 타입: `dict` (JSON)
  - 응답 상태코드: `200 OK` (하위 서버 오프라인 시 장애 격리로 `200 OK` 유지)

#### 정규화 통합 반환 스키마 (예시)
```json
{
  "market": "kr",
  "start_date": "2026-06-09",
  "end_date": "2026-06-09",
  "gaps": [
    {
      "date": "2026-06-09",
      "status": "YELLOW",
      "total_targets": 2500,
      "valid_targets": 2490,
      "missing_count": 10,
      "missing_items": ["005930", "000660"]
    }
  ]
}
```

#### 장애 격리 (Fault Isolation) 발생 시 반환 스키마
하위 백엔드 응답이 실패하거나 오프라인인 경우 폴백 스키마를 반환합니다.
```json
{
  "market": "us",
  "start_date": "2026-06-09",
  "end_date": "2026-06-09",
  "gaps": [],
  "offline": true
}
```
