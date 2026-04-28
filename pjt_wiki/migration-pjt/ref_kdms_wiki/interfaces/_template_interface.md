# {인터페이스 명칭 (예: ecos_api / User 테이블)}

> 마지막 변경: Task-{ID}
> 소스 위치: `{Sub_Project}/path/to/file.py:{라인번호}`

### 1. 개요 및 목적
- {해당 함수, API, 또는 테이블의 역할}
- 연관된 문서: [[path/to/related/file]]

### 2. 상세 명세 (요약 금지)

#### [함수/API인 경우]
**입력 파라미터**:
| 파라미터명 | 타입 | 필수 여부 | 설명 | 기본값 |
|---|---|---|---|---|
| `{param1}` | `str` | Y | ... | ... |

**출력 형식**:
- 반환 타입: `dict` / `pl.DataFrame` 등
- 예시 응답:
```json
{
  "status": "ok",
  "data": [...]
}
```

#### [DB 테이블인 경우]
| 컬럼명 | SQL 타입 | 언어(Python) 타입 | 제약 조건 | 설명 |
|---|---|---|---|---|
| `id` | `INTEGER` | `int` | `PRIMARY KEY` | ... |
| `name` | `VARCHAR` | `str` | `NOT NULL` | ... |

### 3. 주의사항 및 의존성
- 호출 전 반드시 확인해야 할 상태나 제약조건
- 참고 에러: [[p{n}_wiki/errors/{SUB}ERR-{N}]]
