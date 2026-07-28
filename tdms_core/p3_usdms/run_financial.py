import argparse
import asyncio
import logging
import json
from datetime import datetime
from p3_usdms.tasks.us_financial_routine import UsFinancialRoutine

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s"
)

async def main():
    parser = argparse.ArgumentParser(description="USDMS Financial Routine CLI Trigger")
    parser.add_argument("--date", type=str, default=None, help="Target collection date (YYYY-MM-DD). Default is today.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of tickers to collect for testing.")
    parser.add_argument("--force-all", action="store_true", help="Force collection and calculation of all active tickers instead of parsing the daily index.")
    args = parser.parse_args()

    target_dt = None
    if args.date:
        try:
            target_dt = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("Error: Date format must be YYYY-MM-DD")
            return

    print("Initializing Financial Routine...")
    routine = UsFinancialRoutine()
    
    print(f"Starting Financial Routine run (Target Date: {target_dt or 'default=Today'}, Limit: {args.limit or 'No Limit'}, force_all={args.force_all})...")
    report = await routine.run(test_limit=args.limit, target_date=target_dt, force_all=args.force_all)
    
    print("\n================ FINANCIAL ROUTINE REPORT ================")
    print(json.dumps(report, indent=4, ensure_ascii=False))
    print("==========================================================")

if __name__ == "__main__":
    asyncio.run(main())
