# Sub Project 기술 의사결정 (decisions.md)

> **Sub Project**: p4_manager  
> **범위**: 이 Sub Project 내부에만 영향을 미치는 결정  
> **마지막 업데이트**: 2026-06-09 (T-006 완료)

---

## 사용 지침

전체 시스템에 영향을 미치는 결정은 `parent_wiki/decisions.md`에 기록. 이 파일은 이 Sub Project 내부 결정만 다룬다.

---

## 의사결정 목록

| ID | 제목 | Task | 상태 |
|---|---|---|---|
| P4DEC-001 | Nginx 동적 Upstream 리졸브 및 변수 기반 프록시 패스 적용 | T-001 | active |
| P4DEC-002 | 백그라운드 캐싱 폴링 기법 및 실시간 API 장애 격리(Fault Isolation) 레이어 적용 | T-002 | active |
| P4DEC-003 | 이종 갭 검출 데이터의 정규화(Normalization) 및 실시간 API 장애 격리(Fault Isolation) | T-006 | active |
| P4DEC-004 | 개발 PC 백업 허브 프로파일 식별 및 서버 PC 물리 차단 안전장치 아키텍처 | T-008 | active |
| P4DEC-005 | 컨테이너 재생성 시 백업 유실 방지를 위한 데이터 볼륨 바인딩 및 호스트 Docker.sock 연동 | T-009 | active |
| P4DEC-006 | 시장 격리형 물리 백업 및 개별 복구 오케스트레이션 아키텍처 | T-009 | active |
| P4DEC-007 | Windows PowerShell 우회 DNS 쿼리 및 Async C클래스 포트 스캔을 통한 서버 IP 자가 갱신 | T-010 | active |

---

## [P4DEC-001] Nginx 동적 Upstream 리졸브 및 변수 기반 프록시 패스 적용 (T-001)

### 배경
*   통합 테스트 환경 기동 시점이나 로컬 운영 중 특정 백엔드 컨테이너(`p2_kdms`, `p3_usdms`)가 꺼져 있거나 Docker DNS 네트워크에 미기동 상태일 때, Nginx 컨테이너가 `host not found in upstream` 오류를 내며 아예 부팅되지 않고 무한 재시작 루프에 빠지는 현상이 발견되었습니다.

### 결정 내용
*   Nginx 설정 내부(`nginx.conf`)에 도커 내장 DNS 리졸버(`resolver 127.0.0.11 valid=10s;`)를 명시적으로 부여했습니다.
*   Upstream 경로 설정 시 호스트명을 직접 전달하는 대신, `set $upstream_kdms p2_kdms;` 와 같이 변수화하여 `proxy_pass http://$upstream_kdms:8000;` 형태로 주입하도록 설계했습니다. Nginx는 변수가 사용된 프록시 타깃을 기동 시점에 정적 검증하지 않고 런타임에 동적으로 해석하기 때문에 백엔드 컨테이너의 가동 순서에 무관하게 항상 Nginx가 안전하게 부팅될 수 있습니다.
*   Nginx의 `rewrite ... break;` 지시어 뒤에 `set`이 수행되면 무시되는 특성을 피하기 위해, `set` 선언을 `rewrite`보다 우선적으로 배치하도록 규칙을 정립했습니다.

### 영향 범위
*   `tdms_core/p4_manager/nginx/nginx.conf`
*   `tdms_core/p4_manager/tests/test_infra.py` (Nginx 설정 검증 단언문도 변수식에 매칭되도록 변경)

### 대안 검토

| 대안 | 거부 이유 |
|------|----------|
| `docker-compose.yml` 내 `extra_hosts` 지정 | `/etc/hosts` 하드코딩 우회 방식은 도커의 내장 DNS resolver 해석보다 높은 우선순위를 가지게 됩니다. 이로 인해 실제 운영망 환경에서 Nginx가 다른 컨테이너로 통신하려 할 때 도커 컨테이너 IP가 아닌 로컬호스트(`127.0.0.1`)로 경로가 고정되어 버려, 실 런타임 통신 연결이 단절되는 심각한 사이드 이펙트가 발생합니다. |

---

