# T-004 토큰 매니저 + Kiwoom API 코어 구현 Walkthrough

## 1. 구현 개요
- **대상 Task**: T-004 토큰 매니저 + Kiwoom API 코어
- **목표**: 파일 기반 API 토큰 캐싱을 담당하는 `TokenManager` 모듈과 이를 연동하여 Kiwoom REST API 인증 요청을 담당하는 `KiwoomApiCore`를 TDD 방식으로 구현하여 의존성과 관심사를 분리.

## 2. 생성 및 변경된 파일 목록
- **추가**: `tdms_core/p1_shared/p1_shared/api/__init__.py`
- **추가**: `tdms_core/p1_shared/p1_shared/api/token_manager.py`
  - `TokenManager` 클래스: `save_token`, `get_valid_token`, `is_valid` 구현
  - 만료 시간 5분 전 조기 갱신(버퍼) 로직 적용. 손상된 캐시 대응(`JSONDecodeError`, `KeyError` 예외 방어).
- **추가**: `tdms_core/p1_shared/p1_shared/api/kiwoom_api_core.py`
  - `KiwoomApiCore` 클래스: `TokenManager` 인스턴스를 통해 Authorization 헤더 구성, HTTP 요청(`request()`).
  - 캐시가 없거나 만료 시 Kiwoom Open API(`/oauth2/token`)를 호출하여 신규 발급(`_issue_new_token`) 및 재저장.
- **추가**: `tdms_core/p1_shared/tests/test_token_manager.py` (9개 테스트)
- **추가**: `tdms_core/p1_shared/tests/test_kiwoom_api_core.py` (6개 테스트)

## 3. 주요 구현 및 설계 결정사항
1. **TokenManager와 HTTP 분리**:
   - `TokenManager`는 JSON 파싱과 날짜 계산 로직만 갖도록 설계하고, 실제 토큰 발급 로직(`requests.post`)은 클라이언트인 `KiwoomApiCore` 내부에 배치하여 역할 분리를 달성했습니다.
2. **KST 타임존 처리**:
   - Kiwoom API에서 전달되는 `expires_dt`("YYYYMMDDHHMMSS")를 파싱할 때 `timedelta(hours=9)`를 사용해 명시적으로 KST(한국 표준시)를 반영한 `datetime` 객체로 변환하고 캐싱에 사용하도록 하였습니다.
3. **만료 5분 조기 버퍼**:
   - 토큰 갱신 경계값 테스트를 통과하도록 `is_valid`에서 `expires_at`과 현재 UTC 시간의 차이가 5분 이상 남아있을 때만 유효한 것으로 판단하도록 하여 간헐적 인증 실패를 방지했습니다.

## 4. 테스트 결과
- 단위 테스트(T-004): 15개 통과
- 기존 스위트(T-001~T-003): 52개 전체 통과
- **최종: 67개 테스트 스위트 완전 통과 (All Green)**

## 5. 다음 Task 유의사항
- `T-005` (KIS API 코어) 구현 시에도 동일한 `TokenManager` 인터페이스를 공유하되, token_type을 "kis"로 설정하여 활용하면 됩니다.
- 개발 환경의 `pytest` Mocking(`requests.post`) 외에 향후 통합 환경 연결 시 Open API App Key 및 Secret Key 환경 변수 연동이 요구됩니다.
