---
description: TDMS 프로젝트의 Python 가상환경 및 의존성 관리 정책. 구현 작업 시작 전, 패키지 설치, 터미널 명령 실행, 가상환경 구축 등 의존성과 관련된 모든 상황에서 반드시 이 정책을 따르십시오. "어떤 환경에서 실행해야 하는지", "패키지를 어떻게 설치해야 하는지" 불분명할 때마다 이 워크플로우를 먼저 참조하십시오.
---

# TDMS 환경 및 의존성 관리 정책

> **적용 범위**: p1_shared, p2_kdms, p3_usdms, p4_manager 모든 서브프로젝트
> **환경**: WSL 2 (Ubuntu 24.04 LTS) · Conda(Miniforge) · uv

---

## 1. 핵심 규칙 (반드시 준수)

| 규칙 | 설명 |
|---|---|
| **네이티브 Python 금지** | 시스템 Python 절대 사용 금지. 반드시 Conda 가상환경 내에서만 작업 |
| **pip 사용 금지** | `pip install` 대신 반드시 `uv pip install` 사용 |
| **conda install 금지** | Conda는 환경 생성(Python 버전 고정)에만 사용. 패키지 설치는 전부 uv로 처리 |
| **직접 설치 금지** | `uv pip install <패키지>` 직접 설치 금지. 반드시 `requirements.txt` 수정 후 설치 |
| **conda activate 금지** | 비대화형 셸(에이전트 터미널)에서 동작하지 않음 → `conda run` 사용 |

---

## 2. 가상환경 명칭 규칙

| 서브프로젝트 | 가상환경명 |
|---|---|
| p1_shared | `tdms_p1_env` |
| p2_kdms | `tdms_p2_env` |
| p3_usdms | `tdms_p3_env` |
| p4_manager | `tdms_p4_env` |

---

## 3. 최초 환경 구성

```bash
# Step 1: requirements.txt 먼저 작성 (해당 서브프로젝트 폴더 내)
# Step 2: Conda 환경 생성
conda create -n tdms_p{n}_env python=3.12 -y

# Step 3: 의존성 설치
conda run -n tdms_p{n}_env uv pip install -r <경로>/requirements.txt

# Step 4: p2·p3·p4의 경우 p1_shared editable install 추가
# requirements.txt에 아래 항목 포함:
# -e ../p1_shared
conda run -n tdms_p{n}_env uv pip install -r <경로>/requirements.txt
```

---

## 4. 에이전트 터미널 실행 규칙 ⚠️

에이전트가 `run_command`로 실행하는 셸은 **비대화형 서브프로세스**이므로
`conda activate`가 동작하지 않는다. **반드시 `conda run`을 사용**한다.

```bash
# ❌ 잘못된 방법 — 환경이 전환되지 않음
conda activate tdms_p1_env
python script.py

# ✅ 올바른 방법
conda run -n tdms_p1_env python script.py
conda run -n tdms_p1_env pytest tests/ -v
conda run -n tdms_p1_env uv pip install -r requirements.txt
```

### 상황별 명령 형식

| 상황 | 명령 형식 |
|---|---|
| 스크립트 실행 | `conda run -n tdms_p{n}_env python <script>` |
| 테스트 실행 | `conda run -n tdms_p{n}_env pytest <경로>/ -v` |
| 패키지 설치 | `conda run -n tdms_p{n}_env uv pip install -r requirements.txt` |
| editable install | `conda run -n tdms_p{n}_env uv pip install -e <패키지_경로>/` |
| 환경 확인 | `conda run -n tdms_p{n}_env python --version` |

---

## 5. 패키지 추가·업그레이드 절차

새 패키지가 필요할 때 **직접 설치 금지**.

```
1. requirements.txt에 패키지(버전 포함) 추가 또는 수정
2. conda run -n tdms_p{n}_env uv pip install -r requirements.txt
3. git add requirements.txt && git commit
```

---

## 6. 환경 존재 여부 확인

명령 실행 전 환경이 있는지 먼저 확인한다. 없으면 §3 절차로 생성한다.

```bash
conda env list | grep tdms_p{n}_env
```
