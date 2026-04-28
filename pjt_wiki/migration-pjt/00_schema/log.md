# Wiki Log

> **규칙**: append-only. 항목을 삭제하거나 수정하지 않는다. **형식**: `## [{날짜}] {유형} | {내용}` **유형**: Task완료 / 의사결정 / 에러등록 / 환경변경 / Lint / 실험완료 / 배포

---

## 사용 지침

이 파일은 프로젝트 전체의 타임라인이다. `grep "^## \[" log.md | tail -10` 으로 최근 10개 항목 확인 가능. index.md의 "빠른 참조" 섹션은 이 log를 기반으로 갱신된다.

---

<!-- 아래부터 실제 로그 항목 추가. 최신 항목이 위에 오도록. -->

## [2026-04-28] 초기화 | migration-pjt 위키 최초 구축 완료
- KDMS(kdms_origin) + USDMS(usdms_origin) 두 참조 프로젝트의 지식 체계화
- Graphify 지식 그래프 연동 (1,066 nodes, 2,480 edges, 32 communities)
- God Node 분석: DatabaseManager(243 edges)가 두 프로젝트 전반의 핵심 추상화
- 생성 문서: codebase_map, environment, db_schema, pit_pattern, price_factor, coexistence ADR
- 신규 프로젝트 매핑 정보: p1_kdms ← kdms_origin, p2_usdms ← usdms_origin, p3_manager ← 공통 패턴