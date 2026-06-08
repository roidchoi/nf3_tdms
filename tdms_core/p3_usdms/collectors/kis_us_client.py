import logging
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from p1_shared.api.kis_api_core import KisApiCore

logger = logging.getLogger(__name__)

class KisUSClient(KisApiCore):
    """
    한국투자증권 미국 주식 REST API 클라이언트.
    p1_shared.api.KisApiCore를 상속받아 토큰 발급 및 재시도 메커니즘을 상속합니다.
    """
    TR_ID_DAILY = 'HHDFS76240000'
    URL_DAILY = '/uapi/overseas-price/v1/quotations/dailyprice'
    EXCHANGE_CANDIDATES = ['NAS', 'NYS', 'AMS']

    def __init__(self, app_key: str, app_secret: str, account_no: str, is_mock: bool = False):
        super().__init__(app_key, app_secret, account_no, is_mock=is_mock)
        logger.info(f"✅ [KisUSClient] 미국 주식 모듈 초기화 (is_mock={is_mock})")

    def _fetch_chunk(self, ticker: str, exchange: str, base_date: str, mod_yn: str) -> list[dict]:
        """
        1회 데이터 요청(최대 100건).
        BRK-B 처럼 하이픈이 들어간 티커는 KIS API 호환을 위해 슬래시(/)로 변경(BRK/B).
        """
        formatted_ticker = ticker.replace('-', '/')
        params = {
            'AUTH': '',
            'EXCD': exchange,
            'SYMB': formatted_ticker,
            'GUBN': '0',         # 0: 일봉 시세
            'BYMD': base_date,    # 기준일자 (이 날짜 이전 데이터를 가져옴)
            'MODP': mod_yn,       # '0': Raw Close, '1': Adj Close
            'KEYB': ''
        }
        
        try:
            # 부모의 request 함수 사용. requests.Response 객체가 아닌 dict를 직접 반환함.
            res = self.request('GET', self.URL_DAILY, params=params, tr_id=self.TR_ID_DAILY)
            return res.get('output2', [])
        except Exception as e:
            logger.warning(f"⚠️ [{ticker}] Chunk fetch failed (Exch: {exchange}, Date: {base_date}): {e}")
            return []

    def _find_exchange(self, ticker: str) -> Optional[str]:
        """
        거래소 코드가 지정되지 않은 경우, 주요 거래소를 순환하며 종목이 존재하는지 확인합니다.
        """
        logger.debug(f"🔍 [{ticker}] 거래소 자동 탐색 시작...")
        today_str = datetime.now().strftime("%Y%m%d")
        
        for ex in self.EXCHANGE_CANDIDATES:
            # 가장 최근 데이터 1건만 요청해보는 핑(Ping) 테스트
            chunk = self._fetch_chunk(ticker, ex, today_str, mod_yn='0')
            if chunk:
                logger.debug(f"✅ [{ticker}] 거래소 확인됨: {ex}")
                return ex
            time.sleep(0.1) # 과도한 호출 방지
            
        logger.error(f"❌ [{ticker}] 해당 종목을 {self.EXCHANGE_CANDIDATES}에서 찾을 수 없습니다.")
        return None

    def _collect_period_data(self, ticker: str, exchange: str, 
                             start_date: str, end_date: str, 
                             mod_yn: str) -> pd.DataFrame:
        """
        지정된 기간의 데이터를 페이지네이션하며 수집합니다.
        """
        all_data = []
        current_base_date = end_date 
        target_start_dt = datetime.strptime(start_date, "%Y%m%d")

        while True:
            # 1. 청크 데이터 요청
            chunk = self._fetch_chunk(ticker, exchange, current_base_date, mod_yn)
            
            if not chunk:
                break

            # 2. 데이터 가공
            temp_df = pd.DataFrame(chunk)
            temp_df['date'] = pd.to_datetime(temp_df['xymd'])
            
            # 3. 유효 데이터 필터링 (start_date보다 크거나 같은 것만)
            valid_rows = temp_df[temp_df['date'] >= target_start_dt]
            
            if not valid_rows.empty:
                all_data.append(valid_rows)
            
            # 4. 종료 조건 확인
            oldest_date_in_chunk = temp_df['date'].min()
            
            # 이번 청크의 가장 과거 날짜가 목표 시작일보다 더 과거라면, 더 이상 조회할 필요 없음
            if oldest_date_in_chunk < target_start_dt:
                break
            
            # 데이터가 더 없는데(청크 크기가 100개 미만) API가 끝난 경우
            if len(chunk) < 100:
                break

            # 5. 다음 페이지네이션 설정 (하루를 빼서 이전 페이지 조회)
            next_base_dt = oldest_date_in_chunk - timedelta(days=1)
            current_base_date = next_base_dt.strftime("%Y%m%d")
            
            time.sleep(0.1) # Rate Limit 관리

        if not all_data:
            return pd.DataFrame()

        # 전체 병합
        result_df = pd.concat(all_data).sort_values('date').reset_index(drop=True)
        
        # 날짜 범위 정리
        result_df = result_df[result_df['date'] >= target_start_dt]

        # 컬럼 매핑
        cols = {
            'date': 'Date',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'clos': 'Close',
            'tvol': 'Volume'
        }
        result_df = result_df.rename(columns=cols)
        # 필요한 열만 필터링
        result_df = result_df[[c for c in cols.values() if c in result_df.columns]]
        
        # 숫자형 변환
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in result_df.columns:
                result_df[col] = pd.to_numeric(result_df[col], errors='coerce')
            
        return result_df.set_index('Date')

    def get_ohlcv(self, ticker: str, 
                  start_date: Optional[str] = None, 
                  end_date: Optional[str] = None, 
                  exchange: Optional[str] = None, 
                  add_adjusted: bool = True) -> pd.DataFrame:
        """
        yfinance 스타일의 OHLCV + Adj Close 데이터를 반환합니다.
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        
        if start_date is None:
            # 사실상 전체 데이터를 의미하는 과거 날짜
            start_date = "19800101" 

        # 거래소 자동 탐색
        if exchange is None:
            exchange = self._find_exchange(ticker)
            if exchange is None:
                logger.warning(f"⚠️ [Stop] {ticker}의 거래소를 찾을 수 없어 조회를 중단합니다.")
                return pd.DataFrame()

        logger.debug(f"🇺🇸 시세 수집 시작: {ticker}({exchange}) {start_date}~{end_date}")

        # 1. Raw Data 수집 (MODP='0')
        df_raw = self._collect_period_data(ticker, exchange, start_date, end_date, mod_yn='0')
        
        if df_raw.empty:
            logger.warning(f"❌ 데이터 없음: {ticker}")
            return df_raw

        # 수정 주가를 원하지 않으면 여기서 반환
        if not add_adjusted:
            return df_raw

        # 2. Adjusted Data 수집 (MODP='1') -> Adj Close 확보용
        logger.debug(f"🔄 수정주가(Adj Close) 추가 수집 중...")
        df_adj = self._collect_period_data(ticker, exchange, start_date, end_date, mod_yn='1')

        if df_adj.empty:
            df_raw['Adj Close'] = df_raw['Close']
            return df_raw

        # 3. 병합 (Index인 Date 기준)
        df_adj_subset = df_adj[['Close']].rename(columns={'Close': 'Adj Close'})
        final_df = df_raw.join(df_adj_subset, how='left')
        
        # NaN 값 방어 (조인 실패 등 대비)
        if 'Adj Close' in final_df.columns:
            final_df['Adj Close'] = final_df['Adj Close'].fillna(final_df['Close'])
        else:
            final_df['Adj Close'] = final_df['Close']

        # 4. 컬럼 순서 정리
        desired_order = ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        existing_cols = [c for c in desired_order if c in final_df.columns]
        final_df = final_df[existing_cols]
        
        logger.debug(f"✅ 수집 완료: {len(final_df)}건")
        return final_df
