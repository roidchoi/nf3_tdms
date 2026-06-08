# Error: WSL2 바인드 마운트 동기화 유실 (USDMS 물리 DB 미인식)

> **에러 ID**: USDMS-ERR-001
> **Severity**: High (물리 데이터 마운트 유실 및 테이블 미존재 오진 유발)
> **발생 Task**: T-001 (프로젝트 기반 구조 및 DB 인계)
> **최종 수정일**: 2026-05-29
> **상태**: 해결 완료

---

## 1. 에러 현상 및 증상

- **현상**: 로컬 `usdms_timescaledb` 컨테이너가 정상적으로 실행 중(`Up`)인 상태이고 데이터베이스 포트(`5433`) 접속도 가능하지만, 데이터베이스 내에 테이블이 하나도 존재하지 않는 텅 빈 상태로 조회됨.
- **주요 탐지 로그 및 정황**:
  - `BaseRepository`를 이용해 접속 시 커커풀 가동에는 성공했으나, `us_` 접두사가 포함된 10종의 필수 테이블들이 `❌ 미존재`로 판정됨.
  - 호스트(WSL2)의 실제 물리 저장 폴더 `/home/roid2/pjt/nf3/01_nf3_tdms/data/usdms_db` 에는 `base`, `global` 등 37GB 이상의 대용량 바이너리 데이터가 정상 보존되어 있었음.
  - 결정적으로, 컨테이너 내부의 `postmaster.pid` 수정일자는 최근 도커 기동 시점으로 갱신되어 있으나, WSL2 호스트 상의 `postmaster.pid` 수정일자는 과거의 상태(예: May 12일자)로 고정되어 상호 시간 불일치가 확인됨.

---

## 2. 발생 원인

1. **WSL2 Bind Mount Sync Error (도커 마운트 유실)**:
   - Windows 호스트 및 Docker Desktop이 재부팅되는 과정에서 WSL2 내의 파일 링크/마운트가 꼬일 때 발생함.
   - 도커 데스크탑이 실행되면서 지정된 호스트 디렉토리를 바인딩하지 못하면, 도커 VM 내부의 임시 디렉토리를 강제로 마운트하여 컨테이너를 기동함.
   - 이로 인해 PostgreSQL 엔진은 마운트 폴더가 비어 있는 것으로 인식하고 내부적으로 완전히 새롭고 텅 빈 기본 데이터베이스 인스턴스(User: `roid`, Password: `password`)로 새로 초기화를 진행하여 실행해 버림.
2. **DHCP 환경에서의 IP 변경**:
   - 개발 PC의 재부팅 이후 외부 망 IP가 `.env`에 하드코딩되어 있던 `DEV_IP`와 달라지며 내부망 컨테이너 간의 네트워크 및 바인딩 매치 오작동이 유도됨.

---

## 3. 해결 및 복구 절차

1. **설정 롤백 및 IP 정합성 갱신**:
   - `.env`에 정의된 `DEV_IP`를 현재 재부팅 후 할당받은 윈도우 호스트 실제 IP로 갱신하여 네트워크 맵을 복구함.
     ```bash
     # EnvDetector를 사용하여 실제 IP 변경 감지 및 알림
     conda run -n tdms_p1_env python -c "from p1_shared.utils.env_detector import EnvDetector; EnvDetector().verify_dev_ip_sync()"
     ```
   - 임의로 수정했었던 `DEV_USDMS_DB_USER` 및 `DEV_USDMS_DB_PASSWORD` 설정을 5월 12일자 원본 복구 데이터의 로그인 정보인 `postgres` / `pjsr104edml511`로 원상 롤백함.
2. **컨테이너 완전 재기동 및 마운트 리프레시**:
   - 기동 중인 컨테이너들을 정지 및 해제하여 잘못 매핑된 볼륨 결합을 릴리즈함.
     ```bash
     docker compose down
     ```
   - WSL2 셸 상태에서 직접 컴포즈 업을 지시하여 물리 폴더에 대한 바인드 마운트 마크를 정확하게 동기화함.
     ```bash
     docker compose up -d
     ```
