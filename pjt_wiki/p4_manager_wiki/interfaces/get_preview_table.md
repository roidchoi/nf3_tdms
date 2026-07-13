# GET /api/mgr/preview/{market}/{table}
선택된 시장과 테이블에 대한 데이터를 하위 백엔드로부터 조회하여 중계(Proxy)하는 API입니다. 장애 발생 시 상위 매니저 레이어로 오류가 전파되지 않도록 장애를 격리하고 정규화된 폴백 데이터를 반환합니다.

## 1. 요청 정보
*   **Method**: `GET`
*   **URL**: `/api/mgr/preview/{market}/{table}`
*   **Path Parameters**:
    *   `market`: `'kr'` 또는 `'us'`
    *   `table`: 각 시장별로 허용된 테이블 화이트리스트 10종 중 하나
*   **Query Parameters**:
    *   `limit`: `int` (기본값: 50, 허용 범위: 1 ~ 1000)
    *   `offset`: `int` (기본값: 0, 0 이상)
    *   `stk_cd`: `str | null` (선택, 종목코드 필터링)
    *   `start_date`: `str | null` (선택, YYYY-MM-DD 포맷)
    *   `end_date`: `str | null` (선택, YYYY-MM-DD 포맷)
    *   `quarter`: `str | null` (선택, YYYYQn 포맷 분기 필터링)
    *   `market_filter`: `str | null` (선택, 시장/거래소 필터링)
    *   `keyword`: `str | null` (선택, 종목 코드/명칭 헬퍼 검색어)
    *   `match_type`: `str | null` (선택, 'contains' | 'exact' 매칭 방식)
    *   `search_field`: `str | null` (선택, 'all' | 'code' | 'name' 검색 범위)

## 2. 응답 구조 (JSON)

### 2.1. 정상 응답 (200 OK)
하위 백엔드가 정상 구동 중이고 데이터를 무사히 받아왔을 경우 반환되는 구조입니다.
```json
{
  "offline": false,
  "table": "stock_info",
  "count": 2500,
  "data": [
    {
      "stk_cd": "005930",
      "stk_nm": "삼성전자",
      "market_type": "KOSPI"
    }
  ]
}
```

### 2.2. 장애 격리 폴백 응답 (200 OK)
하위 백엔드가 오프라인이거나 통신 장애(Timeout, Connect Error 등)가 일어났을 때 반환되는 구조입니다. 프론트엔드가 이를 감지하여 "오프라인 상태 배너"를 표시하고 시스템 오류로 오작동하지 않게 보호합니다.
```json
{
  "offline": true,
  "table": "stock_info",
  "count": 0,
  "data": [],
  "message": "Backend communication error: [에러 상세 내용]"
}
```

### 2.3. 입력 검증 오류 (400 Bad Request)
허용되지 않는 `market` 값이 전달되었거나, 각 시장의 화이트리스트에 부합하지 않는 테이블명이 입력되었을 때 반환됩니다.
```json
{
  "detail": "Table 'invalid_table' is not allowed in KR market."
}
```

## 3. 소스 코드 구현
*   **위치**: `tdms_core/p4_manager/routers/manager.py`
*   `httpx.AsyncClient` 비동기 비차단 방식으로 포워딩하며, 화이트리스트 보안 필터를 내장하고 있습니다.
