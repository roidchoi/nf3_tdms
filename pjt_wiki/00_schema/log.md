# Wiki Log

> **규칙**: append-only. 항목을 삭제하거나 수정하지 않는다. **형식**: `## [{날짜}] {유형} | {내용}` **유형**: Task완료 / 의사결정 / 에러등록 / 환경변경 / Lint / 실험완료 / 배포

---

## 사용 지침

이 파일은 프로젝트 전체의 타임라인이다. `grep "^## \[" log.md | tail -10` 으로 최근 10개 항목 확인 가능. index.md의 "빠른 참조" 섹션은 이 log를 기반으로 갱신된다.

---

<!-- 아래부터 실제 로그 항목 추가. 최신 항목이 위에 오도록. -->

## [2026-05-27] 의사결정+Task완료 | 한국거래소(KRX) 2024년 알파벳 혼용 종목코드 전면 지원을 위한 수집기 필터 완화 결정(P2DEC-003) 등록 및 관련 DB 스키마 주석(schema_kdms_db.md) 보강 완료.

## [2026-05-26] Task완료 | kdms_timescaledb 내 12개 테이블 컬럼/PK/인덱스 상세 스키마(schema_kdms_db.md) 및 배치 태스크 실행/수동 트리거 운영 런북(runbook.md) 지식화 완료. MoC(index.md) 갱신.

## [2026-05-26] Task완료+지식화 | p2_kdms_wiki 전체 구축 — Graphify(425 nodes, 841 edges, 19 communities) 기반. codebase_map 전면 작성, interfaces 5개(ohlcv_repo, financial_repo, data_api_endpoints, fastapi_lifespan, settings_config), decisions 2개(PIT 재무 패턴, 수정주가 이중 전략), environment 전면 갱신. MoC(index.md) p2_kdms 섹션 현행화.

## [2026-05-14] Task완료+초기화 | p1_shared_wiki 전체 구축 — T-001~T-008 완료 기반. interfaces 5개, decisions 2개, errors 2개, runbook, codebase_map, environment 신규 생성. MoC를 Graphify God Node 기준으로 재구성.

## [{YYYY-MM-DD}] 초기화 | pjt_wiki 초기 구조 생성