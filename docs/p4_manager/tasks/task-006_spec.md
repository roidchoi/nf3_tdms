# Task-006 구현 명세서: 공통 헬스 모니터링 및 시장별 특화 패널

## 1. 개요 및 목적
본 태스크는 한국 시장(`p2_kdms`)과 미국 시장(`p3_usdms`)의 수집 신선도(Freshness), 데이터 갭(Gaps), 그리고 시장 특화 메타데이터(KR 마일스톤, US 블랙리스트)를 오케스트레이션 레이어인 P4에서 통합 조회 및 제어할 수 있는 모니터링 체계를 구축합니다. 
특히 미국 시장의 수집 실패 블랙리스트 CIK 차단 해제 API를 USDMS 및 P4 매니저에 신설하고, 프론트엔드에서는 다크 글래스모피즘 테마의 통합 헬스 대시보드 화면(`HealthView`) 및 특화 컴포넌트 2종을 구현합니다.

---

## 2. 위키 선조회 결과

| 확인 구분 | 대상 항목 | 확인 경로 / 출처 | 상태 |
|---|---|---|---|
| **기존 파일 및 API** | `p2_kdms/routers/health.py` | `GET /api/health/freshness`, `GET /api/health/gaps`, `GET/POST /api/health/milestones` | 확인 완료 |
| **기존 파일 및 API** | `p3_usdms/routers/health.py` | `GET /api/health/freshness`, `GET /api/health/gaps`, `GET /api/health/blacklist` | 확인 완료 |
| **기존 클래스** | `p3_usdms.repositories.blacklist_repo.BlacklistRepo` | `release_blacklist(self, cik: str, admin_note: str)` 함수 | 확인 완료 |
| **신규 API** | `p3_usdms/routers/health.py` | `POST /api/health/blacklist/{cik}/release` | 설계/신설 예정 |
| **신규 중계 API** | `p4_manager/routers/manager.py` | `/api/mgr/health/freshness/{market}`, `/api/mgr/health/gaps/{market}`, `/api/mgr/health/kr/milestones`, `/api/mgr/health/us/blacklist`, `/api/mgr/health/us/blacklist/{cik}/release` | 설계/신설 예정 |
| **신규 프론트엔드** | `p4_manager/frontend` | `healthStore.ts`, `HealthView.vue`, `MilestoneTimeline.vue`, `BlacklistPanel.vue` | 설계/신설 예정 |

---

## 3. 기능 요구사항 및 스펙

### (1) 미국 시장 백엔드 (`p3_usdms`) 블랙리스트 차단 해제 API 신설
* **엔드포인트**: `POST /api/health/blacklist/{cik}/release`
* **동작**: `BlacklistRepo.release_blacklist(cik)`를 호출하고 누적 실패 횟수(fail_count)를 0으로 초기화한 뒤 `is_blocked = FALSE`로 업데이트합니다.

### (2) P4 통합 백엔드 (`p4_manager`) 중계 API 5종 및 장애 격리
P4 매니저 백엔드(`tdms_core/p4_manager/routers/manager.py`)에 다음 API를 구현합니다:
1. **데이터 신선도 중계**: `GET /api/mgr/health/freshness/{market}`
   * `market == 'kr'`: `http://p2_kdms:8000/api/health/freshness` 중계
   * `market == 'us'`: `http://p3_usdms:8000/api/health/freshness` 중계
2. **누락 갭 중계**: `GET /api/mgr/health/gaps/{market}`
   * `market == 'kr'`: `http://p2_kdms:8000/api/health/gaps` 중계 (쿼리 파라미터 `start_date`, `end_date` 전달)
   * `market == 'us'`: `http://p3_usdms:8000/api/health/gaps` 중계 (쿼리 파라미터 `start_date`, `end_date` 전달)
3. **한국 마일스톤 조회/등록 중계**:
   * `GET /api/mgr/health/kr/milestones` -> `http://p2_kdms:8000/api/health/milestones` 중계
   * `POST /api/mgr/health/kr/milestones` -> `http://p2_kdms:8000/api/health/milestones` 중계 (바디 전달)
4. **미국 블랙리스트 조회 중계**: `GET /api/mgr/health/us/blacklist`
   * `http://p3_usdms:8000/api/health/blacklist` 중계
5. **미국 블랙리스트 차단 해제 중계**: `POST /api/mgr/health/us/blacklist/{cik}/release`
   * `http://p3_usdms:8000/api/health/blacklist/{cik}/release` 중계 (신설된 미국 백엔드 API 호출)

