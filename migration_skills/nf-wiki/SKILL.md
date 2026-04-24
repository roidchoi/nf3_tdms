---
name: nf-wiki
description: 프로젝트 지식 관리 관제소. 세션 간 지식 축적을 위해 wiki(pjt_wiki)를 초기화하거나 업데이트한다.
when_to_use: 새로운 프로젝트의 위키 초기화, 작업 완료 후 지식(에러, 인터페이스, 결정사항 등) 문서화 및 전파
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, ListDir, RunCommand
---

# nf-wiki Skill (v2.0)

프로젝트 중 발생한 핵심 지식이 유실되지 않도록 **pjt_wiki** 구조를 관리하고 최신화를 자동화합니다. 

> [!TIP]
> 이 스킬은 하드코딩된 경로 대신 가변적인 프로젝트 구조를 지원하며, 내장된 템플릿(`.claude/skills/nf-wiki/templates/`)을 소스 모델로 사용합니다.

## 1. 역할 및 범위

- **[초기화 모드]**: 새로운 프로젝트 시작 시 표준 위키 구조를 생성합니다.
- **[업데이트 모드]**: 작업(Task) 완료 보고서를 분석하여 관련 위키 파일을 갱신합니다.
- **담당 범위**: 위키 파일 쓰기/수정, 인덱싱, 로그 관리.
- **비담당 범위**: 실제 코드 수정(Antigravity), 작업 명세서 작성(nf05), 위키 유효성 검사(nf-lint).

## 2. 변수 및 경로 정의

스킬 실행 시 아래 개념적 경로를 기반으로 동작합니다.

- `{WIKI_ROOT}`: 위키의 루트 폴더 (기본값: `./pjt_wiki`).
- `{SUB_PROJECT}`: 특정 서브 프로젝트 폴더 (예: `p1_wiki`). `task_spec`에서 확인.
- `{TEMPLATE_DIR}`: `.claude/skills/nf-wiki/templates/`.

## 3. [초기화 모드] 새로운 프로젝트 위키 구축

위키가 없는 새 프로젝트에서 실행 시 아래 절차를 따릅니다.

1. **구조 생성**: `{WIKI_ROOT}`를 생성하고 내부 구조(`00_schema`, `parent_wiki`)를 준비합니다.
2. **템플릿 복사**: `{TEMPLATE_DIR}` 내의 파일들을 `{WIKI_ROOT}`로 복사합니다.
3. **초기화**: `policy.md`, `index.md`, `overview.md` 등의 프로젝트 정보를 현재 상황에 맞게 초기화합니다.
4. **Sub Project 설정**: 필수가 아니면 사용자에게 서브 프로젝트(p1, p2...) 생성 여부를 확인합니다.

## 4. [업데이트 모드] 작업 완료 후 지식 축적

Antigravity의 작업 완료 보고서(Task-ID 포함)를 분석하여 위키를 갱신합니다.

### Step 1: 업데이트 대상 식별 (Checklist)
- [ ] **인터페이스**: DB 스키마나 함수 시그니처가 변경되었나? → `interfaces.md`
- [ ] **에러/해결**: 해결된 에러 정보가 확보되었나? → `errors.md`
- [ ] **구조 변경**: 폴더/파일 구조가 바뀌었나? → `codebase_map.md`
- [ ] **결정 사항**: 중요한 기술적 결정이 있었나? → `decisions.md`
- [ ] **실험 결과**: 테스트나 벤치마크 결과가 나왔나? → `experiments.md`
- [ ] **환경 변화**: 패키지 버전이나 설정이 바뀌었나? → `environment.md`

### Step 2: 문서 갱신 가이드
위키 갱신 시 반드시 `{TEMPLATE_DIR}` 내의 해당 파일 형식과 `{WIKI_ROOT}/00_schema/policy.md`를 참조합니다.

- **필수(Always)**: `log.md` (상단에 최신 내역 추가), `index.md` (업데이트 Task ID 갱신)
- **정보 보존**: `interfaces.md`는 요약하지 않고 상세 정보를 모두 기재합니다.
- **신뢰성**: `errors.md`는 해결법이 확인된 경우에만 등록합니다.

### Step 3: 완료 보고
업데이트 완료 후 사용자에게 어떤 파일이 갱신되었는지 보고하고 다음 단계(예: nf-lint 실행 권장)를 제안합니다.

## 5. 지침 및 주의사항

- **Single Source of Truth**: 모든 규칙은 `{WIKI_ROOT}/00_schema/policy.md`가 우선합니다.
- **최소 변경 원칙**: 전체 파일을 다시 쓰지 않고, 필요한 섹션만 `Edit` 툴을 사용해 수정합니다.
- **Sub Project 구분**: 여러 서브 프로젝트가 혼재된 경우, `task_spec`에 지정된 서브 프로젝트 위키 폴더를 정확히 식별합니다.
- **템플릿 활용**: 형식(Format)은 내장 템플릿과 동일하게 유지하여 일관성을 보장합니다.
