# KiwoomApiCore (Kiwoom REST API 공통 클라이언트)

> 마지막 변경: 2026-05-28
> 소스 위치: `tdms_core/p1_shared/p1_shared/api/kiwoom_api_core.py:7`

### 1. 개요 및 목적
- 키움증권 OpenAPI(REST API 버전) 연동을 위한 공통 인터페이스입니다.
- OAuth2 토큰 발급 및 만료일자 자동 캐싱 관리(`TokenManager` 연동), Bearer 인증 헤더 자동 구성을 처리합니다.
- 키움 API의 공식 초당 트래픽 제한(초당 5회) 규격을 안전하게 회피하기 위해 기본 스로틀링(Throttling) 딜레이를 내장하고 있습니다.
- 연관된 문서: [[p2_kdms_wiki/decisions/dec-004_kis_api_throttling_strategy.md]]

### 2. 상세 명세 (요약 금지)

#### 생성자: `__init__`
```python
def __init__(
    self,
    app_key: str,
    app_secret: str,
    token_cache_path: str = "~/.cache/tdms/kiwoom_token.json",
    throttle_delay: float = 0.25,
) -> None
```
**입력 파라미터**:
| 파라미터명 | 타입 | 필수 여부 | 설명 | 기본값 |
|---|---|---|---|---|
| `app_key` | `str` | Y | 키움증권 App Key | — |
| `app_secret` | `str` | Y | 키움증권 App Secret | — |
| `token_cache_path` | `str` | N | 토큰 파일 캐시 저장 경로 | `"~/.cache/tdms/kiwoom_token.json"` |
| `throttle_delay` | `float` | N | API 요청 성공 후 강제 sleep 지연 시간 (초) | `0.25` |

---

#### 핵심 함수: `request`
```python
def request(
    self,
    method: str,
    path: str,
    params: dict = {},
) -> dict
```
**입력 파라미터**:
| 파라미터명 | 타입 | 필수 여부 | 설명 | 기본값 |
|---|---|---|---|---|
| `method` | `str` | Y | HTTP 메서드 (`GET`, `POST` 등) | — |
| `path` | `str` | Y | API 엔드포인트 상대 경로 (예: `/api/dostk/stkinfo`) | — |
| `params` | `dict` | N | HTTP Query parameters | `{}` |

**출력 형식**:
- 반환 타입: `dict` (JSON Response 파싱 결과)

### 3. 주의사항 및 의존성
- **하위 호환성 및 상위 클래스 상속**:
  - `KiwoomClient` 상속체에서 호출 시 부모 생성자 인자를 추가로 기입하지 않는 경우에도 `throttle_delay=0.25` 기본값 바인딩이 완벽하게 지원되도록 보증합니다.
  - `KiwoomClient.get_minute_chart`는 연속 조회를 위해 직접 `requests.post`를 사용하여 자체 딜레이(`0.2초`)를 기동하므로, 본 코어 `request()`의 0.25초 딜레이와 중복 적용되지 않아 이중 지연이 발생하지 않습니다.
