# Task-003: SEC XBRL 재무 파싱 + 주식수 이력

> **Sub Project**: p3_usdms
> **PRD 근거**: F-05 (SEC XBRL 재무 파싱), F-06 (주식 수 이력 관리)
> **작성일**: 2026-06-01
> **의존 Task**: T-002-B

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/p3_usdms_wiki/environment.md` | ✅ 확인 |
| SECClient 시그니처 | `pjt_wiki/p3_usdms_wiki/interfaces/sec_client.md` | ✅ 확인 |
| DB 스키마 | `pjt_wiki/migration-pjt/ref_usdms_wiki/interfaces/db_schema.md` | ✅ 확인 |
| XBRLMapper 설계 | 위키 미기록 → `migration_pjt/usdms_origin/backend/collectors/xbrl_mapper.py` 직접 확인 | ⚠️ 직접 확인 |
| FinancialParser 설계 | 위키 미기록 → `migration_pjt/usdms_origin/backend/collectors/financial_parser.py` 직접 확인 | ⚠️ 직접 확인 |
| FinancialRepo 시그니처 | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

SEC EDGAR의 Company Facts API 데이터를 활용하여 로우 데이터(EAV) 적재, 회계 표준 필드(US-GAAP) 매핑, 연도/분기별 이산값 산출(FY/FP 그룹화 및 Q2/Q3/Q4 이산화 역산), 그리고 발행주식수 이력(PIT) 정보를 데이터베이스에 완벽하게 정제하여 적재하는 파이프라인을 구축합니다.

**구현 범위:**
- IN: 
  - `XBRLMapper`: US-GAAP 태그를 분석용 표준 회계 필드에 우선순위/대체 매핑 처리 및 가감 normalization 수행.
  - `FinancialParser`: CIK 기반 `company_facts` 조회 결과의 DEI(발행주식수) 추출 및 GAAP 데이터 플랫화, 로우 팩츠 벌크 삭제 후 삽입, `_standardize_financials_v2` 알고리즘을 통한 연도/분기 조합(BS instant 및 IS/CF duration) 및 discrete quarter 역산 가공.
  - `FinancialRepo`: `us_financial_facts` EAV 벌크 삽입, `us_standard_financials` upsert, `us_share_history` upsert 및 조회 인터페이스.
- OUT:
  - 데일리 갭 감지(Gap Scanner) 및 오케스트레이터 결합은 `T-005` (일일 루틴 자동화)에서 구현합니다.

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p3_usdms/collectors/xbrl_mapper.py` — XBRL 태그 매핑 매니저
- `tdms_core/p3_usdms/collectors/financial_parser.py` — 재무 데이터 파싱 및 표준화 파이프라인
- `tdms_core/p3_usdms/repositories/financial_repo.py` — `us_financial_facts`, `us_standard_financials`, `us_share_history` 레포지토리
- `tdms_core/p3_usdms/tests/test_financial_collect.py` — TDD 단위 및 통합 테스트 코드

---

## § 3. 핵심 인터페이스

