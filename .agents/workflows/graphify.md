---
name: graphify
description: "사용자가 /graphify 슬래시 명령어를 입력했을 때 발동되는 워크플로우 진입점입니다."
---

# Graphify Workflow

이 워크플로우는 사용자가 `/graphify` 명령어를 호출했을 때 트리거되는 얇은 래퍼(Thin Wrapper)입니다. 

사용자가 이 명령어를 호출하면, 즉시 `.agents/skills/graphify/SKILL.md` 파일에 정의된 실제 지침과 로직을 따라 그래프 생성 및 분석 작업을 수행하십시오.

- 대상 경로가 지정되지 않은 경우 현재 디렉토리(`.`)를 대상으로 실행합니다.
- 특정 옵션(예: `--update`, `--mode deep`)이 주어진 경우 해당 옵션을 스킬 실행 시 반영합니다.
- 실행이 완료되면 사용자에게 분석 결과를 요약하여 보고합니다.
