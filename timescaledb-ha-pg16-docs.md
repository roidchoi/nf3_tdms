# TimescaleDB HA (PostgreSQL 16) 사용 가이드

이 문서는 `timescale/timescaledb-ha:pg16` Docker 이미지를 사용하여 고가용성(High Availability) TimescaleDB 환경을 구축하고 운영하기 위한 최신 정보를 요약합니다.

## 1. 개요 (Overview)
`timescale/timescaledb-ha` 이미지는 단순한 TimescaleDB 익스텐션을 넘어, 실제 운영 환경(Production)에서 필요한 고가용성 솔루션과 백업 도구가 포함된 올인원 이미지입니다. 특히 PostgreSQL 16 버전을 기반으로 하여 최신 기능과 최적화된 성능을 제공합니다.

### 포함된 주요 구성 요소
*   **PostgreSQL 16**: 안정적인 관계형 데이터베이스 엔진.
*   **TimescaleDB**: 시계열 데이터 최적화 익스텐션.
*   **Patroni**: 자동 장애 조치(Failover) 및 복제 관리를 위한 HA 솔루션.
*   **pgBackRest**: 안정적인 백업 및 복구 관리 도구.
*   **PostGIS**: 지리 정보 시스템(GIS) 지원 익스텐션.

---

## 2. 주요 특징 (Key Features)
*   **고가용성 (HA)**: Patroni를 내장하여 클러스터 상태를 모니터링하고 자동 장애 조치를 수행합니다.
*   **백업 및 복구**: pgBackRest를 통해 증분 백업 및 특정 시점 복구(PITR)가 가능합니다.
*   **자동 튜닝**: 컨테이너 시작 시 `timescaledb-tune`이 실행되어 시스템 리소스에 맞게 `postgresql.conf` 설정을 자동으로 최적화합니다.
*   **Kubernetes 최적화**: Helm 차트를 통한 K8s 배포에 최적화되어 있으며, 엄격한 권한 및 경로 구조를 가집니다.

---

## 3. 설정 및 환경 변수 (Configuration)

### 자동 튜닝 (Timescaledb-tune)
컨테이너의 리소스에 맞춰 설정을 제어할 수 있습니다.
*   `TS_TUNE_MEMORY`: 튜닝에 사용할 메모리 제한 설정 (예: `4GB`).
*   `TS_TUNE_NUM_CPUS`: 튜닝에 사용할 CPU 개수 설정 (예: `4`).
*   `TS_TUNE_MAX_BG_WORKERS`: `timescaledb.max_background_workers` 값 설정.
*   `NO_TS_TUNE`: `true`로 설정 시 자동 튜닝을 비활성화합니다.

### 표준 PostgreSQL 환경 변수
*   `POSTGRES_PASSWORD`: `postgres` 슈퍼유저의 비밀번호.
*   `POSTGRES_DB`: 초기 생성할 데이터베이스 이름.
*   `POSTGRES_USER`: 기본 슈퍼유저 이름 변경 시 사용.

### HA 이미지의 특이사항 (중요)
*   **PGDATA 경로**: 기본값이 `/home/postgres/pgdata/data`로 고정되어 있습니다. 볼륨 마운트 시 이 경로를 사용해야 합니다.
*   **권한 (Permissions)**: 이미지는 `UID 1000:GID 1000` (postgres 사용자)으로 실행됩니다. 호스트 볼륨 마운트 시 해당 디렉토리의 소유권이 `1000:1000`이어야 합니다.

---

## 4. 실행 가이드 (Deployment)

### Docker 실행 예시
단일 컨테이너로 테스트 시 아래와 같이 실행할 수 있습니다. (HA 기능을 온전히 사용하려면 Kubernetes나 다중 컨테이너 환경 권장)

```bash
docker run -d \
  --name timescaledb-ha \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=mysecretpassword \
  -v timescaledb_data:/home/postgres/pgdata/data \
  timescale/timescaledb-ha:pg16
```

### 환경 설정 파일 추가 (Custom Config)
추가적인 설정이 필요한 경우 `/etc/postgresql/postgresql.conf.d/` 디렉토리에 `.conf` 파일을 마운트하여 적용할 수 있습니다.

---

## 5. 권장 사항 및 베스트 프랙티스
1.  **텔레메트리 관리**: 초기 설치 후 `TIMESCALEDB_TELEMETRY=off` 환경 변수를 통해 데이터 수집을 비활성화할 수 있습니다.
2.  **데이터 영속성**: 반드시 외부 볼륨(Docker Volume 또는 K8s PVC)을 사용하여 데이터를 보존하십시오.
3.  **리소스 할당**: `TS_TUNE_MEMORY`를 실제 컨테이너에 할당된 메모리보다 약간 낮게 설정하여 OOM(Out of Memory)을 방지하십시오.
4.  **보안**: 운영 환경에서는 반드시 기본 `postgres` 사용자 외에 필요한 권한만 가진 별도 사용자를 생성하여 사용하십시오.

---

## 참고 링크
*   [TimescaleDB 공식 문서](https://docs.timescale.com/)
*   [TimescaleDB Docker HA GitHub](https://github.com/timescale/timescaledb-docker-ha)
