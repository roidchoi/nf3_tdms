# T-005 KIS API 코어 구현 Walkthrough

## 1. 구현 개요
- **대상 Task**: T-005 KIS API 코어 (`KisApiCore`)
- **목표**: `p2_kdms`와 `p3_usdms` 양쪽에서 중복으로 구현되는 KIS REST API 로직을 공통 모듈로 통합하고, TokenManager를 통한 토큰 공유 및 401 오류 시 자동 재시도 로직을 구현합니다.

## 2. 생성 및 변경된 파일 목록
- **수정**: `docs/p1_shared/p1_shared_pjt_tasks.md` (T-005 상태 업데이트)
- **추가**: `tdms_core/p1_shared/p1_shared/api/kis_api_core.py`
  - `KisApiCore` 클래스: KIS API와의 통신을 캡슐화합니다.
  - `base_url` 프로퍼티를 통해 `is_mock` 플래그에 따라 실전/모의 투자 URL을 자동 분기합니다.
  - `get_headers()`: 발급된 토큰 및 `extra` 파라미터를 조합하여 KIS API 요청에 필요한 헤더 구조를 반환합니다.
  - `request()`: 401 Unauthorized 에러 감지 시 즉시 토큰을 강제 재발급받고 동일 요청을 1회 재시도하도록 설계되었습니다.
- **추가**: `tdms_core/p1_shared/tests/test_kis_api_core.py` (11개 단위 테스트)
  - `test_two_instances_with_same_cache_path_share_token`: TokenManager를 통해 파일 기반 토큰 캐시를 여러 인스턴스가 안전하게 공유함을 검증합니다.
  - `test_request_retries_once_on_401_and_succeeds`: 401 발생 시 재발급 로직이 올바르게 실행되는지 Mock 검증합니다.

## 3. 주요 설계 결정사항
1. **토큰 공유 체계 확보**:
   - `p2_kdms`의 국내주식 클라이언트와 `p3_usdms`의 해외주식 클라이언트가 모두 `KisApiCore`를 상속하여 동일한 `token_cache_path`를 가리킬 경우, 파일 시스템을 통해 서로 토큰 발급 상태를 공유할 수 있습니다. 이를 통해 KIS API 토큰 중복 발급 및 제한을 회피할 수 있습니다.
2. **자동 갱신 및 재시도 로직 (`request`)**:
   - KIS API는 토큰 만료뿐만 아니라 일시적인 세션 초기화로 인해 401 에러를 응답할 수 있습니다. 이를 방어하기 위해 예외 처리 블록 내에 명시적인 재시도 패턴을 구현하였으며, 무한루프 방지를 위해 1회 재시도로 제한했습니다.
3. **URL 분기 체계화**:
   - 도메인이 다른 실전/모의 서버를 `is_mock` 플래그 하나로 손쉽게 전환할 수 있도록 처리했습니다. 추후 `.env` 환경 변수와 쉽게 연동될 수 있습니다.

## 4. 테스트 결과
- 단위 테스트(T-005): 11개 통과
- 기존 스위트(T-001~T-004): 67개 통과
- **최종: 78개 단위/통합 테스트 스위트 완전 통과 (All Green)**

## 5. 다음 Task 관련 참고
- KIS 관련 기능은 이제 `p2_kdms` 및 `p3_usdms`에서 `KisApiCore`를 상속받은 `KisKrClient`, `KisUsClient`를 만들어 각각 필요한 도메인 특화 요청(예: 주식현재가 조회, 해외주식 주문)에만 집중할 수 있게 되었습니다.
