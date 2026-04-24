# 시스템 아키텍처 (architecture.md)

> **마지막 업데이트**: {YYYY-MM-DD} (Task-{ID})

---

## 1. Sub Project 구성 및 관계

```
{PROJECT_NAME}/
├── P1_{Name}   — {한줄 역할}
├── P2_{Name}   — {한줄 역할}
└── data/       — 공유 데이터 저장소
```

### Sub Project 간 의존 관계

```
P1_{Name}
    │ 출력: {데이터 형식/경로}
    ▼
P2_{Name}
    │ 출력: {데이터 형식/경로}
    ▼
{최종 결과물}
```

---

## 2. 전체 데이터 흐름

```
[외부 소스]
    │ {수집 방법}
    ▼
[P1: {레이어명}]  →  {저장소 (DB/파일)}
    │
    ▼
[P2: {레이어명}]  →  {저장소}
    │
    ▼
[결과물: {형식}]
```

---

## 3. 공유 자원

|자원|경로|접근 Sub Project|비고|
|---|---|---|---|
|공유 DB|data/{파일명}|P1, P2|{설명}|
|공유 데이터|data/{폴더}|P1, P2|git 제외|

---

## 4. 기술 스택 요약

|영역|기술|선택 근거|
|---|---|---|
|DB|{SQLite 등}|`parent_wiki/decisions.md#{DEC-ID}`|
|DataFrame|{Polars 등}|`p{n}_wiki/decisions.md#{DEC-ID}`|
|언어|Python {버전}|—|

---

## 5. 인터페이스 계약 (Sub Project 간)

> P1 출력 = P2 입력. 스키마 불일치는 즉시 양쪽 interfaces.md 동기화.

```
P1 출력 형식:
  {타입}: {컬럼 목록}

P2 입력 기대 형식:
  {타입}: {컬럼 목록}
```

상세: `p1_wiki/interfaces.md#{섹션}`, `p2_wiki/interfaces.md#{섹션}` 참조