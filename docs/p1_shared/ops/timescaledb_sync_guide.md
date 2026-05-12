# TimescaleDB 데이터 인계 및 동기화 가이드 (v2.0 - 최종본)

본 문서는 개발PC(WSL2)와 서버PC(Docker) 간의 대규모 TimescaleDB(37GB+, 2.5억 건) 이전 과정에서 발생한 설계적 결함과 이를 해결한 최종 표준 프로토콜을 기록합니다.

## 1. 잘못된 시도와 교훈 (Failure Analysis)

### ❌ 실패 1: 논리적 덤프(`pg_dump`) 및 복원(`pg_restore`)
*   **시도**: SQL/Custom 포맷으로 데이터를 덤프하여 `pg_restore` 수행.
*   **결과**: 하이퍼테이블 메타데이터(Catalog) 불일치로 인해 데이터는 전송되나 테이블 조회가 불가능하거나, 복원 시 `out of shared memory`로 인한 시스템 마비 발생.
*   **교훈**: 1억 건 이상의 대규모 시계열 데이터는 논리적 백업이 아닌 **물리적 바이너리 복제**가 유일하고 정확한 해답임.

### ❌ 실패 2: 가동 중인 어플리케이션과의 간섭
*   **시도**: DB만 복원하면 된다고 생각하여 백엔드/프론트엔드 컨테이너를 기동한 상태로 작업.
*   **결과**: 컨테이너 재시작 시 스케줄러가 자동 실행되어 인계받은 깨끗한 데이터에 오늘 자 신규 데이터가 유입(Pollution)됨.
*   **교훈**: 데이터 인계 시에는 **모든 어플리케이션을 중지**하고 DB만 격리하여 작업해야 함.

### ❌ 실패 3: 도커 설계 및 환경 설정 무시
*   **시도**: 도커 볼륨 마운트 경로와 내부 `PGDATA` 경로의 불일치를 간과함.
*   **결과**: `/var/lib/postgresql/data`에 데이터를 부었으나, 엔진은 내부의 다른 경로(`/home/postgres/pgdata/data`)를 보고 있어 데이터가 증발한 것처럼 보임.
*   **교훈**: `PGDATA` 환경 변수를 명시적으로 일치시키고, `init.sql` 등 자동 초기화 스크립트 마운트를 해제하여 데이터 덮어쓰기를 방지해야 함.

---

## 2. 올바른 마이그레이션 프로토콜 (The Protocol)

### 단계 1: 환경 격리 및 스케줄러 차단
서버의 `docker-compose.yml`에서 앱 서비스를 주석 처리하거나 중지하여 외부 유입을 100% 차단합니다.

### 단계 2: 물리적 데이터 추출 (Physical Extraction)
개발PC의 실제 데이터 경로를 확인하고, 바이너리 레벨에서 통째로 압축합니다.
```bash
# 컨테이너 내부의 실제 DATA_DIRECTORY 확인 후 실행
docker exec kdms_timescaledb tar -czf /tmp/physical.tar.gz -C /home/postgres/pgdata/data .
docker cp kdms_timescaledb:/tmp/physical.tar.gz ./kdms_physical_backup.tar.gz
```

### 단계 3: 서버 볼륨 초기화 및 주입
서버의 기존 볼륨을 물리적으로 삭제하고, 압축 파일을 해제합니다. 이때 **사용자 권한(UID/GID)**을 서버 도커 환경에 맞게 강제 교정합니다.
```bash
docker volume rm kdms_db_data && docker volume create kdms_db_data
# 주입 후 권한 교정 (서버 환경에 따라 1000:1000 또는 999:999)
docker run --rm -v kdms_db_data:/data alpine chown -R 1000:1000 /data
```

### 단계 4: 설정 파일 정립 (Config Alignment)
바이너리 복제 시 설정 파일(`postgresql.conf`, `pg_hba.conf`)이 꼬이지 않도록 다음과 같이 조치합니다.
1.  `docker-compose.yml`에서 호스트 설정 파일 바인드 마운트 해제.
2.  `PGDATA` 환경 변수를 볼륨 경로와 일치시킴.
3.  최초 기동 시 `listen_addresses`와 `pg_hba.conf`를 수동으로 안전하게 주입.

---

## 3. 정립된 운영 설정 (Best Practices)

1.  **데이터 무결성 검사**: 행 수(Count)만 보지 말고, 테이블별 **첫 행과 끝 행의 전체 필드 값**을 대조할 것.
2.  **하이퍼테이블 관리**: 청크 사이즈가 너무 작아 메모리 부족이 발생하는 경우, 복제된 환경에서 `set_chunk_time_interval`을 통해 설정을 최적화할 것.
3.  **초기화 스크립트 주의**: 운영 중인 DB에는 `init.sql`이 마운트되어 있으면 재기동 시 예기치 않은 스키마 변경이 발생할 수 있으므로, 초기 구축 이후에는 마운트를 해제함.

---
**이 가이드는 2026-05-07 발생한 37GB 데이터 인계 실패를 물리적 복제로 해결한 실전 경험을 바탕으로 작성되었습니다.**