> **장애 격리 (Fault Isolation) 규격**
> 대상 백엔드 서버가 다운(오프라인)되거나 통신 중 타임아웃/오류가 발생하면, API 500 에러를 전파하지 않고 **`{"status": "RED", "offline": true, "message": "Market backend offline"}`** 포맷의 응답을 반환하여 격리합니다.

### (3) 갭 검출 응답 스키마 정규화 (Normalization)
중계 API(`GET /api/mgr/health/gaps/{market}`)는 클라이언트가 일관되게 처리할 수 있도록 응답 형식을 아래와 같이 표준 구조로 가공하여 반환합니다:
```json
{
  "market": "kr",
  "start_date": "2026-06-03",
  "end_date": "2026-06-03",
  "gaps": [
    {
      "date": "2026-06-03",
      "status": "GREEN",
      "total_targets": 2000,
      "valid_targets": 1985,
      "missing_count": 0,
      "missing_items": []
    }
  ]
}
```
* **한국 마켓 매핑**: `total_targets` = total_targets, `valid_targets` = valid_targets, `missing_count` = missing_stocks_count, `missing_items` = missing_stocks
* **미국 마켓 매핑**: `total_targets` = total_targets, `valid_targets` = valid_targets, `missing_count` = gaps_count, `missing_items` = [] (미국 백엔드는 티커 목록을 응답하지 않으므로 빈 배열)

### (4) 프론트엔드 설계
1. **`healthStore.ts`**:
   * 한국/미국 신선도, 갭 이력, 마일스톤 목록, 블랙리스트 목록 상태 관리.
   * `fetchFreshness(market)`, `fetchGaps(market, start, end)`, `fetchMilestones()`, `createMilestone()`, `fetchBlacklist()`, `releaseBlacklist(cik)` 비동기 액션 구현.
2. **`HealthView.vue`**:
   * 상단에 한국/미국 주식 시장별 '신선도 요약 카드' 2개를 배치 (오프라인 시 그레이아웃 필터 및 오프라인 알림 표시).
   * 하단에 '한국 시장 모니터링', '미국 시장 모니터링' 탭 메뉴 구성.
3. **`MilestoneTimeline.vue` (한국 탭)**:
   * 수집/운영 마일스톤 이력을 세로 타임라인 레이아웃으로 표현.
   * 우측 상단에 "마일스톤 등록" 버튼 배치, 클릭 시 폼 모달 오픈 및 등록 연동.
4. **`BlacklistPanel.vue` (미국 탭)**:
   * 차단된 미국 CIK 및 사유 목록을 테이블 또는 그리드로 표출.
   * 각 행마다 "차단 해제" 버튼 배치. 클릭 시 더블 컨펌 창을 띄운 뒤 `releaseBlacklist(cik)` API를 연동하여 목록을 갱신.

---

## 4. 테스트 케이스 요약

### (1) 백엔드 테스트 케이스 (`pytest`)

| 테스트 파일 | 테스트 케이스명 | 계층 | 검증 목적 |
|---|---|---|---|
| `tests/test_health_bridge.py` | `test_get_integrated_freshness_kr_success` | Tier 2 | 한국 신선도 조회 중계 성공 검증 |
| `tests/test_health_bridge.py` | `test_get_integrated_freshness_us_success` | Tier 2 | 미국 신선도 조회 중계 성공 검증 |
| `tests/test_health_bridge.py` | `test_get_integrated_freshness_offline_fallback` | Tier 2 | 대상 백엔드 중단 시 503 전파 없이 offline 응답 격리 반환 검증 |
| `tests/test_health_bridge.py` | `test_get_integrated_gaps_kr_success` | Tier 2 | 한국 갭 조회 중계 및 정규화(gaps.missing_items) 매핑 검증 |
| `tests/test_health_bridge.py` | `test_get_integrated_gaps_us_success` | Tier 2 | 미국 갭 조회 중계 및 정규화(gaps.missing_count) 매핑 검증 |
| `tests/test_health_bridge.py` | `test_get_kr_milestones_success` | Tier 2 | 한국 마일스톤 조회 중계 성공 검증 |
| `tests/test_health_bridge.py` | `test_post_kr_milestone_success` | Tier 2 | 한국 마일스톤 등록 중계 성공 검증 |
| `tests/test_health_bridge.py` | `test_get_us_blacklist_success` | Tier 2 | 미국 블랙리스트 조회 중계 성공 검증 |
| `tests/test_health_bridge.py` | `test_release_us_blacklist_success` | Tier 2 | 미국 CIK 차단 해제 중계 성공 검증 |
| `tests/test_health_auditors.py` | `test_usdms_release_blacklist_endpoint` | Tier 2 | `p3_usdms` 백엔드 자체에 구현한 차단 해제 API 엔드포인트의 리포지토리 연동 검증 |

