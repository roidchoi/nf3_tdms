# Task-010 Walkthrough: DB 물리 동기화 연동 및 감사 리포팅

개발 PC와 원격 서버 PC 간 대용량 TimescaleDB 물리적 동기화(Pull/Push) 파이프라인 연동, 무인화를 위한 사전 NOPASSWD 권한 진단, 그리고 DHCP 환경 하에서의 IP 변동 및 WSL2 네트워크 해석 결함을 극복하는 네트워크 IP 자가 탐색 및 실시간 갱신 API 구현을 성공적으로 완료하였습니다.

---

## 1. 구현 파일 목록 및 역할

### 백엔드 (Backend)
1. **[NEW]** [sync_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/sync_service.py)
   * `PhysicalSyncManager`를 기동하기 위한 백그라운드 스레드 오케스트레이션 및 메모리 로그 버퍼링을 총괄합니다.
   * `run_sync_task()`: 이중 확인 텍스트 매칭 검증, 운영계 서버 push 수신 쓰기 행위 원천 차단(403), 로컬/원격 무인 실행용 `sudo -n` 검사 기동을 수행합니다.
   * `detect_server_ip()`: WSL2 내 리눅스 DNS 한계를 타개하기 위해 `powershell.exe` 서브프로세스로 Windows Native Dns API를 우회 호출하며, 2차 실패 시 C클래스 사설망 전체 대역에 대해 Port 8000 TCP 비동기 병렬 프로빙 스캔을 기동하여 서버를 Auto-Discovery합니다.
   * `sync_ip_in_env()`: 정규식을 이용해 `.env` 파일의 타깃 IP 키-값만 유실 없이 치환하고, `os.environ` 딕셔너리에 즉각 반영하여 백엔드 핫플러깅을 구현합니다.
2. **[MODIFY]** [manager.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/routers/manager.py)
   * 물리 동기화 실행 및 감사, IP 탐색/갱신/테스트를 위한 REST API 엔드포인트 6종을 결합 노출하였습니다.
     * `POST /api/mgr/sync`: 동기화 실행
     * `GET /api/mgr/sync/status`: 동기화 상태 및 로그 버퍼 조회
     * `POST /api/mgr/sync/audit`: 양측 적재 무결성 정밀 감사
     * `GET /api/mgr/network/detect-server`: 서버 IP 자동 탐색
     * `POST /api/mgr/network/sync-ip`: .env IP 갱신
     * `POST /api/mgr/network/test-connection`: 수동 IP 연결 핑 테스트
3. **[NEW]** [test_sync_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/tests/test_sync_service.py)
   * TDD에 기반한 단위 테스트, API 통합 테스트, 그리고 실물 환경을 전제로 하는 Tier 3 실제 통합 테스트 케이스 총 14개를 수록하고 전체 검증을 완수했습니다.
4. **[MODIFY]** [docker-compose.yml](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/docker-compose.yml)
   * `p4_backend` 서비스의 볼륨 마운트에 `- ../../.env:/app/.env` 바인드 마운트를 탑재하여, 도커 컨테이너 실행 환경에서도 호스트의 실제 `.env` 파일과 완벽히 동기화되도록 조치하였습니다.

---

## 2. 테스트 검증 결과

### Pytest 테스트 스위트 구동 결과
* **단위 및 API 격리 통합 테스트 (Tier 1 & Tier 2)**: 총 13개 케이스 통과
  * 이중 컨펌 텍스트 미일치 예외 차단 검증 통과.
  * 운영 서버 환경에서의 PUSH(쓰기 수신) 시도 403 Forbidden 거절 검증 통과.
  * 로컬 및 원격지의 sudo NOPASSWD 가이드 메시지 표출 및 412 오류 검증 통과.
  * PowerShell 우회 DNS IP 획득 검증 통과.
  * asyncio 기반 사설 대역 비동기 스캔 및 서버 IP 감출 검증 통과.
  * 정규식 기반 `.env` 내 IP 치환 및 메모리 변수 적용 검증 통과.
  * socket connection 검사 및 API 라우터 매핑 검증 통과.
* **실물 통합 테스트 (Tier 3)**: 1개 케이스 통과
  * `test_physical_sync_preflight_check_against_real_target`: 실제 등록된 서버 및 개발 PC 정보를 기반으로 SSH 접속 및 tar 등 사전 기동 가능 여부를 진단하여 All Green 통과 확인.

