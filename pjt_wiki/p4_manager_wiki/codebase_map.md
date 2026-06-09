# 코드베이스 맵 (codebase_map.md)

> **Sub Project**: p4_manager (통합 관리 레이어)  
> **마지막 업데이트**: 2026-06-09 (T-001 완료)  
> **기록 원칙**: "현재 상태"만 기재. 미래 계획 혼재 금지. 상태 표시 필수.

---

## 1. 현재 폴더 구조

```
tdms_core/p4_manager/
├── nginx/
│   └── nginx.conf          # Nginx 리버스 프록시 및 WS 중계 설정 [✅완성]
├── tests/
│   ├── conftest.py         # pytest 커스텀 런타임 옵션 정의 [✅완성]
│   └── test_infra.py       # 인프라 3단계 TDD 검증 코드 [✅완성]
├── backend.Dockerfile      # FastAPI 백엔드 이미지 빌드 명세 [✅완성]
├── frontend.Dockerfile     # Nginx 프론트엔드 이미지 빌드 명세 [✅완성]
├── docker-compose.yml      # 멀티 컨테이너 환경 및 tdms-net 정의 [✅완성]
├── main.py                 # FastAPI 헬스 체크 API 엔드포인트 [✅완성]
├── pyproject.toml          # pytest 환경 및 패키지 메타데이터 [✅완성]
└── requirements.txt        # 의존 패키지 정의 [✅완성]
```

---

## 2. 핵심 데이터 흐름

```
[클라이언트 브라우저 (포트 80)]
       │ (HTTP Request / WS 연결)
       ▼
[p4_frontend (Nginx 리버스 프록시)]
       ├── /api/kr/*  ──> [p2_kdms (포트 8000)] (한국 시세 데이터 API)
       ├── /api/us/*  ──> [p3_usdms (포트 8005)] (미국 시세 데이터 API)
       ├── /api/mgr/* ──> [p4_backend (포트 8010)] (통합 관리 API)
       ├── /ws/logs/* ──> [p2 / p3 웹소켓] (실시간 로그 중계 터널)
       └── / (Index.html) ──> 정적 페이지 서빙 (Vue SPA 대시보드)
```

---

## 3. 모듈별 상태 및 역할

| 모듈/폴더 | 상태 | 핵심 파일 | 역할 요약 |
|---|---|---|---|
| nginx | ✅완성 | `nginx.conf` | 포트 80 수신 및 각 백엔드(p2, p3, p4) 프록시 및 WebSocket 중계 |
| tests | ✅완성 | `test_infra.py` | 헬스체크 API 검증, nginx.conf 구문 확인, docker-compose 통합 프록시 통신 검증 |
| 루트 패키지 | ✅완성 | `main.py` | p4 통합 관리 백엔드 API (현재 `/api/mgr/health` 헬스체크 노출) |

---

## 4. 핵심 진입점 (Entry Points)

| 스크립트 / 서비스 | 실행 방법 | 역할 |
|---|---|---|
| `p4_frontend` (Nginx) | `docker-compose up --build -d p4_frontend` | 80 포트 리프록시 및 정적 SPA 서빙 기동 |
| `p4_backend` (FastAPI) | `docker-compose up --build -d p4_backend` | 통합 관리 레이어 API 서버 구동 |
| `test_infra` (pytest) | `conda run -n tdms_p4_env env PYTHONPATH=. pytest tests/ -v --run-integration` | 인프라 및 전체 기능 통합 검증 실행 |

---

## 5. 테스트 현황

| 테스트 파일 | 커버 대상 | 상태 |
|---|---|---|
| `tests/test_infra.py` | FastAPI 헬스 체크 엔드포인트 (`main.py`) | ✅통과 |
| `tests/test_infra.py` | `nginx.conf` 프록시 규칙 검증 | ✅통과 |
| `tests/test_infra.py` | Docker Compose & Nginx 통합 라우팅 | ✅통과 |

---

## 6. 가비지 현황

> Lint 시 사용자 승인 후 삭제. 이 섹션이 비어있는 것이 정상.

| 파일/폴더 | 생성 Task | 삭제 사유 |
|---|---|---|
| — | — | — |

---

## 7. 변경 이력 요약

| Task | 주요 변경 내용 |
|---|---|
| Task-초기화 | 초기 구조 생성 |
| T-001 | Conda 가상환경, Docker Compose, Nginx 프록시 인프라 구축 및 TDD 검증 완료 |