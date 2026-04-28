# USDMS Migration and Co-existence Plan (to KDMS Production PC)

본 문서는 현재 개발된 **USDMS**를 기존 **KDMS**가 운영 중인 리눅스 운영 PC로 이관하여 함께 운영하기 위한 절차와 리스크 점검 내용을 담고 있습니다.

## 1. KDMS와 동일 PC 운영 적합성 점검 (Pre-Migration Check)

분석 결과, USDMS는 이미 KDMS와의 충돌을 피하도록 설계되어 있어 동일 PC 운영에 큰 문제가 없습니다.

### 포트 및 리소스 충돌 여부
| 항목 | KDMS (기존) | USDMS (이관 대상) | 충돌 여부 | 비고 |
| :--- | :--- | :--- | :--- | :--- |
| **DB Port** | 5432 | **5435** | **없음** | `.env` 설정 확인 완료 |
| **Backend Port** | 8000 | **8005** | **없음** | `.env` 설정 확인 완료 |
| **DB Name** | `kdms_db` | `usdms_db` | **없음** | 독립적인 데이터베이스 사용 |
| **Docker Network** | `kdms-net` | `usdms_net` | **없음** | 브릿지 네트워크 분리 |
| **스케줄링 시간** | 한국 시장 마감 후 | 미국 시장 마감 후 | **운영 분산** | KR(15:30), US(06:00 KST) |

### 성능 리스크 (Performance Risks)
1.  **메모리(RAM)**: TimescaleDB는 인메모리 인덱싱을 선호합니다. 두 시스템 합산 최소 16GB 이상(추천 32GB 이상)을 권장합니다.
2.  **디스크 I/O**: 대량의 OHLCV 데이터와 XBRL 파싱 데이터가 누적되므로 **SSD/NVMe** 사용이 필수적입니다.
3.  **CPU**: 초기 데이터 적재(Backfill) 시에는 CPU 점유율이 높을 수 있으나, 일일 운영 시에는 두 시스템이 구동되는 시간대가 달라 충돌이 적습니다.

---

## 2. 이관 준비 사항 (Preparation)

1.  **프로젝트 복제(Git Clone)**: 운영 PC의 대상 경로(예: `~/pjt/ag/`)에서 저장소를 클론합니다.
    ```bash
    mkdir -p ~/pjt/ag && cd ~/pjt/ag
    
    # 원하는 프로젝트 폴더명(예: usdms_prod)을 지정하여 클론합니다.
    git clone https://github.com/your-repo/01_usdms.git <대상_폴더명>
    cd <대상_폴더명>
    ```
    > [!NOTE]
    > 저장소 URL은 실제 프로젝트의 Git URL로 대체하십시오.

2.  **Docker 환경**: 운영 PC에 `docker` 및 `docker-compose`가 설치되어 있어야 합니다.
3.  **Python 환경**: 운영 PC에서 관리 스크립트를 실행하기 위해 `conda` 환경(또는 `venv`) 구축이 필요합니다.

---

## 3. 이관 절차 (Migration Procedure)

### Step 1: 환경 설정 확인
운영 PC의 최상위 루트에 위치한 `.env` 파일을 확인하여 아래 설정이 실제 운영 환경과 맞는지 점검합니다.
- `POSTGRES_PORT=5435`
- `BACKEND_PORT=8005`
- `SEC_USER_AGENT`: 실제 연락 가능한 이메일 정보로 업데이트 (SEC 차단 방지)

### Step 2: DB 데이터 이관 (개발 PC -> 운영 PC)

개발 PC의 데이터를 운영 PC로 이관하기 위해 체크포인트 파일을 활용합니다.

1.  **개발 PC: 백업 생성**
    ```bash
    # 개발 PC에서 실행
    python ops/run_db_checkpoint.py migration_target
    ```
    - 결과물: `backups/checkpoint_migration_target_YYYYMMDD_HHMMSS.dump` 생성 확인

2.  **데이터 전송**
    - 위에서 생성된 `.dump` 파일을 운영 PC의 `backups/` 폴더로 수동 복사(SCP, USB 등)합니다.

3.  **운영 PC: 컨테이너 구동 (DB만 우선 실행)**
    ```bash
    cd ~/pjt/ag/01_usdms/
    docker-compose up -d timescaledb
    ```

4.  **운영 PC: 데이터 복원**
    ```bash
    # 컨테이너 내에서 pg_restore 실행
    # (주의: -d usdms_db 옵션으로 대상 DB 지정)
    docker exec -i usdms_db pg_restore -U postgres -d usdms_db -c --if-exists < backups/checkpoint_filename.dump

    docker exec -i usdms_db pg_restore -U postgres -d usdms_db -c --if-exists < backups/checkpoint_migration_target_20260203_181023.dump


    ```
    - `-c --if-exists`: 기존 테이블을 드롭하고 복원 (초기 셋업 시 권장)