## [P4DEC-002] 백그라운드 캐싱 폴링 기법 및 실시간 API 장애 격리(Fault Isolation) 레이어 적용 (T-002)

### 배경
*   통합 관리 API(/api/mgr/status) 호출 시마다 p2 및 p3 백엔드에 동기식 HTTP 요청을 직접 트리거하면, 둘 중 한 백엔드가 오프라인 상태일 때 Connection Timeout(최대 10~20초) 또는 Connection Error가 발생해 통합 API 전체가 마비되는 심각한 결함이 발생합니다.
*   또한, 실시간 API 조회를 수행하면 응답 지연 시간이 극도로 높아져 사용자 대시보드 사용성이 크게 저하됩니다.

### 결정 내용
*   **백그라운드 캐싱 폴링**: FastAPI의 `lifespan` 이벤트에 백그라운드 무한 루프 태스크를 물리고, 30초마다 캐시 변수(`_cache`)를 갱신합니다. 요청자는 메모리에 캐시된 데이터를 즉시 리턴받으므로 응답 속도가 1ms 이내로 최적화됩니다.
*   **장애 격리 (Fault Isolation)**: p2, p3 호출부에 각각 예외 처리(`try-except`) 블록을 격리 배치하여 특정 백엔드가 오프라인 상태이거나 500 오류가 나도, 타 백엔드의 정보는 여전히 `ONLINE`으로 정상 노출하고 에러가 난 시장만 안전하게 `OFFLINE`으로 매핑하여 서빙을 정상화합니다.
*   **비동기 병렬화**: `asyncio.gather`를 사용하여 p2 및 p3의 헬스체크와 태스크 목록 조회를 비동기로 병렬 수집해 네트워크 입출력 대기 효율을 극대화합니다.

### 영향 범위
*   `tdms_core/p4_manager/services/status_service.py`
*   `tdms_core/p4_manager/main.py`
*   `tdms_core/p4_manager/tests/test_status.py`

### 대안 검토

| 대안 | 거부 이유 |
|------|----------|
| 캐시 없이 매 요청마다 동기/비동기 실시간 조회 | 특정 타깃 다운 시 Timeout/Connection Error가 프론트엔드로 그대로 전파되어 대시보드가 크래시되며, 지연 시간(Latency)이 2초 이상으로 고정되는 악영향을 초래합니다. |

### 관련 링크
*   `status_service.py` (폴링 및 에러 격리 구현부)
*   `get_integrated_status.md` (통합 상태 API 인터페이스 정의)

---

## [P4DEC-003] 이종 갭 검출 데이터의 정규화(Normalization) 및 실시간 API 장애 격리(Fault Isolation) (T-006)

### 배경
*   한국 주식 백엔드(KDMS)와 미국 주식 백엔드(USDMS)의 수집 신선도 및 누락 갭 데이터 포맷이 서로 다릅니다. KDMS는 미수집 분봉 리스트를 반환하고 USDMS는 daily_gap과 minute_gap의 일간 누락 수를 제공하기 때문에, 프론트엔드에서 일관된 그리드 및 신선도 차트를 그리기 힘듭니다.
*   단순 조회가 아닌 차단 해제(`POST .../release`)나 마일스톤 생성(`POST .../milestones`) 등 리프레시 성격의 API는 장애 격리 시 200 OK 폴백을 리턴하면 클라이언트가 등록에 성공했다고 오인하는 중대한 흐름 왜곡이 생깁니다.

### 결정 내용
*   **구조 정규화(Normalization)**: P4 백엔드 레이어에서 KDMS/USDMS 로우 데이터를 단일 가시성 모델(`gaps: [GapItem]`)로 사전 가공하여 전달하도록 라우터를 보강했습니다.
*   **동적 예외 차별화**: 단순 상태 조회성 API(freshness, gaps, milestones get, blacklist get)는 예외 발생 시 `200 OK` 와 `offline: true` 캐스팅 객체를 제공하여 화면이 크래시되지 않게 막았습니다. 반면 변경 유발 API(milestones post, release post)는 통신 실패 시 `502 Bad Gateway` 및 구체적인 에러 메시지를 던져 클라이언트 단에서 트랜잭션 오류를 확실히 포착하게 유도했습니다.

