# collectors/kiwoom_rest.py

import requests
import time
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from dotenv import load_dotenv
import os

LOG_FILE = 'kiwoom_api.log'

# (수정) 커스텀 예외는 exceptions 모듈에서 import
from collectors.exceptions import KiwoomAPIError, TokenAuthError

class TokenManager:
    """접근 토큰 관리를 담당하는 클래스"""
    def __init__(self, app_key: str, secret_key: str, base_url: str,
                 cache_file: str, logger: logging.Logger):
        self.app_key = app_key
        self.secret_key = secret_key
        self.base_url = base_url
        self.cache_file = cache_file
        self.logger = logger
        self.access_token = ""
        self.token_expires_at = datetime.now()
        Path(cache_file).parent.mkdir(parents=True, exist_ok=True)

    def get_valid_token(self) -> str:
        """유효한 토큰을 반환합니다. 없거나 만료되었으면 새로 발급합니다."""
        if self._is_valid():
            return self.access_token
        if self._load_from_cache():
            if self._is_valid():
                return self.access_token
        self._issue_new_token()
        return self.access_token

    def _is_valid(self) -> bool:
        """현재 토큰이 유효한지 확인 (2시간 여유)"""
        return self.access_token and datetime.now() < self.token_expires_at - timedelta(hours=2)

    def _load_from_cache(self) -> bool:
        """캐시 파일에서 토큰 로드"""
        if not os.path.exists(self.cache_file):
            return False
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            if cached.get('app_key') != self.app_key:
                return False
            self.access_token = cached.get('access_token', '')
            self.token_expires_at = datetime.fromisoformat(cached.get('expires_at', ''))

            if self._is_valid():
                remaining = self.token_expires_at - datetime.now()
                hours, remainder = divmod(remaining.total_seconds(), 3600)
                minutes, _ = divmod(remainder, 60)
                self.logger.info(f"✅ 캐시 토큰 로드 (유효시간: {int(hours)}h {int(minutes)}m)")
                return True
            return False
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(f"⚠️ 캐시 로드 실패: {e}")
            return False

    def _issue_new_token(self):
        """새로운 토큰 발급"""
        endpoint = '/oauth2/token'
        url = self.base_url + endpoint
        headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'api-id': 'au10001'
        }
        data = {
            'grant_type': 'client_credentials',
            'appkey': self.app_key,
            'secretkey': self.secret_key
        }
        try:
            self.logger.info("🔑 새 토큰 발급 요청...")
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            
            if 'token' not in result or 'expires_dt' not in result:
                 raise KiwoomAPIError(f"토큰 발급 응답 오류: {result.get('msg1', 'Unknown error')}", result.get('return_code'))

            self.access_token = result['token']
            self.token_expires_at = datetime.strptime(result['expires_dt'], '%Y%m%d%H%M%S')
            self._save_to_cache()
            self.logger.info(f"✅ 토큰 발급 성공 (만료일: {self.token_expires_at.strftime('%Y-%m-%d %H:%M:%S')})")

        except requests.exceptions.RequestException as e:
            self.logger.critical(f"❌ 토큰 발급 실패: {e}")
            raise

    def _save_to_cache(self):
        """토큰을 캐시에 저장"""
        cache_data = {
            'access_token': self.access_token,
            'expires_at': self.token_expires_at.isoformat(),
            'app_key': self.app_key,
            'issued_at': datetime.now().isoformat()
        }
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"💾 토큰 캐시 저장: {self.cache_file}")
        except IOError as e:
            self.logger.warning(f"⚠️ 캐시 저장 실패: {e}")

    def revoke(self) -> bool:
        """토큰 폐기"""
        if not self.access_token:
            self.logger.warning("폐기할 접근 토큰이 없습니다.")
            return False
        endpoint = '/oauth2/revoke'
        url = self.base_url + endpoint
        headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'api-id': 'au10002'
        }
        data = {
            "appkey": self.app_key,
            "secretkey": self.secret_key,
            "token": self.access_token
        }
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            self.access_token = ""
            self.token_expires_at = datetime.now()
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            self.logger.info("✅ 토큰 폐기 성공")
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ 토큰 폐기 실패: {e}")
            return False

