"""
Enhanced Financial Parser for SEC XBRL facts.
Standardizes EAV facts into standard fields with discrete quarter derivation.
"""
import logging
import time
import pandas as pd
from typing import List, Dict, Any, Optional
from tqdm import tqdm
from p3_usdms.collectors.sec_client import SECClient
from p3_usdms.collectors.xbrl_mapper import XBRLMapper
from p3_usdms.repositories.financial_repo import FinancialRepo

logger = logging.getLogger(__name__)

class FinancialParser:
    def __init__(self) -> None:
        """
        Initialize SECClient, FinancialRepo, and XBRLMapper dependencies.
        """
        self.sec_client = SECClient()
        self.repo = FinancialRepo()
        self.mapper = XBRLMapper()

    def process_filings(self, filings_list: List[Dict[str, Any]]) -> None:
        """
        Process a list of filings identified by the Gap Scanner.
        Expects list of dicts: [{'cik': '123...', ...}, ...]
        Deduplicates by CIK and delegates to self.run().
        """
        if not filings_list:
            return
            
        target_ciks = set()
        for f in filings_list:
            if 'cik' in f:
                target_ciks.add(str(f['cik']).zfill(10))
                
        logger.info(f"Gap Recovery: Processing {len(target_ciks)} CIKs...")
        self.run(sorted(list(target_ciks)))

    def run(self, ciks: List[str]) -> None:
        """
        Process list of CIKs with progress bar.
        """
        logger.info(f"Starting Financial Backfill for {len(ciks)} tickers...")
        
        for cik in tqdm(ciks, desc="Fetching Financials", unit="ticker"):
            try:
                self.process_company(cik)
                # Rate Limiting
                time.sleep(0.5) 
            except Exception as e:
                logger.error(f"Failed to process CIK {cik}: {e}")

    def process_company(self, cik: str) -> None:
        """
        1. SEC API를 통한 raw company facts 데이터 fetch
        2. dei 파트 내 주식수 정보 추출 및 us_share_history 저장
        3. us-gaap raw facts 데이터 추출 및 EAV 구조로 us_financial_facts에 벌크 업서트
        4. _standardize_financials_v2 알고리즘을 통한 회계 데이터 그룹화 및 이산값 계산
        5. 정제 완료된 표준 데이터 us_standard_financials에 업서트
        """
        facts_json = self.sec_client.get_company_facts(cik)
        
        # 1. Process Shares Outstanding (DEI)
        dei_data = facts_json.get('facts', {}).get('dei', {})
        if dei_data:
            self._process_shares_outstanding(cik, dei_data)

        us_gaap_data = facts_json.get('facts', {}).get('us-gaap', {})
        if not us_gaap_data:
            logger.warning(f"No us-gaap data for CIK {cik}")
            return

        # 2. Flatten & Normalize
        raw_facts = []
        for tag, data in us_gaap_data.items():
            units = data.get('units', {})
            for unit_name, records in units.items():
                for r in records:
                    if 'end' not in r:
                        continue
                    
                    period_start = r.get('start')
                    period_end = r['end']
                    
                    raw_facts.append({
                        'cik': cik,
                        'tag': tag,
                        'val': r['val'],
                        'period_start': period_start,
                        'period_end': period_end,
                        'filed_dt': r['filed'],
                        'frame': r.get('frame'),
                        'form': r.get('form'),
                        'fy': r.get('fy'),
                        'fp': r.get('fp'),
                        'unit': unit_name,
                    })
                    
        # 3. Clean & Bulk Insert
        if raw_facts:
            self.repo.delete_raw_facts_by_cik(cik)
            self.repo.insert_financial_facts(raw_facts) 

        # 4. Standardize using improved method
        std_financials = self._standardize_financials_v2(cik, raw_facts)
        
        # 5. Upsert Standard Financials
        if std_financials:
            self.repo.upsert_standard_financials(std_financials)

    def _standardize_financials_v2(self, cik: str, raw_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        - (fy, fp) 기준으로 그룹화
        - Instant 정보(B/S)와 Duration 정보(I/S, C/F) 결합
        - _derive_discrete_from_ytd() 및 _derive_q4() 를 적용하여 분기 이산 정보 보완
        """
        if not raw_facts:
            return []
            
        df = pd.DataFrame(raw_facts)
        
        # Ensure dates
        df['period_end'] = pd.to_datetime(df['period_end'])
        df['filed_dt'] = pd.to_datetime(df['filed_dt'])
        df['period_start'] = pd.to_datetime(df['period_start'])
        
        # Calculate duration (0 for instant items like Balance Sheet)
        df['days'] = df.apply(
            lambda x: (x['period_end'] - x['period_start']).days if pd.notna(x['period_start']) else 0,
            axis=1
        )
        df['days'] = df['days'].fillna(0)
        
        # Filter forms
        valid_forms = ['10-K', '10-Q', '10-K/A', '10-Q/A', '8-K']
        df_filtered = df[df['form'].isin(valid_forms)].copy()
        
        if df_filtered.empty or len(df_filtered) < len(df) * 0.1:
            df_filtered = df.copy()
        
        # [개선 2] fy(회계연도) 결측치 및 타입 혼선 방지를 위한 정수 캐스팅
        df_filtered['fy'] = pd.to_numeric(df_filtered['fy'], errors='coerce').fillna(0).astype(int)
        df_filtered = df_filtered[df_filtered['fy'] > 0]
        
        results = []
        
        # Group by fiscal year and period
        grouped = df_filtered.groupby(['fy', 'fp'])
        
        for (fy, fp), group in grouped:
            if pd.isna(fy) or pd.isna(fp):
                continue
                
            max_end_date = group['period_end'].max()
            group = group[group['period_end'] == max_end_date]
            
            if group.empty:
                continue
            
            latest_filed = group['filed_dt'].max()
            period_end = group['period_end'].max()
            
            facts_pool = {}
            
            # 1. Instant (Balance Sheet items)
            instant_rows = group[group['days'] == 0]
            instant_sorted = instant_rows.sort_values(['filed_dt', 'period_end'], ascending=[False, False])
            for _, row in instant_sorted.iterrows():
                if row['tag'] not in facts_pool:
                    facts_pool[row['tag']] = row['val']
                    
            # 2. Duration (Income Statement / Cash Flow items)
            duration_rows = group[group['days'] > 0]
            if not duration_rows.empty:
                duration_rows = duration_rows.copy()
                duration_rows['qtr_type'] = duration_rows['days'].apply(self._classify_duration)
                
                if fp == 'FY':
                    fy_rows = duration_rows[duration_rows['qtr_type'] == 'FY']
                    for _, row in fy_rows.sort_values('filed_dt', ascending=False).iterrows():
                        if row['tag'] not in facts_pool:
                            facts_pool[row['tag']] = row['val']
                elif fp in ['Q1', 'Q2', 'Q3']:
                    q_rows = duration_rows[duration_rows['qtr_type'] == 'Q']
                    for _, row in q_rows.sort_values('filed_dt', ascending=False).iterrows():
                        if row['tag'] not in facts_pool:
                            facts_pool[row['tag']] = row['val']
                            
            # 3. Derivations
            if fp in ['Q2', 'Q3']:
                facts_pool = self._derive_discrete_from_ytd(cik, fy, fp, facts_pool, df_filtered)
            elif fp == 'FY':
                facts_pool = self._derive_q4(cik, fy, facts_pool, df_filtered)
                
            # 4. Map to standardized fields
            std_record = {
                'cik': cik,
                'report_period': period_end.date(),
                'filed_dt': latest_filed.date(),
                'fiscal_year': int(fy),
                'fiscal_period': fp
            }
            
            facts_list = [{'tag': k, 'val': v} for k, v in facts_pool.items()]
            
            for field in self.mapper.MAPPING.keys():
                if field == 'total_debt':
                    # [개선 1] ltd와 std 중 하나라도 수집되었다면 0이라도 유효값으로 반환
                    ltd = self.mapper.map_fact('long_term_debt', facts_list)
                    std = self.mapper.map_fact('short_term_debt', facts_list)
                    if ltd is not None or std is not None:
                        val = (ltd or 0.0) + (std or 0.0)
                    else:
                        val = None
                elif field in ['fcf', 'ebitda']:
                    val = None
                elif field in ['bank_interest_income', 'bank_noninterest_income', 'insurance_premiums']:
                    continue
                else:
                    val = self.mapper.map_fact(field, facts_list)
                std_record[field] = val
                
            # 5. Post Calculations
            if std_record.get('ocf') is not None and std_record.get('capex') is not None:
                std_record['fcf'] = std_record['ocf'] - std_record['capex']
            if std_record.get('op_income') is not None:
                dep = self.mapper.map_fact('depreciation_amortization', facts_list) or 0
                std_record['ebitda'] = std_record['op_income'] + dep
                
            # 6. Validate (Ensure basic balance sheet or income statement content exists)
            has_bs = std_record.get('total_assets') is not None
            has_is = std_record.get('revenue') is not None or std_record.get('net_income') is not None
            
            if has_bs or has_is:
                results.append(std_record)
                
        if not results:
            return []
            
        # Dedup on (cik, report_period, filed_dt)
        deduped = {}
        for r in results:
            key = (r['cik'], r['report_period'], r['filed_dt'])
            if key in deduped:
                old_cnt = sum(1 for v in deduped[key].values() if v is not None)
                new_cnt = sum(1 for v in r.values() if v is not None)
                if new_cnt >= old_cnt:
                    deduped[key] = r
            else:
                deduped[key] = r
                
        final_results = list(deduped.values())
        if len(final_results) < len(results):
            logger.info(f"[{cik}] Batch Deduped: {len(results)} -> {len(final_results)} records.")
            
        return final_results
    
    def _classify_duration(self, days: int) -> str:
        """Classify a duration into quarter type."""
        if days <= 0:
            return 'INSTANT'
        elif 80 <= days <= 100:
            return 'Q'
        elif 170 <= days <= 195:
            return 'H1'
        elif 260 <= days <= 290:
            return 'Q3_YTD'
        elif 350 <= days <= 380:
            return 'FY'
        else:
            return 'OTHER'
    
    def _derive_discrete_from_ytd(self, cik: str, fy: int, fp: str, 
                                   facts_pool: Dict[str, float], df: pd.DataFrame) -> Dict[str, float]:
        """
        Derive discrete quarter value from YTD values.
        Q2_discrete = Q2_YTD - Q1
        Q3_discrete = Q3_YTD - Q2_YTD
        """
        if fp == 'Q2':
            current_ytd_type = 'H1'
            prev_qtr = 'Q1'
        elif fp == 'Q3':
            current_ytd_type = 'Q3_YTD'
            prev_qtr = 'Q2'
        else:
            return facts_pool
        
        current_period = df[(df['fy'] == fy) & (df['fp'] == fp)]
        current_ytd = current_period[current_period['days'].apply(self._classify_duration) == current_ytd_type]
        
        prev_period = df[(df['fy'] == fy) & (df['fp'] == prev_qtr)]
        if fp == 'Q2':
            prev_values = prev_period[prev_period['days'].apply(self._classify_duration) == 'Q']
        else:
            prev_values = prev_period[prev_period['days'].apply(self._classify_duration) == 'H1']
        
        current_ytd_map = {row['tag']: row['val'] for _, row in current_ytd.iterrows()}
        prev_map = {row['tag']: row['val'] for _, row in prev_values.iterrows()}
        
        for tag, ytd_val in current_ytd_map.items():
            if tag not in facts_pool and tag in prev_map:
                derived = ytd_val - prev_map[tag]
                facts_pool[tag] = derived
                logger.debug(f"[DERIVE] {cik} {fp} {fy}: {tag} = {ytd_val} - {prev_map[tag]} = {derived}")
        
        return facts_pool
    
    def _derive_q4(self, cik: str, fy: int, facts_pool: Dict[str, float], df: pd.DataFrame) -> Dict[str, float]:
        """
        Derive Q4 discrete values (FY - Q3_YTD).
        Keeps facts_pool as is since annual reports typically focus on FY values.
        """
        return facts_pool

    def _process_shares_outstanding(self, cik: str, dei_data: Dict[str, Any]) -> None:
        """Extract EntityCommonStockSharesOutstanding and upsert to us_share_history."""
        tag = 'EntityCommonStockSharesOutstanding'
        if tag not in dei_data:
            return
            
        units = dei_data[tag].get('units', {})
        records = []
        for unit_name, recs in units.items():
            records.extend(recs)
            
        if not records:
            return
        
        parsed_shares = {}
        for r in records:
            if 'val' not in r or 'filed' not in r:
                continue
                
            filed_dt = r['filed']
            val = r['val']
            end_dt = r.get('end', '0000-00-00')
            
            if filed_dt in parsed_shares:
                if end_dt > parsed_shares[filed_dt]['end']:
                   parsed_shares[filed_dt] = {'val': val, 'end': end_dt} 
            else:
                parsed_shares[filed_dt] = {'val': val, 'end': end_dt}
                
        share_list = []
        for f_dt, data in parsed_shares.items():
            share_list.append({
                'cik': cik,
                'filed_dt': f_dt,
                'val': data['val']
            })
            
        if share_list:
            self.repo.upsert_share_history(share_list)
            logger.info(f"Upserted {len(share_list)} shares history records for CIK {cik}")
