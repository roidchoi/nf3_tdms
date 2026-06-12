# [P4-ERR-005] 통합 관리자 KDMS 스케줄러 조회 시 404 Not Found 에러

> **분류**: 백엔드 라우팅 정합성  
> **장애 심각도**: Medium (특정 탭 데이터 로딩 실패)  
> **최초 발생일**: 2026-06-12  

---

## 1. 장애 증상 및 원인 분석

### 1) 장애 증상
* 통합 관리자 대시보드 UI의 "스케줄 및 크론" 탭에서 **대한민국 (KDMS)** 서브 탭을 클릭했을 때, 스케줄러 정보 카드가 로딩되지 않고 화면에 백그라운드 404 에러 팝업이 발생하는 현상.
* US 미국 (USDMS) 탭은 정상 작동하는 반면, KR 탭 진입 시에만 `KR 백엔드 스케줄러 조회 오류: {"detail":"Not Found"}` 응답(502/404)이 검출됨.

### 2) 발생 원인
* **라우팅 접두사(Prefix) 불일치**:
  * `p2_kdms` 한국 주가 수집 백엔드의 라우터 선언부인 `tdms_core/p2_kdms/routers/admin.py` 내부에서 `APIRouter(prefix="/tasks")` 로 접두사가 기입되어 마운트되어 있었습니다.
  * 결과적으로 실제 스케줄러 API 엔드포인트의 최종 URI 경로는 `http://p2_kdms:8000/api/v1/admin/tasks/scheduler` 가 되었습니다.
  * 그러나 이를 프록시 중계 호출하는 `p4_backend` 측의 [manager.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/routers/manager.py) 에서는 중간 접두사 `/tasks` 가 빠진 채로 `http://p2_kdms:8000/api/v1/admin/scheduler` 주소를 하드코딩 쿼리하여 하위 백엔드로부터 `404 Not Found` 응답을 전달받았습니다.

---

## 2. 해결 및 조치 방법

### 1) 프록시 URI 주소 보정
통합 관리자 API 라우터 소스 코드 내에서 `p2_kdms` 를 가리키는 모든 스케줄 관련 URI 엔드포인트(조회, 시간 변경, 토글 제어)에 `/tasks` 경로를 수동으로 삽입하였습니다.

* **수정 대상 파일**: `tdms_core/p4_manager/routers/manager.py`
* **주요 변경 사항**:
  ```python
  # 1. 스케줄 정보 조회 URI 수정
  url = "http://p2_kdms:8000/api/v1/admin/tasks/scheduler" if market == "kr" ...

  # 2. 기동 시간 수정 URI 수정
  url = f"http://p2_kdms:8000/api/v1/admin/tasks/scheduler?job_id={job_id}..."

  # 3. 크론 활성/비활성 토글 URI 수정
  url = f"http://p2_kdms:8000/api/v1/admin/tasks/scheduler/{job_id}/toggle?action={action}"
  ```

### 2) 도커 컨테이너 이미지 재빌드
수정된 소스 코드를 구동 중인 도커 오케스트레이션 망에 반영하기 위해 컨테이너 리빌드 및 재배포를 수행합니다.
```bash
# p4_backend 컴포즈 서비스 리빌드 및 데몬 재기동
docker compose build p4_backend && docker compose up -d p4_backend
```

---

## 3. 재발 방지 대책

* **엔드포인트 연동 정합성 사전 검사 도입**:
  * 각 마이크로서비스 간의 통신 URI가 정합성을 가지는지 통합 테스트 스위트(`tests/test_scheduler_bridge.py` 등)의 테스트 커버리지를 보강하여 빌드 배포 전 단계에서 주소 매핑 오류를 자동으로 포착하도록 구성합니다.
* **REST API 사양 문서의 버전 관리 일원화**:
  * 마이크로서비스들의 API 엔드포인트가 리팩토링이나 구조 조정으로 변경될 시, 반드시 통합 위키 지식과 타 모듈의 프록시 래퍼에 동시 반영되도록 릴리즈 체크리스트를 준수합니다.
