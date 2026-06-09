# WebSocket 로그 중계 프록시 API 스펙 (`/ws/logs/{market}`)

- **Sub Project**: p4_manager
- **구분**: WebSocket API
- **라우트**: `/api/mgr/ws/logs/{market}`
- **최종 업데이트**: 2026-06-09

---

## 1. 개요
프론트엔드 및 외부 모니터링 시스템에서 개별 시장(KDMS, USDMS) 백엔드의 실시간 출력 로그를 일관된 경로로 접근하여 수집할 수 있도록 중계해주는 프록시 터널링 엔드포인트입니다.

---

## 2. 인터페이스 시그니처 (FastAPI)

```python
# tdms_core/p4_manager/routers/proxy_ws.py

@router.websocket("/ws/logs/{market}")
async def websocket_proxy_endpoint(
    websocket: WebSocket,
    market: str,
    log_file: Optional[str] = None
):
    """
    시장 코드(market: 'kr' | 'us')에 따른 실시간 로그를 양방향 중계 처리합니다.
    """
```

### 파라미터 규격
| 파라미터명 | 타입 | 필수 여부 | 설명 |
|---|---|---|---|
| `market` | `str` (Path) | 필수 | `'kr'` (KDMS) 또는 `'us'` (USDMS) |
| `log_file` | `str` (Query) | 선택 | 미국 시장(`us`) 진입 시 분석 대상 특정 로그 파일명 (예: `daily_routine_2026-06-09.log`) |

### Close / 에러 코드 규격
- **`1008 Policy Violation`**: `market` 코드가 `'kr'` 또는 `'us'`가 아닐 때 연결 거부.
- **`1011 Internal Error`**: 대상 백엔드 웹소켓 서버가 오프라인 또는 연결 거부 상태일 때 에러 피드백 메시지 발송 후 소켓 종료.

---

## 3. 타겟 중계 주소 매핑 규칙
1. **한국 시장 (`kr`)**: `ws://p2_kdms:8000/ws/logs`
2. **미국 시장 (`us`)**: `ws://p3_usdms:8005/ws/logs` (쿼리 파라미터 `log_file`을 그대로 릴레이)

---

## 4. 커넥션 누수 방지 설계 결정사항 (Decision)
클라이언트 측 연결이 끊어지는 즉시 (`WebSocketDisconnect`), `finally` 구문을 통하여 업스트림 백엔드로 열려 있던 `websockets.connect` 세션을 비동기식으로 명확히 `close()` 및 태스크를 정리함으로써 백엔드의 리소스 누수를 절대적으로 방지합니다.
