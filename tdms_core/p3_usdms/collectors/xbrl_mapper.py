"""
Enhanced XBRL Mapper with expanded tag coverage for US-GAAP.
Matches legacy tags logic to resolve standard financial fields.
"""
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class XBRLMapper:
    """
    Maps raw XBRL tags to standard financial fields.
    Handles priority (fallback) logic and sign normalization.
    """
    
    # Mapping Dictionary: Field -> List of US-GAAP Tags (Priority Order)
    MAPPING = {
        'total_assets': [
            'Assets',
            'AssetsNet',
        ],
        'current_assets': [
            'AssetsCurrent',
        ],
        'cash_and_equiv': [
            'CashAndCashEquivalentsAtCarryingValue',
            'CashAndCashEquivalents',
            'Cash',
            'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
            'CashAndCashEquivalentsIncludingDiscontinuedOperations',
            'CashEquivalentsAtCarryingValue',
        ],
        'inventory': [
            'InventoryNet',
            'InventoryGross',
            'Inventories',
            'InventoriesNet',
            'InventoryFinishedGoodsAndWorkInProcess',
        ],
        'account_receivable': [
            'AccountsReceivableNetCurrent',
            'AccountsReceivableNet',
            'ReceivablesNetCurrent',
            'AccountsNotesAndLoansReceivableNetCurrent',
            'TradeAndOtherReceivablesCurrent',
            'AccountsAndOtherReceivablesNetCurrent',
            'AccountsReceivableGrossCurrent',
        ],
        'total_equity': [
            'StockholdersEquity',
            'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
            'Equity',
            'MembersEquity',
            'PartnersCapital',
            'PartnerCapital',
            'TotalEquity',
            'ShareholdersEquity',
            'OwnersEquity',
        ],
        'retained_earnings': [
            'RetainedEarningsAccumulatedDeficit',
            'RetainedEarnings',
            'AccumulatedDeficit',
            'RetainedEarningsUnappropriated',
            'RetainedEarningsAppropriatedAndUnappropriated',
        ],
        'total_liabilities': [
            'Liabilities',
            'LiabilitiesTotal',
        ],
        'current_liabilities': [
            'LiabilitiesCurrent',
        ],
        'total_debt': [
            'DebtAndCapitalLeaseObligations',
            'LongTermDebtAndCapitalLeaseObligations',
        ],
        'shares_outstanding': [
            'CommonStockSharesOutstanding',
            'WeightedAverageNumberOfSharesOutstandingBasic',
            'CommonStockSharesIssued',
        ],
        'revenue': [
            'CollaborativeRevenue',
            'RevenueFromCollaborativeAgreements',
            'RevenueFromGrants',
            'ContractRevenue', 
            'LicenseAndServicesRevenue',
            'Revenues',
            'RevenueFromContractWithCustomerExcludingAssessedTax',
            'SalesRevenueNet',
            'SalesRevenueGoodsNet',
            'SalesRevenueServicesNet',
            'RevenueFromContractWithCustomerIncludingAssessedTax',
            'NetSales',
            'TotalRevenuesAndOtherIncome',
            'TotalRevenues',
            'RevenuesNetOfInterestExpense',
            'InterestAndDividendIncomeOperating',
            'PremiumsEarnedNet',
            'HealthCareOrganizationRevenue',
            'RegulatedAndUnregulatedOperatingRevenue',
            'ElectricUtilityRevenue',
            'OilAndGasRevenue',
            'RealEstateRevenueNet',
            'RevenueFromRelatedParties',
        ],
        'cogs': [
            'CostOfGoodsAndServicesSold',
            'CostOfRevenue',
            'CostOfGoodsSold',
            'CostOfServices',
            'CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization',
            'CostOfSales',
            'CostOfProductsAndServicesSold',
            'CostOfMerchandiseSalesBuyingAndOccupancy',
            'DirectCostsOfLeasedAndRentedPropertyOrEquipment',
        ],
        'gross_profit': [
            'GrossProfit',
            'GrossProfitLoss',
        ],
        'sgna_expense': [
            'SellingGeneralAndAdministrativeExpense',
            'GeneralAndAdministrativeExpense',
            'SellingAndMarketingExpense',
            'SellingExpense',
            'GeneralAndAdministrative',
            'OperatingExpenses',
        ],
        'rnd_expense': [
            'ResearchAndDevelopmentExpense',
            'ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost',
            'ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost',
            'ResearchAndDevelopmentInProcess',
        ],
        'op_income': [
            'OperatingIncomeLoss',
            'IncomeLossFromOperations',
            'OperatingProfit',
            'OperatingProfitLoss',
            'IncomeFromOperations',
        ],
        'interest_expense': [
            'InterestExpense',
            'InterestExpenseDebt',
            'InterestExpenseBorrowings',
            'InterestAndDebtExpense',
            'InterestIncomeExpenseNet',
            'InterestCostsIncurred',
            'InterestPaidNet',
        ],
        'tax_provision': [
            'IncomeTaxExpenseBenefit',
            'IncomeTaxesPaidNet',
            'CurrentIncomeTaxExpenseBenefit',
            'IncomeTaxExpenseBenefitContinuingOperations',
            'ProvisionForIncomeTaxes',
        ],
        'net_income': [
            'NetIncomeLoss',
            'ProfitLoss',
            'NetIncomeLossAvailableToCommonStockholdersBasic',
            'NetIncomeLossAttributableToParent',
            'ComprehensiveIncomeNetOfTax',
            'NetIncome',
        ],
        'ocf': [
            'NetCashProvidedByUsedInOperatingActivities',
            'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations',
            'CashFlowsFromUsedInOperatingActivities',
        ],
        'capex': [
            'PaymentsToAcquirePropertyPlantAndEquipment',
            'PaymentsToAcquireProductiveAssets',
            'PaymentsForCapitalImprovements',
            'CapitalExpendituresIncurredButNotYetPaid',
            'PurchaseOfPropertyPlantAndEquipment',
            'PaymentsToAcquireOtherPropertyPlantAndEquipment',
            'AdditionsToPropertyPlantAndEquipment',
        ],
        'fcf': [],
        'depreciation_amortization': [
            'DepreciationDepletionAndAmortization',
            'DepreciationAndAmortization',
            'Depreciation',
            'AmortizationOfIntangibleAssets',
            'DepreciationAmortizationAndAccretionNet',
            'DepletionOfOilAndGasProperties',
            'OtherDepreciationAndAmortization',
        ],
        'long_term_debt': [
            'LongTermDebt',
            'LongTermDebtNoncurrent',
            'LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities',
            'LongTermNotesPayable',
            'SeniorNotes',
            'ConvertibleDebt',
            'ConvertibleDebtNoncurrent',
            'SubordinatedDebt',
            'SubordinatedLongTermDebt',
            'SecuredDebt',
            'UnsecuredDebt',
            'DebtInstrumentCarryingAmount',
        ],
        'short_term_debt': [
            'ShortTermBorrowings',
            'LongTermDebtCurrent',
            'DebtCurrent',
            'ShortTermDebt',
            'CommercialPaper',
            'BankOverdrafts',
            'LineOfCredit',
            'LinesOfCreditCurrent',
            'NotesPayableCurrent',
            'ConvertibleNotesPayableCurrent',
            'SecuredDebtCurrent',
            'CurrentPortionOfLongTermDebt',
        ],
        'bank_interest_income': [
            'InterestAndDividendIncomeOperating',
            'InterestIncomeExpenseNet',
            'InterestAndFeeIncomeLoansAndLeases',
            'InterestIncomeOperating',
        ],
        'bank_noninterest_income': [
            'NonInterestIncome',
            'NoninterestIncome',
            'FeesAndCommissions',
            'InvestmentBankingRevenue',
        ],
        'insurance_premiums': [
            'PremiumsEarnedNet',
            'PremiumsWrittenNet',
            'InsurancePremiumsRevenueRecognizedNet',
        ],
    }

    POSITIVE_TAGS = {'capex'}
    EXPENSE_TAGS = {'cogs', 'sgna_expense', 'rnd_expense', 'interest_expense', 'tax_provision'}

    @staticmethod
    def normalize_sign(field: str, value: float) -> float:
        """
        Normalize sign for specific fields.
        - Capex: Should be positive in DB (representing the magnitude of expense).
        """
        if field == 'capex':
            return abs(value)
        return value

    @classmethod
    def map_fact(cls, field: str, facts: List[Dict[str, Any]]) -> Optional[float]:
        """
        Extract value for a standard field from a list of facts (for a specific period).
        facts: List of fact dicts (tag, val, ...) available for this period.
        """
        fact_map = {f['tag']: f['val'] for f in facts if f.get('tag') and f.get('val') is not None}

        # SPECIAL HANDLING FOR SPECIFIC INDUSTRIES
        
        # --- REVENUE FALLBACK LOGIC ---
        if field == 'revenue':
            val = cls._try_map(field, fact_map)
            if val is not None:
                return val
            
            # Bank Fallback: Interest Income + Non-Interest Income
            ii = None
            for tag in cls.MAPPING.get('bank_interest_income', []):
                if tag in fact_map:
                    ii = fact_map[tag]
                    break
            nii = None
            for tag in cls.MAPPING.get('bank_noninterest_income', []):
                if tag in fact_map:
                    nii = fact_map[tag]
                    break
            if ii is not None and nii is not None:
                return ii + nii
            if ii is not None:
                return ii
                
            # Insurance Fallback
            for tag in cls.MAPPING.get('insurance_premiums', []):
                if tag in fact_map:
                    return fact_map[tag]
                
        # --- OPERATING INCOME FALLBACK ---
        elif field == 'op_income':
            val = cls._try_map(field, fact_map)
            if val is not None:
                return val
            
            fallback_tags = [
                'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
                'IncomeLossFromContinuingOperationsBeforeIncomeTaxes',
                'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
                'IncomeLossBeforeIncomeTaxes',
            ]
            for tag in fallback_tags:
                if tag in fact_map:
                    return fact_map[tag]
                    
            gp = fact_map.get('GrossProfit')
            sgna = fact_map.get('SellingGeneralAndAdministrativeExpense')
            rnd = fact_map.get('ResearchAndDevelopmentExpense', 0)
            if gp is not None and sgna is not None:
                return gp - sgna - (rnd or 0)

        # --- EQUITY FALLBACK ---
        elif field == 'total_equity':
            val = cls._try_map(field, fact_map)
            if val is not None:
                return val
            
            assets = fact_map.get('Assets')
            liab = fact_map.get('Liabilities')
            if assets is not None and liab is not None:
                return assets - liab

        # --- GROSS PROFIT CALCULATION ---
        elif field == 'gross_profit':
            val = cls._try_map(field, fact_map)
            if val is not None:
                return val
            
            rev = cls._try_map('revenue', fact_map)
            cogs = cls._try_map('cogs', fact_map)
            if rev is not None and cogs is not None:
                return rev - cogs

        # --- TOTAL LIABILITIES FALLBACK ---
        elif field == 'total_liabilities':
            val = cls._try_map(field, fact_map)
            if val is not None:
                return val
            
            assets = fact_map.get('Assets')
            equity_tags = ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest']
            equity = None
            for tag in equity_tags:
                if tag in fact_map:
                    equity = fact_map[tag]
                    break
            if assets is not None and equity is not None:
                return assets - equity

        # --- EBITDA CALCULATION ---
        elif field == 'ebitda':
            op_inc = cls._try_map('op_income', fact_map)
            if op_inc is not None:
                dep = cls._try_map('depreciation_amortization', fact_map) or 0
                return op_inc + dep
            return None

        # DEFAULT LOGIC
        return cls._try_map(field, fact_map)

    @classmethod
    def _try_map(cls, field: str, fact_map: Dict[str, float]) -> Optional[float]:
        """Try to map a field using the standard tag priority list."""
        tags = cls.MAPPING.get(field, [])
        for tag in tags:
            if tag in fact_map:
                val = fact_map[tag]
                if val is not None:
                    return cls.normalize_sign(field, val)
        return None
    
    @classmethod
    def get_all_tracked_tags(cls) -> set:
        """Return all XBRL tags that this mapper tracks."""
        all_tags = set()
        for tags in cls.MAPPING.values():
            all_tags.update(tags)
        return all_tags
