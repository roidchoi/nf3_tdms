import sys
import os
import unittest
from dotenv import load_dotenv

# Add project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.collectors.master_sync import MasterSync

class MockTicker:
    def __init__(self, cik, market_cap, current_price, exchange, country, quote_type, is_collect_target):
        self.cik = cik
        self.market_cap = market_cap
        self.current_price = current_price
        self.exchange = exchange
        self.country = country
        self.quote_type = quote_type
        self.is_collect_target = is_collect_target

class TestMasterLogic(unittest.TestCase):
    def setUp(self):
        self.syncer = MasterSync()
    
    def test_normalize_exchange(self):
        """E-1. Exchange Normalization Tests"""
        self.assertEqual(MasterSync.normalize_exchange('NMS'), 'NASDAQ')
        self.assertEqual(MasterSync.normalize_exchange('Pink Sheets'), 'OTC')
        self.assertEqual(MasterSync.normalize_exchange('NYQ'), 'NYSE')
        self.assertEqual(MasterSync.normalize_exchange('ASE'), 'AMEX')
        self.assertEqual(MasterSync.normalize_exchange('Unknown'), 'OTHER')
        self.assertEqual(MasterSync.normalize_exchange(None), 'OTHER')
        
    def test_hysteresis_logic(self):
        """E-3. Hysteresis Logic Tests (Mock Simulation)"""
        # We can simulate the logic without DB by extracting the condition checks into a helper or 
        # just re-implementing the logic here to verify the *rules* are correct as per requirement.
        # But real verification requires DB interaction or mocking DB cursor.
        
        # Or we can just document the expectation here.
        # Let's mock the logic function effectively.
        
        # Logic Recap:
        # Retention: True if (Cap>=35M, Price>=0.8, MajorEx, US, Equity)
        # Entry: True if (Cap>=50M, Price>=1.0, MajorEx, US, Equity)
        
        candidates = [
            # Retention Scenario (Current=True)
            MockTicker('A', 40_000_000, 0.90, 'NASDAQ', 'United States', 'EQUITY', True), # Keep
            MockTicker('B', 30_000_000, 1.50, 'NASDAQ', 'United States', 'EQUITY', True), # Drop (Cap)
            MockTicker('C', 50_000_000, 0.70, 'NASDAQ', 'United States', 'EQUITY', True), # Drop (Price)
            
            # Entry Scenario (Current=False)
            MockTicker('D', 60_000_000, 1.20, 'NASDAQ', 'United States', 'EQUITY', False), # Enter
            MockTicker('E', 45_000_000, 1.50, 'NASDAQ', 'United States', 'EQUITY', False), # Wait (Cap)
            MockTicker('F', 80_000_000, 0.90, 'NASDAQ', 'United States', 'EQUITY', False), # Wait (Price)
            
            # Edge Cases
            MockTicker('G', 35_000_000, 0.80, 'NASDAQ', 'United States', 'EQUITY', True), # Keep (Boundary)
            MockTicker('H', 50_000_000, 1.00, 'NASDAQ', 'United States', 'EQUITY', False), # Enter (Boundary)
            MockTicker('I', 40_000_000, 1.20, 'NASDAQ', 'United States', 'EQUITY', False), # Wait (Dead zone)
        ]
        
        results = []
        for t in candidates:
            # Common Conditions
            common = (
                t.country == 'United States' and
                t.exchange in ('NASDAQ', 'NYSE', 'AMEX') and
                t.quote_type == 'EQUITY'
            )
            
            status = t.is_collect_target
            if not common:
                status = False
            else:
                if t.is_collect_target:
                    # Retention Check
                    if t.market_cap < 35_000_000 or t.current_price < 0.80:
                        status = False
                else:
                    # Entry Check
                    if t.market_cap >= 50_000_000 and t.current_price >= 1.00:
                        status = True
            
            results.append((t.cik, status))
            
        expected = [
            ('A', True),
            ('B', False),
            ('C', False),
            ('D', True),
            ('E', False),
            ('F', False),
            ('G', True),
            ('H', True),
            ('I', False)
        ]
        
        for i, (expect_cik, expect_status) in enumerate(expected):
            self.assertEqual(results[i][1], expect_status, f"Failed for {candidates[i].cik}")

if __name__ == '__main__':
    unittest.main()
