#
# models/data_models.py
#
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime

class StockInfo(BaseModel):
    """
    PRD 섹션 3.2.1 응답 예시에 대응하는 종목 정보 모델
    """
    stk_cd: str
    stk_nm: str
    market_type: str
    list_dt: Optional[date] = None
    status: str

    class Config:
        from_attributes = True # (SQLAlchemy/DB 결과와 호환)

class StockListResponse(BaseModel):
    """
    GET /api/v1/data/stocks 응답 모델
    """
    total: int
    stocks: List[StockInfo]

class OhlcvData(BaseModel):
    """
    PRD 섹션 3.2.2 응답 예시의 'data' 리스트 항목
    """
    dt: Optional[date] = None           # 일봉
    dt_tm: Optional[datetime] = None    # 분봉 (향후 사용)
    open_prc: float
    high_prc: float
    low_prc: float
    cls_prc: float
    vol: float
    amt: Optional[float] = None
    turn_rt: Optional[float] = None

    class Config:
        from_attributes = True

class OhlcvPeriod(BaseModel):
    start: date
    end: date

class OhlcvResponse(BaseModel):
    """
    PRD 섹션 3.2.2 GET /ohlcv/daily/{stk_cd} 응답 모델
    """
    stk_cd: str
    stk_nm: str
    period: OhlcvPeriod
    data: List[OhlcvData]

class MinuteOhlcvResponse(BaseModel):
    """
    PRD 섹션 3.2.2 GET /ohlcv/minute/{stk_cd} 응답 모델
    (OhlcvResponse와 구조가 동일하나 명시적으로 분리)
    """
    stk_cd: str
    stk_nm: str
    period: OhlcvPeriod
    data: List[OhlcvData] # (OhlcvData 모델이 dt_tm도 포함하므로 재사용)

# --- (수정) Phase 6.3: v3 퀀트 스크리닝 (요청 Body 모델) ---

class ScreeningBaseCriteria(BaseModel):
    """ POST /financials/screening 'base_criteria' """
    market: str = Field(..., enum=["KOSPI", "KOSDAQ"])
    stac_yymm: str = Field(..., description="결산년월 (예: 202409)")
    pit_date: date = Field(..., description="조회 기준 시점 (Point-in-Time)")

class ScreeningFilter(BaseModel):
    """ 'filters' 배열 항목 (예: 'bsop_prti' > 0) """
    field: str = Field(..., description="필터링할 컬럼명 (예: bsop_prti, pbr)")
    operator: str = Field(..., enum=["gt", "gte", "lt", "lte", "eq", "neq"])
    value: float # (숫자형 필터만 지원 가정)

class RankingFactor(BaseModel):
    """ 'ranking_strategy.factors' 배열 항목 (마법공식) """
    field: str = Field(..., description="랭킹에 사용할 컬럼명 (예: pbr)")
    order: str = Field("asc", enum=["asc", "desc"])
    weight: float = Field(..., description="가중치 (예: 0.5)")

class RankingStrategy(BaseModel):
    """ 'ranking_strategy' 객체 """
    factors: List[RankingFactor]
    final_order: str = Field("asc", enum=["asc", "desc"], description="종합 점수 정렬")
    limit: int = Field(50, gt=0, le=1000)

class ScreeningRequest(BaseModel):
    """ POST /api/v1/data/financials/screening (v3) 요청 Body """
    base_criteria: ScreeningBaseCriteria
    filters: List[ScreeningFilter] = []
    ranking_strategy: RankingStrategy

# --- (수정) Phase 6.3: v3 퀀트 스크리닝 (응답 모델) ---

class FinancialScreeningData(BaseModel):
    """
    PRD 3.2.3 퀀트 스크리닝 'data' 항목 (v3)
    (init.sql의 모든 항목 + 실시간 계산 항목 + 랭킹 점수)
    """
    stk_cd: str
    stk_nm: str
    
    # [신규] 실시간 계산
    pit_cls_prc: Optional[float] = None
    pbr: Optional[float] = None
    per: Optional[float] = None
    
    # [신규] 랭킹 점수
    combined_score: Optional[float] = None
    # (개별 랭크도 필요시 추가. 예: rank_pbr: Optional[int] = None)
    
    # [신규] financial_statements
    cras: Optional[float] = None
    fxas: Optional[float] = None
    total_aset: Optional[float] = None
    flow_lblt: Optional[float] = None
    fix_lblt: Optional[float] = None
    total_lblt: Optional[float] = None
    cpfn: Optional[float] = None
    total_cptl: Optional[float] = None
    sale_account: Optional[float] = None
    sale_cost: Optional[float] = None
    sale_totl_prfi: Optional[float] = None
    bsop_prti: Optional[float] = None
    op_prfi: Optional[float] = None
    thtr_ntin: Optional[float] = None
    
    # [신규] financial_ratios
    grs: Optional[float] = None
    bsop_prfi_inrt: Optional[float] = None
    ntin_inrt: Optional[float] = None
    roe_val: Optional[float] = None
    eps: Optional[float] = None
    sps: Optional[float] = None
    bps: Optional[float] = None
    rsrv_rate: Optional[float] = None
    lblt_rate: Optional[float] = None
    cptl_ntin_rate: Optional[float] = None
    self_cptl_ntin_inrt: Optional[float] = None
    sale_ntin_rate: Optional[float] = None
    sale_totl_rate: Optional[float] = None
    eva: Optional[float] = None
    ebitda: Optional[float] = None
    ev_ebitda: Optional[float] = None
    bram_depn: Optional[float] = None
    crnt_rate: Optional[float] = None
    quck_rate: Optional[float] = None
    equt_inrt: Optional[float] = None
    totl_aset_inrt: Optional[float] = None

    class Config:
        from_attributes = True

class ScreeningMetadata(BaseModel):
    # (v3에 맞게 수정)
    base_criteria: ScreeningBaseCriteria
    filters_applied: int
    ranking_factors: int
    total_stocks: int

class FinancialScreeningResponse(BaseModel):
    """
    POST /api/v1/data/financials/screening (v3) 응답 모델
    """
    screening: ScreeningMetadata
    data: List[FinancialScreeningData]

# --- (신규) Phase 6.3: 수정계수 모델 (PRD 3.2.4) ---

class FactorEvent(BaseModel):
    """
    PRD 3.2.4 'factors' 리스트 항목
    """
    event_dt: date
    price_ratio: float
    volume_ratio: float
    price_source: str
    effective_dt: datetime
    details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class FactorResponse(BaseModel):
    """
    PRD 3.2.4 GET /factors/{stk_cd} 응답 모델
    """
    stk_cd: str
    stk_nm: str
    factors: List[FactorEvent]
# (향후 OhlcvData, FinancialResponse 등 추가 예정)