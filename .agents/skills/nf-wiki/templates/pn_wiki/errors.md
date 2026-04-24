# 에러 패턴 (errors.md)

> **Sub Project**: P{n}_{Name} **마지막 업데이트**: {YYYY-MM-DD} (Task-{ID}) **등록 원칙**: 해결법이 확인된 것만 등록. 원인만 있는 항목 불허.

---

## 사용 지침

- **Task Spec 작성 시**: Claude가 이 파일 전체를 읽고 §0에 관련 항목 포함
- **구현 중 에러 발생 시**: Antigravity가 결과 보고에 포함 → Claude가 등록
- **재발 시**: 해당 항목의 "발생 이력"에 Task ID 추가

---

## 에러 목록

|ID|요약|severity|status|마지막 발생|
|---|---|---|---|---|
|—|(초기 상태)|—|—|—|

---

<!-- 에러 항목 템플릿: 아래를 복사해서 추가 --> <!-- --- id: {SUB}ERR-{N} sub_project: p{n} severity: low / medium / high / critical status: confirmed / suspected / resolved last_seen: Task-{ID} related: p{n}_wiki/interfaces.md#{섹션} --- ## [{SUB}ERR-{N}] {에러 제목} ### 발생 패턴 {어떤 상황에서 발생하는가 — 재현 조건} ### 원인 {왜 발생하는가} ### 해결법 ← 필수. 없으면 등록 불가 ```python {구체적인 해결 코드 또는 절차} ``` ### 발생 이력 Task-{ID} 최초 | Task-{ID} 재발 | ... -->

---

## severity 기준

|레벨|기준|
|---|---|
|critical|데이터 손실 또는 시스템 중단 가능|
|high|주요 기능 실패, 3회 이상 재발|
|medium|기능 저하, 우회 가능|
|low|사소한 불편, 코드 품질 이슈|