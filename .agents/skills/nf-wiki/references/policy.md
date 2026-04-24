# Wiki 운영 정책 (policy.md)

> **버전**: v3.0 
> **이 파일의 역할**: nf-wiki skill이 참조하는 운영 규칙의 단일 출처. 위키 업데이트 전 반드시 읽어야 합니다.

---

## 1. 업데이트 의무 규칙

| 트리거 | 의무 업데이트 파일 | 담당 |
| --- | --- | --- |
| 모든 Task 완료 | 00_schema/log.md, 00_schema/index.md | Antigravity (nf-wiki) |
| DB/함수 시그니처 변경 | p{n}_wiki/interfaces.md | Antigravity (nf-wiki) |
| 에러 발생 + 해결 확인 | p{n}_wiki/errors.md | Antigravity (nf-wiki) |
| 폴더/모듈 구조 변경 | p{n}_wiki/codebase_map.md | Antigravity (nf-wiki) |
| 기술 의사결정 발생 | decisions.md + graph.md | Antigravity (nf-wiki) |
| 실험/평가 완료 | operations/experiments.md | Antigravity (nf-wiki) |
| 개발환경/패키지 변경 | environment.md | Antigravity (nf-wiki) (즉시) |

---

## 2. 정보 열화 방지 규칙 (환각 방지)

### interfaces.md
- **요약 금지** — LLM 환각(Hallucination) 방지를 위해 정확한 타입, 컬럼명, 경로 전체 기재 필수.
- 타입은 실제 Python/SQL 타입으로 명시 (예: `pl.DataFrame`, `TEXT`, `REAL`)
- 함수 위치는 파일 경로와 라인 번호까지 기재

### errors.md
- **해결법 없으면 등록 금지** — 발생 원인만 있는 항목은 불필요한 노이즈를 만드므로 불허.
- 재발 시 "발생 이력"에 Task ID 추가 (삭제하지 않음)
- severity 변경은 재발 2회 이상 시 high로 승격

### codebase_map.md
- **"현재 상태" 기준만** — 미래 계획 혼재 금지
- 완성/진행중/미착수 상태 표시 필수 (✅/🔄/⬜)

### environment.md
- 패키지 버전은 실제 설치 버전으로 기재 (범위 표기 금지)
- 알려진 이슈는 해결법 또는 회피법이 있을 때만 등록

---

## 3. 교차 참조 규칙

- 다른 wiki 파일을 언급할 때: `{파일명}#{섹션ID}` 형식
  - 예: `p2_wiki/errors.md#ERR-001`
- 새 연결 발생 시 graph.md 즉시 업데이트

---

## 4. Antigravity 접근 규칙

- **읽기 및 쓰기**: 모든 wiki 업데이트는 Antigravity가 수행합니다.
- **주도성**: Antigravity가 코드를 수정하다가 발견한 중요 이슈/변경사항은 작업 완료 시 스스로 판단하여 위키에 적극적으로 반영해야 합니다.

---

## 5. Sub Project 추가 시 절차

1. `pjt_wiki/p{n}_wiki/` 폴더 생성
2. `templates/pn_wiki/` 파일 일체 복사 후 Sub Project 정보로 초기화
3. `00_schema/index.md`에 새 Sub Project 섹션 추가
4. `parent_wiki/architecture.md` 업데이트
5. `00_schema/log.md`에 항목 추가