### 3.1 XBRLMapper
```python
# [출처: migration_pjt/usdms_origin/backend/collectors/xbrl_mapper.py — 위키 미기록으로 직접 확인]
from typing import Dict, List, Optional

class XBRLMapper:
    MAPPING: Dict[str, List[str]] = {
        "total_assets": ["Assets", "AssetsNet"],
        "current_assets": ["AssetsCurrent"],
        "cash_and_equiv": [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashAndCashEquivalents",
            "Cash",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "CashAndCashEquivalentsIncludingDiscontinuedOperations",
            "CashEquivalentsAtCarryingValue",
        ],
        "inventory": ["InventoryNet", "InventoryGross", "Inventories", "InventoriesNet", "InventoryFinishedGoodsAndWorkInProcess"],
        "account_receivable": [
            "AccountsReceivableNetCurrent",
            "AccountsReceivableNet",
            "ReceivablesNetCurrent",
            "AccountsNotesAndLoansReceivableNetCurrent",
            "TradeAndOtherReceivablesCurrent",
            "AccountsAndOtherReceivablesNetCurrent",
            "AccountsReceivableGrossCurrent",
        ],
        "total_equity": [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "Equity",
            "MembersEquity",
            "PartnersCapital",
            "PartnerCapital",
            "TotalEquity",
            "ShareholdersEquity",
            "OwnersEquity",
        ],
        "retained_earnings": ["RetainedEarningsAccumulatedDeficit", "RetainedEarnings", "AccumulatedDeficit", "RetainedEarningsUnappropriated", "RetainedEarningsAppropriatedAndUnappropriated"],
        "total_liabilities": ["Liabilities", "LiabilitiesTotal"],
        "current_liabilities": ["LiabilitiesCurrent"],
        "total_debt": ["DebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligations"],
        "shares_outstanding": ["CommonStockSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic", "CommonStockSharesIssued"],
        "revenue": [
            "CollaborativeRevenue", "RevenueFromCollaborativeAgreements", "RevenueFromGrants", "ContractRevenue", "LicenseAndServicesRevenue",
            "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax", "NetSales", "TotalRevenuesAndOtherIncome", "TotalRevenues",
            "RevenuesNetOfInterestExpense", "InterestAndDividendIncomeOperating", "PremiumsEarnedNet", "HealthCareOrganizationRevenue",
            "RegulatedAndUnregulatedOperatingRevenue", "ElectricUtilityRevenue", "OilAndGasRevenue", "RealEstateRevenueNet", "RevenueFromRelatedParties",
        ],
        "cogs": [
            "CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfServices",
            "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", "CostOfSales", "CostOfProductsAndServicesSold",
            "CostOfMerchandiseSalesBuyingAndOccupancy", "DirectCostsOfLeasedAndRentedPropertyOrEquipment",
        ],
        "gross_profit": ["GrossProfit", "GrossProfitLoss"],
        "sgna_expense": [
            "SellingGeneralAndAdministrativeExpense", "GeneralAndAdministrativeExpense", "SellingAndMarketingExpense",
            "SellingExpense", "GeneralAndAdministrative", "OperatingExpenses",
        ],
        "rnd_expense": ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost", "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost", "ResearchAndDevelopmentInProcess"],
        "op_income": ["OperatingIncomeLoss", "IncomeLossFromOperations", "OperatingProfit", "OperatingProfitLoss", "IncomeFromOperations"],
        "interest_expense": ["InterestExpense", "InterestExpenseDebt", "InterestExpenseBorrowings", "InterestAndDebtExpense", "InterestIncomeExpenseNet", "InterestCostsIncurred", "InterestPaidNet"],
        "tax_provision": ["IncomeTaxExpenseBenefit", "IncomeTaxesPaidNet", "CurrentIncomeTaxExpenseBenefit", "IncomeTaxExpenseBenefitContinuingOperations", "ProvisionForIncomeTaxes"],
        "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLossAttributableToParent", "ComprehensiveIncomeNetOfTax", "NetIncome"],
        "ocf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "CashFlowsFromUsedInOperatingActivities"],
        "capex": [
            "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PaymentsForCapitalImprovements",
            "CapitalExpendituresIncurredButNotYetPaid", "PurchaseOfPropertyPlantAndEquipment", "PaymentsToAcquireOtherPropertyPlantAndEquipment",
            "AdditionsToPropertyPlantAndEquipment",
        ],
        "fcf": [],
        "depreciation_amortization": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation", "AmortizationOfIntangibleAssets", "DepreciationAmortizationAndAccretionNet", "DepletionOfOilAndGasProperties", "OtherDepreciationAndAmortization"],
        "long_term_debt": ["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "LongTermNotesPayable", "SeniorNotes", "ConvertibleDebt", "ConvertibleDebtNoncurrent", "SubordinatedDebt", "SubordinatedLongTermDebt", "SecuredDebt", "UnsecuredDebt", "DebtInstrumentCarryingAmount"],
        "short_term_debt": ["ShortTermBorrowings", "LongTermDebtCurrent", "DebtCurrent", "ShortTermDebt", "CommercialPaper", "BankOverdrafts", "LineOfCredit", "LinesOfCreditCurrent", "NotesPayableCurrent", "ConvertibleNotesPayableCurrent", "SecuredDebtCurrent", "CurrentPortionOfLongTermDebt"],
        "bank_interest_income": ["InterestAndDividendIncomeOperating", "InterestIncomeExpenseNet", "InterestAndFeeIncomeLoansAndLeases", "InterestIncomeOperating"],
        "bank_noninterest_income": ["NonInterestIncome", "NoninterestIncome", "FeesAndCommissions", "InvestmentBankingRevenue"],
        "insurance_premiums": ["PremiumsEarnedNet", "PremiumsWrittenNet", "InsurancePremiumsRevenueRecognizedNet"],
    }

    POSITIVE_TAGS = {"capex"}
    EXPENSE_TAGS = {"cogs", "sgna_expense", "rnd_expense", "interest_expense", "tax_provision"}

    @classmethod
    def normalize_sign(cls, field: str, value: float) -> float:
        """Capex는 항상 양수로 변환하여 리턴"""
        ...

    @classmethod
    def map_fact(cls, field: str, facts: List[Dict[str, Any]]) -> Optional[float]:
        """주어진 단일 기간의 raw facts 풀에서 필드 우선순위/대체 로직을 반영해 표준 값을 추출"""
        ...
```

