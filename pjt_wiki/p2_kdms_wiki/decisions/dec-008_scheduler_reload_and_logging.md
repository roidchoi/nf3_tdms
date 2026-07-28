# [P2DEC-008] KDMS 스케줄러 동적 리로드 및 진행률 로깅 개선

> **Sub Project**: p2_kdms
> **Status**: active
> **Date**: 2026-07-09
> **Task**: —
> **관련**: `[[p2_kdms_wiki/interfaces/admin_api.md]]`, `[[p2_kdms_wiki/codebase_map.md]]`

---

## 배경

1. **일일 업데이트 시 가시성 부재**: KDMS 일일 업데이트(`daily_update`) 기동 시, 벌크 일괄 저장 아키텍처 도입으로 인해 수집 도중 로그 출력이 없고 완료율 변화가 없어 기동 여부의 모니터링이 불가능했습니다.
2. **요일 세부 지정 한계**: 스케줄 관리 UI에서 크론 수정 시 시간 단위만 조율 가능하여, 특정 요일에만 실행하도록 요일(`day_of_week`)을 동적으로 설정하지 못하는 한계가 있었습니다.
3. **도커 이미지 재빌드 부하**: `.env` 설정 갱신 또는 크론 일정 변경 시 도커 이미지를 재빌드하거나 컨테이너를 재시작하지 않고 메모리에 동적으로 스케줄을 재로드할 수 있는 방안이 부재했습니다.

---

## 결정 내용

### 1. tqdm 제거 및 logger.info 기반 정밀 진행상황 로깅
* **구현**: tqdm 라이브러리가 유발하는 비표준 스트림 출력(stderr)과 파일 적재 시의 비정상 로그 팽창을 원천 배제하고자, tqdm을 완전히 제거하고 수동/스케줄러 기동 시 모두 호환되는 **순수 `logger.info` 기반의 실시간 progress 로거**로 전면 전환했습니다.
* **로그 출력**: 50개 종목 주기마다 `[진행률 %, 속도 (it/s), 경과시간 (Elapsed), 예상완료시간 (ETA), 현재 수집중인 종목]` 형태의 INFO 로그를 정밀 포맷팅하여 파일 및 웹소켓으로 유실 없이 안정적으로 스트리밍합니다.

### 2. .env 강제 재로드를 통한 무중단 스케줄 리로드 API
* **API 추가**: `.env` 파일 물리 쓰기 이후 이를 동적으로 반영하기 위해 `POST /api/v1/admin/tasks/scheduler/reload` 엔드포인트를 추가했습니다.
* **로직**: `dotenv.load_dotenv(override=True)`를 강제 호출하여 캐시된 Pydantic Settings와 `os.environ` 환경변수를 오버라이드하고, APScheduler 스케줄러에 등록된 크론 트리거를 메모리 상에서 동적으로 재구성합니다.

### 3. day_of_week 스케줄 파라미터 제어
* `PUT /api/v1/admin/tasks/scheduler` 스케줄 일정 변경 API에 `day_of_week` 쿼리 매개변수를 추가하여 시간 외에 특정 요일 설정(예: `mon-fri`, `wed,sat` 등)도 크론 트리거에 동적 바인딩할 수 있도록 확장했습니다.

### 4. misfire_grace_time 15분(900초) 롤백 지정 (신규 추가)
* **배경**: 개발 PC 환경(WSL/Ubuntu) 절전 모드 복귀 시, 누적 지연된 수집 스케줄이 일시에 무차별 기동되면서 DB 커넥션 병목 및 중복 연산 충돌을 유발했습니다.
* **방침**: 과도한 자동 유예(과거 수시간) 기동을 원천 통제하기 위해, APScheduler `misfire_grace_time`을 **15분(900초)**으로 복원 롤백했습니다. 찰나의 지터나 몇 초간의 컨테이너 기동 지연은 극복하되 수시간 밀린 스케줄은 강제 스킵 처리하여 데이터 유실 및 동시 충돌 리스크를 전면 방어합니다.

---

## 영향 범위

* `tdms_core/p2_kdms/tasks/daily_task.py` (tqdm 제거 및 정밀 로깅 반영)
* `tdms_core/p2_kdms/main.py` (misfire_grace_time 900초 적용 및 로그 중복 제거)
* `tdms_core/p2_kdms/routers/admin.py` (reload 스케줄 API 신설 및 파라미터 확장)
* `tdms_core/p1_shared/p1_shared/utils/schedule_utils.py` (물리 .env 파싱 헬퍼 활용)

---

## 대안 검토

| 대안 | 거부 이유 |
|---|---|
| 주기적인 Docker 컨테이너 재시작 | 실행 중인 수집/연산 배치 프로세스가 중단될 수 있으며, 재부팅에 따른 가용성 손실이 생김 |
| tqdm 라이브러리 직접 활용 | 비동기 백그라운드 태스크 내부에서 표준 출력 리다이렉션으로 인해 로거(Logger) 파일에 진행률 그래프 문자열이 비정상적으로 누적되어 로그 파일 크기가 비대해짐 |

