import os
import sys
import time
import logging
from datetime import datetime

# Setup logging
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'job_alerts.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

def run_job_alerts():
    try:
        logging.info("Starting job alerts at " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # Import and run the job alerts script
        import try as job_alerts
        job_alerts.send_jobs()
        
        logging.info("Job alerts completed successfully")
    except Exception as e:
        logging.error(f"Error running job alerts: {e}")

if __name__ == "__main__":
    run_job_alerts()