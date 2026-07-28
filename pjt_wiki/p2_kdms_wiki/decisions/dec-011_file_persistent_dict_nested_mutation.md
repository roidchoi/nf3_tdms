# [DEC-011] FilePersistentDict 중첩 딕셔너리 변경 시 캐시 저장 보장 패턴 (KDMS)

## Status
- **상태**: Approved ✅
- **결정일**: 2026-07-22
- **작성자**: Antigravity

---

## 1. 맥락 (Context)
- KDMS 백필 태스크(`backfill_task.py`)를 수행할 때 작업 상태 캐싱을 위해 `FilePersistentDict`를 상속받은 `job_statuses` 객체를 사용하고 있었음.
- 백필 3자 검증 프로세스 실행 도중 중첩된 딕셔너리 구조(예: `job_statuses[job_id]["steps"]` 리스트 또는 상세 결과 값) 내부에 직접 수치를 대입하거나 수정할 경우, `FilePersistentDict`가 내부적으로 감지하는 키 수준의 마법 메서드(`__setitem__`) 호출이 발생하지 않아 캐시 파일이 실제로 디스크에 저장되지 않고 유실되는 현상이 발생함.
- 이로 인해 백필 연산 도중 에러가 나거나 세션이 끝난 뒤에 3자 검증 상세 결과(`discrepancy`, `rebuilt` 종목 등)가 대시보드 UI에 반영되지 못하고 증발해 버리는 문제를 해결해야 했음.

---

## 2. 결정 사항 (Decision)
- **명시적 재할당 패턴 강제**:
  - `job_statuses`의 내부 딕셔너리 데이터를 수정할 때는, 원본 딕셔너리에서 데이터를 꺼내와 조작한 뒤에 최종적으로 `job_statuses[job_id] = <수정된 딕셔너리>` 형태로 **키 수준의 재할당을 명시적으로 실행**한다.
  - 이 패턴을 통해 `FilePersistentDict.__setitem__` 이 의도적으로 호출되어 디스크에 캐시가 자동 커밋되도록 보장한다.

---

## 3. 구현 내용 (Implementation)
- `tdms_core/p2_kdms/tasks/backfill_task.py` 파일의 상태 저장 로직 수정:
  ```python
  # 1. 딕셔너리 데이터를 로컬로 가져와 조작
  status_dict = job_statuses.get(job_id, {})
  status_dict.update({
      "is_running": False,
      "last_status": "success",
      "steps": steps, # 상세 3자 검증 데이터 (Discrepancy, Rebuilt 등) 포함
      "end_time": datetime.now(KST).isoformat(),
  })
  
  # 2. 명시적으로 최상위 키에 재할당하여 디스크 동기화 유도 (핵심)
  job_statuses[job_id] = status_dict
  ```

---

## 4. 결과 및 영향 (Consequences)
- **장점**:
  - `FilePersistentDict` 내부의 디스크 저장 함수(`_save()`)가 무조건 보장되어 3자 검증 세부 통계 메트릭이 누락 없이 대시보드 UI에 표시됨.
  - 복잡한 프레임워크나 저장 메커니즘을 뜯어고칠 필요 없이, 순수 파이썬의 사전 객체 바인딩 특성만을 이용하여 안전하고 가볍게 해결할 수 있음.
- **주의 사항**:
  - 중첩 딕셔너리를 다룰 때는 `job_statuses[job_id]["some_key"] = value`와 같이 직접 접근하여 변경하면 `_save`가 발동되지 않으므로, 반드시 `status_dict` 전체를 최상위 키 수준에서 덮어쓰는 패턴을 견지해야 함.

---
## 관련 엔티티
- [[pjt_wiki/p2_kdms_wiki/errors/err-007_run_daily_update_name_error_metric_tracking.md]]
