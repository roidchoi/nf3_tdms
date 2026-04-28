# 결정: KDMS-USDMS 공존 운영 아키텍처 (coexistence_with_kdms.md)

> **유형**: ADR (Architecture Decision Record)
> **소스**: `migration_pjt/usdms_origin/docs/USDMS_migration_guide.md`
> **결정 날짜**: 2025-12-18 (원본 문서 기준)
> **마지막 업데이트**: 2026-04-28

---

## 컨텍스트

USDMS를 KDMS가 운영 중인 동일 PC에 이관하여 두 시스템을 함께 운영해야 하는 상황.

---

## 결정

포트 및 네트워크를 완전히 분리하여 충돌 없이 공존.

| 항목 | KDMS | USDMS | 충돌 |
|---|---|---|---|
| DB Port | 5432 | **5435** | 없음 |
| Backend Port | 8000 | **8005** | 없음 |
| DB Name | kdms_db | **usdms_db** | 없음 |
| Docker Network | kdms-net | **usdms_net** | 없음 |
| 스케줄 시간 | 한국 시장 마감 후 (15:30 KST) | 미국 시장 마감 후 (06:00 KST) | 운영 분산 |

---

## 결과

- 기술적 충돌 없음 확인
- RAM 16GB 이상(추천 32GB+), SSD/NVMe 필수
- CPU 부하: 초기 백필 시에만 높음, 일일 운영 시 시간대 분산으로 충돌 적음

---

## 신규 프로젝트(p3_manager) 설계 시 시사점

- `p3_manager`가 두 DB를 함께 관리할 경우, 이 포트 체계를 그대로 활용
- 공통 스케줄러가 있다면 두 시스템의 운영 시간대(KR: 17:10, US: 07:00 KST)를 반드시 분리
