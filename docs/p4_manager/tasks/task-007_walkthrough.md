# T-007 데이터 익스플로러 테이블 동적 미리보기 구현 Walkthrough

## 1. 구현 파일 목록 및 역할

### [백엔드 (FastAPI)]
* **`tdms_core/p4_manager/routers/manager.py`** (수정)
  * 각 시장별 조회 허용 테이블 화이트리스트 상수(`ALLOWED_TABLES_KR`, `ALLOWED_TABLES_US`) 선언.
  * `GET /api/mgr/preview/meta` 엔드포인트를 구현하여 시장별 영문 테이블 및 한글 표시명 반환.
  * `GET /api/mgr/preview/{market}/{table}` 엔드포인트를 구현하여 하위 백엔드(`p2_kdms`, `p3_usdms`)로 쿼리 필터를 전송 및 중계.
  * 통신 장애 발생 시 `try-except`로 오류를 잡아 정규화된 오프라인 폴백 객체(`offline: true`)를 반환하는 장애 격리(Fault Isolation) 설계 반영.

### [프론트엔드 (Vue 3 / TypeScript)]
* **`tdms_core/p4_manager/frontend/src/stores/explorerStore.ts`** (신규)
  * 데이터 탐색기에 필요한 상태(metadata, 선택 시장, 테이블, 필터, loading, isOffline, tableData 등) 관리.
  * 메타데이터 조회(`fetchMetadata`), 데이터 중계 API 조회(`fetchPreviewData`) 및 필터 제어 액션들 구현.
* **`tdms_core/p4_manager/frontend/src/views/ExplorerView.vue`** (신규)
  * HSL 다크 테마 및 Glassmorphism 디자인 가이드를 반영한 DB 테이블 동적 데이터 미리보기 화면.
  * 동적 컬럼 렌더링 (`Object.keys(tableData[0])` 파싱) 및 스켈레톤 로딩 로더 애니메이션 적용.
  * 페이징 제어 바(이전/다음 버튼 및 limit 크기 조절 셀렉트 박스) 및 오프라인 경고 배너 포함.
* **`tdms_core/p4_manager/frontend/src/views/DashboardView.vue`** (수정)
  * `ExplorerView`를 탭 네비게이션 및 콘텐츠 레이아웃에 포함하여 연동.

### [테스트 코드]
* **`tdms_core/p4_manager/tests/test_explorer_bridge.py`** (신규)
  * 백엔드 API 기능 검증 테스트 6종(단위/격리/통합) 포함.
* **`tdms_core/p4_manager/frontend/src/tests/explorerStore.spec.ts`** (신규)
  * Pinia 스토어 단위 기능(메타데이터 세팅, 데이터 쿼리, 오프라인 폴백 처리) 검증 테스트 4종.
* **`tdms_core/p4_manager/frontend/src/tests/ExplorerView.spec.ts`** (신규)
  * `ExplorerView` 컴포넌트 렌더링, 스켈레톤 UI 노출 및 오프라인 배너 작동 검증 테스트 4종.

---

## 2. 설계상 주요 결정사항

* **장애 격리 (Fault Isolation) 보장**:
  * `p4_backend` 중계 레이어에서 `httpx.RequestError` 발생 시 이를 `502/503` 예외로 그대로 클라이언트에 전달하는 대신, `200 OK`와 `offline: true` 상태를 포함하는 JSON 폴백 응답을 반환하도록 설계하였습니다.
  * 이로 인해 하위 데이터 수집 백엔드가 내려가 있더라도 통합 매니저 UI가 완전히 멈추거나 에러 페이지만을 노출하는 상황을 방지하고, 사용자에게 명시적으로 "XX 시장 오프라인" 상태 배너를 노출하여 회복 탄력성을 확보하였습니다.
* **유연한 동적 컬럼 렌더링**:
  * 사전에 정의되지 않은 신규 테이블이나 시장별로 구조가 완전히 상이한 10종의 테이블을 처리하기 위해, 수신된 데이터 배열의 첫 번째 객체의 Key 리스트를 바탕으로 테이블 컬럼을 동적 파싱 및 가로 스크롤 가능한 테이블 컨테이너에 매핑하였습니다.

---

## 3. 테스트 및 검증 결과

### 3.1 백엔드 API 테스트
* **Tier 1 & 2 격리 테스트 (6개)**:
  * `test_get_preview_metadata_success` - **통과**
  * `test_get_preview_table_kr_success` - **통과**
  * `test_get_preview_table_us_success` - **통과**
  * `test_get_preview_table_with_invalid_market_raises_bad_request` - **통과**
  * `test_get_preview_table_with_invalid_table_raises_bad_request` - **통과**
  * `test_get_preview_table_offline_fallback` - **통과**
* **Tier 3 실제 통합 테스트 (1개)**:
  * `test_get_preview_real_backend_integration` - **통과** (실제 통신 불가 시 오프라인 폴백 처리 안전성 확인 완료)

### 3.2 프론트엔드 테스트 (Vitest)
* **explorerStore Pinia 스토어 단위 테스트 (4개)**: **전원 통과**
* **ExplorerView.vue 컴포넌트 단위 테스트 (4개)**: **전원 통과**

### 3.3 프론트엔드 빌드 검증
* `npm run build` 실행 결과, 타입 에러 및 번들링 오류 없이 정상 빌드 완료 (`dist/` 생성 성공).

---

## 4. 다음 작업 시 참고 및 주의사항

* **T-008 DB 백업 실행 및 이력 관리 연동**:
  * T-008에서 백업 파일 생성 및 복구를 다룰 때, 본 데이터 익스플로러를 사용하여 백업 전/후 데이터 적재 상태(예: stock_info 레코드 개수 변화)를 즉각 수동으로 확인하는 도구로 교차 연계하여 활용할 수 있습니다.
* **Spec 대비 실 구현 변경사항**:
  * 변경 사항 없음. 설계 명세서(`task-007_spec.md`)의 인터페이스 규격 및 비즈니스 요건을 100% 준수하여 구현하였습니다.