### 3.2 FinancialParser
```python
# [출처: migration_pjt/usdms_origin/backend/collectors/financial_parser.py — 위키 미기록으로 직접 확인]
from typing import List, Dict, Any

class FinancialParser:
    def __init__(self) -> None:
        """
        SECClient, FinancialRepo, XBRLMapper 의존성 인스턴스 주입 초기화.
        """
        ...

    def process_filings(self, filings_list: List[Dict[str, Any]]) -> None:
        """
        Gap Scanner 혹은 루틴에서 넘긴 Filings 목록 수집 위임 처리.
        """
        ...

    def run(self, ciks: List[str]) -> None:
        """
        CIK 리스트를 받아 순차적으로 수집 및 정제 처리 수행.
        """
        ...

    def process_company(self, cik: str) -> None:
        """
        1. SEC API를 통한 raw company facts 데이터 fetch
        2. dei 파트 내 주식수 정보 추출 및 us_share_history 저장
        3. us-gaap raw facts 데이터 추출 및 EAV 구조로 us_financial_facts에 벌크 업서트
        4. _standardize_financials_v2 알고리즘을 통한 회계 데이터 그룹화 및 이산값 계산
        5. 정제 완료된 표준 데이터 us_standard_financials에 업서트
        """
        ...

    def _standardize_financials_v2(self, cik: str, raw_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        - (fy, fp) 기준으로 그룹화
        - Instant 정보(B/S)와 Duration 정보(I/S, C/F) 결합
        - _derive_discrete_from_ytd() 및 _derive_q4() 를 적용하여 분기 이산 정보 보완
        """
        ...

    def _classify_duration(self, days: int) -> str:
        """days 길이에 따라 'INSTANT' / 'Q' / 'H1' / 'Q3_YTD' / 'FY' 분류"""
        ...
```

### 3.3 FinancialRepo
```python
# [신규 정의 — 구현 Agent가 아래 시그니처로 생성]
from p3_usdms.repositories.base import BaseRepository
from typing import List, Dict, Any

class FinancialRepo(BaseRepository):
    def delete_raw_facts_by_cik(self, cik: str) -> None:
        """특정 CIK에 대한 기존 us_financial_facts EAV 데이터 일괄 삭제"""
        ...

    def insert_financial_facts(self, records: List[Dict[str, Any]]) -> None:
        """us_financial_facts 테이블에 EAV 데이터를 bulk insert"""
        ...

    def upsert_standard_financials(self, records: List[Dict[str, Any]]) -> None:
        """
        us_standard_financials 테이블에 표준화 재무 데이터를 upsert.
        Conflict Target: (cik, report_period, filed_dt)
        """
        ...

    def upsert_share_history(self, records: List[Dict[str, Any]]) -> None:
        """
        us_share_history 테이블에 주식 수 이력을 upsert.
        Conflict Target: (cik, filed_dt)
        """
        ...
```

---

## § 4. 테스트 케이스

### 4.1 정상 동작 케이스

```python
# [Tier 1 — 단위]
def test_xbrl_mapper_maps_primary_tag_successfully():
    """
    [목적] XBRLMapper가 주어진 팩츠 리스트에서 최우선 순위 태그를 올바르게 매핑하는지 확인
    [유도] XBRLMapper.map_fact가 우선순위 배열대로 매치하며 가산/감산 노멀라이즈를 수행하게 유도
    """
    from p3_usdms.collectors.xbrl_mapper import XBRLMapper
    facts = [
        {"tag": "AssetsCurrent", "val": 1000.0},
        {"tag": "Assets", "val": 5000.0}
    ]
    val = XBRLMapper.map_fact("total_assets", facts)
    assert val == 5000.0
```

```python
# [Tier 1 — 단위]
def test_xbrl_mapper_falls_back_when_primary_missing():
    """
    [목적] 최우선 순위 태그가 없을 때 대체 태그(Fallback)를 성공적으로 로드하는지 확인
    [유도] map_fact 내부의 fallback tag 매칭 루프를 유도
    """
    from p3_usdms.collectors.xbrl_mapper import XBRLMapper
    facts = [
        {"tag": "AssetsNet", "val": 4500.0}
    ]
    val = XBRLMapper.map_fact("total_assets", facts)
    assert val == 4500.0
```

