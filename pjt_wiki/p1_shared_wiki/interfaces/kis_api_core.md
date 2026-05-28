# KisApiCore (KIS REST API 공통 클라이언트)

> 마지막 변경: 2026-05-28
> 소스 위치: `tdms_core/p1_shared/p1_shared/api/kis_api_core.py:8`

### 1. 개요 및 목적
- 한국투자증권(KIS) REST API 연동을 위한 공통 인터페이스입니다.
- OAuth2 토큰 자동 캐싱 관리(`TokenManager` 연동), 401 Unauthorized 시 자동 토큰 재발급, 429(Rate Limit)/5xx(서버 장애) 시 지수 백오프 기반 최대 3회 재시도를 보증합니다.
- 호출 속도 한도를 안전하게 통제하기 위해 기본 안전 마진 스로틀링(Throttling)을 적용합니다.
- 연관된 문서: [[p2_kdms_wiki/decisions/dec-004_kis_api_throttling_strategy.md]]

### 2. 상세 명세 (요약 금지)

#### 생성자: `__init__`
```python
def __init__(
    self,
    app_key: str,
    app_secret: str,
    account_no: str,
    is_mock: bool = False,
    token_cache_path: str = "~/.cache/tdms/kis_token.json",
    throttle_delay: float = None,
) -> None
```
**입력 파라미터**:
| 파라미터명 | 타입 | 필수 여부 | 설명 | 기본값 |
|---|---|---|---|---|
| `app_key` | `str` | Y | 한국투자증권 App Key | — |
| `app_secret` | `str` | Y | 한국투자증권 App Secret | — |
| `account_no` | `str` | Y | 계좌번호 (8자리-2자리) | — |
| `is_mock` | `bool` | N | 모의투자 서버 여부 | `False` |
| `token_cache_path` | `str` | N | 토큰 파일 캐시 저장 경로 | `"~/.cache/tdms/kis_token.json"` |
| `throttle_delay` | `float` | N | API 요청 성공 후 강제 sleep 딜레이 시간 (초) | `None` (내부 설정값 사용) |

> **Throttling Delay 자동 설정**:
> - `throttle_delay`가 `None`으로 제공되면, 다음 마진 정책에 의해 자동 구성됩니다.
>   - **실전 투자 (`is_mock=False`)**: `0.08초` (초당 최대 12.5회 호출 수준)
>   - **모의 투자 (`is_mock=True`)**: `0.4초` (초당 최대 2.5회 호출 수준)

---

#### 핵심 함수: `request`
```python
def request(
    self,
    method: str,
    path: str,
    params: dict = None,
    body: dict = None,
    tr_id: str = "",
    extra_headers: dict = None,
) -> dict
```
**입력 파라미터**:
| 파라미터명 | 타입 | 필수 여부 | 설명 | 기본값 |
|---|---|---|---|---|
| `method` | `str` | Y | HTTP 메서드 (`GET`, `POST` 등) | — |
| `path` | `str` | Y | API 엔드포인트 상대 경로 (예: `/uapi/domestic-stock/v1/quotations/inquire-price`) | — |
| `params` | `dict` | N | HTTP Query parameters | `None` |
| `body` | `dict` | N | JSON Request body | `None` |
| `tr_id` | `str` | N | KIS 거래 ID (`tr_id`) 헤더 | `""` |
| `extra_headers` | `dict` | N | 추가 헤더 커스텀 딕셔너리 | `None` |

**출력 형식**:
- 반환 타입: `dict` (JSON Response 파싱 결과)

### 3. 주의사항 및 의존성
- **IP 차단 위험**: 스로틀 딜레이(`throttle_delay`)를 `0`으로 비활성화하여 무제한 호출 루프를 돌릴 경우, 게이트웨이 호출 한계에 걸려 당사 개발 및 서버 IP 자체가 차단될 위험이 매우 큽니다.
- **참고 에러**: [[p2_kdms_wiki/errors/err-001_kis_api_403_forbidden.md]]
