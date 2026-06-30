import os
import sys
import tempfile
import urllib.request
import zipfile
import re

# 루트 경로 추가
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms")
sys.path.append("/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core")

def download_and_inspect():
    urls = {
        "KOSPI": "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip",
        "KOSDAQ": "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip"
    }
    
    temp_dir = tempfile.gettempdir()
    
    for market, url in urls.items():
        zip_path = os.path.join(temp_dir, f"{market.lower()}_code.mst.zip")
        print(f"\n==================== {market} Master Inspection ====================")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                zip_data = response.read()
            
            with open(zip_path, "wb") as temp_f:
                temp_f.write(zip_data)
            
            with zipfile.ZipFile(zip_path) as z:
                for filename in z.namelist():
                    if filename.endswith(".mst"):
                        print(f"Reading file: {filename}")
                        with z.open(filename) as f:
                            content_bytes = f.read()
                            lines = content_bytes.splitlines()
                            print(f"Total lines: {len(lines)}")
                            
                            # 파이프 포함 줄 및 일반 줄 샘플 각각 3개씩 분석
                            pipe_lines = []
                            fixed_lines = []
                            for line in lines:
                                if not line.strip():
                                    continue
                                if b'|' in line:
                                    pipe_lines.append(line)
                                else:
                                    fixed_lines.append(line)
                                    
                            # 특정 문제 종목 찾기
                            target_codes = ["0000Z0", "702BA7", "003080"]
                            for line in lines:
                                if not line.strip():
                                    continue
                                stk_cd_bytes = line[0:9]
                                stk_cd = stk_cd_bytes.decode('cp949', errors='ignore').strip()[-6:]
                                if stk_cd in target_codes:
                                    print(f"\nTarget Found: {stk_cd} (Length: {len(line)} bytes)")
                                    print(f"  Raw bytes: {line}")
                                    # 파싱 시도
                                    stk_nm = line[21:61].decode('cp949', errors='ignore').strip()
                                    group_code = line[61:63].decode('cp949', errors='ignore').strip()
                                    
                                    if market == "KOSPI":
                                        listed_dt = line[166:174].decode('cp949', errors='ignore').strip()
                                        listed_shares = line[174:189].decode('cp949', errors='ignore').strip()
                                        cap = line[189:210].decode('cp949', errors='ignore').strip()
                                    else:
                                        listed_dt = line[161:169].decode('cp949', errors='ignore').strip()
                                        listed_shares = line[169:184].decode('cp949', errors='ignore').strip()
                                        cap = line[184:205].decode('cp949', errors='ignore').strip()
                                        
                                    print(f"    Name: '{stk_nm}', Group: '{group_code}'")
                                    print(f"    Listed Date: '{listed_dt}'")
                                    print(f"    Listed Shares: '{listed_shares}'")
                                    print(f"    Capital: '{cap}'")
                                    
        except Exception as e:
            print(f"Error inspecting {market}: {e}")
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)

if __name__ == "__main__":
    download_and_inspect()