```bash
$ pytest tdms_core/p4_manager/tests/test_sync_service.py -v --run-integration
collected 14 items

test_sync_service.py::test_sync_preflight_direction_and_confirm PASSED
test_sync_service.py::test_sync_preflight_server_push_forbidden PASSED
test_sync_service.py::test_sync_preflight_local_sudoers_fails PASSED
test_sync_service.py::test_sync_preflight_remote_sudoers_fails PASSED
test_sync_service.py::test_sync_preflight_success_starts_thread PASSED
test_sync_service.py::test_sync_status_logs_captured PASSED
test_sync_service.py::test_sync_audit_success PASSED
test_sync_service.py::test_detect_server_via_powershell PASSED
test_sync_service.py::test_detect_server_via_scan_success PASSED
test_sync_service.py::test_detect_server_scan_failed PASSED
test_sync_service.py::test_sync_ip_env_update PASSED
test_sync_service.py::test_test_connection_api PASSED
test_sync_service.py::test_api_sync_endpoints PASSED
test_sync_service.py::test_physical_sync_preflight_check_against_real_target PASSED

========================== 14 passed in 1.50s ==========================
```

---

## 3. 핵심 아키텍처 및 의사결정

* **P4DEC-007: Windows PowerShell 우회 DNS 쿼리**:
  * WSL2 리눅스 커널 DNS 한계로 인해 `SERVER_HOSTNAME` 리졸빙이 먹통이 되는 브릿지 결함을 피하기 위해, 리눅스에서 `powershell.exe` 프로세스를 구동하여 Windows OS Native의 DNS 쿼리를 호출해 IP 주소를 역으로 확보합니다.
* **asyncio C클래스 포트 스캔**:
  * DNS 해석이 불가능하거나 서버의 DHCP IP가 통째로 변경되어 모르는 상태일 경우, 개발 PC가 속한 서브넷 대역 `192.168.35.0/24`에 대해 `asyncio`로 TCP 포트 8000 연결을 초고속 동시 병렬 스캔하여 서버 IP를 3초 이내에 Auto-Discovery합니다.
* **서버계 쓰기 차단 및 sudo 무인화 검증**:
  * 수동 동기화 방향이 PUSH일 때 서버 PC가 데이터 복구 수신처가 되어 기존 운영 데이터가 유실되는 비극을 강제 방어합니다.
  * 무인 백그라운드 SSH 전송 시 패스워드 대기(Hang) 현상이 일어나지 않도록 사전에 `sudo -n true` 명령을 로컬/원격 양측에 수행하고, 미등록 시 무인화 권한 가이드를 리턴합니다.
* **호스트-컨테이너 간 실시간 .env 바인드 마운트**:
  * 런타임 시 갱신된 IP가 컨테이너 내부 가상 파일시스템에만 파편화 기입되어 컨테이너 재배포 시 휘발되는 문제를 해결하기 위해, `docker-compose.yml` 볼륨 맵에 호스트 `.env` 파일을 직접 연결(`- ../../.env:/app/.env`)하였습니다. 이를 통해 운영 중 IP 자가 갱신 시 호스트의 실제 물리 파일에 변경 사항이 즉각적이고 영구적으로 전파됩니다.

---

## 4. 최종 통합 UI 시각 검증 결과

Windows 호스트 디버깅 크롬 포트(9222) 포워딩 터널링 연동을 통해, WSL2 도커 상에 배포된 통합 Nginx 패널에 접속하여 시각 정합성 확인을 수행했습니다.

### 데이터 헬스 모니터 화면 (정상)
![데이터 헬스 모니터](/home/roid2/.gemini/antigravity/brain/be5f086d-aefc-4ee5-94f9-3c621167165c/artifacts/health_monitor_dashboard.png)
* KR 및 US 시장의 수집 완료율, 수집 누락 갭 데이터가 정상 수집되어 UI 컴포넌트에 표기되는 것을 입증했습니다.

### 대한민국 (KDMS) 스케줄 및 크론 조회 화면 (404 경로 해결 완료)
![KR 스케줄러 목록](/home/roid2/.gemini/antigravity/brain/be5f086d-aefc-4ee5-94f9-3c621167165c/artifacts/kr_scheduler_dashboard.png)
* `p4_backend` 내부에서 `p2_kdms`로 라우팅하는 스케줄러 엔드포인트 누락 접두사(`/tasks`)를 수정 후 이미지를 재생성하여, 404 에러 팝업 없이 `daily_update` 및 `financial_update` 스케줄 정보 카드가 정상적으로 노출되는 것을 확인했습니다.

---

## 5. 다음 단계 개발(T-011)을 위한 제언

* **T-011 스케줄 환경 변수 통합 마이그레이션 방향**:
  * T-011 에서는 `.env` 내의 기존 KDMS, USDMS 스케줄러 환경 변수의 중앙 마이그레이션을 이행합니다.
  * 루트 `.env`에 정의된 `SCHEDULE_KDMS_*` 및 `SCHEDULE_USDMS_*` 변수 규격을 일원화하고, `p2_kdms`와 `p3_usdms` 각 백엔드 서비스의 기존 로컬 스케줄링 적재 로직이 이 중앙 환경 설정 파일을 바라보고 동작하도록 결합을 통합해야 합니다.
