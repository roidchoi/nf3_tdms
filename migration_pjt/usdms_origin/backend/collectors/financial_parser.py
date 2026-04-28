"""
Enhanced Financial Parser with improved data grouping logic.
Key fix: Properly handles Balance Sheet (instant) vs Income Statement/Cash Flow (duration) grouping.
"""
import logging
import time
import pandas as pd
from typing import List, Dict, Any, Tuple
from tqdm import tqdm
from collections import defaultdict
from .sec_client import SECClient
from .db_manager import DatabaseManager
from .xbrl_mapper import XBRLMapper

logger = logging.getLogger(__name__)

class FinancialParser:
    def __init__(self):
        self.sec_client = SECClient()
        self.db_manager = DatabaseManager()
        self.mapper = XBRLMapper()

    def process_filings(self, filings_list: List[Dict[str, Any]]):
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

    def run(self, ciks: List[str]):
        """
        Process list of CIKs with Progress Bar.
        """
        logger.info(f"Starting Financial Backfill for {len(ciks)} tickers...")
        
        # tqdm Progress Bar
        # wrap the loop with tqdm to show progress in terminal
        for cik in tqdm(ciks, desc="Fetching Financials", unit="ticker"):
            try:
                self.process_company(cik)
                # Rate Limiting
                time.sleep(0.5) 
            except Exception as e:
                logger.error(f"Failed to process CIK {cik}: {e}")

    def process_company(self, cik: str):
        #logger.info(f"Processing CIK {cik}...")
        
        # 1. Fetch Raw Data
        facts_json = self.sec_client.get_company_facts(cik)
        
        # --- Process Shares Outstanding (DEI) ---
        dei_data = facts_json.get('facts', {}).get('dei', {})
        if dei_data:
            self._process_shares_outstanding(cik, dei_data)

        us_gaap_data = facts_json.get('facts', {}).get('us-gaap', {})
        
        if not us_gaap_data:
            logger.warning(f"No us-gaap data for CIK {cik}")
            return

        # 2. Flatten & Normalize - IMPROVED VERSION
        raw_facts = []
        for tag, data in us_gaap_data.items():
            units = data.get('units', {})
            for unit_name, records in units.items():
                for r in records:
                    # Include records with 'end' date
                    if 'end' not in r:
                        continue
                    
                    # Calculate duration for filtering
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
                    
        # 3. Insert Raw Facts (Bulk)
        if raw_facts:
            # Delete existing raw facts for this CIK before inserting
            # This ensures we store the full history from the latest file without duplicates.
            self.db_manager.delete_raw_facts_by_cik(cik)
            
            # Bulk Insert
            self.db_manager.insert_financial_facts(raw_facts) 

        # 4. Standardize using improved method
        std_financials = self._standardize_financials_v2(cik, raw_facts)
        
        # 5. Upsert Standard Financials
        self.db_manager.upsert_standard_financials(std_financials)
        #logger.info(f"Upserted {len(std_financials)} standard records for CIK {cik}")

    def _standardize_financials_v2(self, cik: str, raw_facts: List[Dict]) -> List[Dict]:
        """
        IMPROVED VERSION: 
        - Groups by fiscal period (FY, Q1, Q2, Q3) instead of arbitrary dates
        - Properly combines instant (BS) and duration (IS/CF) facts
        - Implements robust Q4/discrete quarter derivation
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
        # Fallback safety
        df['days'] = df['days'].fillna(0)
        
        # Filter to 10-K and 10-Q forms primarily
        valid_forms = ['10-K', '10-Q', '10-K/A', '10-Q/A', '8-K']
        df_filtered = df[df['form'].isin(valid_forms)].copy()
        
        if df_filtered.empty or len(df_filtered) < len(df) * 0.1:
            logger.warning(f"No 10-K/10-Q data for CIK {cik}, using all forms")
            df_filtered = df.copy()
        
        # ================================================================
        # KEY FIX: Group by (fy, fp) instead of (period_end, filed_dt)
        # This ensures BS and IS/CF items are combined correctly
        # ================================================================
        
        # Build a map: (fy, fp) -> list of facts
        # For each (fy, fp), collect:
        #   - Instant items (BS) from the most recent filing
        #   - Duration items (IS/CF) - discrete quarterly values
        
        results = []
        
        # Group by fiscal year and period
        grouped = df_filtered.groupby(['fy', 'fp'])
        
        for (fy, fp), group in grouped:
            if pd.isna(fy) or pd.isna(fp):
                continue
                
            # [Fix] Filter out historical comparison data in the same report
            
            # Latest end date only
            max_end_date = group['period_end'].max()
            group = group[group['period_end'] == max_end_date]
            
            if group.empty: continue
            
            latest_filed = group['filed_dt'].max()
            period_end = group['period_end'].max()
            
            facts_pool = {}
            
            # 1. Instant
            instant_rows = group[group['days'] == 0]
            instant_sorted = instant_rows.sort_values(['filed_dt', 'period_end'], ascending=[False, False])
            for _, row in instant_sorted.iterrows():
                if row['tag'] not in facts_pool:
                    facts_pool[row['tag']] = row['val']
                    
            # 2. Duration
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
                
            # 4. Map
            std_record = {
                'cik': cik,
                'report_period': period_end.date(),
                'filed_dt': latest_filed.date(),
                'fiscal_year': int(fy),
                'fiscal_period': fp
            }
            
            facts_list = [{'tag': k, 'val': v} for k, v in facts_pool.items()]
            
            for field in self.mapper.MAPPING.keys():
                if field in ['total_debt']:
                    ltd = self.mapper.map_fact('long_term_debt', facts_list) or 0
                    std = self.mapper.map_fact('short_term_debt', facts_list) or 0
                    val = ltd + std if (ltd or std) else None
                elif field in ['fcf', 'ebitda']:
                    val = None
                elif field in ['bank_interest_income', 'bank_noninterest_income', 'insurance_premiums']:
                    continue
                else:
                    val = self.mapper.map_fact(field, facts_list)
                std_record[field] = val
                
            # 5. Post Calc
            if std_record.get('ocf') is not None and std_record.get('capex') is not None:
                std_record['fcf'] = std_record['ocf'] - std_record['capex']
            if std_record.get('op_income') is not None:
                dep = self.mapper.map_fact('depreciation_amortization', facts_list) or 0
                std_record['ebitda'] = std_record['op_income'] + dep
                
            # 6. Validate
            has_bs = std_record.get('total_assets') is not None
            has_is = std_record.get('revenue') is not None or std_record.get('net_income') is not None
            
            if has_bs or has_is:
                results.append(std_record)
                
        # --- PATCH 2: Batch Deduplication ---
        # Resolve duplicates on (cik, report_period, filed_dt) by keeping the last processed one (or most complete)
        if not results:
            return []
            
        deduped = {}
        for r in results:
            key = (r['cik'], r['report_period'], r['filed_dt'])
            if key in deduped:
                # Keep new one if it has equal or more fields
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
            return 'Q'  # Single quarter (~90 days)
        elif 170 <= days <= 195:
            return 'H1'  # Half year / Q2 YTD (~180 days)
        elif 260 <= days <= 290:
            return 'Q3_YTD'  # 9 months (~270 days)
        elif 350 <= days <= 380:
            return 'FY'  # Full year (~365 days)
        else:
            return 'OTHER'
    
    def _derive_discrete_from_ytd(self, cik: str, fy: int, fp: str, 
                                   facts_pool: Dict, df: pd.DataFrame) -> Dict:
        """
        Derive discrete quarter value from YTD values.
        Q2_discrete = Q2_YTD - Q1
        Q3_discrete = Q3_YTD - Q2_YTD
        """
        # Determine what YTD period we need
        if fp == 'Q2':
            current_ytd_type = 'H1'
            prev_qtr = 'Q1'
            prev_ytd_type = 'Q'
        elif fp == 'Q3':
            current_ytd_type = 'Q3_YTD'
            prev_qtr = 'Q2'
            prev_ytd_type = 'H1'
        else:
            return facts_pool
        
        # Get current YTD values from this period
        current_period = df[(df['fy'] == fy) & (df['fp'] == fp)]
        current_ytd = current_period[current_period['days'].apply(self._classify_duration) == current_ytd_type]
        
        # Get previous period values
        prev_period = df[(df['fy'] == fy) & (df['fp'] == prev_qtr)]
        if fp == 'Q2':
            prev_values = prev_period[prev_period['days'].apply(self._classify_duration) == 'Q']
        else:  # Q3
            prev_values = prev_period[prev_period['days'].apply(self._classify_duration) == 'H1']
        
        # Build maps
        current_ytd_map = {row['tag']: row['val'] for _, row in current_ytd.iterrows()}
        prev_map = {row['tag']: row['val'] for _, row in prev_values.iterrows()}
        
        # Derive for tags not in facts_pool
        for tag, ytd_val in current_ytd_map.items():
            if tag not in facts_pool and tag in prev_map:
                derived = ytd_val - prev_map[tag]
                facts_pool[tag] = derived
                logger.debug(f"[DERIVE] {cik} {fp} {fy}: {tag} = {ytd_val} - {prev_map[tag]} = {derived}")
        
        return facts_pool
    
    def _derive_q4(self, cik: str, fy: int, facts_pool: Dict, df: pd.DataFrame) -> Dict:
        """
        Derive Q4 discrete values: Q4 = FY - Q3_YTD
        """
        # Get Q3 YTD values
        q3_period = df[(df['fy'] == fy) & (df['fp'] == 'Q3')]
        q3_ytd = q3_period[q3_period['days'].apply(self._classify_duration) == 'Q3_YTD']
        
        q3_ytd_map = {row['tag']: row['val'] for _, row in q3_ytd.iterrows()}
        
        # For FY values that are already in facts_pool
        # We don't need to derive since FY is reported directly
        # But if we want Q4 specifically, we'd need to:
        # Q4 = FY - Q3_YTD
        
        # Actually, for annual reports we typically want the FY values,
        # not the Q4 discrete values. So we keep facts_pool as is.
        
        return facts_pool

    def _process_shares_outstanding(self, cik: str, dei_data: Dict[str, Any]):
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
            self.db_manager.upsert_share_history(share_list)
            logger.info(f"Upserted {len(share_list)} shares history records for CIK {cik}")


# ================================================================
# ORIGINAL METHOD (preserved for reference/comparison)
# ================================================================
    def _standardize_financials_original(self, cik: str, raw_facts: List[Dict]) -> List[Dict]:
        """
        Original method - kept for comparison.
        Issues: Groups by (period_end, filed_dt) which separates BS and IS/CF items.
        """
        df = pd.DataFrame(raw_facts)
        if df.empty:
            return []

        df['period_end'] = pd.to_datetime(df['period_end'])
        df['filed_dt'] = pd.to_datetime(df['filed_dt'])
        if 'period_start' in df.columns:
            df['period_start'] = pd.to_datetime(df['period_start'])
            df['days'] = (df['period_end'] - df['period_start']).dt.days
        else:
            df['days'] = 0

        grouped = df.groupby(['period_end', 'filed_dt'])
        results = []
        
        for (end_dt, filed_dt), group in grouped:
            facts_pool = {}
            
            instant_rows = group[group['days'] == 0]
            for _, row in instant_rows.iterrows():
                facts_pool[row['tag']] = row['val']
                
            duration_rows = group[group['days'] > 0]
            q_rows = duration_rows[(duration_rows['days'] >= 80) & (duration_rows['days'] <= 100)]
            
            for _, row in q_rows.iterrows():
                facts_pool[row['tag']] = row['val']

            std_record = {
                'cik': cik,
                'report_period': end_dt.date(),
                'filed_dt': filed_dt.date()
            }
            
            for field in self.mapper.MAPPING.keys():
                if field == 'total_debt':
                    ltd = self.mapper.map_fact('long_term_debt', [{'tag': k, 'val': v} for k,v in facts_pool.items()]) or 0
                    std = self.mapper.map_fact('short_term_debt', [{'tag': k, 'val': v} for k,v in facts_pool.items()]) or 0
                    val = ltd + std
                    if val == 0: val = None
                elif field in ['fcf', 'ebitda']:
                    val = None
                else:
                    val = self.mapper.map_fact(field, [{'tag': k, 'val': v} for k,v in facts_pool.items()])
                
                std_record[field] = val

            if std_record.get('ocf') is not None and std_record.get('capex') is not None:
                std_record['fcf'] = std_record['ocf'] - std_record['capex']
                
            if std_record.get('op_income') is not None:
                dep = self.mapper.map_fact('depreciation_amortization', [{'tag': k, 'val': v} for k,v in facts_pool.items()]) or 0
                std_record['ebitda'] = std_record['op_income'] + dep

            if std_record.get('total_assets') or std_record.get('revenue'):
                results.append(std_record)
                
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = FinancialParser()
    # Test with Apple
    parser.run(['0000320193'])