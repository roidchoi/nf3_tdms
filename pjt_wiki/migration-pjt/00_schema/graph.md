# Knowledge Graph

> **마지막 업데이트**: {YYYY-MM-DD} (Task-{ID})

---

## 사용 지침

파일 간 교차 참조를 명시적으로 관리한다. 새로운 의존 관계나 연결이 발생하면 즉시 추가. 형식: `출발_파일#섹션 → 도착_파일#섹션 | {연결 이유}`

---

## Sub Project 내부 연결

### p{n}_wiki 내부

```
{파일}#{섹션} → {파일}#{섹션} | {이유}
```

---

## Sub Project 간 연결

### P1 ↔ P2

```
p1_wiki/{파일}#{섹션} → p2_wiki/{파일}#{섹션} | {이유}
```

---

## Parent ↔ Sub 연결

```
parent_wiki/{파일}#{섹션} → p{n}_wiki/{파일}#{섹션} | {이유}
```

---

## 연결 유형 범례

|유형|의미|예시|
|---|---|---|
|`→`|단방향 참조|errors.md#ERR-001 → interfaces.md#parquet|
|`↔`|양방향 의존|p1 output ↔ p2 input|
|`∈`|포함 관계|decisions.md#DEC-001 ∈ architecture.md#db|

---

## 변경 이력

|날짜|Task|추가된 연결|
|---|---|---|
|{YYYY-MM-DD}|Task-{ID}|{연결 요약}|