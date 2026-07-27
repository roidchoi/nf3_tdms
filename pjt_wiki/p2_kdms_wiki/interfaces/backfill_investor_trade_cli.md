# Investor Trade CLI 백필 스크립트 인터페이스 (`scripts/backfill_investor_trade_by_year.py`)

> **최초 작성일**: 2026-07-25  
> **관련 모듈/파일**: [`scripts/backfill_investor_trade_by_year.py`](file:///home/roid2/pjt/nf3/01_nf3_tdms/scripts/backfill_investor_trade_by_year.py), [`tdms_core/p2_kdms/repositories/investor_trade_repo.py`](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/investor_trade_repo.py)

---

## 1. 개요 (Overview)

한국 주식시장 일별 투자자 매매동향(수급) 데이터를 연도별로 안정적으로 분할 백필하기 위한 독립형 CLI 스크립트. KIS API 호출 스로틀링(초당 4회 제한), 데이터 가공, 커넥션 풀 자원 정리를 안전하게 수행합니다.

---

## 2. CLI 인자 및 사용법 (Arguments & Usage)

```bash
# 기본 사용법 (Conda 환경 tdms_p2_env 필수)
conda run -n tdms_p2_env python scripts/backfill_investor_trade_by_year.py --start-year 2024 --end-year 2025 --skip-existing
```

### 파라미터 옵션

| 인자명 | 타입 | 기본값 | 설명 |
| :--- | :--- | :--- | :--- |
| `--start-year` | `int` | `2026` | 백필 시작 연도 |
| `--end-year` | `int` | `2026` | 백필 종료 연도 |
| `--skip-existing` | `flag` | `False` | 설정 시 해당 연도 이미 수집된 종목 스킵 처리 |
| `--test-mode` | `flag` | `False` | 설정 시 상위 3개 종목만 테스트 수집 수행 |

---

## 3. 진행률 로깅 규격 (Progress Format)

표준 수급 백필 진행률 로그 템플릿:
`[YYYY년 수급 백필] Progress: XX.X% (idx/total) | Speed: X.X it/s | Elapsed: Xs | ETA: HH:MM:SS | Current: symbol`

---

## 4. 자원 해제 및 프로세스 종료 보장 (Process Lifecycle)

* 작업 완료 시 DB 커넥션 풀 반환 `pool.closeall()` 및 표준 출력 버퍼 방출 `sys.stdout.flush()`, `sys.exit(0)`을 호출하여 터미널 세션 프롬프트 복구를 보장합니다.
