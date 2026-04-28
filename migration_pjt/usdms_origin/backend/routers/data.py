from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging
from ..collectors.db_manager import DatabaseManager

router = APIRouter(prefix="/api/v1/us", tags=["US Data"])
logger = logging.getLogger(__name__)

# We need a DB instance. 
# In FastAPI, usually we use dependency injection.
# For simplicity, we instantiate DatabaseManager here or use a global one.
# Since DatabaseManager uses a thread-safe pool, it's fine to share.

db = DatabaseManager()

@router.get("/tickers")
def get_tickers(search: Optional[str] = None):
    """
    Get list of active tickers.
    """
    with db.get_cursor() as cur:
        if search:
            query = """
                SELECT cik, latest_ticker, latest_name, exchange, sector 
                FROM us_ticker_master 
                WHERE is_active = TRUE 
                AND (latest_ticker ILIKE %s OR latest_name ILIKE %s)
                LIMIT 100
            """
            term = f"%{search}%"
            cur.execute(query, (term, term))
        else:
            query = """
                SELECT cik, latest_ticker, latest_name, exchange, sector 
                FROM us_ticker_master 
                WHERE is_active = TRUE 
                LIMIT 100
            """
            cur.execute(query)
        
        return cur.fetchall()

@router.get("/financials/{cik}")
def get_financials(cik: str):
    """
    Get standardized financials for a CIK.
    """
    with db.get_cursor() as cur:
        query = """
            SELECT * FROM us_standard_financials 
            WHERE cik = %s 
            ORDER BY report_period DESC
        """
        cur.execute(query, (cik,))
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Financials not found")
        return rows

@router.get("/valuation/{cik}")
def get_valuation(cik: str):
    """
    Get daily valuation ratios for a CIK.
    Returns lightweight JSON (Date, PER, PBR, EV/EBITDA).
    """
    with db.get_cursor() as cur:
        # Optimized query: Select only key metrics
        query = """
            SELECT dt, pe_ratio, pb_ratio, ps_ratio, ev_ebitda, pfcf_ratio, gp_a_ratio 
            FROM us_valuation_ratios 
            WHERE cik = %s 
            ORDER BY dt DESC
        """
        cur.execute(query, (cik,))
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Valuation data not found")
        return rows