### 영향 범위
*   `tdms_core/p4_manager/routers/manager.py` (정규화 및 장애 격리 분기 로직)
*   `tdms_core/p4_manager/tests/test_health_bridge.py` (API 6종 및 예외 격리 검증)

### 관련 링크
*   `get_health_freshness.md`, `get_health_gaps.md` (정규화 중계 스펙 정의)
*   `post_blacklist_release.md`, `kr_milestones.md` (액션 중계 및 502 예외 전달 정의)

---

## [P4DEC-004] 개발 PC 백업 허브 프로파일 식별 및 서버 PC 물리 차단 안전장치 아키텍처 (T-008)

### 배경
*   통합 관리 기능에 로컬 DB 물리 스냅샷 아카이빙(tar.gz) 기능을 탑재하게 되면서, 서버 PC(운영계)에서 이 기능이 구동될 경우 실시간 지속 수집으로 돌아가는 TimescaleDB의 I/O 경합 및 데이터 정합성 교란이 초래될 우려가 제기되었습니다.
*   특히 개발 PC와 서버 PC 간에 동일한 매니저 웹 콘솔이 기동될 수 있으므로, 운영자의 조작 실수로 인한 실서버에서의 스냅샷 생성을 예방할 수 있는 엄격하고 강건한 설계 안전장치가 요구되었습니다.

### 결정 내용
*   **백엔드 API 수준 원천 봉쇄**: `p1_shared.utils.env_detector`를 사용하여 구동 장비가 `server`일 경우, `POST /api/mgr/backup` 요청에 대해 즉각 `403 Forbidden` 예외를 던지며 백업 아카이빙 프로세스(tar)의 실행 시도 자체를 원천 차단합니다.
*   **프론트엔드 UI/UX 다중 경고 및 비활성화**:
    *   글로벌 헤더 우측에 `GET /api/mgr/env` 결과를 기반으로 한 실시간 접속 환경 식별 배지(개발 PC: 🟢녹색 표시 / 서버 PC: 🔴적색 점멸 표시)를 영구 노출하여 운영자에게 시각적 경각심을 줍니다.
    *   `BackupView.vue` 내에서 `server` 환경일 경우, 스냅샷 백업 실행 관련 모든 컨트롤(태그 입력 폼, 백업 실행 버튼)을 비활성화(`:disabled`) 처리하고 눈에 띄는 적색 차단 가이드 배너를 상단에 배치합니다.
*   **통합 테스트 데이터 격리**: 실물 tar 아카이브 검증 시, 66GB에 달하는 실제 TimescaleDB 볼륨 압축에 걸리는 I/O 부하와 오랜 시간을 피하기 위해, 테스트 기동 전 일시적으로 설정 객체의 `data_path`를 테스트용 더미 물리 디렉토리로 변경(오버라이드)하여 검증하고 원복시키는 방식을 취함으로써 안전하고 신속한 실 subprocess 검증을 수행합니다.

### 영향 범위
*   `tdms_core/p4_manager/services/backup_service.py`
*   `tdms_core/p4_manager/routers/manager.py`
*   `tdms_core/p4_manager/frontend/src/views/BackupView.vue`
*   `tdms_core/p4_manager/frontend/src/views/DashboardView.vue`
*   `tdms_core/p4_manager/tests/test_backup.py`

### 관련 링크
*   `backup_api.md` (환경 식별 및 물리 백업 API 명세)

---

## [P4DEC-005] 컨테이너 재생성 시 백업 유실 방지를 위한 데이터 볼륨 바인딩 및 호스트 Docker.sock 연동 (T-009)

### 배경
*   P4 백엔드 매니저 서비스(`p4_backend`) 컨테이너는 빌드 및 구동 시점의 임시 파일 시스템을 사용하므로, 컨테이너 재생성/재빌드 시 내부에 보관하고 있던 로컬 백업 아카이브(`.tar.gz`)들이 유실되는 심각한 결함이 식별되었습니다.
*   또한, 개발 PC 환경에서 복구 실행 시 타 도커 DB 및 API 서버 컨테이너들을 기동/중지(`docker stop`/`start`) 시켜야 하지만, 컨테이너 내부에 `docker` CLI 명령어가 없으며 호스트 도커 데몬 소켓과의 통신로가 차단되어 물리 복구 라이프사이클 오케스트레이션이 불가능했습니다.

