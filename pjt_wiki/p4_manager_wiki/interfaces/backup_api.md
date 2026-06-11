# 물리 백업 및 환경 프로파일 API 규격 (F-11, F-12, F-16)

이 문서는 TDMS 통합 매니저(P4)의 로컬 물리 볼륨 백업 및 구동 장비 환경 감지 인터페이스 규격을 상세하게 정의합니다. 

---

## 1. 개요 및 안전 정책
* **목적**: 개발 PC 환경(백업 허브)에서 로컬 DB의 물리적 스냅샷 아카이브 생성을 지원하고, 서버 PC(운영계) 환경에서는 I/O 교란을 예방하기 위해 스냅샷 생성을 원천 차단합니다.
* **통제 방식**: FastAPI 백엔드 라우터에서 `EnvDetector`를 활용해 환경을 식별하고, `server` 환경일 경우 `POST /api/mgr/backup` 요청에 대해 HTTP 403 Forbidden 예외를 반환합니다.

---

## 2. API Endpoints 명세

### 2.1. 구동 환경 식별 (GET `/env`)
현재 인프라 구동 장비의 환경 프로파일 정보를 조회합니다.

* **요청 (Request)**:
  * Method: `GET`
  * Path: `/api/mgr/env`
* **응답 (Response)**:
  * Status: `200 OK`
  * Body (JSON):
    ```json
    {
      "env": "dev"
    }
    ```
    * `env` 값 종류: `"dev"` (개발 PC), `"server"` (서버 PC), `"unknown"` (기타)

---

### 2.2. 물리 백업 스냅샷 실행 (POST `/backup`)
로컬 TimescaleDB 데이터 볼륨 디렉토리를 `tar.gz` 형식으로 아카이빙합니다. **(개발 PC 환경에서만 승인, 시장 격리)**

* **요청 (Request)**:
  * Method: `POST`
  * Path: `/api/mgr/backup`
  * Query Parameter:
    * `market` (string, required): 백업 대상 시장 식별자 (`"kdms"` 또는 `"usdms"`).
    * `tag` (string, optional, default: `"manual"`): 백업 식별용 꼬리표 태그.
* **응답 (Response - 개발 PC 성공)**:
  * Status: `200 OK`
  * Body (JSON):
    * KDMS 예시:
      ```json
      {
        "status": "success",
        "path": "/app/backups/kdms/manual/physical_checkpoint_kdms_20260610_153022.tar.gz",
        "filename": "physical_checkpoint_kdms_20260610_153022.tar.gz",
        "market": "kdms",
        "tag": "manual",
        "size_bytes": 1048576,
        "created_at": "2026-06-10T15:30:22.451000"
      }
      ```
* **응답 (Response - 서버 PC 차단)**:
  * Status: `403 Forbidden`
  * Body (JSON):
    ```json
    {
      "detail": "서버 PC 환경에서는 물리 스냅샷 백업 생성을 수행할 수 없습니다. 개발 PC의 동기화 기능을 이용해 안전하게 백업을 확보하십시오."
    }
    ```

---

### 2.3. 백업 보관소 이력 조회 (GET `/backup/list`)
현재 백업 디렉토리에 아카이빙된 파일들의 목록을 최근 생성 역순(Desc)으로 리스팅합니다. (서버/개발 환경 무관 조회 가능)

* **요청 (Request)**:
  * Method: `GET`
  * Path: `/api/mgr/backup/list`
* **응답 (Response)**:
  * Status: `200 OK`
  * Body (JSON):
    ```json
    [
      {
        "path": "/app/backups/kdms/manual/physical_checkpoint_kdms_20260610_153022.tar.gz",
        "filename": "physical_checkpoint_kdms_20260610_153022.tar.gz",
        "market": "kdms",
        "tag": "manual",
        "created_at": "2026-06-10T15:30:22.451000",
        "size_bytes": 1048576,
        "verified": true
      }
    ]
    ```

---

### 2.4. 물리 백업 안전 복구 (POST `/restore`)
지정된 백업 파일 아카이브를 사용하여 개발 PC 로컬 DB의 물리적 스냅샷을 덮어쓰기 복구합니다. **(개발 PC 환경에서만 승인, 대상 시장 및 이중 안전 확인 문구 필수)**

* **요청 (Request)**:
  * Method: `POST`
  * Path: `/api/mgr/restore`
  * Body (JSON):
    ```json
    {
      "market": "kdms",
      "tag": "manual",
      "filename": "physical_checkpoint_kdms_20260610_153022.tar.gz",
      "confirm_text": "RESTORE LOCAL DB"
    }
    ```
* **응답 (Response - 개발 PC 성공 및 StartupValidator 진단)**:
  * Status: `200 OK`
  * Body (JSON):
    * KDMS 복구 시 예시:
      ```json
      {
        "status": "success",
        "message": "로컬 DB 물리 복구 및 컨테이너 재기동이 정상 완료되었습니다.",
        "validation_results": {
          "kdms": {
            "is_healthy": true,
            "is_connected": true,
            "missing_tables": [],
            "low_row_tables": {},
            "hypertable_ok": true
          }
        }
      }
      ```
* **응답 (Response - 서버 PC 차단)**:
  * Status: `403 Forbidden`
  * Body (JSON):
    ```json
    {
      "detail": "서버 PC 환경에서는 안전상의 이유로 복구 실행이 금지됩니다."
    }
    ```
* **응답 (Response - 확인 문구 미달 / 비정합)**:
  * Status: `400 Bad Request`
  * Body (JSON):
    ```json
    {
      "detail": "복구를 승인하려면 confirm_text에 정확히 'RESTORE LOCAL DB'를 입력해야 합니다."
    }
    ```

---

## 3. 관련 소스 코드 레퍼런스
* **백엔드 서비스 로직**: [backup_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/backup_service.py)
* **백엔드 라우터**: [manager.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/routers/manager.py)
* **백엔드 테스트 코드**: [test_restore.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/tests/test_restore.py)
* **프론트엔드 스토어**: [backupStore.ts](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/stores/backupStore.ts)
* **프론트엔드 UI 컴포넌트**: [BackupView.vue](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/views/BackupView.vue)
* **프론트엔드 테스트 코드**: [BackupView.spec.ts](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/tests/BackupView.spec.ts)

