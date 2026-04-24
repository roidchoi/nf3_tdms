# pjt_wiki Index

> **프로젝트**: {PROJECT_NAME} **마지막 업데이트**: {YYYY-MM-DD} (Task-{ID}) **총 등록 파일**: {N}개

---

## 사용 지침

이 파일은 Claude가 새 세션에서 가장 먼저 읽는 파일이다. 전체 wiki를 읽지 않아도 "어디에 무엇이 있는지" 파악하는 용도. 실제 내용은 각 파일에서 읽는다.

---

## parent_wiki

|파일|내용 요약|마지막 업데이트|
|---|---|---|
|overview.md|{전체 진행도 및 현재 상태 한줄 요약}|Task-{ID}|
|architecture.md|{시스템 구조 한줄 요약}|Task-{ID}|
|decisions.md|{Parent 의사결정 건수 및 최근 결정 요약}|Task-{ID}|
|environment.md|{공통 환경 정보 한줄 요약}|Task-{ID}|

---

## p{n}_wiki (Sub Project별 반복)

### p1_wiki

|파일|내용 요약|마지막 업데이트|
|---|---|---|
|errors.md|{등록 건수}건. {가장 중요한 에러 ID} 필독|Task-{ID}|
|interfaces.md|{주요 DB/함수 한줄 요약}|Task-{ID}|
|codebase_map.md|{현재 구조 한줄 요약}|Task-{ID}|
|decisions.md|{의사결정 건수}건|Task-{ID}|
|environment.md|{환경 한줄 요약}|Task-{ID}|
|operations/|{operations 파일 현황}|Task-{ID}|

### p2_wiki

|파일|내용 요약|마지막 업데이트|
|---|---|---|
|errors.md|{등록 건수}건. {가장 중요한 에러 ID} 필독|Task-{ID}|
|interfaces.md|{주요 DB/함수 한줄 요약}|Task-{ID}|
|codebase_map.md|{현재 구조 한줄 요약}|Task-{ID}|
|decisions.md|{의사결정 건수}건|Task-{ID}|
|environment.md|{환경 한줄 요약}|Task-{ID}|
|operations/|{operations 파일 현황}|Task-{ID}|

---

## 빠른 참조 — 현재 가장 중요한 항목

> 이 섹션은 nf-lint 실행 시 Claude가 자동 갱신한다.

### ⚠️ 필독 에러

- [{SUB}_ERR-{N}] {에러 요약} → {파일경로}#섹션

### 📐 최근 변경된 인터페이스

- {함수/테이블명}: {변경 요약} → {파일경로}#섹션

### 🔄 진행중인 작업

- Task-{ID}: {작업명} ({Sub Project})