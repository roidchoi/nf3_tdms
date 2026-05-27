# T-007: 조회 API 완성 및 Blacklist 패턴 구현 Walkthrough

## 1. 구현 개요
본 문서에는 P2 KDMS의 `T-007` 테스크(데이터 조회 API 구축 및 수집 시 블랙리스트 스킵 패턴 반영)의 구현 내용과 검증 절차를 정리합니다.

---

## 2. 세부 구현 사항

### A. 데이터 조회 API 5종 추가 (`tdms_core/p2_kdms/routers/data.py`)
1. **`GET /api/data/ohlcv/daily`**
   - `adjusted=True` 옵션 지정 시, 온더플라이(On-the-fly) 누적곱을 통해 실시간으로 수정주가와 수정거래량을 계산하여 반환합니다.
   - `adjusted=False`인 경우, `daily_ohlcv` 원본 시세를 그대로 반환합니다.
2. **`GET /api/data/ohlcv/minute`**
   - 특정 종목의 분봉 데이터를 기간 조회합니다.
   - **조회 품질 보장**: 최대 조회 기간을 30일 이내로 제한하며, 30일 초과 시 `HTTP 400 Bad Request`를 즉시 반환합니다.
   - **Anti-Pandas 원칙**: 메모리 OOM 예방을 위해 Repository 단에서 Pandas DataFrame 가공을 완전히 배제하고, raw 튜플 리스트를 직접 딕셔너리로 다듬어 응답합니다.
   - **이진 직렬화 포맷**: HTTP 요청 헤더에 `Accept: application/vnd.apache.arrow.stream`이 지정된 경우, `pyarrow` IPC 바이너리 스트림 형식으로 포맷을 인코딩하여 `StreamingResponse`로 즉시 스트리밍 반환합니다. 지정되지 않은 일반 요청의 경우 JSON 구조로 응답합니다.
3. **`GET /api/data/market-cap`**
   - 특정 종목과 기간에 대응하는 시가총액, 누적 거래대금, 거래량, 상장주식수 데이터를 조회합니다.
4. **`POST /api/data/screening`**
   - 최신 Point-in-Time 스냅샷 기준의 재무 비율(ROE 등) 조건을 만족하는 종목 리스트를 DB 레벨에서 효율적으로 스크리닝하여 반환합니다.
   - SQL Injection 방지를 위해 필터 필드명(`roe_val` 등) 및 연산자(`gte`, `lt` 등)에 대한 화이트리스트 검증을 통과한 문자열만 바인딩 쿼리 조립에 사용합니다.
5. **`GET /api/data/preview/{table}`**
   - 내부 시스템 테이블 10종에 대한 `limit` 및 `offset` 기반 페이지네이션 미리보기를 지원합니다.
   - 테이블 명칭 검증을 위해 허용 리스트(`daily_ohlcv`, `stock_info` 등 10개)로 검사한 후 바인딩 처리합니다.
   - `limit` 파라미터는 최대 1000건으로 강제 제한(캡핑) 처리됩니다.

### B. Blacklist 수집 스킵 패턴 구현 (`tdms_core/p2_kdms/tasks/daily_task.py`)
- `daily_ohlcv_gap` 테이블에서 최근 5일 이상 지속적으로 수집 실패한 종목들을 추출하는 `OhlcvRepo.get_blacklisted_stocks()`를 개발하였습니다.
- `DailyTask` 일지 수집 루프 시작 전에 해당 블랙리스트를 조회하여 수집 대상 활성 종목에서 제거(Skip)함으로써 KIS API 할당량을 비효율적으로 소진하지 않도록 차단하였습니다. 스킵된 건수는 `skipped` 카운트에 정확히 누적됩니다.

---

## 3. 검증 결과 및 테스트 세부정보

### A. pytest 실행 결과 (TDD 24개 테스트 케이스 통과)
`tdms_core/p2_kdms/tests/test_data_api_t007.py` 및 `tests/test_blacklist.py`를 통해 모든 조건과 에러 상황을 다각도로 테스트하였으며 전원 통과하였습니다.

```bash
$ conda run -n tdms_p2_env python -m pytest tests/test_data_api_t007.py tests/test_blacklist.py
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms
configfile: pyproject.toml
plugins: anyio-4.13.0, mock-3.15.1
collected 24 items

tests/test_data_api_t007.py .....................                        [ 87%]
tests/test_blacklist.py ...                                              [100%]

============================== 24 passed in 0.85s ==============================
```

### B. 주요 검증 케이스 목록
- **TC-01, 02**: adjusted 옵션 유무에 따른 raw / 온더플라이 수정 일봉 데이터 검증
- **TC-04, 19, 20**: 분봉 조회 시 30일 이하 정상 응답 및 30일 초과 시 400 즉시 차단 검증
- **TC-21**: Accept 헤더에 `arrow` 지정 시 PyArrow IPC Stream 응답 검증 (바이너리 역직렬화 정상 작동)
- **TC-22**: `OhlcvRepo.get_minute_ohlcv` 메서드 내 Pandas 비사용 여부 정적 분석 검증
- **TC-23**: Screening 시 전체 조회 후 파이썬 필터링이 아닌, DB 레벨에서 스크리닝이 수행되는지 검증
- **TC-24**: Preview API 페이지네이션(offset 및 limit 파라미터 유효성) 검증
- **TC-13**: Preview API limit=2000 요청 시 최대 1000개로 정상 캡핑되는지 검증
- **TC-14, 15, 16**: 블랙리스트 등록 종목의 KIS 수집 작업 생략 및 skipped 카운트 정상 반영 검증
