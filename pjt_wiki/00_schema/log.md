# Wiki Log

> **규칙**: append-only. 항목을 삭제하거나 수정하지 않는다. **형식**: `## [{날짜}] {유형} | {내용}` **유형**: Task완료 / 의사결정 / 에러등록 / 환경변경 / Lint / 실험완료 / 배포

---

## 사용 지침

이 파일은 프로젝트 전체의 타임라인이다. `grep "^## \[" log.md | tail -10` 으로 최근 10개 항목 확인 가능. index.md의 "빠른 참조" 섹션은 이 log를 기반으로 갱신된다.

---

<!-- 아래부터 실제 로그 항목 추가. 최신 항목이 위에 오도록. -->

## [2026-06-04] Task완료 | p3_usdms 미국 시장 백엔드 T-006(데이터 조회 REST API 완성) 완료에 따른 REST API 7종 엔드포인트 명세(data_api_endpoints.md) 신규 등록, pyarrow 패키지 추가에 따른 환경 문서(environment.md) 및 MoC(index.md) 현행화 완료.

## [2026-06-04] Task완료+의사결정+에러등록 | p3_usdms 미국 시장 백엔드 T-005(Blacklist + MasterEnricher + 일일 자동화) 완료에 따른 핵심 인터페이스(blacklist_repo, blacklist_manager, master_enricher, daily_routine) 추가, 60일 룩백 자가 치유 및 쿼리 병목 최적화(USDMS_DEC-002, USDMS-ERR-002), 이원화 에러 분기 및 자동 릴리즈(USDMS_DEC-003) 위키 지식화 완료.

## [2026-06-02] Task완료 | p3_usdms 미국 시장 백엔드 T-004(가치평가 및 재무비율 대량 실 계산) 완료에 따른 핵심 인터페이스(valuation_repo, valuation_engine) 추가 및 550종목 DB 캐싱 최적화(Bulk Cache Caching) 위키 지식화 완료.

## [2026-06-02] Task완료 | p3_usdms 미국 시장 백엔드 T-003(SEC XBRL 재무 파싱 + 주식수 이력) 완료에 따른 핵심 인터페이스(financial_parser, financial_repo, xbrl_mapper) 및 의사결정(USDMS_DEC-001) 위키 지식화 완료.

## [2026-06-01] Task완료 | p3_usdms 미국 시장 백엔드 T-002-A 완료에 따른 핵심 인터페이스(sec_client, master_sync, master_repo) 문서화 완료 및 SECClient get_company_facts 누락 기능 복구 및 검증 완료.

## [2026-05-29] 에러등록 | WSL2 도커 데스크탑 바인드 마운트 동기화 유실로 인한 빈 DB 기동 및 IP 변경 에러(USDMS-ERR-001) 등록 완료.

## [2026-05-28] 환경변경+의사결정 | Kiwoom REST API의 초당 5회 한도 초과 차단 방지를 위한 0.25초 스로틀링 딜레이(P2DEC-004) 도입 완료. 관련 pytest 6종 통과 검증 완료.

## [2026-05-28] 의사결정+에러등록+Task완료 | KIS API Rate Limit 차단 회피를 위한 안전 마진 스로틀링 지연 도입(P2DEC-004, p2ERR-001) 및 시가총액 bigint 정수 오버플로우 방어막 패치(p2ERR-002) 적용 완료. 전 종목 E2E 청정 데이터 수집 백필 완수.

## [2026-05-27] 의사결정+Task완료 | 한국거래소(KRX) 2024년 알파벳 혼용 종목코드 전면 지원을 위한 수집기 필터 완화 결정(P2DEC-003) 등록 및 관련 DB 스키마 주석(schema_kdms_db.md) 보강 완료.

## [2026-05-26] Task완료 | kdms_timescaledb 내 12개 테이블 컬럼/PK/인덱스 상세 스키마(schema_kdms_db.md) 및 배치 태스크 실행/수동 트리거 운영 런북(runbook.md) 지식화 완료. MoC(index.md) 갱신.

## [2026-05-26] Task완료+지식화 | p2_kdms_wiki 전체 구축 — Graphify(425 nodes, 841 edges, 19 communities) 기반. codebase_map 전면 작성, interfaces 5개(ohlcv_repo, financial_repo, data_api_endpoints, fastapi_lifespan, settings_config), decisions 2개(PIT 재무 패턴, 수정주가 이중 전략), environment 전면 갱신. MoC(index.md) p2_kdms 섹션 현행화.

## [2026-05-14] Task완료+초기화 | p1_shared_wiki 전체 구축 — T-001~T-008 완료 기반. interfaces 5개, decisions 2개, errors 2개, runbook, codebase_map, environment 신규 생성. MoC를 Graphify God Node 기준으로 재구성.

## [{YYYY-MM-DD}] 초기화 | pjt_wiki 초기 구조 생성