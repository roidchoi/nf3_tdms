---
id: {SUB}ERR-{N}
sub_project: p{n}
severity: {low/medium/high/critical}
status: confirmed
last_seen: Task-{ID}
related: [[path/to/related/file]]
---

# [{SUB}ERR-{N}] {에러 제목}

### 발생 패턴 및 재현 조건
- **환경**: {OS, Python 버전 등}
- **발생 시점**: {어떤 함수/API 호출 시}
- **재현 방법**:
  1. ...
  2. ...

### 실제 에러 로그 (요약 금지)
```text
{실제 에러 traceback 전체 붙여넣기}
```

### 원인
- {에러 발생의 근본 원인 상세 설명}
- 원인 코드 경로: `{경로}:{라인번호}`

### 해결법 (필수)
- **해결 절차**:
  1. ...
- **수정된 코드**:
```python
{수정된 코드 블록}
```

### 발생 이력
- Task-{ID} 최초 발생
