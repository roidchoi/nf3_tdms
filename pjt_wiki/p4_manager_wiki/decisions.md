# Sub Project 기술 의사결정 (decisions.md)

> **Sub Project**: p4_manager  
> **범위**: 이 Sub Project 내부에만 영향을 미치는 결정  
> **마지막 업데이트**: 2026-06-09 (T-001 완료)

---

## 사용 지침

전체 시스템에 영향을 미치는 결정은 `parent_wiki/decisions.md`에 기록. 이 파일은 이 Sub Project 내부 결정만 다룬다.

---

## 의사결정 목록

| ID | 제목 | Task | 상태 |
|---|---|---|---|
| P4DEC-001 | Nginx 동적 Upstream 리졸브 및 변수 기반 프록시 패스 적용 | T-001 | active |
| P4DEC-002 | 백그라운드 캐싱 폴링 기법 및 실시간 API 장애 격리(Fault Isolation) 레이어 적용 | T-002 | active |

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