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

### 2차 고도화 (2026-07-23 UI 품질 요약 데이터 왜곡 정밀 보정)
- **현상**: P4 대시보드 품질 요약 탭에서 `Master Sync` 신규 상장 수가 4,313개(전체 KIS 마스터 수량)로 표시되고, `Market Data Loader` 시세/시총 수집 수가 15,660종목(4개 거래일치 총 레코드 Row 수)으로 엉뚱하게 왜곡되어 표출됨.
- **원인 및 조치**:
  1. `new_listings`를 KIS API 전체 개수(`len(master_records)`)가 아닌 `prev_shares_map` 미존재 신규 종목 수로 카운팅하도록 보정.
  2. `daily_ohlcv_count` 및 `market_cap_count`에 총 레코드 건수가 아닌 **실제 수집 처리된 독자 종목 수 (Distinct Stock Count: 약 3,923개)**를 대입하여 UI 표출 정합성 확보.
  3. `steps` 내 각 Step별 `duration_seconds` 측정 코드를 추가하여 UI에 각 단계별 소요 시간이 실시간 표출되도록 완수.

### 3차 고도화 (2026-07-23 수급 수집 타겟 3,920개 확대 및 폭풍 로그 제거)
- **현상**: P4 대시보드에서 `Market Data Loader` 단계의 `수급: 2399` 수치가 전체 활성 종목(3,920개)이 아닌 분봉 백필 타겟(2,399개)으로 엉뚱하게 묶여 출력되고, 종목별 벌크 UPSERT 완료 로그가 매번 INFO로 수천 번 남는 로그 폭풍 발생.
- **원인 및 조치**:
  1. `investor_trade_repo.py:get_active_symbols_for_date()` 쿼리를 `minute_target_history`가 아닌 `stock_info` 테이블의 `status = 'listed'` 전체 활성 상장 종목(약 3,920개)을 반환하도록 정비하여 대시보드 표출 `수급: 3920` 정합성 완수.
  2. `investor_trade_repo.py` 내의 종목별 `logger.info`를 `logger.debug`로 격하하여 무의미한 연쇄 로그를 제거하고, 50종목 단위의 실시간 진행률 전용 로그(Progress %, Speed, ETA)만 깔끔하게 출력되도록 로깅 시스템 최적화 완료.

### 발생 이력
- 2026-07-22 21:20:05 자동 수집 중 최초 발생 및 보고됨.
- 2026-07-23 21:35:00 2차 품질 요약 집계 데이터왜곡 정밀 보정 및 도커 배포 완료.
- 2026-07-23 23:22:00 3차 수급 수집 타겟 전체 활성 종목(3,920개) 정상화 및 폭풍 로그 제거 완료.