### 결정 내용
*   **물리 볼륨 바인딩 설계**:
    - `docker-compose.yml` 에서 `p4_backend` 컨테이너에 호스트의 데이터 폴더(`../../data`)와 백업 폴더(`../../backups`)를 각각 `/app/data` 및 `/app/backups` 경로로 직접 이중 바인딩 매핑하도록 보강하였습니다.
    - 이를 통해 도커 이미지가 리빌드되거나 소멸 후 재기동되더라도 호스트의 물리 백업본은 절대로 소실되지 않는 강건성을 확보했습니다.
*   **호스트 도커 소켓 및 CLI 내장**:
    - 호스트의 도커 소켓 `/var/run/docker.sock`을 컨테이너 내부의 동일한 위치로 마운트하여 컨테이너 내부 프로세스가 호스트의 도커 데몬에게 직접 제어 패킷을 날릴 수 있도록 연결로를 개방했습니다.
    - `backend.Dockerfile` 내부에 static Docker CLI 정적 바이너리를 curl로 다운로드하여 설치하는 과정을 보강하여 컨테이너 환경 내에서도 `subprocess.run(["docker", "stop", ...])` 명령어 구동이 완벽하게 가동되도록 조치했습니다.

### 영향 범위
*   `tdms_core/p4_manager/docker-compose.yml` (볼륨 마운트 매핑)
*   `tdms_core/p4_manager/backend.Dockerfile` (docker CLI 내장화)
*   `tdms_core/p4_manager/services/backup_service.py` (컨테이너 내 subprocess 실행성 보장)

### 관련 링크
*   `backup_api.md` (물리 백업 및 복구 명세서)

---

## [P4DEC-006] 시장 격리형 물리 백업 및 개별 복구 오케스트레이션 아키텍처 (T-009)

### 배경
*   기존 통합 물리 백업(`all` 옵션)은 88GB(KDMS 66GB + USDMS 22GB)의 전체 데이터베이스를 한꺼번에 압축하므로 기기 리소스 소모 및 압축 시간(I/O 과부하)이 극대화되는 문제가 있었습니다.
*   또한, 시장별(`kdms`/`usdms`)로 데이터 관리 주체와 변경 지점이 서로 다름에도 불구하고, 복구 시 모든 데이터가 동시에 롤백되어 의도치 않은 시장의 최신 수집 데이터가 유실되는 사고 가능성이 존재했습니다.
*   TimescaleDB 데이터 디렉토리 권한이 `700`으로 묶여 있어 일반 권한으로는 아카이빙 시 데이터가 누락되는(빈 껍데기만 압축되어 용량이 비정상적으로 작아지는) 결함이 발견되어, 컨테이너 내외부를 아우르는 동적 권한 보정 래퍼가 필수적이었습니다.

### 결정 내용
*   **통합 백업 제거 및 시장 격리형 백업/복구 구현**:
    - 물리 백업 및 복구 프로세스에서 `all` 옵션을 완전히 도려내고, 오직 시장별(`kdms`/`usdms`) 개별 격리 트랜잭션만 수행하도록 구조를 개편했습니다.
    - `kdms` 복구 시에는 오직 `["p2_kdms", "kdms_backend", "kdms_timescaledb"]` 컨테이너들만 정지 후 복구하며, `usdms` 복구 시에는 오직 `["p3_usdms", "usdms_backend", "usdms_timescaledb"]` 컨테이너들만 제어하여 상호 간섭 및 데이터 오염을 완벽히 차단합니다.
*   **동적 권한 보정 래퍼 적용**:
    - 백엔드 서비스 실행 환경의 `sudo` 명령어 탑재 여부와 현재 UID(`os.geteuid()`)를 판별하여, 필요한 경우 `sudo tar` 및 `sudo chown` 명령어로 자동 래핑하여 88GB 원본 데이터가 유실 없이 원본 용량 그대로 안전하게 압축 및 소유권 복구되도록 설계했습니다.