```python
# [Tier 1 — 단위]
def test_xbrl_mapper_normalizes_capex_to_positive():
    """
    [목적] Capex와 같은 음수 혹은 양수로 혼용되어 기록되는 Expense 항목을 양수 크기로 정규화하는지 검증
    [유도] normalize_sign이 'capex'에 대해 abs(value)를 강제하게 유도
    """
    from p3_usdms.collectors.xbrl_mapper import XBRLMapper
    facts = [
        {"tag": "PaymentsToAcquirePropertyPlantAndEquipment", "val": -300.0}
    ]
    val = XBRLMapper.map_fact("capex", facts)
    assert val == 300.0
```

```python
# [Tier 2 — 격리 통합]
def test_financial_parser_standardizes_discrete_q2_values(mocker):
    """
    [목적] YTD 누적값에서 이전 분기값을 차감하여 Q2 이산(discrete) 값을 정확히 도출하는지 확인
    [유도] _derive_discrete_from_ytd 메서드가 Q2_discrete = Q2_YTD - Q1_YTD 공식을 올바르게 계산하도록 함
    """
    from p3_usdms.collectors.financial_parser import FinancialParser
    parser = FinancialParser()
    
    raw_facts = [
        # Q1 (90 days duration)
        {"cik": "0000000001", "tag": "Revenues", "val": 100.0, "period_start": "2026-01-01", "period_end": "2026-03-31", "filed_dt": "2026-04-10", "form": "10-Q", "fy": 2026, "fp": "Q1", "unit": "USD"},
        # Q2 YTD (180 days duration)
        {"cik": "0000000001", "tag": "Revenues", "val": 220.0, "period_start": "2026-01-01", "period_end": "2026-06-30", "filed_dt": "2026-07-10", "form": "10-Q", "fy": 2026, "fp": "Q2", "unit": "USD"},
    ]
    
    std_records = parser._standardize_financials_v2("0000000001", raw_facts)
    # Q2 레코드의 revenue가 220 - 100 = 120 인지 검증
    q2_record = next(r for r in std_records if r["fiscal_period"] == "Q2")
    assert q2_record["revenue"] == 120.0
```

### 4.2 경계값 케이스

```python
# [Tier 1 — 단위]
def test_financial_parser_with_empty_raw_facts_returns_empty():
    """
    [목적] 입력 데이터가 없을 때 빈 리스트를 예외 없이 반환하는지 확인
    [유도] _standardize_financials_v2에 빈 리스트를 넣었을 때 에러 없이 []을 반환하게 함
    """
    from p3_usdms.collectors.financial_parser import FinancialParser
    parser = FinancialParser()
    assert parser._standardize_financials_v2("0000000001", []) == []
```

### 4.3 예외/오류 처리 케이스

