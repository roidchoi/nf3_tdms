# GET /api/mgr/preview/meta
데이터 익스플로러에서 동적으로 조회 가능한 한국(KR) 및 미국(US)의 테이블 명칭과 메타데이터 목록을 일관되게 제공하는 API입니다.

## 1. 요청 정보
*   **Method**: `GET`
*   **URL**: `/api/mgr/preview/meta`
*   **인증 및 권한**: 필요 없음 (시스템 내부 권한)

## 2. 응답 구조 (JSON)
*   **성공 시 (200 OK)**:
    ```json
    {
      "kr": [
        { "table": "stock_info", "name": "종목 마스터 정보" },
        { "table": "daily_ohlcv", "name": "일봉 시세" },
        { "table": "daily_market_cap", "name": "일별 시가총액" },
        { "table": "minute_ohlcv", "name": "분봉 시세" },
        { "table": "financial_statements", "name": "PIT 재무제표" },
        { "table": "financial_ratios", "name": "PIT 재무비율" },
        { "table": "price_adjustment_factors", "name": "수정주가 팩터" },
        { "table": "system_milestones", "name": "수집 마일스톤 이력" },
        { "table": "trading_calendar", "name": "영업일 달력" },
        { "table": "minute_target_history", "name": "수집 대상 이력" }
      ],
      "us": [
        { "table": "us_ticker_master", "name": "미국 티커 마스터" },
        { "table": "us_ticker_history", "name": "티커 변경 이력" },
        { "table": "us_collection_blacklist", "name": "차단 종목 목록" },
        { "table": "us_financial_facts", "name": "SEC XBRL 수시 공시 재무 팩트" },
        { "table": "us_standard_financials", "name": "PIT 표준재무제표" },
        { "table": "us_share_history", "name": "주식수 변동 이력" },
        { "table": "us_daily_price", "name": "일봉 시세" },
        { "table": "us_price_adjustment_factors", "name": "수정주가 팩터" },
        { "table": "us_daily_valuation", "name": "일별 가치평가 지표" },
        { "table": "us_financial_metrics", "name": "분기별 재무비율" }
      ]
    }
    ```

## 3. 소스 코드 구현
*   **위치**: `tdms_core/p4_manager/routers/manager.py`
*   정적 딕셔너리를 직접 바인딩하여 빠르게 프론트엔드로 전달합니다.
