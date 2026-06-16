# get_integrated_status (통합 상태 집계 API)

> 마지막 변경: Task-002 (2026-06-16 보완 반영)
> 소스 위치: `tdms_core/p4_manager/routers/manager.py:5` 및 `tdms_core/p4_manager/services/status_service.py:7`

### 1. 개요 및 목적
- 한국 시장(KDMS) 및 미국 시장(USDMS) 백엔드의 헬스(데이터 최신성) 및 관리자 태스크 기동 상태를 수집하고 단일 스펙으로 가공하여 통합 서빙합니다.
- 동기식 호출의 연쇄 지연 및 특정 서버 중단 시 대시보드가 멈추는 동기화 병목을 막기 위해 **백그라운드 캐싱 폴링 및 장애 격리(Fault Isolation) 레이어**를 내장하고 있습니다.
- 연관된 문서: [[p4_manager_wiki/codebase_map]], [[p4_manager_wiki/decisions#P4DEC-002]]

### 2. 상세 명세 (요약 금지)

#### API 명세
**엔드포인트**: `GET /api/mgr/status`  
**전송 프로토콜**: HTTP/1.1  
**인증/인가**: 없음  

**출력 형식**:
- 반환 타입: `JSON`
- 응답 코드: `200 OK` (특정 백엔드가 다운된 상태에서도 200 응답이 보장되며, 해당 시장 상태만 `OFFLINE`으로 반환됩니다)
- 예시 응답 (양쪽 백엔드 정상인 경우):
```json
{
  "kr": {
    "status": "ONLINE",
    "freshness": {
      "status": "GREEN",
      "latest_trading_date": "2026-06-08",
      "daily_coverage_ratio": 0.996,
      "is_daily_fresh": true
    },
    "tasks": {
      "is_running": false,
      "last_run_time": "2026-06-08T17:05:00",
      "last_status": "success"
    }
  },
  "us": {
    "status": "ONLINE",
    "freshness": {
      "status": "YELLOW",
      "latest_trading_date": "2026-06-08",
      "daily_coverage_ratio": 0.966,
      "is_daily_fresh": true
    },
    "tasks": {
      "is_running": false,
      "last_run_time": "2026-06-09T07:35:00",
      "last_status": "success"
    }
  }
}
```
- 예시 응답 (한국 백엔드가 다운되었거나 접속 지연 시):
```json
{
  "kr": {
    "status": "OFFLINE",
    "freshness": null,
    "tasks": null
  },
  "us": {
    "status": "ONLINE",
    "freshness": {
      "status": "YELLOW",
      "latest_trading_date": "2026-06-08",
      "daily_coverage_ratio": 0.966,
      "is_daily_fresh": true
    },
    "tasks": {
      "is_running": false,
      "last_run_time": "2026-06-09T07:35:00",
      "last_status": "success"
    }
  }
}
```

### 3. 주의사항 및 의존성
- **타임아웃 설정**: 백그라운드 수집 시 `httpx.AsyncClient(timeout=10.0)`을 통해 개별 호출 시간 한도를 10초로 제한하고 있습니다. 10초가 초과되거나 통신 에러가 나면 해당 백엔드를 `OFFLINE` 처리합니다. (2026-06-16 기존 2초에서 상향 보완)
- **최신 태스크 상태 보존**: USDMS(미국 시장) 백엔드가 파일 목록을 기반으로 최근 실행 이력을 전달할 때, 실시간 실행 상태(`is_running: true`)가 주입된 최신 리포트를 우선 반환합니다. P4 Manager는 이 리스트를 파싱할 때 동일 태스크(job_id)에 대해 이미 최신 상태가 캐시에 등록되었다면 뒤에 등장하는 과거 완료 이력에 의해 상태가 `is_running: false`로 덮어씌워지지 않도록 중복 방어 처리를 수행합니다. (2026-06-16 보완 반영)
- **백그라운드 캐시 의존**: 런타임에 직접 백엔드를 찌르지 않고 30초 주기(`TASK_POLL_INTERVAL`)로 갱신되는 로컬 메모리 변수(`_cache`)를 반환하므로, API 조회 호출 부하가 1ms 이내로 낮습니다.
- 참고 에러: [[p4_manager_wiki/errors/p4err-001_module_not_found_tdms_core]]
