---
id: KDMSErr-007
sub_project: p2
severity: critical
status: confirmed
last_seen: Daily-Update-2026-07-22
related: [[pjt_wiki/p2_kdms_wiki/decisions/dec-011_file_persistent_dict_nested_mutation.md]]
---

# [KDMSErr-007] 일일 수집 업데이트 태스크 NameError 발생 및 수집 통계 누락

### 발생 패턴 및 재현 조건
- **환경**: Ubuntu 24.04 LTS (WSL), Python 3.12.13 (tdms_p2_env 가상환경)
- **발생 시점**: 매주 월~금 오후 20시 10분, APScheduler를 통해 `run_daily_update` 태스크가 자동 크론으로 기동되어 완료될 때.
- **재현 방법**:
  1. `daily_task.py`의 `run_daily_update` 수집 루프를 임의 실행함.
  2. 수집 조정자 `DailyTask.run`이 끝난 후 캐시 파일의 `steps` 객체를 구성하려 함.
  3. 로컬 변수 `active_cnt`가 바인딩되지 않아 `NameError`로 크래시 발생.

### 실제 에러 로그 (요약 금지)
```text
[2026-07-22 21:20:05,513] CRITICAL - [daily_update] 일일 수집 태스크 구동 중 오류 발생: name 'active_cnt' is not defined
Traceback (most recent call last):
  File "/app/tdms_core/p2_kdms/tasks/daily_task.py", line 766, in run_daily_update
    "active_count": active_cnt,
                    ^^^^^^^^^^
NameError: name 'active_cnt' is not defined
```

### 원인
- `run_daily_update` 내부에서 일일 수집 작업 통계 데이터를 대시보드 UI에 노출하기 위해 `steps` 상세 구조를 조립하고 있었으나, 해당 변수들(`active_cnt`, `daily_cnt`, `mc_cnt`, `minute_cnt`, `investor_cnt`, `blacklisted_cnt`, `factor_rebuilt`)이 함수 스코프 내에 정의되지 않았습니다.
- 실제 수집 작업을 지휘하는 `DailyTask.run` 메서드는 단지 `{"collected": collected, "failed": failed, "skipped": skipped}` 형태의 기본 키만 반환하고 있어서 세부 단계별 수집 건수를 추출할 방법이 없었습니다.
- 원인 코드 경로: `tdms_core/p2_kdms/tasks/daily_task.py:766`

### 해결법 (필수)
- **해결 절차**:
  1. `DailyTask.run` 내부에 통계 누계 변수들을 추가하고, KIS 마스터 동기화, 일봉 적재, 시가총액 적재, 분봉 적재, 수급 적재가 완료될 때마다 수집 수량을 카운팅하도록 코드를 수정했습니다.
  2. `_collect_daily_minute_data_range` 메서드의 반환 형식을 `int`로 수정하여 적재된 분봉 데이터 총 건수를 반환하게 하여 `minute_count`에 합산했습니다.
  3. `run_daily_update`에서 `DailyTask.run`이 반환한 확장 통계 딕셔너리(`result`)로부터 메트릭 변수들을 안전하게 대입 및 바인딩하도록 수정했습니다.
- **수정된 코드**:
```python
        # daily_task.py 내 DailyTask.run의 반환 방식 확장
        return {
            "collected": collected,
            "failed": failed,
            "skipped": skipped,
            "active_count": len(active_stocks) if active_stocks else 0,
            "new_listings": new_listings,
            "delistings": delistings,
            "ticker_changes": ticker_changes,
            "daily_ohlcv_count": daily_ohlcv_count,
            "market_cap_count": market_cap_count,
            "minute_count": minute_count,
            "investor_count": investor_count,
            "blacklisted_count": len(blacklisted_stocks) if blacklisted_stocks else 0,
            "adjusted_factor_count": adjusted_factor_count,
            "factor_rebuilt_count": factor_rebuilt_count,
        }

        # run_daily_update 내부 바인딩 부분 추가
        active_cnt = result.get("active_count", 0)
        daily_cnt = result.get("daily_ohlcv_count", 0)
        mc_cnt = result.get("market_cap_count", 0)
        minute_cnt = result.get("minute_count", 0)
        investor_cnt = result.get("investor_count", 0)
        blacklisted_cnt = result.get("blacklisted_count", 0)
        factor_rebuilt = result.get("factor_rebuilt_count", 0)
```

### 발생 이력
- 2026-07-22 21:20:05 자동 수집 중 최초 발생 및 보고됨.