### Step 3: 복원 결과 확인 및 워닝 대응 (Troubleshooting)

`pg_restore` 중 `role "readonly_analyst" does not exist` 와 같은 에러가 발생하는 것은 **정상적인 현상**일 가능성이 높습니다.

- **원인**: 개발 환경에서 설정했던 특정 사용자 권한(GRANT) 정보가 운영 환경 DB에는 없기 때문에 발생하는 권한 할당 실패 메시지입니다.
- **영향**: 데이터(Table, Rows, Indexes) 자체의 복원과는 무관하며, 해당 유저에 대한 권한 부여만 실패한 것입니다. 
- **조치**: 아래의 [데이터 검증] 단계를 통해 데이터가 정상적으로 들어왔는지 확인하십시오.

### Step 4: 데이터 검증 (Verification)

운영 PC의 DB 컨테이너에 접속하여 데이터가 정상적으로 복원되었는지 확인합니다.

```bash
# DB 접속
docker exec -it usdms_db psql -U postgres -d usdms_db

# 1. 테이블 목록 확인
\dt

# 2. 주요 테이블 데이터 건수 확인 (예시)
SELECT count(*) FROM us_ticker_master;
SELECT count(*) FROM us_daily_price;
SELECT count(*) FROM us_standard_financials;

# 3. 하이퍼테이블(Hypertables) 설정 확인
# 아래 명령 실행 시 반드시 끝에 세미콜론(;)을 붙여야 합니다.
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;

# 4. 인덱스 및 상세 구조 확인
\d us_daily_price
# 결과 하단에 'Number of child tables: XXXX'가 보인다면 하이퍼테이블이 정상적으로 조각(Chunk) 단위로 복원된 것입니다.
```

데이터 건수와 하이퍼테이블 구조가 확인되었다면 복원은 완벽하게 성공한 것입니다.

### Step 5: 세션 종료 및 컨테이너 탈출
- **psql 종료**: `\q` 입력 또는 `Ctrl + D`
- **컨테이너 탈출**: (터미널 세션이 유지된 경우) `exit` 입력

### Step 6: 백엔드 컨테이너 구동
```bash
# 복원이 완료된 후 백엔드 실행
docker-compose up -d backend

# 전체 서비스 상태 확인
docker-compose ps
```

### Step 3: DB 초기화 및 성능 최적화
- `docker-compose` 실행 시 `backend/init/init.sql`이 자동으로 실행되어 스키마가 생성됩니다.
- 로그를 통해 테이블 및 하이퍼테이블(Hypertables) 생성을 확인합니다.
  ```bash
  docker-compose logs -f timescaledb
  ```

### Step 4: Python 운영 환경 구축
```bash
# 콘다 환경 생성
conda create -n usdms_env python=3.12 -y
conda activate usdms_env

# 의존성 설치 (uv 사용 권장)
# 만약 tqdm, yfinance 등이 누락되었다면 아래 명령어로 다시 설치하십시오.
uv pip install -r backend/requirements.txt
```

### Step 5: 시스템 진단 실행
연결성 및 로직이 정상인지 확인하기 위해 진단 스크립트를 실행합니다.
```bash
python ops/run_diagnostics.py
```

---

## 4. 운영 가이드 (Operational Guide)

### 일일 루틴 자동화 (Crontab 설정)
미국 시장 마감(평시 06:00 KST, 서머타임 05:00 KST) 이후 데이터를 수집하도록 스케줄링합니다.
```bash
# crontab -e
# 매주 화-토 오전 07:00 실행 (미국 시장 월-금 데이터 수집)
0 7 * * 2-6 /home/user/anaconda3/envs/usdms_env/bin/python /home/user/pjt/ag/01_usdms/ops/run_daily_routine.py >> /home/user/pjt/ag/01_usdms/logs/daily_cron.log 2>&1
```

### 모니터링
1.  **DB 락 체크**: 프로세스가 꼬였을 경우 `python ops/kill_db_locks.py` 실행
2.  **백업**: 주기적으로 `python ops/run_db_checkpoint.py`를 통해 스냅샷 생성

---

## 5. 결론 및 건의
현재 설정 기준으로 KDMS와의 **공존에는 기술적 장애물이 없습니다.** 다만, 운영 중 메모리 부족 현상이 발생할 경우 Docker 컨테이너의 메모리 제한(limits)을 설정하거나 PC의 RAM을 증설하는 것을 권장합니다.