3. **마운트 유효성 및 데이터 무결성 검증**:
   - 컨테이너 내부의 `postmaster.pid` 갱신 여부를 다시 대조하여 날짜/시간 싱크가 맞물렸는지 확인.
     ```bash
     docker exec usdms_timescaledb ls -la /var/lib/postgresql/data/postmaster.pid
     ```
   - `p1_shared`에 구현된 감사 도구(`audit_usdms`) 혹은 핀포인트 스캔 쿼리를 구동하여 `us_` 접두사가 포함된 10종 테이블의 레코드 수가 대용량 원본 데이터와 일치하는지 시연.
     ```bash
     # 스캔 쿼리 구동 (us_ticker_master 등 10종 스캔 확인)
     conda run -n tdms_p3_env python scratch/verify_db_conn.py
     ```

---

## 4. 근본 방지 대책 (승인 및 적용 완료)

동일한 마운트 유실 현상이 재부팅 후 다시 발생하더라도, 무한 재시작 루프에 빠지지 않으면서 성능 및 서비스에 전혀 악영향을 주지 않고 스스로 복구할 수 있는 이중 방어막을 설계하여 적용 완료함.

### 1) [방안 B] 기동 시 1회 물리 마운트 자가 검증 및 횟수 제한 재시작 (docker-compose.yml)
- **개념**: DB 컨테이너가 처음 부팅되는 시점(Entrypoint 단계)에만 필수 테이블이 잘 마운트되었는지 딱 1회만 체크하고 종료하며, 실패 시 에러 코드(`exit 1`)와 함께 종료시켜 도커 컴포즈가 최대 5회까지만 리스타트를 해보도록 통제하는 기법.
- **적용**: `docker-compose.yml` 상에 `entrypoint` 및 `command`를 다음과 같이 오버라이드함.
  ```yaml
  kdms_db:
    restart: on-failure:5
    entrypoint: ["/bin/sh", "-c"]
    command:
      - |
        (
          sleep 15
          until pg_isready -h localhost -p 5432 -U roid; do sleep 2; done
          psql -U roid -d kdms_db -c "SELECT 1 FROM stock_info LIMIT 1;" > /dev/null 2>&1
          if [ $$? -ne 0 ]; then
            echo "❌ [KDMS 검증 실패] 물리 데이터 마운트 유실 또는 테이블 미존재 감지! 컨테이너를 중지합니다."
            kill -15 1
            exit 1
          else
            echo "✅ [KDMS 검증 통과] 물리 데이터 마운트 정합성 확보 완료."
          fi
        ) &
        exec docker-entrypoint.sh postgres
  ```
  *(USDMS 역시 동일하게 `us_ticker_master` 테이블을 감지하는 조건으로 대칭 구성 적용 완료)*
- **효과**: 정상 작동 시에는 15초 후 검증 통과 로그를 단 1회만 뿌리고 검증 루프가 완전히 종료되므로 기동 이후 상시 데이터 적재/조회 쿼리 성능에는 영향을 전혀 미치지 않음.

### 2) VirtioFS 파일 가상화 공유 설정 적용 가이드 (근본 원인 해소)
WSL2 배포판과 Windows Docker Desktop 간의 파일 바인딩 캐시 정합성을 커널 수준에서 강화하는 옵션을 켜두어 유실 현상을 방지함.
- **조치 방법**:
  1. Windows 작업 표시줄에서 **Docker Desktop GUI** 기동.
  2. 우측 상단의 톱니바퀴 아이콘 (**Settings**) 클릭.
  3. **General** 탭으로 이동.
  4. **Choose file sharing implementation for directory mounts** 설정 항목을 찾아 기존의 *gRPC FUSE*에서 **`VirtioFS`**로 체크박스 변경.
  5. 우측 하단의 **Apply & Restart**를 눌러 도커 데스크탑 서비스를 재시작함.
- **복구 및 롤백**: 해당 가상화 공유로 인해 호스트 환경이나 네트워크 에러 등 특이사항이 발견되면 언제든지 동일 경로에서 **gRPC FUSE**로 스위칭하여 10초 만에 기존 정상 상태로 원복 가능함.

