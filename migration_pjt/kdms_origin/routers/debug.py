#
# routers/debug.py
#
"""
API 진단 도구 라우터 (Advanced API Inspector)
- collectors의 메소드를 동적으로 실행하여 결과/에러를 검증
- 외부 API 응답 포맷 변경 감지
"""

import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException

from models.debug_models import (
    MethodInfo,
    MethodExecuteRequest,
    MethodExecuteResponse,
    ExecutionMetadata,
    ErrorDetail
)
from collectors.kiwoom_rest import KiwoomREST, KiwoomAPIError
from collectors.kis_rest import KisREST, KisAPIError
from collectors.utils import DATA_MAPPER

router = APIRouter()
logger = logging.getLogger(__name__)

# --- 핵심 메소드 메타데이터 정의 ---
# 실제 tasks/에서 사용하는 주요 메소드만 선별하여 등록
METHOD_METADATA: Dict[str, Dict[str, Any]] = {
    "kiwoom": {
        "get_stock_info": {
            "params": ["market_type"],
            "defaults": {
                "market_type": "0"  # 코스피
            },
            "description": "시장(코스피:0, 코스닥:10)에 상장된 모든 종목의 기본 정보를 조회 (ka10099)",
            "data_mapper_key": "stock_info"
        },
        "get_daily_chart": {
            "params": ["stock_code", "start_date", "end_date", "adjusted_price", "max_requests"],
            "defaults": {
                "stock_code": "005930",  # 삼성전자
                "start_date": (datetime.now() - timedelta(days=30)).strftime('%Y%m%d'),  # 최근 1개월
                "end_date": datetime.now().strftime('%Y%m%d'),
                "adjusted_price": "0",  # 수정주가 미적용
                "max_requests": 10
            },
            "description": "특정 기간 동안의 일봉 데이터를 조회 (ka10081)",
            "data_mapper_key": "daily_ohlcv"
        },
        "get_minute_chart": {
            "params": ["stock_code", "start_date", "end_date", "tic_scope", "adjusted_price", "max_requests"],
            "defaults": {
                "stock_code": "005930",  # 삼성전자
                "start_date": (datetime.now() - timedelta(days=2)).strftime('%Y%m%d'),  # 최근 2일
                "end_date": datetime.now().strftime('%Y%m%d'),
                "tic_scope": "1",  # 1분봉
                "adjusted_price": "0",  # 수정주가 미적용
                "max_requests": 30
            },
            "description": "특정 기간 동안의 분봉 데이터를 조회 (ka10080)",
            "data_mapper_key": "minute_ohlcv"
        }
    },
    "kis": {
        "check_holiday": {
            "params": ["bass_dt"],
            "defaults": {
                "bass_dt": datetime.now().strftime('%Y%m%d')
            },
            "description": "휴장일 조회 (CTCA0903R, 실전 전용)",
            "data_mapper_key": None  # 별도 매퍼 없음
        },
        "fetch_daily_price": {
            "params": ["stock_code", "start_date", "end_date", "adj_price", "period_code"],
            "defaults": {
                "stock_code": "005930",  # 삼성전자
                "start_date": (datetime.now() - timedelta(days=30)).strftime('%Y%m%d'),  # 최근 1개월
                "end_date": datetime.now().strftime('%Y%m%d'),
                "adj_price": "0",  # 수정주가 미적용
                "period_code": "D"  # 일봉
            },
            "description": "일봉/주봉/월봉/년봉 조회 (FHKST03010100)",
            "data_mapper_key": None
        },
        "fetch_balance_sheet": {
            "params": ["stock_code", "div_cls_code"],
            "defaults": {
                "stock_code": "005930",  # 삼성전자
                "div_cls_code": "1"  # 분기 (1: 분기, 0: 연간)
            },
            "description": "대차대조표 조회 (FHKST66430100, 실전 전용)",
            "data_mapper_key": "balance_sheet"
        },
        "fetch_financial_ratio": {
            "params": ["stock_code", "div_cls_code"],
            "defaults": {
                "stock_code": "005930",  # 삼성전자
                "div_cls_code": "1"  # 분기 (1: 분기, 0: 연간)
            },
            "description": "재무비율 조회 (FHKST66430300, 실전 전용)",
            "data_mapper_key": "financial_ratio"
        }
    }
}


