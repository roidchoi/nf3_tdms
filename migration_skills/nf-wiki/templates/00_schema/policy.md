# Wiki 운영 정책 (policy.md)

> **버전**: v3.0 **이 파일의 역할**: nf-wiki skill과 nf-lint skill이 참조하는 운영 규칙의 단일 출처. 규칙 변경 시 이 파일만 수정하면 모든 skill에 반영된다.

---

## 1. 업데이트 의무 규칙

|트리거|의무 업데이트 파일|담당|
|---|---|---|
|모든 Task 완료|00_schema/log.md|nf-wiki|
|DB/함수 시그니처 변경|p{n}_wiki/interfaces.md|nf-wiki|
|에러 발생 + 해결 확인|p{n}_wiki/errors.md|nf-wiki|
|폴더/모듈 구조 변경|p{n}_wiki/codebase_map.md|nf-wiki|
|기술 의사결정 발생|decisions.md + graph.md|nf-wiki|
|실험/평가 완료|operations/experiments.md|nf-wiki|
|배포/운영 절차 변경|operations/deployment.md 또는 runbook.md|사용자 or nf-wiki|
|개발환경/패키지 변경|environment.md|nf-wiki (즉시)|
|5 Task마다|nf-lint 실행|사용자 트리거|

---

## 2. 정보 열화 방지 규칙

### interfaces.md

- **요약 금지** — 정확한 타입, 컬럼명, 경로 전체 기재
- 타입은 실제 Python/SQL 타입으로 명시 (예: `pl.DataFrame`, `TEXT`, `REAL`)
- 함수 위치는 파일 경로와 라인 번호까지 기재

### errors.md

- **해결법 없으면 등록 금지** — 발생 원인만 있는 항목 불허
- 재발 시 "발생 이력"에 Task ID 추가 (삭제하지 않음)
- severity 변경은 재발 2회 이상 시 high로 승격

### codebase_map.md

- **"현재 상태" 기준만** — 미래 계획 혼재 금지
- 완성/진행중/미착수 상태 표시 필수 (✅/🔄/⬜)
- 가비지 현황은 별도 섹션으로 관리

### environment.md

- 패키지 버전은 실제 설치 버전으로 기재 (범위 표기 금지)
- 알려진 이슈는 해결법 또는 회피법이 있을 때만 등록

---

## 3. 교차 참조 규칙

- 다른 wiki 파일을 언급할 때: `{파일명}#{섹션ID}` 형식
    - 예: `p2_wiki/errors.md#ERR-001`
- 새 연결 발생 시 graph.md 즉시 업데이트
- 삭제된 항목을 참조하는 링크는 Lint 시 정리

---

## 4. Lint 체크리스트 (nf-lint 실행 기준)

### 4.1 index.md 정확성

- [ ] 모든 wiki 파일이 index에 등록되어 있는가
- [ ] 마지막 업데이트 Task ID가 정확한가
- [ ] "빠른 참조" 섹션이 현재 상태를 반영하는가

### 4.2 errors.md 건강성

- [ ] 해결법 없는 항목이 있는가 → 제거 또는 보완
- [ ] status가 resolved인데 5 Task 이상 지난 항목 → confirmed로 재검토
- [ ] 3회 이상 재발 항목 → severity high 승격 여부 검토

### 4.3 interfaces.md 정확성

- [ ] 실제 코드와 불일치하는 항목이 있는가
- [ ] 삭제된 함수/테이블이 아직 등록되어 있는가
- [ ] 라인 번호가 현재 코드와 맞는가

### 4.4 codebase_map.md 현행화

- [ ] 실제 폴더 구조와 일치하는가
- [ ] 가비지 현황이 최신인가 → 삭제 대상 사용자 확인 요청

### 4.5 graph.md 유효성

- [ ] 삭제된 항목을 참조하는 링크가 있는가
- [ ] 새로 생긴 중요 연결이 누락되어 있는가

### 4.6 environment.md 최신성

- [ ] 패키지 버전이 실제와 다른가
- [ ] 해결된 이슈가 아직 "알려진 이슈"에 남아있는가

### 4.7 overview.md Gap 점검

- [ ] PRD 목표 대비 현재 구현 상태 gap이 기록되어 있는가

### 4.8 operations/ 누락 점검

- [ ] 완료된 실험이 experiments.md에 등록되지 않은 것이 있는가

---

## 5. Antigravity 접근 규칙

- **읽기**: 허용 (Task Spec §0으로 핵심 내용이 전달되므로 직접 접근은 보조용)
- **쓰기**: 금지 — 모든 wiki 업데이트는 Claude(nf-wiki skill) 전담
- **보고**: Antigravity가 발견한 이슈/변경사항은 결과 보고에 포함 → Claude가 반영

---

## 6. Sub Project 추가 시 절차

1. `pjt_wiki/p{n}_wiki/` 폴더 생성
2. 템플릿 파일 일체 복사 후 Sub Project 정보로 초기화
3. `00_schema/index.md`에 새 Sub Project 섹션 추가
4. `parent_wiki/architecture.md` 업데이트
5. `00_schema/log.md`에 항목 추가