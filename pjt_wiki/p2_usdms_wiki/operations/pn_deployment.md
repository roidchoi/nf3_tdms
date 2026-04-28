# 배포 절차서 (deployment.md)

> **Sub Project**: P{n}_{Name} **버전**: v{N} **마지막 업데이트**: {YYYY-MM-DD} **타입**: Type D (결과물/운영 지식)

---

## 1. 사전 조건

- [ ] Python {버전} 이상
- [ ] 가상환경 활성화: `conda activate {env_name}`
- [ ] 환경변수 설정: `.env` 파일 구성 (`environment.md` 참조)
- [ ] {기타 조건}

---

## 2. 최초 설치

```bash
# 1. 패키지 설치
pip install -r {Sub_Project}/requirements.txt

# 2. DB 초기화
python {Sub_Project}/scripts/init_db.py

# 3. 환경 검증
python {Sub_Project}/scripts/validate_env.py
```

---

## 3. 배포 (업데이트)

```bash
# 1. 코드 업데이트
git pull origin main

# 2. 패키지 업데이트 (의존성 변경 시만)
pip install -r requirements.txt

# 3. DB 마이그레이션 (스키마 변경 시만)
python scripts/migrate_db.py

# 4. 동작 확인
python scripts/validate_env.py
```

---

## 4. 환경별 설정

|환경|설정 파일|비고|
|---|---|---|
|개발|`.env.dev`|{설명}|
|운영|`.env.prod`|{설명}|

---

## 5. 롤백 절차

```bash
# 이전 커밋으로 롤백
git checkout {이전_커밋_해시}

# DB 롤백 (백업이 있는 경우)
cp data/backup/{backup_파일} data/{현재_DB}
```

---

## 6. 배포 이력

| 날짜           | 버전   | 주요 변경 | 담당  |
| ------------ | ---- | ----- | --- |
| {YYYY-MM-DD} | v{N} | 초기 배포 | —   |