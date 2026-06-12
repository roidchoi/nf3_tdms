# [P4-ERR-004] WSL2 AI 에이전트 브라우저 구동 및 포트 포워딩 연동 장애 해결 가이드

> **분류**: 개발 환경 (WSL2 / Windows Dual Environment)  
> **장애 심각도**: High (시각 정합성 및 브라우저 자동화 테스트 불가)  
> **최초 발생일**: 2026-06-11  

---

## 1. 장애 증상 및 원인 분석

### 1) 장애 증상
* AI 에이전트의 브라우저 서브에이전트(`browser_subagent` 등)가 웹 애플리케이션 화면 조회를 위해 브라우저를 기동할 때, 주소창 입력이 되지 않거나 통신 거부(`Connection Refused`)가 나며 빈 화면(또는 타임아웃)만 캡처되는 현상.
* WSL2 내부에서 직접 헤드리스 크로미움을 띄우려고 할 때 시스템 공유 라이브러리(`.so`) 누락 오류가 발생함.

### 2) 발생 원인
* **Playwright 의존성 유실**: WSL2 가상 머신 내부에 Playwright 브라우저 바이너리(Chromium) 및 Linux 전용 렌더링 의존성 패키지가 완벽히 캐싱되어 있지 않아 발생.
* **샌드박스 네트워크 격리 결함**: WSL2는 별도의 가상 서브넷을 사용하므로, Windows 호스트의 웹 서비스(`http://localhost/`)에 직접 로컬 루프백 접속을 시도할 때 포트 매핑이나 디버거 세션 바인딩을 통과하지 못함.
* **디버거 포트 바인딩 제한**: Windows 크롬의 원격 디버깅 포트(`9222`)는 기본적으로 Windows 내부의 루프백 주소(`127.0.0.1`)에 강제 바인딩되므로, 다른 가상 머신인 WSL2에서 Windows IP를 경유해 접근하려고 할 때 연결이 거부됨.

---

## 2. 단계별 복구 및 해결 방법 (Runbook)

다음의 5단계 절차를 수행하면 WSL2 세션에서도 Windows의 실제 Chrome 브라우저를 원격 제어하여 로컬 웹 UI를 검증할 수 있습니다.

### [1단계] WSL2 Playwright 시스템 라이브러리 설치
WSL2 내부 터미널에서 공유 라이브러리 패키지와 브라우저 바이너리를 설치하여 Playwright 기본 런타임을 구비합니다.
```bash
# 임시 작업 디렉토리 생성 및 의존성 설치
mkdir -p /tmp/playwright-test
cd /tmp/playwright-test
npm init -y
npm install playwright
npx playwright install-deps
npx playwright install chromium
```

### [2단계] Windows Chrome 원격 디버깅 모드로 기동 (Windows Host)
Windows 호스트에서 구동 중인 모든 Chrome 프로세스를 강제 종료하고, 원격 제어 포트(`9222`)를 활성화하여 실행합니다.
* **명령 실행**: Windows PowerShell 7.x (일반 권한)
```powershell
# 기존 크롬 강제 종료
Stop-Process -Name "chrome" -Force -ErrorAction SilentlyContinue

# 디버깅 포트를 열고 별도 개발 프로필 폴더로 기동
Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222", "--remote-debugging-address=0.0.0.0", "--user-data-dir=C:\chrome-dev-profile"
```

### [3단계] Windows 포트프록시 및 방화벽 설정 (Windows Host)
Windows 루프백에 강제 바인딩된 9222 포트를 외부(WSL2 가상망 포함)에서 접속 가능하도록 로컬 리다이렉트합니다.
* **명령 실행**: **PowerShell 7.x (관리자 권한)**
```powershell
# 1. IP Helper 서비스 활성화 확인 및 기동
Get-Service -Name "iphlpsvc"
Start-Service -Name "iphlpsvc" -ErrorAction SilentlyContinue

# 2. 0.0.0.0:9222 수신 대기를 127.0.0.1:9222로 프록시 매핑
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=9222 connectaddress=127.0.0.1 connectport=9222

# 3. Windows 방화벽 인바운드 예외 허용 규칙 추가 (방화벽 전체 비활성화 금지)
New-NetFirewallRule -DisplayName "WSL Chrome Debugger" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9222
```

### [4단계] WSL2 터미널에서 호스트 IP 탐색 및 socat 중계 (WSL2 Linux)
WSL2는 Windows 호스트의 실제 사설 IP 주소(예: `192.168.35.x`)를 바라보고 가상 터널을 열어야 합니다.
1. **Windows 호스트 IP 주소 실시간 획득**:
   ```bash
   # WSL2 내부에서 Windows 호스트 IP 확인 (일반적으로 2선 라우터 게이트웨이 또는 호스트 어드레스)
   # 예: 192.168.35.29 (Windows 무선/유선 LAN 사설 IP)
   ip route show | grep default | awk '{print $3}'
   ```
2. **socat을 통한 WSL2 내부 루프백 포트 터널 개설**:
   WSL2 내부의 `127.0.0.1:9222` 요청을 방금 획득한 Windows IP의 `9222`로 포워딩 중계합니다.
   ```bash
   # socat 패키지 설치
   sudo apt-get update && sudo apt-get install -y socat

   # 백그라운드로 9222 터널 개설 (기존에 켜진 socat이 있다면 먼저 kill 필요)
   killall socat 2>/dev/null
   socat TCP-LISTEN:9222,fork,reuseaddr TCP:<WINDOWS_HOST_IP>:9222 &
   ```

### [5단계] 연동 결과 최종 검증
WSL2 터미널에서 Windows Chrome 디버거 API가 리스닝되는지 실측 검증합니다.
```bash
curl http://127.0.0.1:9222/json/version
```
* **정상 출력 예시**:
  ```json
  {
     "Browser": "Chrome/149.0.7827.103",
     "Protocol-Version": "1.3",
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; ...)",
     "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/..."
  }
  ```
  이 JSON 데이터가 정상 반환되면, 에이전트의 브라우저 실행 도구가 Windows Chrome 세션에 정상적으로 올라타 웹 화면 조작 및 캡처를 차단 없이 수행할 수 있게 됩니다.

---

## 3. 현장 시행착오 및 주의사항 (Tips)

* ⚠️ **DHCP 환경 하에서의 IP 변동 주의**:
  PC를 리부트하거나 무선 AP를 이동할 경우 Windows의 사설 IP 주소(예: `192.168.x.x`)가 변경됩니다. 이 경우 4단계의 `socat` 명령어에 지정하는 타깃 IP를 새로운 주소로 갱신하여 다시 기동해야 통신이 유지됩니다.
* ⚠️ **보안 규칙**:
  일시적인 연결 테스트 목적으로 Windows 방화벽 프로필 전체를 비활성화(`Enabled False`)하는 조치는 극도로 위험하므로 엄격히 제한합니다. 반드시 방화벽 프로필은 정상 복원(`Enabled True`)해 두고, 3단계의 `New-NetFirewallRule` 명령을 사용해 **오직 9222 TCP 포트만 부분 허용**하도록 규칙을 설계해야 합니다.