@router.get("/methods", summary="[Debug] 테스트 가능한 메소드 목록 조회")
async def get_available_methods() -> Dict[str, List[MethodInfo]]:
    """
    KIS/Kiwoom API의 테스트 가능한 메소드 목록과 파라미터 정보를 반환합니다.
    """
    result = {
        "kis": [],
        "kiwoom": []
    }

    for target in ["kis", "kiwoom"]:
        for method_name, method_info in METHOD_METADATA[target].items():
            result[target].append(
                MethodInfo(
                    name=method_name,
                    params=method_info["params"],
                    defaults=method_info["defaults"],
                    description=method_info["description"]
                )
            )

    return result


@router.post("/execute", summary="[Debug] 메소드 실행 및 응답 구조 검증")
async def execute_method(request: MethodExecuteRequest) -> MethodExecuteResponse:
    """
    선택한 메소드를 실행하고 결과를 반환합니다.
    응답 구조가 DATA_MAPPER의 기대값과 일치하는지 자동으로 검증합니다.

    - KeyError 등 응답 구조 변경 감지
    - API 에러 코드 추적
    - 실행 시간 측정
    - DATA_MAPPER 키값 검증 (해당하는 경우)
    """
    target = request.target.lower()
    method_name = request.method_name

    # 1. 메소드 존재 확인
    if target not in METHOD_METADATA:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 target: {target}")

    if method_name not in METHOD_METADATA[target]:
        raise HTTPException(
            status_code=400,
            detail=f"'{target}'에서 '{method_name}' 메소드를 찾을 수 없습니다."
        )

    method_meta = METHOD_METADATA[target][method_name]

    # 2. 파라미터 병합 (기본값 + 사용자 입력)
    merged_params = {**method_meta["defaults"], **request.params}

    logger.info(f"[Debug] 메소드 실행: {target}.{method_name}({merged_params})")

    try:
        # 3. API 클라이언트 초기화
        if target == "kis":
            client = KisREST(mock=request.mock_mode)
        elif target == "kiwoom":
            client = KiwoomREST(mock=request.mock_mode)
        else:
            raise ValueError(f"Unknown target: {target}")

        # 4. 메소드 동적 실행
        method = getattr(client, method_name, None)
        if not method:
            raise AttributeError(f"'{target}' 클라이언트에 '{method_name}' 메소드가 없습니다.")

        start_time = time.time()
        result = method(**merged_params)
        execution_time = time.time() - start_time

        # 5. 결과 메타데이터 생성
        metadata = ExecutionMetadata(
            execution_time=round(execution_time, 3),
            result_type=type(result).__name__,
            result_length=len(result) if isinstance(result, (list, dict)) else None
        )

        # 6. 응답 구조 검증 (DATA_MAPPER 키값 확인)
        validation_result = None
        data_mapper_key = method_meta.get("data_mapper_key")

        if data_mapper_key and data_mapper_key in DATA_MAPPER.get(target, {}):
            validation_result = _validate_response_structure(
                result, target, data_mapper_key
            )

        logger.info(
            f"[Debug] 실행 성공: {target}.{method_name} "
            f"({execution_time:.2f}s, {metadata.result_length} items)"
        )

        return MethodExecuteResponse(
            success=True,
            result=result,
            metadata=metadata,
            validation_result=validation_result
        )

    except KeyError as e:
        # 응답 구조 변경 감지 (최우선!)
        logger.error(f"[Debug] KeyError 발생: {e}", exc_info=True)
        return MethodExecuteResponse(
            success=False,
            error=ErrorDetail(
                type="KeyError",
                message=str(e),
                traceback=traceback.format_exc(),
                hint="⚠️ API 응답 구조가 변경되었을 수 있습니다. 응답 필드명을 확인하세요."
            )
        )

    except (KisAPIError, KiwoomAPIError) as e:
        # API 에러
        logger.error(f"[Debug] API Error: {e}", exc_info=True)
        return MethodExecuteResponse(
            success=False,
            error=ErrorDetail(
                type=type(e).__name__,
                message=str(e),
                traceback=traceback.format_exc(),
                error_code=getattr(e, 'error_code', None)
            )
        )

    except AttributeError as e:
        # 메소드 없음
        logger.error(f"[Debug] AttributeError: {e}", exc_info=True)
        return MethodExecuteResponse(
            success=False,
            error=ErrorDetail(
                type="AttributeError",
                message=str(e),
                traceback=traceback.format_exc(),
                hint="메소드명을 확인하세요."
            )
        )

    except TypeError as e:
        # 파라미터 오류
        logger.error(f"[Debug] TypeError: {e}", exc_info=True)
        return MethodExecuteResponse(
            success=False,
            error=ErrorDetail(
                type="TypeError",
                message=str(e),
                traceback=traceback.format_exc(),
                hint="필수 파라미터가 누락되었거나 타입이 맞지 않습니다."
            )
        )

    except Exception as e:
        # 기타 예외
        logger.error(f"[Debug] Unexpected error: {e}", exc_info=True)
        return MethodExecuteResponse(
            success=False,
            error=ErrorDetail(
                type=type(e).__name__,
                message=str(e),
                traceback=traceback.format_exc()
            )
        )