```python
# [Tier 2 — 격리 통합]
def test_financial_parser_handles_sec_client_timeout(mocker):
    """
    [목적] SEC EDGAR facts API가 타임아웃 오류를 낼 때 적절히 로깅하고 예외를 격리 처리하는지 검증
    [유도] SECClient.get_company_facts가 ReadTimeout을 뱉어도 run() 루프가 끊기지 않고 다음 CIK로 진행되게 유도
    """
    import requests
    from p3_usdms.collectors.financial_parser import FinancialParser
    
    parser = FinancialParser()
    mocker.patch.object(parser.sec_client, "get_company_facts", side_effect=requests.exceptions.ReadTimeout("SEC Timeout"))
    
    # 예외가 상위 run 루프에서 포착되어 격리되고, 정상 종료되어야 함
    parser.run(["0000320193"]) 
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest

@pytest.mark.integration
def test_financial_pipeline_stores_to_real_db(real_pool, mocker):
    """
    [목적] 실제 DB 연결 상태에서 FinancialRepo가 EAV, 표준 재무 데이터, 주식수 역사를 올바르게 삽입/업서트하는지 확인
    [실행 조건] 실 DB 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    from p3_usdms.repositories.financial_repo import FinancialRepo
    repo = FinancialRepo()
    
    test_cik = "9999999999"
    
    # 1. EAV Clean & Insert 테스트
    repo.delete_raw_facts_by_cik(test_cik)
    
    raw_facts = [
        {"cik": test_cik, "tag": "Assets", "val": 1000000.0, "period_start": None, "period_end": "2026-12-31", "filed_dt": "2027-02-15", "frame": "CY2026", "fy": 2026, "fp": "FY", "form": "10-K"}
    ]
    repo.insert_financial_facts(raw_facts)
    
    # 2. 표준 재무 데이터 업서트 테스트
    std_data = [
        {
            "cik": test_cik, "report_period": "2026-12-31", "filed_dt": "2027-02-15", 
            "fiscal_year": 2026, "fiscal_period": "FY", "total_assets": 1000000.0, "total_debt": 200000.0,
            "shares_outstanding": 50000.0, "revenue": 800000.0, "gross_profit": 400000.0, "op_income": 150000.0,
            "rnd_expense": 30000.0, "interest_expense": 10000.0, "net_income": 100000.0, "ebitda": 180000.0,
            "ocf": 120000.0, "capex": 40000.0, "fcf": 80000.0
        }
    ]
    repo.upsert_standard_financials(std_data)
    
    # 3. 주식 수 역사 업서트 테스트
    shares_data = [
        {"cik": test_cik, "filed_dt": "2027-02-15", "val": 50000.0}
    ]
    repo.upsert_share_history(shares_data)
    
    # DB 조회 검증
    with repo.get_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM us_financial_facts WHERE cik = %s", (test_cik,))
        assert cur.fetchone()["count"] == 1
        
        cur.execute("SELECT total_assets, revenue FROM us_standard_financials WHERE cik = %s", (test_cik,))
        row = cur.fetchone()
        assert row["total_assets"] == 1000000.0
        assert row["revenue"] == 800000.0
        
        cur.execute("SELECT val FROM us_share_history WHERE cik = %s", (test_cik,))
        assert cur.fetchone()["val"] == 50000.0
        
    # 테스트 종료 후 클린업
    with repo.get_cursor() as cur:
        cur.execute("DELETE FROM us_standard_financials WHERE cik = %s", (test_cik,))
        cur.execute("DELETE FROM us_share_history WHERE cik = %s", (test_cik,))
        repo.delete_raw_facts_by_cik(test_cik)
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_xbrl_mapper_maps_primary_tag_successfully` | Tier 1 | 정상 | 우선순위 회계 태그 매핑 정확도 검증 |
| 2 | `test_xbrl_mapper_falls_back_when_primary_missing` | Tier 1 | 정상 | 최우선 태그 누락 시 대체 태그 매핑 검증 |
| 3 | `test_xbrl_mapper_normalizes_capex_to_positive` | Tier 1 | 정상 | 자본 지출(Capex) 등 비용 데이터 양수 표준화 검증 |
| 4 | `test_financial_parser_standardizes_discrete_q2_values` | Tier 2 | 격리 통합 | 누적 분기(YTD) 정보를 분기 이산치 데이터로 변환 산출 |
| 5 | `test_financial_parser_with_empty_raw_facts_returns_empty` | Tier 1 | 경계값 | 빈 데이터 세트 입력 시 에러 없이 빈 리스트 처리 여부 |
| 6 | `test_financial_parser_handles_sec_client_timeout` | Tier 2 | 예외 | SEC EDGAR API 타임아웃 시 파이프라인 중단 없이 예외 고립 |
| 7 | `test_financial_pipeline_stores_to_real_db` | Tier 3 | 실제 통합 | 실제 데이터베이스 테이블 EAV, 표준 재무, 주식수 업서트 정상 동작 검증 |

**총 7개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, Pandas, Numpy, psycopg2-binary, requests (Rate Limit)
- **위키 참조 링크**:
  - `pjt_wiki/p3_usdms_wiki/interfaces/sec_client.md` — SEC API 데이터 연동 포맷 참조
- **관련 문서**: `pjt_wiki/migration-pjt/ref_usdms_wiki/interfaces/db_schema.md` — `us_financial_facts`, `us_standard_financials`, `us_share_history` DDL 명세 참조
- **주의사항**:
  - SEC EDGAR API 데이터 수집 시 초당 최대 10회 제한(`rate_limit_delay = 0.15`) 규정을 준수하는 `sec_client.py` 인스턴스를 무조건 경유해야 합니다.
  - `us_financial_facts` 테이블은 EAV 특성상 히스토리가 길기 때문에, 한 번 정제할 때 해당 CIK의 로우 팩츠를 전체 다 날린 후 최신 facts 데이터셋으로 벌크 인서트(`delete_raw_facts_by_cik`) 하는 레거시 덮어쓰기 로직을 엄격하게 계승합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 실제 DB 통합 테스트 통과
- [ ] `docs/p3_usdms/p3_usdms_pjt_tasks.md`의 `T-003` 상태를 `완료`로 업데이트
- [ ] `docs/p3_usdms/tasks/task-003_walkthrough.md` 작성
