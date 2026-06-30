# 네트워크 자가 감지 및 연결 검증 API (network_api.md)

> **상태**: ✅ 구현 완료 (T-010)
> **최근 업데이트**: 2026-06-11
> **소스 파일**:
> - [manager.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/routers/manager.py)
> - [sync_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/sync_service.py)

---

## 1. 개요
개발 PC가 부팅되거나 서버 PC의 IP가 PC 재부팅 등으로 인해 변동되었을 때, 이를 자동으로 추적 및 진단하고 수동으로 `.env` 파일과 환경 변수를 갱신, 검증하는 네트워크 제어 API 세트입니다.
WSL2 환경 하의 DNS 해석 문제 해결을 위해 powershell.exe DNS 리졸브 호출과 비동기 사설 C클래스 포트 스캔 기술이 유기적으로 탑재되어 있습니다.

---

## 2. API Endpoints 명세

### 2.1. 서버 IP 자가 감지 및 탐색
- **Method & Path**: `GET /api/mgr/network/detect-server`
- **Response (200 OK - DNS 리졸브 성공 시)**:
  ```json
  {
    "server_ip": "192.168.35.176",
    "method": "dns"
  }
  ```
- **Response (200 OK - 사설 대역 비동기 스캔 성공 시)**:
  ```json
  {
    "server_ip": "192.168.35.176",
    "method": "scan"
  }
  ```
- **Response (200 OK - 탐색 실패 시)**:
  ```json
  {
    "server_ip": null,
    "method": "failed"
  }
  ```

### 2.2. IP 환경 변수 및 .env 파일 갱신
- **Method & Path**: `POST /api/mgr/network/sync-ip`
- **Request Body (JSON)**:
  ```json
  {
    "target": "server",   // "server" 또는 "dev"
    "ip": "192.168.35.176"
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "status": "success",
    "message": "Successfully updated SERVER_IP to 192.168.35.176 in .env file"
  }
  ```
- **특징**: `.env` 파일 내 해당 행만 정규표현식으로 정밀 치환하여 다른 키-값 환경 변수의 유실을 완벽히 방지하며, OS 환경 변수(`os.environ`)에 즉각 주입 반영하여 백엔드 재기동 없이 즉시 변경 사항이 효력을 발휘합니다.

### 2.3. 특정 호스트 연결성 테스트
- **Method & Path**: `POST /api/mgr/network/test-connection`
- **Request Body (JSON)**:
  ```json
  {
    "ip": "192.168.35.176",
    "port": 8000
  }
  ```
- **Response (200 OK - 연결 성공)**:
  ```json
  {
    "connected": true,
    "message": "Connection Success"
  }
  ```
- **Response (200 OK - 연결 실패/IP 형식 오류)**:
  ```json
  {
    "connected": false,
    "message": "Socket connection failed: [Errno 111] Connection refused" // 혹은 "Invalid IP format"
  }
  ```

---

## 3. 서버 탐색 내부 메커니즘

1. **DNS Resolver 우회 (Powershell API 호출)**
   - WSL2 환경에서는 리눅스 커널의 DNS 캐싱 및 Windows Host Resolver와의 연동 불일치로 인해 서버 호스트명(`SERVER_HOSTNAME`)을 정상 파싱하지 못하는 경우가 빈번합니다.
   - 이를 극복하기 위해 `powershell.exe` 서브프로세스를 기동하여 Windows OS Native의 DNS API `[System.Net.Dns]::GetHostAddresses()` 를 우회 호출하여 IP를 강제 분해 획득합니다.
   
2. **사설 C클래스 포트 스캔 (Async Port Scanning)**
   - DNS 리졸브를 통해 획득한 IP가 통신에 실패하거나 호스트명이 제공되지 않았을 때, 개발 PC의 로컬 IP(예: `192.168.35.105`) 대역을 기반으로 사설 서브네트워크 영역(`192.168.35.1` ~ `192.168.35.254`)을 도출합니다.
   - Python `asyncio` 라이브러리를 동원해 254개 전체 호스트에 대해 TCP Port 8000 커넥션을 **병렬(Concurrent) 비동기 스캔**합니다. (타임아웃은 각 호스트당 200ms)
   - 커넥션이 열린 타깃 호스트들을 대상으로 `/api/mgr/env` API를 호출하고, 응답 데이터에 `{"env": "server"}`가 포함된 IP를 가려냄으로써 최종 서버를 동적으로 식별합니다.
