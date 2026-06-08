import argparse
import asyncio
import logging
import json
from datetime import datetime
from p3_usdms.tasks.daily_routine import DailyRoutine

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s"
)

async def main():
    parser = argparse.ArgumentParser(description="USDMS Daily Routine CLI Trigger")
    parser.add_argument("--date", type=str, default=None, help="Target collection date (YYYY-MM-DD). Default is yesterday.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of tickers to collect for testing.")
    args = parser.parse_args()

    target_dt = None
    if args.date:
        try:
            target_dt = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print("Error: Date format must be YYYY-MM-DD")
            return

    print("Initializing Daily Routine...")
    routine = DailyRoutine()
    
    print(f"Starting Daily Routine run (Target Date: {target_dt or 'default=Yesterday'}, Limit: {args.limit or 'No Limit'})...")
    report = await routine.run(test_limit=args.limit, target_date=target_dt)
    
    print("\n================ DAILY ROUTINE REPORT ================")
    print(json.dumps(report, indent=4, ensure_ascii=False))
    print("======================================================")

if __name__ == "__main__":
    asyncio.run(main())
