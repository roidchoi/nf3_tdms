# [P4DEC-010] 로그 스트리밍 버퍼링 지원 및 테스트 환경 로그 격리

## 1. 컨텍스트 및 요구사항
- **KDMS 실시간 로그 누락**: KDMS의 스케줄러 일일 작업이 완료되었음에도 모니터링 보드의 로그 스트리밍 영역에 로그가 표시되지 않는 현상 발생. 
  - 원인: KDMS는 실시간 터미널 표준 출력을 인메모리 Pub/Sub 방식으로 중계(`log_broadcaster`)하는 실시간 전송만 수행하고 있었으며, 영구 저장 파일 로그와 웹소켓 최초 연결 시의 백필(마지막 N개 라인 선제 전송) 로직이 부재함.
- **USDMS 테스트 로그 오염**: USDMS 모니터링 보드 로그 스트림 창에 Mock 관련 에러 스택 트레이스(`TypeError: 'Mock' object...`, `SEC Connection Failed`)가 비정상적으로 다수 노출됨.
  - 원인: pytest 구동 시 `DailyRoutine.run()`이 동일한 프로덕션 로그 파일(`logs/daily_routine.log`)에 테스트 시점의 Mock 예외를 직접 기록하여 프로덕션 파일이 오염되었고, 웹소켓이 이 파일의 끝 100라인을 읽어 쏴준 결과임.

---

## 2. 해결 결정 (Decision)

### 1) KDMS 영구 파일 로깅 도입 및 웹소켓 100라인 버퍼백필
- `p2_kdms/main.py`에 `FileHandler`를 추가 적용하여 스케줄러 및 전체 서비스 로그를 `logs/daily_update.log` 에 기록하도록 보강함.
- `websocket_endpoint`(`/ws/logs`) 접속 즉시, 해당 로그 파일이 존재할 경우 마지막 100라인을 `send_text`로 선제 전송하는 백필 기능을 구현. (이후 실시간 Pub/Sub 브로드캐스터로 전환 바인딩)

### 2) USDMS & KDMS 테스트 환경 로그 격리 세이프가드
- pytest 테스트 수행 시 프로덕션 로그 파일이 오염되지 않도록 격리 장치를 추가함.
- `os.environ.get("TDMS_ENV") == "test"` 또는 `pytest` 모듈 로드 여부(`"pytest" in sys.modules`)를 조건화하여, 테스트 중일 경우 `daily_routine_test.log` 및 `daily_update_test.log` 와 같이 테스트 격리 로그 파일 경로로 분기 처리함.
- **추가 조치 (웹소켓 긁기 스캔 제외)**: USDMS 웹소켓 핸들러(`tdms_core/p3_usdms/routers/admin.py`)가 최신 로그 파일을 동적으로 검색할 때 `daily_routine_test.log` 와 같은 임시 테스트 로그를 잘못 긁어가 과거 Mock 에러를 계속 띄우던 문제를 식별, 최신 로그 스캔 대상에서 `_test.log` 형식을 완전히 제외(`not f.endswith("_test.log")`)하도록 패치했습니다. 또한 기존에 오염되어 잔존해 있던 프로덕션 로그 파일(`daily_routine.log`)의 내용을 깨끗이 비워 초기화 완료했습니다.

---

## 3. 결과 및 기대효과
- **모니터링 신뢰성 보장**: 사용자가 모니터링 페이지를 이탈해 있는 상황에서 크론 스케줄이 돌아가더라도, 나중에 모니터링 보드에 진입하면 직전의 일일 수집 이력 로그(최대 100줄)를 즉시 로드하여 모니터링할 수 있음.
- **프로덕션 로그 격리 무결성**: pytest 전체를 마음 놓고 수행하더라도 프로덕션 환경의 실질 로깅 데이터와 대시보드가 가짜 에러(Mock Exception)로 채워지는 오염 버그를 완벽히 차단함.

---

## 4. 관련 코드 컨텍스트
- [p2_kdms/main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/main.py)
- [p3_usdms/tasks/daily_routine.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tasks/daily_routine.py)