### (2) 프론트엔드 테스트 케이스 (`vitest`)

| 테스트 파일 | 테스트 케이스명 | 계층 | 검증 목적 |
|---|---|---|---|
| `stores/healthStore.spec.ts` | `fetchFreshness updates store states` | Tier 2 | 신선도 fetch API 호출 시 스토어 변수 정상 업데이트 검증 |
| `stores/healthStore.spec.ts` | `releaseBlacklist calls api and refreshes` | Tier 2 | unblock CIK API 호출 후 블랙리스트 리스트가 갱신되는지 검증 |
| `stores/healthStore.spec.ts` | `offline state sets true on network fail` | Tier 2 | 백엔드 통신 오류 시 `offline` 상태 플래그 활성화 검증 |
| `components/MilestoneTimeline.spec.ts` | `renders milestones in timeline order` | Tier 2 | 마일스톤 배열 데이터가 연도/일자 순서대로 정확히 그려지는지 렌더링 검증 |
| `components/BlacklistPanel.spec.ts` | `clicking release triggers confirmation and api` | Tier 2 | 차단 해제 클릭 시 확인 팝업 등장 및 승인 시 스토어 액션이 올바르게 호출되는지 검증 |

---

## 5. 상세 테스트 코드 명세 (유도력 확보)

### (1) 백엔드 중계 및 격리 테스트 (`tests/test_health_bridge.py` 초안)
```python
import pytest
from fastapi.testclient import TestClient

def test_get_integrated_freshness_offline_fallback(client_with_mocks, respx_mock):
    """
    [Tier 2 - 격리 통합]
    [목적] 한국 백엔드는 정상 작동하나 미국 백엔드가 500 또는 Connection Error를 일으킬 때,
           오류를 전파하지 않고 {"status": "RED", "offline": true} 포맷의 장애 격리 처리가 작동함을 검증.
    """
    respx_mock.get("http://p2_kdms:8000/api/health/freshness").respond(
        200, json={"status": "GREEN", "latest_trading_date": "2026-06-08", "is_daily_fresh": True}
    )
    # 미국 백엔드는 커넥션 에러 시뮬레이션
    respx_mock.get("http://p3_usdms:8000/api/health/freshness").respond(503)

    response_kr = client_with_mocks.get("/api/mgr/health/freshness/kr")
    assert response_kr.status_code == 200
    assert response_kr.json()["status"] == "GREEN"
    assert response_kr.json().get("offline") is not True

    response_us = client_with_mocks.get("/api/mgr/health/freshness/us")
    assert response_us.status_code == 200
    assert response_us.json()["status"] == "RED"
    assert response_us.json()["offline"] is True
```

### (2) 미국 백엔드 차단 해제 자체 검증 (`tests/test_health_auditors.py` 또는 `test_health.py` 내 추가)
```python
def test_usdms_release_blacklist_endpoint(client, mocker):
    """
    [Tier 2 - 격리 통합]
    [목적] USDMS 백엔드에 추가될 POST /api/health/blacklist/{cik}/release API가 
           BlacklistRepo.release_blacklist를 올바르게 호출하는지 검증.
    """
    mock_release = mocker.patch("p3_usdms.repositories.blacklist_repo.BlacklistRepo.release_blacklist")
    
    response = client.post("/api/health/blacklist/0000320193/release")
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    mock_release.assert_called_once_with("0000320193", admin_note="Released via P4 Manager Dashboard")
```

---

## 6. 구현 시 주의사항 및 예외 흐름

1. **미국 CIK 10자리 패딩 처리**:
   * 블랙리스트 해제 요청 시 CIK는 반드시 10자리(예: `320193` -> `0000320193`)로 문자열 패딩하여 리포지토리에 넘겨야 매칭 누락이 발생하지 않습니다.
2. **날짜 범위 유효성 예외**:
   * `GET /api/mgr/health/gaps/{market}` API 호출 시 `start_date` 및 `end_date`가 누락된 경우, 오늘 날짜(`date.today()`)로 기본값을 보완해 중계해야 합니다.
3. **글래스모피즘 테마 및 미크로 인터랙션**:
   * `backdrop-filter: blur(12px)` 및 반투명 테두리를 일관되게 활용합니다.
   * 마일스톤 추가 모달 폼 전송 시, 저장하는 동안 버튼에 스피너 로딩 표시를 두어 사용자의 이중 기동을 물리적으로 방지합니다.
