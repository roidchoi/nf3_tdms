# [P4-ERR-004] WSL2 AI 에이전트 브라우저 구동 및 포트 포워딩 연동 장애 해결 가이드

> **분류**: 개발 환경 (WSL2 / Windows Dual Environment)  
> **장애 심각도**: High (시각 정합성 및 브라우저 자동화 테스트 불가)  
> **최초 발생일**: 2026-06-11  

---

## 1. 장애 증상 및 원인 분석

### 1) 장애 증상
* AI 에이전트의 브라우저 서브에이전트(`browser_subagent` 등)가 웹 애플리케이션 화면 조회를 위해 브라우저를 기동할 때, 주소창 입력이 되지 않거나 통신 거부(`Connection Refused` 또는 `Empty reply from server`)가 나며 빈 화면(또는 타임아웃)만 캡처되는 현상.
* WSL2 내부에서 직접 헤드리스 크로미움을 띄우려고 할 때 시스템 공유 라이브러리(`.so`) 누락 오류가 발생함.

### 2) 발생 원인
* **Playwright 의존성 유실**: WSL2 가상 머신 내부에 Playwright 브라우저 바이너리(Chromium) 및 Linux 전용 렌더링 의존성 패키지가 완벽히 캐싱되어 있지 않아 발생.
* **디버거 포트 바인딩 제한 및 포트 충돌**:
  - Windows 크롬의 원격 디버깅 포트(`9222`)는 기본적으로 윈도우 루프백 주소(`127.0.0.1`)에 바인딩됩니다.
  - 이를 WSL2 외부로 포워딩하기 위해 `netsh portproxy`로 `0.0.0.0:9222` -> `127.0.0.1:9222` 매핑을 맺을 경우, 포트 바인딩 충돌 및 패킷 루핑(Looping)이 생겨 `ERR_EMPTY_RESPONSE` 에러가 나면서 크롬 디버거가 윈도우 로컬에서도 다운됩니다.

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
Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222", "--user-data-dir=C:\chrome-dev-profile"
```

### [3단계] Windows 포트프록시 및 방화벽 설정 (Windows Host)
Windows 루프백에 강제 바인딩된 9222 포트를 외부(WSL2 가상망 포함)에서 접속 가능하도록 하되, **직접 9222 포트프록시 매핑 시 발생하는 포트 루프백 충돌을 방지하기 위해 외부 인입 포트를 9223으로 우회 설계**합니다.
* **명령 실행**: **PowerShell 7.x (관리자 권한)**
```powershell
# 1. IP Helper 서비스 활성화 확인 및 기동
Start-Service -Name "iphlpsvc" -ErrorAction SilentlyContinue

# 2. 0.0.0.0:9223 수신 대기를 127.0.0.1:9222(크롬)로 프록시 매핑 (충돌 회피)
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=9223 connectaddress=127.0.0.1 connectport=9222

# 3. Windows 방화벽 인바운드 예외 허용 규칙 추가 (9223 포트 부분 허용)
New-NetFirewallRule -DisplayName "WSL Chrome Debugger Bypass" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9223 -ErrorAction SilentlyContinue
```

### [4단계] WSL2 터널 가동 및 socat 중계 (WSL2 Linux)
WSL2 내부의 `127.0.0.1:9222` 요청을 Windows 호스트 IP의 우회 포트 `9223`으로 포워딩 중계합니다.
1. **Windows 호스트 IP 주소 실시간 획득 및 socat 백그라운드 구동**:
   ```bash
   # socat 패키지 설치
   sudo apt-get update && sudo apt-get install -y socat

   # 백그라운드로 9222 -> Windows:9223 터널 개설 (기존에 켜진 socat 정리)
   killall socat 2>/dev/null
   socat TCP-LISTEN:9222,fork,reuseaddr TCP:$(ip route show | grep default | awk '{print $3}'):9223 &
   ```
   > [!TIP]
   > **AI 에이전트를 위한 원라이너(One-liner) 자동 구동 명령**:
   > 다음 명령은 WSL2의 가상 게이트웨이 IP(Windows 호스트)를 자동으로 조회하고 기존 socat을 정리한 뒤 즉시 백그라운드 터널을 실행합니다.
   > ```bash
   > killall socat 2>/dev/null; WINDOWS_IP=$(ip route show | grep default | awk '{print $3}'); nohup socat TCP-LISTEN:9222,fork,reuseaddr TCP:${WINDOWS_IP}:9223 >/dev/null 2>&1 &
   > ```

---

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

## 3. 타 세션 AI 에이전트 전용 속성 가이드 (Agent Setup Blueprint)

새로운 세션의 AI 에이전트가 이 문서를 읽는 즉시 테스트 환경을 확보할 수 있도록 아래 절차를 자동으로 순차 대입하십시오:

1. **WSL2 터널 가동 진단**:
   - WSL2 터미널에서 `curl -s http://127.0.0.1:9222/json/version` 을 쳐보고 결과가 오지 않는다면 터널이 닫혀 있거나 꼬여 있는 상태입니다.
   - 즉시 WSL2 터미널에서 아래 원라이너 명령을 무조건적으로 실행하십시오:
     ```bash
     killall socat 2>/dev/null; nohup socat TCP-LISTEN:9222,fork,reuseaddr TCP:$(ip route show | grep default | awk '{print $3}'):9223 >/dev/null 2>&1 &
     ```
