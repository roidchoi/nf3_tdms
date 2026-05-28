# Walkthrough - T-003: 수정계수 수집 + 역산 API 및 수정주가 물리 테이블 반영 (KIS)

T-003 마일스톤(수정계수 계산 및 배치 수정주가 갱신, API 연동)이 성공적으로 구현되었으며, 34개 단위/통합 테스트 케이스가 성공적으로 검증되었습니다.

---

## 1. 구현된 작업 내용 및 결과

### 1.1 데이터베이스 스키마 및 마이그레이션 (`migrations/003_add_daily_ohlcv_adjusted.sql`)
- `daily_ohlcv_adjusted` 물리 테이블 및 하이퍼테이블 생성
- `daily_ohlcv_gap` 테이블 생성
- `p1_shared/db/kdms_origin/init.sql`에 신규 DDL을 선언하여 테스트 격리 환경에서도 테이블이 자동 생성되도록 완료

### 1.2 KIS 주식 마스터 바이트 슬라이싱 적용 (`collectors/kis_kr_client.py`)
- 기존 문자열 기준 슬라이싱에서 발생하던 한글(2바이트) 오프셋 밀림 버그 해결을 위해 **바이트 단위 고정 폭 슬라이싱(Bytes Slicing)** 도입
- KOSPI / KOSDAQ의 고정 폭 규격(`total_kospi_width` / `total_kosdaq_width`)을 정의된 규격의 합으로 동적으로 산정하여 끝에서부터 잘라냄으로써, 한글명 뒤의 공백이 상이해도 강건(Robust)하게 데이터를 파싱하도록 수정

### 1.3 누적수정계수 역산 및 배치 물리 테이블 반영 (`repositories/ohlcv_repo.py`)
- 일별 시세와 수정계수 간 누적곱 역산 알고리즘을 TimescaleDB/PostgreSQL 상에서 최적의 속도로 수행할 수 있도록 **SQL CTE (`LN`, `EXP` 로그 합 연산)** 배치 쿼리 구현
- 전체 데이터를 지우고 다시 부어 넣는 대신 `ON CONFLICT` 및 수정이 필요한 종목만 선별 반영하도록 `refresh_adjusted_ohlcv_batch` 배치 업데이트 함수 정밀 설계

### 1.4 REST API 라우터 구현 및 연동 (`routers/data.py`, `main.py`)
- `/api/data/stocks`: 활성 종목 목록 조회
- `/api/data/factors/{stk_cd}`: 특정 종목의 수정계수 내역 조회
- `/api/data/ohlcv/daily/adjusted`: 실시간으로 누적수정계수를 적용하여 역산된 수정주가 리스트 조회 (On-the-fly 계산)
- `/api/data/ohlcv/adjusted/{stk_cd}`: `daily_ohlcv_adjusted` 물리 테이블에서 최적화된 속도로 수정주가 리스트 조회
- `main.py`에 라우터를 마운트하고, `KDMS_EXPECTED_TABLES`에 신규 테이블(`daily_ohlcv_adjusted`, `daily_ohlcv_gap`) 등록 완료

### 1.5 전체 자동화 태스크 파이프라인 통합 (`tasks/daily_task.py`)
- `DailyTask` 클래스 내부의 `run_daily_update` 파이프라인에 주가 수정계수 계산 및 물리 수정주가 배치 갱신 단계 추가
- 예외 발생 시 트랜잭션 롤백 및 로깅이 정상적으로 처리되도록 설계

---

## 2. 테스트 검증 완료

전체 34개 테스트가 어떠한 환경 의존성이나 DB 기동 검증 실패 없이 오프라인에서 안전하게 작동하도록 모킹 및 설정을 보강하였습니다.

### 2.1 테스트 수트 실행 결과
```bash
$ PYTHONPATH=tdms_core/p1_shared:tdms_core/p2_kdms:tdms_core pytest tdms_core/p2_kdms/tests
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms
configfile: pyproject.toml
plugins: anyio-4.13.0, mock-3.15.1
collected 34 items

tdms_core/p2_kdms/tests/test_base_repository.py .........                [ 26%]
tdms_core/p2_kdms/tests/test_daily_task.py ....                          [ 38%]
tdms_core/p2_kdms/tests/test_factor_calculator.py ...                    [ 47%]
tdms_core/p2_kdms/tests/test_factor_endpoints.py ...                     [ 55%]
tdms_core/p2_kdms/tests/test_factor_repo.py ...                          [ 64%]
tdms_core/p2_kdms/tests/test_kis_kr_client.py ....                       [ 76%]
tdms_core/p2_kdms/tests/test_master_repo.py ...                          [ 85%]
tdms_core/p2_kdms/tests/test_ohlcv_repo.py ....                          [ 97%]
tdms_core/p2_kdms/tests/test_ohlcv_repo_adjusted.py .                    [100%]

============================== 34 passed in 0.57s ==============================
```

### 2.2 해결한 테스트 리그레션 요인
1. **FastAPI Lifespan 모킹 분리 (`tests/conftest.py`)**
   - 테스트 시작 전 FastAPI lifespan 및 StartupValidator 기동 시 실제 DB 커넥션을 맺거나 시스템 밸리데이션 검증을 시도해 타임아웃 500 에러를 뿜는 현상 해결
   - `conftest.py` 내 전역 `mock_lifespan` 오토유즈 피스처를 선언하여 `main`과 `p2_kdms.main` 두 모듈 경로를 완벽히 모킹
2. **모듈 임포트 불일치 해결 (`tests/test_master_repo.py`)**
   - API DI 오버라이드(`app.dependency_overrides`) 설정 시, 테스트의 임포트 경로(`from p2_kdms.routers.data import ...`)와 메인 기동 경로(`from routers.data import ...`)의 불일치로 인해 모킹이 덮어씌워지지 않아 DB `NoneType` 에러가 나던 현상을 `from routers.data import get_master_repo`로 맞춰 수정
3. **바이트 단위 고정 폭 슬라이싱 반영 (`tests/test_kis_kr_client.py`)**
   - 한글 인코딩 시 발생하는 글자 수 대비 바이트 폭 변위 문제를 `part2_bytes`를 역으로 슬라이싱하고 바이트 단위로 오프셋을 처리해 검증 통과

---

## 3. 향후 권장 작업 및 모니터링 사항
- **대량의 과거 주가 데이터 백필**: 수정주가 역산 시 10년 이상의 대량 주가 정보가 존재하면 최초 배치 업데이트 수행 시 락(Lock) 유지 시간이 길어질 수 있으므로, 종목 단위 분할 배치 또는 비혼잡 시간대에 최초 갱신을 수행할 것을 권장합니다.
- **TimescaleDB 하이퍼테이블 인덱스 최적화**: `daily_ohlcv_adjusted` 테이블에 대용량 조회 성능 향상을 위해 `(stk_cd, dt DESC)` 복합 인덱스가 인라인으로 구성되어 있으나, 실 사용 패턴에 따라 쿼리 튜닝이 요구될 수 있습니다.
