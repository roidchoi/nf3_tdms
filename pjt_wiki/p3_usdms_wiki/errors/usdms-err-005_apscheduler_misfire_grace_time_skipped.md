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

## 3. 해결책
- `tdms_core/p3_usdms/main.py` (및 KDMS `main.py`)에서 스케줄러를 선언하는 부분을 다음과 같이 교정하여 **15분(900초)**의 유예 폭을 보장하도록 수정했습니다. (처음에는 10시간으로 설정했으나 장중 리소스 경합 및 중복 실행의 사이드 이펙트를 차단하기 위해 15분으로 최종 하향 조정했습니다.)
  ```python
  # 3. APScheduler 기동 및 태스크 등록
  scheduler = AsyncIOScheduler(
      timezone="Asia/Seoul",
      job_defaults={
          "misfire_grace_time": 900  # 15분 유예 (지터 및 기동 지연으로 인한 스케줄 누락 방지)
      }
  )
  ```
  이를 통해 컨테이너 지터나 임시 시스템 부하 등으로 인한 스케줄 누락 문제를 원천적으로 방지하면서도, 너무 늦게 기동되어 거래 시간 및 마감 데이터에 부정적인 영향을 미치는 문제를 차단합니다.

## 4. 검증 결과
- 수정 후 `pytest` 유닛 테스트를 통해 스케줄 설정 변경 이후에도 APScheduler의 job 추가 기능에 영향이 없음을 로컬에서 전원 검증 통과했습니다.
- 원격 운영 서버 PC에 변경 사항을 배포(`scp/rsync`)하고, `docker compose up -d --build`를 실행하여 컨테이너 이미지를 재빌드 및 재부팅하여 정상 배포를 마무리했습니다.