class RateLimiter:
    """API 호출 제한을 관리하는 클래스"""
    def __init__(self, calls_per_second: float):
        self.interval = 1.0 / calls_per_second
        self.last_call = 0.0

    def wait(self):
        """필요한 만큼 대기"""
        elapsed = time.time() - self.last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_call = time.time()

class KiwoomREST:
    """
    키움증권 REST API를 위한 안정적이고 확장 가능한 파이썬 래퍼 클래스.
    - .env 설정, 자동 토큰 관리, API 호출 제한 준수, 자동 재시도, 고급 로깅 기능을 포함합니다.
    """
    REAL_BASE_URL = 'https://api.kiwoom.com'
    MOCK_BASE_URL = 'https://mockapi.kiwoom.com'
    REAL_RATE_LIMIT = 5
    MOCK_RATE_LIMIT = 1

    def __init__(self, mock: bool = True, log_level: int = 3,
                 retry_count: int = 3, retry_delay: float = 2.0,
                 token_cache_dir: str = './.token_cache'):
        self.mock = mock
        self.log_level = log_level
        self.retry_count = retry_count
        self.retry_delay = retry_delay

        self.logger = self._setup_logger()
        
        load_dotenv()
        self.app_key, self.secret_key, self.regi_date = self._load_credentials()

        self.mode_name = '모의투자' if mock else '실전투자'
        self.base_url = self.MOCK_BASE_URL if mock else self.REAL_BASE_URL
        rate_limit = self.MOCK_RATE_LIMIT if mock else self.REAL_RATE_LIMIT
        
        cache_file = f"{token_cache_dir}/kiwoom_token_{'mock' if mock else 'real'}.json"
        self.token_manager = TokenManager(
            self.app_key, self.secret_key, self.base_url, cache_file, self.logger
        )

        self.rate_limiter = RateLimiter(rate_limit)
        
        self.token_manager.get_valid_token()
        self.logger.info(f"✅ [{self.mode_name}] 초기화 완료 (Rate: {rate_limit}/s)")

    def _setup_logger(self):
        logger = logging.getLogger("KiwoomREST")
        logger.setLevel(logging.INFO)
        if logger.hasHandlers(): return logger
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        return logger

    def _load_credentials(self) -> Tuple[str, str, str]:
        prefix = 'MOCK_' if self.mock else ''
        app_key = os.getenv(f'{prefix}KIWOOM_APP_KEY')
        secret_key = os.getenv(f'{prefix}KIWOOM_APP_SECRET')
        regi_date = os.getenv(f'{prefix}REGI_DATE')
        if not all([app_key, secret_key, regi_date]):
            raise ValueError(f"'{self.mode_name}' 모드 환경변수 미설정. .env 파일을 확인하세요.")
        return app_key, secret_key, regi_date

    def _format_response_log(self, response: requests.Response) -> Optional[str]:
        if self.log_level == 0: return None
        headers = response.headers
        log_parts = [f"Status={response.status_code}"]
        if self.log_level >= 1:
            log_parts.append(f"cont-yn={headers.get('cont-yn')}, next-key={headers.get('next-key')}")
        if self.log_level >= 2:
            try: log_parts.append(f"keys={list(response.json().keys())}")
            except json.JSONDecodeError: pass
        if self.log_level >= 3:
            text = response.text
            body_str = f"body={text[:100]}...{text[-100:]}" if len(text) > 200 else f"body={text}"
            log_parts.append(body_str)
        if self.log_level >= 4:
             log_parts.append(f"body={response.text}")
        return ", ".join(log_parts)

    def _retry_with_new_token(self, url: str, headers: Dict, data: Optional[Dict],
                              auth_retry_count: int, max_retries: int,
                              error_context: str) -> Tuple[requests.Response, bool]:
        """
        [Helper] 토큰을 갱신하고 재요청을 수행하는 공통 메소드

        :param url: 요청 URL
        :param headers: 요청 헤더 (갱신됨)
        :param data: 요청 Body
        :param auth_retry_count: 현재 재시도 횟수
        :param max_retries: 최대 재시도 횟수
        :param error_context: 에러 컨텍스트 (로깅용)
        :return: (응답 객체, 성공 여부)
        :raises TokenAuthError: 재시도 한도 초과 시
        """
        self.logger.warning(
            f"⚠️ {error_context}. "
            f"토큰 강제 갱신 및 재시도 ({auth_retry_count + 1}/{max_retries})..."
        )

        try:
            # 1. 기존 토큰 폐기
            self.token_manager.revoke()

            # 2. 신규 토큰 강제 발급
            new_token = self.token_manager.get_valid_token()

            # 3. 헤더 갱신 (in-place 수정)
            headers['authorization'] = f'Bearer {new_token}'

            self.logger.info(
                f"✅ 토큰 갱신 성공. 재시도 진행 ({auth_retry_count + 1}/{max_retries})..."
            )

            # 4. 재시도 간 대기 (API 부하 방지)
            time.sleep(1.0)

            # 5. Rate Limiter 대기 후 재요청
            self.rate_limiter.wait()

            # 6. 재요청 (네트워크 에러 처리 포함)
            try:
                retry_response = requests.post(url, headers=headers, json=data)
                retry_response.raise_for_status()

                # 재요청 성공
                self.logger.info("✅ 토큰 갱신 후 재시도 성공!")
                return retry_response, True

            except requests.exceptions.RequestException as retry_error:
                # 재요청 중 네트워크 에러 발생
                self.logger.error(
                    f"❌ 토큰 갱신 후 재요청 중 네트워크 에러: {retry_error}"
                )

                # 최대 재시도 횟수 초과 시 치명적 에러
                if auth_retry_count + 1 >= max_retries:
                    raise TokenAuthError(
                        f"토큰 갱신 후 재요청 실패 ({max_retries}회 재시도): {retry_error}",
                        original_error=retry_error
                    )

                # 아직 재시도 가능하면 실패 반환
                return None, False

        except TokenAuthError:
            raise  # 즉시 전파

        except Exception as token_error:
            # 토큰 갱신 자체 실패
            self.logger.critical(f"❌ 토큰 갱신 실패: {token_error}")
            raise TokenAuthError(
                f"토큰 갱신 중 오류 발생: {token_error}",
                original_error=token_error
            )

    def _request(self, api_id: str, endpoint: str, data: Optional[Dict] = None,
                 extra_headers: Optional[Dict] = None) -> requests.Response:
        """
        [개선] 토큰 강제 갱신 및 재시도 로직 추가

        인증 에러 발생 시 토큰을 강제 갱신하고 2회 재시도.
        재시도 실패 시 TokenAuthError 발생 (치명적 에러, 작업 중단 필요).
        """
        # Kiwoom API 인증 에러 코드 (실제 확인된 값)
        AUTH_ERROR_CODES = [
            '8001', '8002', '8003', '8005', '8006', '8009', '8010',
            '8011', '8012', '8015', '8016', '8020', '8030', '8031',
            '8040', '8050', '8103'
        ]

        # 초기 헤더 구성
        headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'api-id': api_id,
            'authorization': f'Bearer {self.token_manager.get_valid_token()}'
        }
        if extra_headers:
            headers.update(extra_headers)

        url = self.base_url + endpoint
        auth_retry_count = 0  # 토큰 갱신 재시도 카운터
        MAX_AUTH_RETRIES = 2  # 토큰 갱신 후 최대 재시도 횟수

        for attempt in range(self.retry_count):
            try:
                self.rate_limiter.wait()
                response = requests.post(url, headers=headers, json=data)

                # 로그
                log_msg = self._format_response_log(response)
                if log_msg:
                    self.logger.debug(f"API: {api_id}, {log_msg}")

                # HTTP 상태 코드 체크 (401/403 포함)
                response.raise_for_status()

                # Kiwoom API 응답 검증
                result = response.json()
                return_code = result.get('return_code')

                if return_code != 0:
                    # ========== [핵심 변경] 인증 에러 감지 및 토큰 갱신 시도 ==========
                    msg = result.get('msg1') or result.get('return_msg', 'Unknown error')
                    self.logger.error(f"API Error Response Body: {response.text}")

                    # 인증 관련 에러 코드 확인
                    return_code_str = str(return_code).strip()
                    is_auth_error = (
                        return_code_str in AUTH_ERROR_CODES or
                        any(keyword in msg.lower() for keyword in ['인증', '토큰', 'token', 'auth', '권한'])
                    )

                    if is_auth_error and auth_retry_count < MAX_AUTH_RETRIES:
                        # [리팩토링] Helper 메소드 호출
                        error_context = f"Kiwoom API 인증 에러 감지 (return_code={return_code})"

                        try:
                            retry_response, success = self._retry_with_new_token(
                                url, headers, data,
                                auth_retry_count, MAX_AUTH_RETRIES,
                                error_context
                            )

                            if success:
                                # 재시도 성공
                                retry_result = retry_response.json()
                                if retry_result.get('return_code') == 0:
                                    return retry_response
                                else:
                                    # 재시도도 인증 에러 → 다음 재시도 또는 에러
                                    retry_msg = retry_result.get('msg1') or 'Unknown error'
                                    self.logger.warning(
                                        f"⚠️ 토큰 갱신 후 재시도 실패: {retry_msg} "
                                        f"(return_code={retry_result.get('return_code')})"
                                    )

                                    auth_retry_count += 1

                                    # 최대 재시도 횟수 초과 시 치명적 에러
                                    if auth_retry_count >= MAX_AUTH_RETRIES:
                                        self.logger.critical(
                                            f"❌ 토큰 갱신 후 {MAX_AUTH_RETRIES}회 재시도 모두 실패. "
                                            f"인증 복구 불가."
                                        )
                                        raise TokenAuthError(
                                            f"Kiwoom API 인증 복구 실패 ({MAX_AUTH_RETRIES}회 재시도): {retry_msg}",
                                            original_error=KiwoomAPIError(msg, error_code=return_code)
                                        )
                                    # 아직 재시도 가능하면 계속
                                    continue
                            else:
                                # 재시도 실패 (네트워크 에러) → 다음 재시도
                                auth_retry_count += 1
                                continue

                        except TokenAuthError:
                            raise  # 즉시 전파

                    # 인증 에러가 아니거나 재시도 한도 초과 → 일반 에러 발생
                    raise KiwoomAPIError(
                        f"{msg} (return_code={return_code})",
                        error_code=return_code
                    )

                # 정상 응답
                return response

            except TokenAuthError:
                # 치명적 에러는 즉시 전파 (재시도 불가)
                raise

            except requests.exceptions.HTTPError as e:
                # 401/403 등 HTTP 인증 에러 처리
                if e.response.status_code in [401, 403] and auth_retry_count < MAX_AUTH_RETRIES:
                    error_context = f"HTTP 인증 에러 감지 ({e.response.status_code})"
                    try:
                        retry_response, success = self._retry_with_new_token(
                            url, headers, data,
                            auth_retry_count, MAX_AUTH_RETRIES,
                            error_context
                        )

                        if success:
                            # 재요청 성공 시 return_code 검증
                            try:
                                retry_body = retry_response.json()
                                retry_return_code = retry_body.get("ret_code", "")

                                if retry_return_code == "0":
                                    self.logger.info("✅ HTTP 인증 에러 복구 성공!")
                                    return retry_response
                                else:
                                    # 재요청은 성공했지만 return_code != 0
                                    retry_is_auth_error = retry_return_code in AUTH_ERROR_CODES
                                    if retry_is_auth_error:
                                        if auth_retry_count + 1 >= MAX_AUTH_RETRIES:
                                            raise TokenAuthError(
                                                f"HTTP 인증 복구 후에도 인증 에러 지속 (return_code={retry_return_code}, {MAX_AUTH_RETRIES}회 재시도)",
                                                original_error=e
                                            )
                                        auth_retry_count += 1
                                        continue
                                    else:
                                        # 일반 API 에러
                                        retry_msg = retry_body.get("ret_msg", "Unknown error")
                                        raise KiwoomAPIError(
                                            f"[{api_id}] API 에러 (return_code={retry_return_code}): {retry_msg}",
                                            error_code=retry_return_code
                                        )
                            except (ValueError, KeyError) as json_error:
                                self.logger.error(f"재요청 응답 파싱 실패: {json_error}")
                                auth_retry_count += 1
                                continue
                        else:
                            # 재요청 네트워크 에러 발생 (이미 로깅됨)
                            auth_retry_count += 1
                            continue

                    except TokenAuthError:
                        # 치명적 에러는 즉시 전파
                        raise
                else:
                    # 일반 HTTP 에러는 재시도
                    self.logger.warning(f"HTTP 에러: {e} (시도 {attempt + 1}/{self.retry_count})")

            except requests.exceptions.RequestException as e:
                # 네트워크 에러는 재시도
                self.logger.warning(f"네트워크 에러: {e} (시도 {attempt + 1}/{self.retry_count})")

            except KiwoomAPIError:
                # 일반 API 에러는 즉시 전파
                raise

            # 재시도 대기
            if attempt < self.retry_count - 1:
                time.sleep(self.retry_delay)

        # 모든 재시도 실패
        raise requests.exceptions.RequestException(f"API 요청 최종 실패: {api_id}")

    # --- 1. 유틸리티 메소드 ---
    def check_key_expiration(self):
        """API 키의 유효기간을 확인하고 남은 기간을 출력합니다."""
        try:
            start_date = datetime.strptime(self.regi_date, '%Y%m%d')
            duration = 365 if not self.mock else 90
            expiration_date = start_date + timedelta(days=duration)
            remaining_days = (expiration_date - datetime.now()).days
            
            print("-" * 45)
            print(f"🔑 [{self.mode_name} 계정] API Key 유효기간 정보")
            print(f"  - 키 발급일: {start_date.strftime('%Y-%m-%d')}")
            print(f"  - 만료 예정일: {expiration_date.strftime('%Y-%m-%d')}")
            if remaining_days > 0:
                print(f"  - 남은 유효 기간: {remaining_days}일")
            else:
                print("  - 상태: 만료되었습니다. 키를 갱신해주세요.")
            print("-" * 45)
        except (ValueError, TypeError):
            self.logger.error("API 키 만료일 계산 불가. .env 파일의 REGI_DATE 형식(YYYYMMDD) 확인 필요.")

    def get_api_guide(self):
        """현재 래퍼에서 사용 가능한 모든 API 메소드의 목록과 설명을 출력합니다."""
        print("\n" + "=" * 60, "\n📜 [KiwoomREST] 사용 가능한 메소드 가이드", "\n" + "=" * 60)
        for name in dir(self):
            if callable(getattr(self, name)) and not name.startswith('_'):
                doc = getattr(self, name).__doc__
                if doc: print(f" - {name}(): {doc.strip().splitlines()[0]}")
        print("=" * 60 + "\n")

    # --- 2. 인증 관련 API ---
    def get_access_token(self) -> str:
        """(au10001) API 요청에 필요한 신규 접근 토큰(Access Token)을 발급받습니다."""
        return self.token_manager.get_valid_token()

    def revoke_access_token(self) -> bool:
        """(au10002) 사용이 완료된 접근 토큰을 폐기하여 무효화합니다."""
        return self.token_manager.revoke()

    # --- 3. 시세/차트 조회 API ---
    def _fetch_paginated_data(self, api_id, endpoint, data, list_key, date_key=None,
                              start_datetime_str=None, end_datetime_str=None, max_requests=10):
        all_results = []
        next_key = ''
        for i in range(max_requests or 9999):
            headers = {'cont-yn': 'Y' if next_key else 'N', 'next-key': next_key}
            try:
                res = self._request(api_id, endpoint, data=data, extra_headers=headers)
                res_data = res.json()
                results_list = res_data.get(list_key, [])
                if results_list:
                    all_results.extend(results_list)
                    if date_key and start_datetime_str and results_list[-1].get(date_key, '') < start_datetime_str:
                        self.logger.debug(f"조회 데이터가 시작일({start_datetime_str[:8]})에 도달하여 중단합니다.")
                        break
                cont_yn = res.headers.get('cont-yn', 'N')
                next_key = res.headers.get('next-key', '')
                if cont_yn == 'Y' and next_key:
                    self.logger.debug(f"  -> 연속 조회 중... (요청 {i + 1}회, 현재 {len(all_results)}개 수집)")
                else:
                    break
            except (requests.exceptions.RequestException, KiwoomAPIError) as e:
                self.logger.error(f"연속 데이터 조회 중 에러 발생: {e}")
                raise
        if date_key and start_datetime_str:
            end_str = end_datetime_str or datetime.now().strftime('%Y%m%d%H%M%S')
            return [item for item in all_results if start_datetime_str <= item.get(date_key, '') <= end_str]
        return all_results

    def get_daily_chart(self, stock_code: str, start_date: str, end_date: Optional[str] = None,
                        adjusted_price: str = '1', max_requests: int = 10):
        """(ka10081) 특정 기간 동안의 일봉 데이터를 조회합니다."""
        api_id, endpoint = 'ka10081', '/api/dostk/chart'
        base_date = end_date or datetime.now().strftime('%Y%m%d')
        data = {'stk_cd': stock_code, 'base_dt': base_date, 'upd_stkpc_tp': adjusted_price}
        return self._fetch_paginated_data(
            api_id, endpoint, data, 'stk_dt_pole_chart_qry',
            date_key='dt', start_datetime_str=start_date, end_datetime_str=end_date,
            max_requests=max_requests
        )

    def get_minute_chart(self, stock_code: str, start_date: str, end_date: Optional[str] = None,
                         tic_scope: str = '1', adjusted_price: str = '1', max_requests: int = 30):
        """(ka10080) 특정 기간 동안의 분봉 데이터를 조회합니다."""
        api_id, endpoint = 'ka10080', '/api/dostk/chart'
        data = {'stk_cd': stock_code, 'tic_scope': tic_scope, 'upd_stkpc_tp': adjusted_price}
        start_dt = start_date + "000000"
        end_dt = (end_date or datetime.now().strftime('%Y%m%d')) + "235959"
        return self._fetch_paginated_data(
            api_id, endpoint, data, 'stk_min_pole_chart_qry',
            date_key='cntr_tm', start_datetime_str=start_dt, end_datetime_str=end_dt,
            max_requests=max_requests
        )

    def get_industry_daily_chart(self, industry_code: str, start_date: str, end_date: Optional[str] = None,
                                 max_requests: int = 10):
        """(ka20006) 특정 기간 동안의 업종별 일봉 데이터를 조회합니다."""
        api_id, endpoint = 'ka20006', '/api/dostk/chart'
        base_date = end_date or datetime.now().strftime('%Y%m%d')
        data = {'inds_cd': industry_code, 'base_dt': base_date}
        return self._fetch_paginated_data(
            api_id, endpoint, data, 'inds_dt_pole_qry',
            date_key='dt', start_datetime_str=start_date, end_datetime_str=end_date,
            max_requests=max_requests
        )

    def get_stock_info(self, market_type: str = '0') -> List[Dict]:
        """(ka10099) 시장(코스피:0, 코스닥:10)에 상장된 모든 종목의 기본 정보를 조회합니다."""
        api_id, endpoint = 'ka10099', '/api/dostk/stkinfo'
        data = {'mrkt_tp': market_type}
        return self._fetch_paginated_data(api_id, endpoint, data, 'list', max_requests=None)
        
    def get_industry_codes(self, market_type: str = '0') -> List[Dict]:
        """(ka10101) 시장별 업종 코드 목록을 조회합니다."""
        api_id, endpoint = 'ka10101', '/api/dostk/stkinfo'
        data = {'mrkt_tp': market_type}
        return self._fetch_paginated_data(api_id, endpoint, data, 'list', max_requests=None)

# ==================== 사용 예시 ====================
if __name__ == "__main__":
    try:
        # .env 파일 예시
        # MOCK_KIWOOM_APP_KEY="your_mock_app_key"
        # MOCK_KIWOOM_APP_SECRET="your_mock_secret_key"
        # MOCK_REGI_DATE="20251023"
        
        kw = KiwoomREST(mock=True, log_level=3)
        kw.check_key_expiration()
        
        # 코스피(0) 종목 정보 조회
        kospi_stocks = kw.get_stock_info(market_type='0')
        print(f"✅ 코스피 상장 종목 {len(kospi_stocks)}개 조회 완료")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")