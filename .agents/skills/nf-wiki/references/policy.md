# Wiki 운영 정책 (policy.md)

> **버전**: v4.1 (Atomic & Compounding Edition)
> **이 파일의 역할**: `nf-wiki` 스킬이 참조하는 운영 규칙의 단일 출처. 지식의 파편화를 막고 복리 효과를 극대화하기 위해 위키 업데이트 전 반드시 이 지침을 읽고 확인해야 합니다.

---

## 1. 업데이트 의무 규칙 (Mandatory Updates)

| 트리거 | 의무 업데이트 파일 (경로) | 담당 |
| --- | --- | --- |
| 모든 Task 완료 | `00_schema/log.md`, `00_schema/index.md` | Antigravity (필수 MoC 및 로그 최신화) |
| 폴더/모듈 구조 변경 | `p{n}_wiki/codebase_map.md` | Antigravity (현행화: ✅/🔄/⬜ 상태 표시) |
| 개발환경/패키지 변경 | `p{n}_wiki/environment.md` | Antigravity (즉시 반영, 버전 명시) |
| DB/API/함수 시그니처 변경| `p{n}_wiki/interfaces/` 내 개별 엔티티 | Antigravity (**원자적 분리**) |
| 에러 발생 및 해결 | `p{n}_wiki/errors/` 내 개별 엔티티 | Antigravity (**원자적 분리**, 해결법 포함 필수) |
| 기술적 의사결정 발생 | `decisions/` 내 개별 엔티티 | Antigravity (ADR 형식) |
| 실험/평가 완료 | `operations/experiments.md` | Antigravity |
| 공통 정책/아키텍처 | `parent_wiki/` 내 관련 문서 | Antigravity (프로젝트 전반 영향도 고려) |

---

## 2. 지식 원자화 및 상세 유지 규칙 (Atomic Detail)

### 2.1. 엔티티 기반 분절화 (Atomization)
- `interfaces.md`나 `errors.md`와 같은 거대 파일에 내용을 무작정 추가하지 않습니다.
- 특정 기능이나 특정 에러 단위로 **개별 `.md` 파일**을 생성하여 `interfaces/` 또는 `errors/` 디렉토리에 저장합니다.
- **파일명 규칙**: `feature_name.md` 또는 `error_code_summary.md` (공백 대신 언더바 사용).

### 2.2. 정보 열화 방지 (No Summarization - 환각 방지)
- **절대 요약 금지**: LLM의 환각(Hallucination)을 방지하기 위해 코드 경로, 라인 번호, 정확한 타입(예: `pl.DataFrame`, `Optional[int]`, `TEXT`, `REAL`), 실제 에러 로그 전체를 그대로 보존해야 합니다.
- **Context Link**: 해당 지식이 참조하는 소스 코드 파일의 원본 경로를 반드시 명시합니다.

### 2.3. 특정 항목 작성 가이드
- **errors**: **해결법이 없으면 등록 금지**. 발생 원인만 있는 항목은 불필요한 노이즈를 만듭니다. 재발 시 기존 파일의 "발생 이력"에 Task ID를 추가하고, 2회 이상 재발 시 severity를 high로 승격합니다.
- **codebase_map.md**: **"현재 상태" 기준만** 작성하며, 미래 계획은 혼재하지 않습니다. 상태 표시(✅/🔄/⬜)가 필수입니다.
- **environment.md**: 패키지 버전은 실제 설치 버전으로 기재하며(범위 표기 금지), 알려진 이슈는 해결법/회피법이 있을 때만 등록합니다.

---

## 3. 지식 연결 및 합성 규칙 (Linking & Compounding)

### 3.1. 상호 참조 (Cross-Referencing)
- 새로운 문서를 생성하거나 기존 문서를 수정할 때, 연관된 지식으로의 링크를 반드시 삽입합니다.
- **링크 형식**: `[[path/to/file]]` (Obsidian 스타일 상호 참조).
  - 예: 에러 문서 내에 `원인: [[p2_wiki/interfaces/ecos_api]]의 타임아웃 설정 미비`

### 3.2. MoC (Map of Content) 관리
- `00_schema/index.md`는 단순 목록이 아닌 **지능형 지도**입니다.
- 새로운 원자적 파일이 생성되면, `index.md`의 해당 카테고리에 **한 줄 요약과 상태**를 업데이트하여 LLM이 지식의 위치를 즉시 파악할 수 있게 합니다.

---

## 4. 계층적 위키 운용 지침 (Hierarchy)

- **parent_wiki/**: 전체 프로젝트의 공통 가이드라인, 전역 아키텍처, 공통 데이터 스키마 등을 관리합니다.
- **p{n}_wiki/**: 특정 서브 프로젝트(p1, p2 등)에 국한된 코드 구조(`codebase_map`), 환경(`environment`), 세부 인터페이스 및 에러를 관리합니다.
- **전파 규칙**: 서브 프로젝트에서 발견된 지식이 전사적으로 유용하다고 판단될 경우, `parent_wiki`로 승격(Promotion)하여 기록합니다.

---

## 5. 지식 건강검진 (Linting)

Antigravity는 `.agents/skills/nf-wiki/references/wiki_lint_guideline.md`의 절차에 따라 주기적으로 물리적/논리적 동기화를 점검하고 다음 사항을 보고해야 합니다.
1. **고립된 문서(Orphan)**: 참조되지 않고 `index.md`에도 누락된 문서.
2. **정보 모순(Conflict)**: `interfaces/` 명세와 `errors/` 사례가 충돌하는 경우.
3. **낡은 정보(Stale)**: 오랫동안 현행화되지 않은 항목.

---

## 6. Antigravity 주도권

- **읽기 및 쓰기**: 모든 wiki 업데이트는 Antigravity가 주도적으로 수행합니다.
- **적극성**: 위키는 단순한 결과물이 아니라 **Antigravity의 인지 과정**입니다. 코드를 수정하거나 에러를 잡는 과정에서 "나중의 나(또는 다른 에이전트)"가 알아야 할 가치가 있다고 판단되면, 사용자의 명시적 요청이 없더라도 작업 완료 시점에 위키 반영을 적극 제안/수행해야 합니다.

---
**최종 확인**: 위 지침을 어기고 정보를 한 파일에 몰아넣거나(원자화 무시) 중요한 코드를 요약하는 행위는 지식의 복리 효과를 저해하는 **정책 위반**으로 간주합니다.
