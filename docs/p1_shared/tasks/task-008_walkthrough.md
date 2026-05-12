# Task-008 Walkthrough: 물리적 DB 동기화 파이프라인 (db_sync.py)

## 1. 개요
- **Task ID**: T-008 (T-009 통합 흡수)
- **목표**: 대용량 시계열 DB(TimescaleDB)의 안전하고 완벽한 양방향 동기화를 위한 완전 자동화 파이프라인 구축
- **상태**: 완료
- **핵심 변화**: 과거 `pg_dump` 기반 논리적 동기화의 한계(외래키 에러, 메모리 한계, 타임아웃, 익스텐션 충돌 등)를 극복하기 위해, **데이터 폴더 자체를 물리적으로 복사하는 스톱-앤-카피(Stop-and-Copy)** 방식으로 전면 재설계했습니다. 과거 사용자가 수동으로 진행해야 했던 `Task-009`를 스크립트 기반 자동화(`db_sync.py`)로 완벽히 대체하여 통합 흡수했습니다.

## 2. 주요 구현 내용 및 파일 역할

### `p1_shared/ops/db_sync.py` (전면 개편)
물리 동기화의 안정성을 보장하기 위해 5단계 파이프라인으로 구성되었습니다.
1. **Preflight 점검**: SSH 접속 가능 여부를 확인합니다.
2. **컨테이너 중지 (Maintenance Mode)**: 데이터 쓰기를 원천 차단하여 무결성을 보장하기 위해, 양측 PC의 DB 컨테이너(`kdms_db`, `usdms_db` 등)와 연관 앱 컨테이너를 일시 중지합니다.
3. **물리 데이터 전송 (SSH Pipeline)**: 중간 디스크 소모(`tar` 파일 생성)를 생략합니다. `tar -czf` 스트림을 SSH 파이프로 넘겨, 수신 측에서 즉시 해제(`tar -xzf`)하여 속도와 효율을 극대화했습니다.
4. **권한 교정 (Permission Fix)**: 컨테이너 내부 UID(70)와 호스트 UID(1000)의 불일치로 인한 탐색기 접근 불가 및 PostgreSQL 기동 에러를 막기 위해, 수신 후 자동으로 `sudo chown -R 1000:1000`을 실행합니다.
5. **재기동 (Resume)**: 전송과 권한 세팅이 완료되면 중지했던 양측 컨테이너를 정상 기동합니다.

### `tests/test_db_sync.py` (전면 개편)
실제 데이터 파괴를 방지하기 위해 로컬 셸 실행(`subprocess.run`)과 원격 셸 실행(`ssh ...`)을 Mocking하여, 5단계의 명령어 생성 로직과 흐름을 엄격하게 검증했습니다.

## 3. 검증 방법 및 사용법 (T-009 통합)

향후 갱신된 데이터를 서버와 개발PC 간에 동기화할 때는 아래 명령어를 사용하십시오. 
이 단일 명령어가 기존 T-009의 수동 인계 절차를 모두 대신합니다.

```bash
# 개발PC(로컬)의 KDMS 데이터를 서버로 밀어넣을 때 (Push)
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db kdms --direction push

# 서버의 USDMS 데이터를 개발PC(로컬)로 가져올 때 (Pull)
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db usdms --direction pull
```

> **⚠️ 주의사항**
> 이 명령어는 대상 DB의 물리 폴더 전체를 덮어쓰는 파괴적인 작업이므로, 실행 시 "yes"를 입력해야만 진행됩니다. 스케줄러를 통한 자동화 적용 시에는 `--yes` 플래그를 추가하여 사용할 수 있습니다.

상세한 원리와 사용법 트러블슈팅 가이드는 `docs/p1_shared/ops/db_sync_guide.md` 문서를 참조하시기 바랍니다.