2. **연결 상태 재측정**:
   - 다시 `curl -s http://127.0.0.1:9222/json/version` 을 기동하여 연결 정합성을 확인합니다.
   - 만약 이래도 접속이 안 된다면 Windows 호스트에서 디버거 크롬 기동(`Start-Process` 구문) 및 포트프록시 매핑(`netsh`)이 해제되어 있는 상태입니다.
   - 이 경우 즉시 사용자에게 **"Windows PowerShell을 관리자 권한으로 열어 아래 블록을 복사-붙여넣기 해달라"**고 정중히 요청하십시오:
     ```powershell
     # Windows Chrome 원격 디버깅 기동 (기존 크롬 완전 종료 후 백그라운드 구동)
     gps chrome | stop-process -Force -ErrorAction SilentlyContinue
     Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9222", "--user-data-dir=C:\chrome-dev-profile"
     
     # 포트프록시 및 방화벽 설정 허용 (9223 우회 포트 사용)
     Start-Service -Name "iphlpsvc" -ErrorAction SilentlyContinue
     netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=9223 connectaddress=127.0.0.1 connectport=9222
     New-NetFirewallRule -DisplayName "WSL Chrome Debugger Bypass" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9223 -ErrorAction SilentlyContinue
     ```

---

## 4. 현장 시행착오 및 주의사항 (Tips)

* ⚠️ **포트 충돌 및 루핑 회피**:
  Windows의 포트프록시를 9222 -> 127.0.0.1:9222로 다이렉트 바인딩하면 포트 루프백 간섭이 생겨 크롬 연결 시 `ERR_EMPTY_RESPONSE`나 `Empty reply from server` 오류가 발생합니다. 반드시 윈도우 수신 포트는 **9223**, 내부 전달 포트는 **9222**로 이원화 맵핑해 주어야 영구적이고 안정적으로 구동됩니다.
* ⚠️ **WSL 게이트웨이 IP 매핑 안정성**:
  Windows의 물리 사설 IP(예: `192.168.x.x`)는 공유기 교체나 PC 재부팅 시 수시로 바뀌어 터널이 끊어지지만, WSL2 가상 머신 관점에서의 기본 게이트웨이 IP(`ip route show`의 `default` 게이트웨이)는 WSL 가상 스위치가 항상 동일한 범위 내에서 관리하므로, 터널의 대상 주소를 `127.0.0.1`로 우회하거나 게이트웨이 주소로 연동하는 편이 IP 변동 시 훨씬 안정적입니다.
* ⚠️ **보안 규칙**:
  일시적인 연결 테스트 목적으로 Windows 방화벽 프로필 전체를 비활성화(`Enabled False`)하는 조치는 극도로 위험하므로 엄격히 제한합니다. 반드시 방화벽 프로필은 정상 복원(`Enabled True`)해 두고, 3단계의 `New-NetFirewallRule` 명령을 사용해 **오직 9223 TCP 포트만 부분 허용**하도록 규칙을 설계해야 합니다.
