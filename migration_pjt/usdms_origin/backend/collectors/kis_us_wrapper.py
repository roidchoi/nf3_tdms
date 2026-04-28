# collectors/kis_us_rest.py

import pandas as pd
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Union
from .kis_api_core import KisREST  # 부모 클래스 임포트

class KisUSREST(KisREST):
    """
    한국투자증권 미국 주식 REST API 래퍼
    기존 KisREST를 상속받아 토큰 관리 및 기본 요청 로직을 공유합니다.
    """

    # 해외주식 기간별시세 상수
    TR_ID_DAILY = 'HHDFS76240000'
    URL_DAILY = '/uapi/overseas-price/v1/quotations/dailyprice'
    
    # 순환 확인할 거래소 목록 (나스닥, 뉴욕, 아멕스)
    EXCHANGE_CANDIDATES = ['NAS', 'NYS', 'AMS']

    def __init__(self, mock: bool = False, log_level: int = 3):
        super().__init__(mock=mock, log_level=log_level)
        self.logger.info(f"✅ [KisUSREST] 미국 주식 모듈 초기화 ({self.mode_name})")

    def _fetch_chunk(self, ticker: str, exchange: str, base_date: str, 
                     mod_yn: str, period_code: str = '0') -> List[Dict]:
        """
        1회(최대 100건) 데이터를 요청합니다.
        """
        # KIS API Compatibility: Replace '-' with '/' (e.g., BRK-B -> BRK/B)
        formatted_ticker = ticker.replace('-', '/')

        params = {
            'AUTH': '',
            'EXCD': exchange,
            'SYMB': formatted_ticker,
            'GUBN': period_code,  # 0:일, 1:주, 2:월
            'BYMD': base_date,    # 기준일자 (이 날짜 이전 데이터를 가져옴)
            'MODP': mod_yn,       # 0:미반영(Raw), 1:반영(Adj)
            'KEYB': ''            
        }

        try:
            # 부모 클래스의 _request 메서드 재사용
            # 404나 500 에러가 아닌 API 로직상 실패(데이터 없음 등)는 빈 리스트 반환으로 처리
            res = self._request('GET', self.URL_DAILY, self.TR_ID_DAILY, params=params)
            return res.json().get('output2', [])
        except Exception:
            # 거래소 코드가 틀렸거나 데이터가 없는 경우 예외가 발생할 수 있음
            return []

    def _find_exchange(self, ticker: str) -> Optional[str]:
        """
        거래소 코드가 지정되지 않은 경우, 주요 거래소를 순환하며 종목이 존재하는지 확인합니다.
        """
        self.logger.debug(f"🔍 [{ticker}] 거래소 자동 탐색 시작...")
        today_str = datetime.now().strftime("%Y%m%d")
        
        for ex in self.EXCHANGE_CANDIDATES:
            # 가장 최근 데이터 1건만 요청해보는 핑(Ping) 테스트
            chunk = self._fetch_chunk(ticker, ex, today_str, mod_yn='0')
            if chunk:
                self.logger.debug(f"✅ [{ticker}] 거래소 확인됨: {ex}")
                return ex
            time.sleep(0.1) # 과도한 호출 방지
            
        self.logger.error(f"❌ [{ticker}] 해당 종목을 {self.EXCHANGE_CANDIDATES}에서 찾을 수 없습니다.")
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
            # 이번 청크의 가장 과거 날짜
            oldest_date_in_chunk = temp_df['date'].min()
            
            # 이번 청크의 가장 과거 날짜가 목표 시작일보다 더 과거라면, 더 이상 조회할 필요 없음
            if oldest_date_in_chunk < target_start_dt:
                break
            
            # 데이터가 더 없는데(청크 크기가 100개 미만) API가 끝난 경우
            if len(chunk) < 100:
                break

            # 5. 다음 페이지네이션 설정
            next_base_dt = oldest_date_in_chunk - timedelta(days=1)
            current_base_date = next_base_dt.strftime("%Y%m%d")
            
            time.sleep(0.1) # Rate Limit 관리

        if not all_data:
            return pd.DataFrame()

        # 전체 병합
        result_df = pd.concat(all_data).sort_values('date').reset_index(drop=True)
        
        # 날짜 범위 재필터링 (청크 단위라 섞일 수 있는 부분 정리)
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
        result_df = result_df.rename(columns=cols)[cols.values()]
        
        # 숫자형 변환
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            result_df[col] = pd.to_numeric(result_df[col])
            
        return result_df.set_index('Date')

    def get_ohlcv(self, ticker: str, 
                  start_date: Optional[str] = None, 
                  end_date: Optional[str] = None, 
                  exchange: Optional[str] = None, 
                  add_adjusted: bool = True) -> pd.DataFrame:
        """
        [Main] yfinance 스타일의 OHLCV + Adj Close 데이터를 반환합니다.
        
        :param ticker: 종목코드 (예: TSLA)
        :param start_date: 시작일 (YYYYMMDD). None일 경우 19800101(전체)로 설정.
        :param end_date: 종료일 (YYYYMMDD). None일 경우 오늘 날짜로 설정.
        :param exchange: 거래소코드. None일 경우 자동 탐색.
        :param add_adjusted: True일 경우 수정주가(Adj Close) 컬럼을 포함. (API 2회 호출)
        """
        # 1. 날짜 기본값 설정
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        
        if start_date is None:
            # 사실상 전체 데이터를 의미하는 과거 날짜
            start_date = "19800101" 

        # 2. 거래소 자동 탐색
        if exchange is None:
            exchange = self._find_exchange(ticker)
            if exchange is None:
                self.logger.warning(f"⚠️ [Stop] {ticker}의 거래소를 찾을 수 없어 조회를 중단합니다.")
                return pd.DataFrame()

        self.logger.debug(f"🇺🇸 시세 수집 시작: {ticker}({exchange}) {start_date}~{end_date}")

        # 3. Raw Data 수집 (MODP='0')
        df_raw = self._collect_period_data(ticker, exchange, start_date, end_date, mod_yn='0')
        
        if df_raw.empty:
            self.logger.warning(f"❌ 데이터 없음: {ticker}")
            return df_raw

        # 수정 주가를 원하지 않으면 여기서 반환 (이름 변경 반영: adjusted -> add_adjusted)
        if not add_adjusted:
            return df_raw

        # 4. Adjusted Data 수집 (MODP='1') -> Adj Close 확보용
        self.logger.debug(f"🔄 수정주가(Adj Close) 추가 수집 중...")
        df_adj = self._collect_period_data(ticker, exchange, start_date, end_date, mod_yn='1')

        if df_adj.empty:
            df_raw['Adj Close'] = df_raw['Close']
            return df_raw

        # 5. 병합 (Index인 Date 기준)
        df_adj_subset = df_adj[['Close']].rename(columns={'Close': 'Adj Close'})
        final_df = df_raw.join(df_adj_subset, how='left')
        
        # 6. 컬럼 순서 정리
        desired_order = ['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
        # 혹시 모를 누락 컬럼 대비
        existing_cols = [c for c in desired_order if c in final_df.columns]
        final_df = final_df[existing_cols]
        
        self.logger.debug(f"✅ 수집 완료: {len(final_df)}건")
        return final_df

# === 사용 예시 ===
if __name__ == "__main__":
    try:
        kis_us = KisUSREST(mock=False)
        
        # 1. 거래소, 날짜 미지정 테스트 (자동 탐지 + 전체 기간)
        print("\n--- [Test 1] Auto Exchange & Full History (TSLA) ---")
        df_full = kis_us.get_ohlcv("TSLA", add_adjusted=True)  # 변경된 인자명 테스트
        if not df_full.empty:
            print(f"조회 기간: {df_full.index.min()} ~ {df_full.index.max()}")
            print(df_full.tail())
        
        # 2. Raw 데이터만 수집 테스트
        print("\n--- [Test 2] Raw Only (TSLA) ---")
        df_raw = kis_us.get_ohlcv("TSLA", start_date="20240101", add_adjusted=False) # 변경된 인자명 테스트
        print(f"컬럼 확인: {df_raw.columns.tolist()}")

    except Exception as e:
        print(f"Error: {e}")