# [P4DEC-009] 가치평가 테이블 날짜 기본 필터 최적화 및 코드 검색기 옵션/레이아웃 개편

## 1. 컨텍스트 및 요구사항
- **가치평가 필터 지연**: 미국 일별 가치평가 지표(`us_daily_valuation`) 로드 시 날짜 범위 기본값이 설정되어 있지 않아 1개 종목에 대해서도 4,273건에 달하는 역사적 데이터가 무조건 전부 풀스캔 렌더링되면서 지연을 발생시킴.
- **검색기 사용성**: 종목 코드 검색기(코드 헬퍼)의 상하 배치가 불필요한 공백을 차지함. 입력 검색기 영역이 오른쪽에 위치하고 7:3 (좌 결과, 우 조건) 비율로 컴팩트하게 좌우로 정렬되는 것이 사용성 면에서 더 우수함.
- **검색 정밀도 한계**: 짧은 티커(T, F 등) 검색 시 부분 일치 조건으로 인해 무수히 많은 결과물이 출력되어 원하는 종목 탐색이 불가함. 정확히 일치(`exact`) / 부분 일치(`contains`) 옵션과 코드/이름/전체 범위 옵션을 유동적으로 제어해야 함.
- **회사명 공백**: 미국 종목 검색 시 회사명이 나타나지 않는 컬럼 누락 버그 존재.

---

## 2. 해결 결정 (Decision)
- **6개월 기본 날짜 기본값 적용**:
  - `us_daily_valuation` 테이블을 대상으로 데이터 익스플로러가 로드될 때, 6개월 전(`today - 6 months`)부터 오늘까지로 날짜 필터를 자동 기본 주입하여 풀스캔의 스캔 횟수와 UI 렌더링 부하를 대폭 줄임.
- **좌우 7:3 분할 레이아웃 개편**:
  - `ExplorerView.vue` 코드 헬퍼 템플릿 마크업을 `<div class="helper-layout">`을 기준으로 좌측 70%(`helper-left-pane`), 우측 30%(`helper-right-pane`)로 배치하는 Flexbox 분할 구조를 채택.
- **상세 매칭 검색기 옵션 연동**:
  - 프론트엔드 상태에 `helperMatchType` (contains/exact) 및 `helperSearchField` (all/code/name) 추가.
  - 게이트웨이(Manager) 백엔드(`/preview/{market}/{table}`) 및 하위 백엔드(KDMS, USDMS) preview API 파라미터로 이를 확장 릴레이.
  - 백엔드 쿼리 생성 시 `match_type`에 따라 `=` 또는 `ILIKE` 연산자를 적용하고, `search_field`에 맞게 컬럼 타겟을 축소하여 동적 WHERE 구문을 빌드.
- **검색 옵션 컴팩트화 및 2:3 가로 비율 정렬**:
  - 수직 공간의 효율화를 위해 우측 패널 내의 검색 옵션 그룹 '일치 방식'과 '검색 범위'를 좌우로 병렬 배치하되, flex-grow 비율을 각각 `2`와 `3`으로 조정 (`.match-type-group { flex: 2 }`, `.search-field-group { flex: 3 }`).
  - 선택 옵션 라벨 텍스트를 컴팩트하게 단축 ('부분 일치'->'부분', '정확히 일치'->'정확', '코드/티커'->'코드', '명칭'->'명칭').
  - 텍스트 단축에 따라 옵션 내부 라디오 버튼 정렬을 가로(row) 방향으로 복구하고 `flex-wrap: wrap`을 적용하여 좁은 공간 내에서의 가독성과 레이아웃 완성도를 만족시킴.
- **검색 실행 버튼의 검색어 입력 행 인라인 배치**:
  - 기존에 독립된 행을 차지하여 세로 높이를 불필요하게 차지하던 '검색 실행' 버튼을 검색어 입력란(`helper-search-input-wrapper`) 내부로 인라인 이동.
  - 텍스트를 '검색'으로 단축하고 버튼 너비를 60px 고정(`flex-shrink: 0`)으로 제어하여 인풋 필드와 나란히 배치함으로써 행 높이 하나만큼의 수직 공간을 추가 절약.
- **회사명 바인딩 바인딩 보정**:
  - US 마스터 스키마의 회사명 컬럼(`latest_name`)과 예비 필드(`name`)를 함께 폴백하도록 `item.latest_name || item.name || '-'`로 바인딩 변경.

---

## 3. 결과 및 기대효과
- 6개월 필터링으로 대용량 가치평가 테이블 로드 시 페이지 응답 시간 단축.
- 7:3 분할 배치로 종목 코드 검색 시 화면 스크롤 불필요 및 고정된 컨트롤 뷰 유지.
- `T`나 `F` 등의 짧은 미국 티커 입력 시에도 '정확히 일치' + '코드/티커'를 선택하여 즉각적으로 타겟 종목 1건만 선별 검색 가능.

---

## 4. 관련 코드 컨텍스트
- [ExplorerView.vue](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/views/ExplorerView.vue)
- [explorerStore.ts](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/stores/explorerStore.ts)
- [manager.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/routers/manager.py)
- [data.py (KDMS)](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/data.py)
- [data.py (USDMS)](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/routers/data.py)
