# [P4-ERR-010] 정밀 감사 리포트 구동 시 Conda 누락 및 DB 비밀번호 오류

- **분류**: P4 Manager 에러
- **Severity**: High
- **발생 Task ID**: T-110 (물리 동기화 및 감사 리포팅)
- **Context Link**: [sync_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/sync_service.py), [audit_deep.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/ops/auditors/audit_deep.py)

## 1. 현상
- 동기화 후 페이지 하단 정밀 감사 리포트(Deep Audit Report) 영역 호출 시 백엔드 내부 콘솔에 `[Errno 2] No such file or directory: 'conda'` 예외가 출력되며 리포트 생성이 강제 중단되고 프론트엔드 UI에 빈 내용만 렌더링되었습니다.
- 추가로 DB 패스워드 로드 실패로 인해 `audit_deep.py` 감사기 내부에서 Postgres 인증 에러(`FATAL: password authentication failed for user "roid"`)가 유발되었습니다.

## 2. 원인
1. **백엔드 컨테이너 내 Conda 부재**: 
   - `sync_service.py`는 기존에 `conda run -n tdms_p1_env python ...`을 활용해 감사 모듈(`audit_deep.py`)을 격리 구동하도록 코딩되어 있었습니다.
   - 하지만 배포용 `p4_backend` 도커 이미지 내부에는 Conda 환경 관리자 및 `tdms_p1_env` 가상환경이 존재하지 않아 subprocess 실행 과정에서 `conda` 실행기를 찾지 못해 크래시가 났습니다.
2. **`POSTGRES_PASSWORD` 환경 변수 탐색 고립**:
   - `audit_deep.py` 및 관련 감사 스크립트들이 `POSTGRES_PASSWORD` 환경 변수가 누락되었을 때 기본값으로 `'password'` 혹은 빈 값을 읽어 로그인하려다가 원격지/로컬 DB의 실제 비밀번호(`pjsr104edml511`) 매핑을 누락하여 인증에 실패했습니다.

## 3. 해결책
1. **인터프리터 주소로 동적 Fallback**:
   - `sync_service.py` 내부의 `get_audit_report` 함수에서 `shutil.which("conda")`를 검사하도록 수정했습니다.
   - Conda 실행기가 시스템 경로상에 존재하지 않는 경우(즉 컨테이너 내부 환경인 경우), Conda를 거치지 않고 현재 기동 중인 백엔드 프로세스의 파이썬 인터프리터 경로인 **`sys.executable`**로 감사기 스크립트를 다이렉트 실행하도록 구조적 Fallback을 도입했습니다.
2. **DB 비밀번호 다중 탐색 기법 적용**:
   - `audit_deep.py` 내부에서 `POSTGRES_PASSWORD`가 비어있을 경우, 프로젝트 환경 변수 구조에 맞추어 `DEV_KDMS_DB_PASSWORD` 및 `SERVER_KDMS_DB_PASSWORD`를 순차 조회하여 적절한 비밀번호를 동적으로 주입하도록 코드를 보완했습니다.

## 4. 검증 결과
- 해당 패치 후 정밀 감사(KDMS / USDMS) 리포트 생성을 시도했을 때, 컨테이너 내부 런타임에서도 `sys.executable`을 통해 감사 프로세스가 정상 스레드로 기동되어, 6,300만 건 규모의 테이블을 포함한 정합성 교차 검증 및 무결성 100% 검증 보고서 출력이 중단 없이 원활하게 완료되었습니다.