*   **StartupValidator 결과 필터링**:
    - 특정 시장 복구 이후의 자가 진단(StartupValidator) 결과를 호출된 해당 시장 정보만으로 필터링하여 불필요한 시장 정보 노출 및 예외 발생 가능성을 억제했습니다.

### 영향 범위
*   `tdms_core/p4_manager/services/backup_service.py`
*   `tdms_core/p4_manager/routers/manager.py`
*   `tdms_core/p4_manager/tests/test_restore.py`
*   `tdms_core/p4_manager/frontend/src/stores/backupStore.ts`
*   `tdms_core/p4_manager/frontend/src/views/BackupView.vue`
*   `tdms_core/p4_manager/frontend/src/tests/BackupView.spec.ts`

### 관련 링크
*   `backup_api.md` (시장 구분 필드가 적용된 API 규격 명세)

---

## [P4DEC-007] Windows PowerShell 우회 DNS 쿼리 및 Async C클래스 포트 스캔을 통한 서버 IP 자가 갱신 (T-010)

### 배경
*   물리 DB 동기화 파이프라인(`db_sync.py`)은 대용량 파일 전송을 위해 로컬 개발 PC와 원격 서버 PC의 정확한 IP를 `.env` 프로필에서 조회하여 SSH 채널을 수립합니다.
*   그러나 개발 PC나 서버 PC의 재부팅, 또는 DHCP IP 재할당 문제로 인해 IP 불일치가 빈번하게 발생하여 동기화 작업이 멈추거나 실패하는 장애가 발생했습니다.
*   특히 WSL2 환경에서 실행되는 리눅스 커널에서는 윈도우 호스트의 DNS 리졸버와의 브릿지 특성상 서버 호스트명(`SERVER_HOSTNAME`)을 정상 파싱하지 못하는 환경적 결함이 있었습니다.

### 결정 내용
*   **PowerShell 우회 DNS 리졸빙 (DNS Resolution Bypass)**:
    - WSL2 내 리눅스 네트워크 한계를 우회하기 위해, 리눅스 셸에서 `powershell.exe` 서브프로세스를 기동하여 Windows OS Native의 DNS API `[System.Net.Dns]::GetHostAddresses()` 를 우회 쿼리함으로써 원격 서버 IP를 강제 확보하도록 설계했습니다.
*   **비동기 사설 C클래스 포트 스캔 (Async C-Class Port Scanning)**:
    - DNS 리졸브마저 작동하지 않는 극단적 장애 상황에 대비하여, 개발 PC의 로컬 사설 C클래스 대역(`192.168.35.0/24`)에 대해 Port 8000 커넥션을 `asyncio` 기반으로 초고속 동시 스캔하는 자가 치유(Self-Healing) 탐색 루틴을 구축했습니다.
    - 스캔된 후보 호스트에 대해 `/api/mgr/env` GET 요청을 질의하고, 응답에서 `{"env": "server"}`를 식별하여 현재 활성화된 운영 서버의 IP를 동적으로 확정합니다.
*   **원터치 .env 갱신 및 OS Environ 즉시 투영**:
    - 탐색 완료된 IP를 API를 통해 `.env` 파일의 기존 다른 키-값을 훼손하지 않고 정규표현식으로 정밀 치환 기입하도록 하였으며, `os.environ` 값도 즉각 업데이트하여 백엔드 컴포넌트 재기동 없이 네트워크 경로 설정이 핫플러깅되도록 개선했습니다.

### 영향 범위
*   `tdms_core/p4_manager/services/sync_service.py` (우회 DNS 및 비동기 스캔 코어 탑재)
*   `tdms_core/p4_manager/routers/manager.py` (네트워크 및 동기화 제어 엔드포인트 노출)
*   `tdms_core/p4_manager/tests/test_sync_service.py` (비동기 스캔 모의 및 PowerShell 호출 검증용 격리 테스트 추가)
*   `tdms_core/p4_manager/docker-compose.yml` (.env 바인드 마운트 볼륨 매핑)

### 관련 링크
*   `network_api.md` (서버 IP 자동 탐색 및 환경변수 갱신 API 명세)
*   `physical_sync.md` (물리 동기화 및 사전 검증 인터페이스 명세)