def _validate_response_structure(
    result: Any, target: str, data_mapper_key: str
) -> Dict[str, Any]:
    """
    응답 데이터가 DATA_MAPPER에 정의된 키값을 모두 포함하는지 검증

    [개선] 리스트의 여러 항목을 샘플링하여 검증 (첫 번째, 중간, 마지막)

    :param result: API 응답 결과
    :param target: "kis" or "kiwoom"
    :param data_mapper_key: DATA_MAPPER의 키 (예: "balance_sheet")
    :return: 검증 결과 딕셔너리
    """
    try:
        mapper = DATA_MAPPER[target][data_mapper_key]
        required_keys = set(mapper.keys())

        # 리스트 형태의 응답인 경우 다중 샘플링 검증
        if isinstance(result, list):
            if not result:
                return {
                    "status": "error",
                    "message": "❌ 응답 데이터가 비어있습니다. API가 데이터를 반환하지 않았거나 조회 조건을 확인하세요.",
                    "required_keys": list(required_keys),
                    "missing_keys": [],
                    "present_keys": []
                }

            # 다중 샘플링: 첫 번째, 중간, 마지막 항목 검증
            sample_indices = []
            if len(result) >= 1:
                sample_indices.append(0)  # 첫 번째
            if len(result) >= 3:
                sample_indices.append(len(result) // 2)  # 중간
            if len(result) >= 2:
                sample_indices.append(len(result) - 1)  # 마지막

            all_missing_keys = []
            all_extra_keys = []
            validation_details = []

            for idx in sample_indices:
                sample = result[idx]
                actual_keys = set(sample.keys())
                missing_keys = required_keys - actual_keys
                extra_keys = actual_keys - required_keys

                validation_details.append({
                    "index": idx,
                    "missing_keys": list(missing_keys),
                    "extra_keys": list(extra_keys)
                })

                if missing_keys:
                    all_missing_keys.extend(missing_keys)
                if extra_keys:
                    all_extra_keys.extend(extra_keys)

            # 중복 제거
            unique_missing = list(set(all_missing_keys))
            unique_extra = list(set(all_extra_keys))

            if unique_missing:
                return {
                    "status": "error",
                    "message": f"⚠️ 응답에 필수 키가 누락되었습니다: {unique_missing}",
                    "required_keys": list(required_keys),
                    "missing_keys": unique_missing,
                    "present_keys": list(set(result[0].keys())),
                    "extra_keys": unique_extra,
                    "sample_count": len(sample_indices),
                    "total_items": len(result),
                    "validation_details": validation_details
                }
            else:
                return {
                    "status": "success",
                    "message": f"✅ 모든 필수 키가 응답에 포함되어 있습니다. (검증: {len(sample_indices)}개 항목 / 전체: {len(result)}개)",
                    "required_keys": list(required_keys),
                    "missing_keys": [],
                    "present_keys": list(set(result[0].keys())),
                    "extra_keys": unique_extra,
                    "sample_count": len(sample_indices),
                    "total_items": len(result),
                    "validation_details": validation_details
                }

        elif isinstance(result, dict):
            # dict 응답의 경우 직접 검증
            actual_keys = set(result.keys())
            missing_keys = required_keys - actual_keys
            extra_keys = actual_keys - required_keys

            if missing_keys:
                return {
                    "status": "error",
                    "message": f"⚠️ 응답에 필수 키가 누락되었습니다: {missing_keys}",
                    "required_keys": list(required_keys),
                    "missing_keys": list(missing_keys),
                    "present_keys": list(actual_keys),
                    "extra_keys": list(extra_keys)
                }
            else:
                return {
                    "status": "success",
                    "message": "✅ 모든 필수 키가 응답에 포함되어 있습니다.",
                    "required_keys": list(required_keys),
                    "missing_keys": [],
                    "present_keys": list(actual_keys),
                    "extra_keys": list(extra_keys)
                }
        else:
            return {
                "status": "skip",
                "message": f"검증 불가능한 응답 타입: {type(result).__name__}"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"검증 중 오류 발생: {str(e)}"
        }
