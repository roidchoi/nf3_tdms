# [USDMS-ERR-005] APScheduler misfire_grace_time 미지정으로 인한 스케줄러 트리거 누락

- **분류**: USDMS 에러
- **Severity**: High
- **발생 Task ID**: T-111 (스케줄링 고도화)
- **Context Link**: `tdms_core/p3_usdms/main.py`

## 1. 현상
- 수요일 아침(7월 1일) USDMS 수집 스케줄(`wed,sat:07:30`)이 예정된 한국 시간 07:30(UTC 22:30)에 정상 트리거되지 않고 작동이 스킵되는 현상이 발생했습니다. 사용자가 결국 매니저 페이지 혹은 수동 트리거로 작업을 실행해야 했습니다.

## 2. 원인
1. **컨테이너 지터 및 이벤트 루프 지연**:
   수요일 KST 07:30:00 정각에 작업을 가동하는 과정에서, 백엔드 컨테이너의 이벤트 루프 지연 혹은 API 호출 폴링 처리 등으로 인해 실제 트리거 타임이 **1.32초** 늦어지는 현상이 발생했습니다.
   * `p3_usdms` 컨테이너 로그 분석 결과:
     ```
     2026-06-30T22:30:01.329129861Z WARNING:apscheduler.executors.default:Run time of job "scheduled_daily (trigger: cron[day_of_week='wed,sat', hour='7', minute='30'], next run at: 2026-07-04 07:30:00 KST)" was missed by 0:00:01.327872
     ```
2. **misfire_grace_time 설정 누락**:
   `p3_usdms` 백엔드 진입점인 `main.py`에서 `AsyncIOScheduler`를 생성할 때 `job_defaults` 내에 유예 시간 설정이 누락되어 있었습니다. 이로 인해 APScheduler 기본 지연 한계값(1초)을 약간이라도 초과하는 찰나의 지터(1.32초)가 발생하자 스케줄러가 작업을 통째로 스킵("misfired") 처리했습니다. (반면, KDMS는 이미 `misfire_grace_time: 900`인 15분 유예가 설정되어 있어 누락이 없었습니다.)

## 3. 해결책 및 추가 조치 (15분 유예 및 동시 실행 충돌 방지 도입)
- 개발 PC나 WSL 환경의 특성상 절전 모드(sleep) 진입이 빈번하여, 시스템 복귀 시각에 15분 한계를 가뿐히 초과해 `misfired`로 통째로 스킵되는 현상이 재발했습니다.
- 그러나 단순히 허용 지연 시간(`misfire_grace_time`)을 지나치게 길게(예: 1시간 또는 10시간) 가져가면, 절전 모드 해제 시점에 밀린 수집 일정이 원치 않는 때에 대거 활성화되어 DB 락 경합 등 동시 실행 충돌을 유발하거나 데이터 수집의 정합성을 훼손하는 리스크가 발생합니다.
- 이를 해결하기 위해 `tdms_core/p3_usdms/main.py` 및 `tdms_core/p2_kdms/main.py`에서 유예 시간을 찰나의 지터는 허용하되 과도한 지연 기동을 배제하는 **15분(900초)**으로 최종 조정하고, 아래와 같은 동시성 보호 정책을 추가 적용했습니다.
  - `coalesce: True`: 동일 작업이 절전 상태 등으로 인해 여러 번 밀린 경우, 중복 실행하지 않고 **오직 최근 1건만 병합하여 실행**합니다.
  - `max_instances: 1`: 동일한 작업이 동시에 2개 이상 활성화되지 않도록 철저히 제어하여 레이스 컨디션을 예방합니다.
  ```python
  # APScheduler 기동 및 태스크 등록
  scheduler = AsyncIOScheduler(
      timezone="Asia/Seoul",
      job_defaults={
          "misfire_grace_time": 900,   # 15분 유예 (찰나의 지터는 허용하고 과도한 지연 기동은 방지)
          "coalesce": True,            # 동일 작업 누적 시 1회만 병합 실행
          "max_instances": 1           # 중복 동시 실행 철저 제한
      }
  )
  ```
  이로써 찰나의 지터를 안정적으로 수용하는 동시에, 불필요한 지연 자동 실행으로 인한 리소스 병목 및 정합성 리스크를 차단하였습니다.

## 4. 검증 결과
- 수정 후 `pytest` 유닛 테스트를 통해 스케줄 설정 변경 이후에도 APScheduler의 job 추가 기능에 영향이 없음을 로컬에서 전원 검증 통과했습니다.
- 원격 운영 서버 PC에 변경 사항을 배포(`scp/rsync`)하고, `docker compose up -d --build`를 실행하여 컨테이너 이미지를 재빌드 및 재부팅하여 정상 배포를 마무리했습니다.
