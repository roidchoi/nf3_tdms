import logging
from p3_usdms.repositories.master_repo import MasterRepo
from p3_usdms.engines.valuation_calculator import ValuationCalculator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger("ValuationRebuilder")

def main():
    master_repo = MasterRepo()
    val_calc = ValuationCalculator()
    
    targets = master_repo.get_collect_targets()
    ciks = [t['cik'] for t in targets]
    
    logger.info(f"Starting Valuation self-healing recovery for {len(ciks)} companies...")
    for idx, cik in enumerate(ciks):
        try:
            # start_date를 명시하지 않고 rebuild=False로 호출하여, 
            # 내부 자가치유(Self-healing) 논리가 자동으로 갭을 감지하여 채우도록 유도합니다.
            val_calc.calculate_and_save(cik, rebuild=False)
            if (idx + 1) % 500 == 0:
                logger.info(f"Progress: {idx + 1}/{len(ciks)} processed.")
        except Exception as e:
            logger.error(f"Failed to rebuild valuation for CIK: {cik}. Error: {e}")
    logger.info("Valuation recovery completed successfully!")

if __name__ == "__main__":
    main()
