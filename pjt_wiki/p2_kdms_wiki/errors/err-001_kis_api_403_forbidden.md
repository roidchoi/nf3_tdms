---
id: p2ERR-001
sub_project: p2_kdms
severity: high
status: confirmed
last_seen: Task-010
related: [[decisions/dec-004_kis_api_throttling_strategy.md]]
---

# [p2ERR-001] KIS API 403 Forbidden IP 차단 장애

### 발생 패턴 및 재현 조건
- **환경**: WSL 2 (Ubuntu 24.04 LTS), Python 3.12, Miniforge3 가상환경
- **발생 시점**: 일일 데이터 수집 태스크(`daily_task.py`) 구동 시, 2,700여 개 전 종목에 대해 단기간 내 스로틀링(Throttling) 없이 초당 20회 이상의 속도로 연속 호출이 발생할 때.
- **재현 방법**:
  1. `KisApiCore`에 스로틀 sleep 지연을 `0`으로 세팅한다.
  2. 전 종목 일봉 범위 수집(`fetch_daily_ohlcv_range`) 루프를 가동한다.
  3. 약 200~300종목 조회를 수행하는 도중 KIS OpenAPI 게이트웨이가 Rate Limit 초과 트래픽으로 판단하고 당사 IP로부터의 모든 요청을 `403 Forbidden`으로 강제 차단한다.

### 실제 에러 로그 (요약 금지)
```text
⚠️ KIS API 요청 실패 (Error: 403 Client Error: Forbidden for url: https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice?adj_price=1&FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD=308120&FID_INPUT_DATE_1=20260522&FID_INPUT_DATE_2=20260527&FID_PERIOD_DIV_CODE=D&FID_ORG_ADJ_PRC=1). 2.93초 후 재시도합니다... (시도 1/3)
```

### 원인
- KIS OpenAPI 공식 규격 상 **초당 호출 한도(실전 투자 계정: 초당 20회, 모의 투자 계정: 초당 2~5회)**가 지정되어 있으나, 기존 수집 파이프라인에는 속도 제어 장치(Throttling Sleep)가 누락되어 있었습니다. 
- 트래픽이 순간 임계치를 초과하면서 IP 차단 상태가 유발되었으며, 이 차단은 약 10분의 쿨다운(Cool-off) 시간을 가져야만 거래소 단에서 자동 해제되는 메커니즘을 가집니다.
- 원인 코드 경로: `tdms_core/p1_shared/p1_shared/api/kis_api_core.py`

### 해결법 (필수)
- **해결 절차**:
  1. `kis_api_core.py` 생성자에 `is_mock` 상태에 맞는 안전 마진 기반 `throttle_delay` 인자를 추가합니다.
  2. KIS API 요청(`request` 메소드) 반환 직전 `time.sleep(self.throttle_delay)`을 호출하여 강제 속도 제한(Rate Limiting)을 구현합니다.
  3. 실전 계정은 `0.08초`(초당 최대 12.5회 호출), 모의 계정은 `0.4초`(초당 최대 2.5회 호출)의 지연 시간을 갖도록 지정하여 IP 차단을 영구적으로 방지합니다.

- **수정된 코드**:
```python
# tdms_core/p1_shared/p1_shared/api/kis_api_core.py L16-32, L127-147
class KisApiCore:
    def __init__(self, app_key: str, app_secret: str, account_no: str = "", is_mock: bool = True):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.is_mock = is_mock
        self.base_url = "https://openapivts.koreainvestment.com:29443" if is_mock else "https://openapi.koreainvestment.com:9443"
        self._token = None
        self._token_expired_at = None
        
        # 안전 마진 고려 속도 지연(Throttling) 설정
        self.throttle_delay = 0.4 if is_mock else 0.08
        logger.info(f"KisApiCore initialized. base_url={self.base_url}, is_mock={is_mock}, throttle_delay={self.throttle_delay}s")

    def _send_request(self, method: str, path: str, headers: dict = None, params: dict = None, data: dict = None) -> dict:
        # (중략) API 호출 진행 ...
        
        # 성공 응답 수령 및 반환 직전 강제 스로틀 딜레이 부여
        if self.throttle_delay > 0:
            time.sleep(self.throttle_delay)
        return res_json
```

### 발생 이력
- Task-010 최초 발생 및 해결 완료
