import os
import sys
import subprocess
import datetime
import logging

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def create_checkpoint(phase_name: str):
    """
    Create a database checkpoint (backup) using pg_dump.
    """
    # 1. Prepare Directory
    backup_dir = os.path.join(os.path.dirname(__file__), '..', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    # 2. Generate Filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"checkpoint_{phase_name}_{timestamp}.dump"
    filepath = os.path.join(backup_dir, filename)
    
    logger.info(f"Starting Checkpoint for {phase_name}...")
    
    # 3. Execute pg_dump via Docker
    # docker exec usdms_db pg_dump -U postgres -Fc usdms_db > filepath
    # We need to run this command from the host shell.
    
    cmd = f"docker exec usdms_db pg_dump -U postgres -Fc usdms_db > {filepath}"
    
    try:
        # Use shell=True to handle redirection
        subprocess.run(cmd, shell=True, check=True)
        
        # Verify file size
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        logger.info(f"Checkpoint created successfully: {filepath} ({size_mb:.2f} MB)")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Checkpoint failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python db_checkpoint.py <phase_name>")
        sys.exit(1)
        
    phase = sys.argv[1]
    create_checkpoint(phase)
