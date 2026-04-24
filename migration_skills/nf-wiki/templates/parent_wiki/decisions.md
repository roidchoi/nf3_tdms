# Parent 기술 의사결정 (decisions.md)

> **범위**: 전체 시스템 또는 복수 Sub Project에 영향을 미치는 결정 **마지막 업데이트**: {YYYY-MM-DD} (Task-{ID})

---

## 사용 지침

Sub Project 내부에만 영향을 미치는 결정은 `p{n}_wiki/decisions.md`에 기록. 이 파일은 Parent 레벨(시스템 전체)의 결정만 다룬다.

---

<!-- 템플릿: 아래 형식을 복사해서 사용 --> <!-- --- id: DEC-{N} date: YYYY-MM-DD task: Task-{ID} status: active # active / superseded / reverted affects: [p1, p2, parent] --- ## [DEC-{N}] {결정 제목} (Task-{ID}) ### 배경 {왜 이 결정이 필요했는가} ### 결정 내용 {무엇을 결정했는가} ### 영향 범위 - P1: {영향 내용} - P2: {영향 내용} ### 대안 검토 | 대안 | 거부 이유 | |------|----------| | {대안A} | {이유} | ### 관련 링크 - `p{n}_wiki/decisions.md#{DEC-ID}` (하위 결정) - `parent_wiki/architecture.md#{섹션}` (구조 반영) -->

---

## 의사결정 목록

|ID|제목|Task|상태|
|---|---|---|---|
|—|(초기 상태)|—|—|