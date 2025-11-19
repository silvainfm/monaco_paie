"""
Scheduler Module for Monaco Payroll System
==========================================
Provides automatic monthly payroll processing with scheduling capabilities
"""

import schedule
import time
import logging
import polars as pl
from datetime import datetime, date, timedelta
from pathlib import Path
import json
import threading
import queue
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import subprocess
import sys
import traceback

# Import main payroll system components
from services.payroll_calculations import CalculateurPaieMonaco, ValidateurPaieMonaco
from services.import_export import ExcelImportExport, DataConsolidation
from services.data_mgt import DataManager
from services.pdf_generation import PDFGeneratorService
from services.email_archive import create_email_distribution_system

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
        logging.StreamHandler()
    ]
)


class JobStatus(Enum):
    """Status of scheduled jobs"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    """Types of scheduled jobs"""
    PAYROLL_PROCESSING = "payroll_processing"
    EMAIL_DISTRIBUTION = "email_distribution"
    BACKUP_CREATION = "backup_creation"
    REPORT_GENERATION = "report_generation"
    DATA_IMPORT = "data_import"
    REMINDER = "reminder"


@dataclass
class ScheduledJob:
    """Represents a scheduled job"""
    id: str
    type: JobType
    schedule: str  # Cron-like schedule or specific date
    params: Dict
    status: JobStatus
    created_at: datetime
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    enabled: bool = True
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        data = asdict(self)
        data['type'] = self.type.value
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        data['last_run'] = self.last_run.isoformat() if self.last_run else None
        data['next_run'] = self.next_run.isoformat() if self.next_run else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ScheduledJob':
        """Create from dictionary"""
        data['type'] = JobType(data['type'])
        data['status'] = JobStatus(data['status'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('last_run'):
            data['last_run'] = datetime.fromisoformat(data['last_run'])
        if data.get('next_run'):
            data['next_run'] = datetime.fromisoformat(data['next_run'])
        return cls(**data)


class PayrollScheduler:
    """Main scheduler for automatic payroll processing"""
    
    def __init__(self, config_dir: Path = Path("data/config"), data_dir: Path = Path("data")):
        self.config_dir = Path(config_dir)
        self.data_dir = Path(data_dir)
        self.jobs_file = self.config_dir / "scheduled_jobs.json"
        self.config_file = self.config_dir / "scheduler_config.json"
        
        # Create directories
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Load configuration
        self.config = self._load_config()
        self.jobs = self._load_jobs()
        
        # Threading for background execution
        self.job_queue = queue.Queue()
        self.worker_thread = None
        self.scheduler_thread = None
        self.running = False
        
        # Email notification settings
        self.notification_config = self.config.get('notifications', {})
    
    def _load_config(self) -> Dict:
        """Load scheduler configuration"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        
        # Default configuration
        default_config = {
            'run_hour': 2,  # Run at 2 AM
            'run_minute': 0,
            'timezone': 'Europe/Monaco',
            'companies': ['CARAX_MONACO', 'RG_CAPITAL_SERVICES'],
            'notifications': {
                'enabled': True,
                'smtp_server': 'smtp.office365.com',
                'smtp_port': 587,
                'sender': 'scheduler@company.mc',
                'recipients': ['admin@company.mc'],
                'on_success': True,
                'on_failure': True
            },
            'backup': {
                'enabled': True,
                'retention_days': 90
            }
        }
        
        # Save default configuration
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        return default_config
    
    def _load_jobs(self) -> List[ScheduledJob]:
        """Load scheduled jobs from storage"""
        if self.jobs_file.exists():
            with open(self.jobs_file, 'r') as f:
                jobs_data = json.load(f)
                return [ScheduledJob.from_dict(job) for job in jobs_data]
        return []
    
    def _save_jobs(self):
        """Save scheduled jobs to storage"""
        jobs_data = [job.to_dict() for job in self.jobs]
        with open(self.jobs_file, 'w') as f:
            json.dump(jobs_data, f, indent=2)
    
    def add_monthly_payroll_job(self, company_id: str, day_of_month: int = 25) -> ScheduledJob:
        """
        Add a monthly payroll processing job
        
        Args:
            company_id: Company identifier
            day_of_month: Day of month to run (default: 25th)
        """
        job_id = f"payroll_{company_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        job = ScheduledJob(
            id=job_id,
            type=JobType.PAYROLL_PROCESSING,
            schedule=f"monthly:{day_of_month}",
            params={
                'company_id': company_id,
                'day_of_month': day_of_month,
                'auto_validate': False,
                'send_emails': True,
                'generate_reports': True
            },
            status=JobStatus.PENDING,
            created_at=datetime.now(),
            next_run=self._calculate_next_run(f"monthly:{day_of_month}")
        )
        
        self.jobs.append(job)
        self._save_jobs()
        
        logger.info(f"Added monthly payroll job for {company_id} on day {day_of_month}")
        return job
    
    def add_email_distribution_job(self, company_id: str, period: str, 
                                  scheduled_date: datetime) -> ScheduledJob:
        """Add a scheduled email distribution job"""
        job_id = f"email_{company_id}_{period}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        job = ScheduledJob(
            id=job_id,
            type=JobType.EMAIL_DISTRIBUTION,
            schedule=scheduled_date.isoformat(),
            params={
                'company_id': company_id,
                'period': period,
                'test_mode': False
            },
            status=JobStatus.PENDING,
            created_at=datetime.now(),
            next_run=scheduled_date
        )
        
        self.jobs.append(job)
        self._save_jobs()
        
        logger.info(f"Added email distribution job for {company_id} period {period}")
        return job
    
    def _calculate_next_run(self, schedule: str) -> datetime:
        """Calculate next run time based on schedule"""
        now = datetime.now()
        
        if schedule.startswith("monthly:"):
            day = int(schedule.split(":")[1])
            
            # Calculate next occurrence
            if now.day < day:
                next_run = now.replace(day=day, hour=self.config['run_hour'], 
                                      minute=self.config['run_minute'], second=0, microsecond=0)
            else:
                # Next month
                if now.month == 12:
                    next_run = now.replace(year=now.year + 1, month=1, day=day,
                                         hour=self.config['run_hour'], 
                                         minute=self.config['run_minute'], second=0, microsecond=0)
                else:
                    next_run = now.replace(month=now.month + 1, day=day,
                                         hour=self.config['run_hour'], 
                                         minute=self.config['run_minute'], second=0, microsecond=0)
            
            return next_run
        
        elif schedule.startswith("weekly:"):
            day_of_week = int(schedule.split(":")[1])
            days_ahead = day_of_week - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            
            next_run = now + timedelta(days=days_ahead)
            return next_run.replace(hour=self.config['run_hour'], 
                                   minute=self.config['run_minute'], second=0, microsecond=0)
        
        else:
            # Assume it's an ISO datetime string
            return datetime.fromisoformat(schedule)
    
    def execute_payroll_job(self, job: ScheduledJob) -> bool:
        """
        Execute a payroll processing job
        
        Args:
            job: The scheduled job to execute
            
        Returns:
            Success status
        """
        try:
            logger.info(f"Starting payroll job {job.id}")
            job.status = JobStatus.RUNNING
            job.last_run = datetime.now()
            self._save_jobs()
            
            company_id = job.params['company_id']
            
            # Determine period (current month)
            now = datetime.now()
            period = now.strftime("%Y-%m")
            
            # Initialize payroll system
            calculator = CalculateurPaieMonaco()
            validator = ValidateurPaieMonaco()
            excel_manager = ExcelImportExport()
            data_consolidator = DataConsolidation()
            
            # Load company data
            year, month = now.year, now.month
            df = DataManager.load_period_data(company_id, month, year)
            
            if df.empty:
                raise Exception(f"No data found for {company_id} period {period}")
            
            # Process payroll
            processed_data = []
            for _, row in df.iterrows():
                row_dict = row.to_dict()
                matricule = row_dict.get('matricule', '')
                cumul_brut_annuel = DataManager.get_cumul_brut_annuel(
                    company_id, matricule, year, month
                ) if matricule else 0.0

                payslip = calculator.process_employee_payslip(row_dict, cumul_brut_annuel=cumul_brut_annuel)
                is_valid, issues = validator.validate_payslip(payslip)
                
                if not is_valid:
                    payslip['statut_validation'] = 'À vérifier'
                    payslip['edge_case_flag'] = True
                    payslip['edge_case_reason'] = '; '.join(issues)
                else:
                    payslip['statut_validation'] = 'Validé'
                    payslip['edge_case_flag'] = False
                
                processed_data.append(payslip)
            
            # Save processed data
            processed_df = pl.DataFrame(processed_data)
            DataManager.save_period_data(processed_df, company_id, month, year)
            
            # Generate PDFs
            if job.params.get('generate_reports', True):
                company_info = self._load_company_info(company_id)
                pdf_service = PDFGeneratorService(company_info, logo_path="logo.png")
                
                output_dir = self.data_dir / "output" / company_id / period
                output_dir.mkdir(parents=True, exist_ok=True)
                
                documents = pdf_service.generate_monthly_documents(
                    processed_df,
                    period,
                    output_dir
                )
                
                logger.info(f"Generated PDFs for {company_id}")
            
            # Send emails if configured
            if job.params.get('send_emails', False):
                self._queue_email_job(company_id, period, processed_df)
            
            # Update job status
            job.status = JobStatus.SUCCESS
            job.next_run = self._calculate_next_run(job.schedule)
            job.retry_count = 0
            self._save_jobs()
            
            # Send success notification
            self._send_notification(
                f"Payroll Processing Success - {company_id}",
                f"Successfully processed payroll for {company_id} period {period}\n"
                f"Processed {len(processed_data)} employees"
            )
            
            logger.info(f"Completed payroll job {job.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error in payroll job {job.id}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Update job status
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.retry_count += 1
            
            # Retry if under limit
            if job.retry_count < job.max_retries:
                job.status = JobStatus.PENDING
                job.next_run = datetime.now() + timedelta(hours=1)  # Retry in 1 hour
                logger.info(f"Scheduling retry {job.retry_count}/{job.max_retries} for job {job.id}")
            
            self._save_jobs()
            
            # Send failure notification
            self._send_notification(
                f"Payroll Processing Failed - {job.params.get('company_id', 'Unknown')}",
                f"Error: {str(e)}\nRetry count: {job.retry_count}/{job.max_retries}"
            )
            
            return False
    
    def _load_company_info(self, company_id: str) -> Dict:
        """Load company information"""
        company_file = self.config_dir / f"company_{company_id}.json"
        
        if company_file.exists():
            with open(company_file, 'r') as f:
                return json.load(f)
        
        # Default company info
        return {
            'name': company_id.replace('_', ' '),
            'siret': '000000000',
            'address': '98000 MONACO',
            'phone': '+377 93 00 00 00',
            'email': 'contact@company.mc'
        }
    
    def _queue_email_job(self, company_id: str, period: str, df):
        """Queue an email distribution job"""
        # Schedule email job for next business day at 9 AM
        next_business_day = datetime.now() + timedelta(days=1)
        while next_business_day.weekday() >= 5:  # Skip weekends
            next_business_day += timedelta(days=1)
        
        scheduled_time = next_business_day.replace(hour=9, minute=0, second=0, microsecond=0)
        
        self.add_email_distribution_job(company_id, period, scheduled_time)
    
    def _send_notification(self, subject: str, body: str):
        """Send email notification"""
        if not self.notification_config.get('enabled', False):
            return
        
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = self.notification_config['sender']
            msg['To'] = ', '.join(self.notification_config['recipients'])
            
            with smtplib.SMTP(self.notification_config['smtp_server'], 
                             self.notification_config['smtp_port']) as server:
                server.starttls()
                # Note: In production, use proper authentication
                server.send_message(msg)
            
            logger.info(f"Notification sent: {subject}")
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
    
    def worker(self):
        """Background worker thread for job execution"""
        logger.info("Worker thread started")
        
        while self.running:
            try:
                # Get job from queue (timeout to allow checking running status)
                job = self.job_queue.get(timeout=1)
                
                if job.type == JobType.PAYROLL_PROCESSING:
                    self.execute_payroll_job(job)
                elif job.type == JobType.EMAIL_DISTRIBUTION:
                    self.execute_email_job(job)
                elif job.type == JobType.BACKUP_CREATION:
                    self.execute_backup_job(job)
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}")
    
    def scheduler_loop(self):
        """Main scheduler loop"""
        logger.info("Scheduler loop started")
        
        while self.running:
            try:
                now = datetime.now()
                
                # Check all jobs
                for job in self.jobs:
                    if not job.enabled:
                        continue
                    
                    if job.status == JobStatus.PENDING and job.next_run:
                        if now >= job.next_run:
                            logger.info(f"Queueing job {job.id}")
                            self.job_queue.put(job)
                
                # Sleep for a minute
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(60)
    
    def start(self):
        """Start the scheduler"""
        if self.running:
            logger.warning("Scheduler already running")
            return
        
        self.running = True
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self.worker, daemon=True)
        self.worker_thread.start()
        
        # Start scheduler thread
        self.scheduler_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        logger.info("Stopping scheduler...")
        self.running = False
        
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        logger.info("Scheduler stopped")
    
    def execute_email_job(self, job: ScheduledJob) -> bool:
        """Execute email distribution job"""
        try:
            logger.info(f"Starting email job {job.id}")
            
            # Initialize email system
            email_system = create_email_distribution_system()
            
            # Load data
            company_id = job.params['company_id']
            period = job.params['period']
            year, month = map(int, period.split('-'))

            df = DataManager.load_period_data(company_id, month, year)
            
            if df.empty:
                raise Exception(f"No data found for email job")
            
            # Generate PDFs if not already done
            output_dir = self.data_dir / "output" / company_id / period
            
            # Send emails
            employees_with_email = df[df['email'].notna() & (df['email'] != '')]
            
            report = email_system['email_service'].send_batch(
                employees_with_email.to_dict('records'),
                {},  # PDF buffers would be loaded here
                period,
                test_mode=job.params.get('test_mode', False)
            )
            
            job.status = JobStatus.SUCCESS
            self._save_jobs()
            
            logger.info(f"Email job completed: {report['sent']} sent, {report['failed']} failed")
            return True
            
        except Exception as e:
            logger.error(f"Email job failed: {e}")
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            self._save_jobs()
            return False
    
    def execute_backup_job(self, job: ScheduledJob) -> bool:
        """Execute backup creation job"""
        try:
            logger.info(f"Starting backup job {job.id}")
            
            # Create backup of all data
            backup_dir = self.data_dir / "backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy all relevant files
            import shutil
            
            # Copy data files
            for file in self.data_dir.glob("**/*.parquet"):
                dest = backup_dir / file.relative_to(self.data_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, dest)
            
            # Create archive
            archive_name = backup_dir.with_suffix('.zip')
            shutil.make_archive(str(backup_dir), 'zip', backup_dir)
            
            # Clean up directory
            shutil.rmtree(backup_dir)
            
            # Clean old backups based on retention policy
            if self.config['backup']['retention_days'] > 0:
                cutoff_date = datetime.now() - timedelta(days=self.config['backup']['retention_days'])
                for backup in (self.data_dir / "backups").glob("*.zip"):
                    # Parse date from filename
                    try:
                        backup_date = datetime.strptime(backup.stem, "%Y%m%d_%H%M%S")
                        if backup_date < cutoff_date:
                            backup.unlink()
                            logger.info(f"Deleted old backup: {backup.name}")
                    except:
                        continue
            
            job.status = JobStatus.SUCCESS
            self._save_jobs()
            
            logger.info(f"Backup created: {archive_name}")
            return True
            
        except Exception as e:
            logger.error(f"Backup job failed: {e}")
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            self._save_jobs()
            return False
    
    def get_job_status(self, job_id: str) -> Optional[ScheduledJob]:
        """Get status of a specific job"""
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None
    
    def list_jobs(self, job_type: Optional[JobType] = None, 
                  status: Optional[JobStatus] = None) -> List[ScheduledJob]:
        """List jobs with optional filtering"""
        jobs = self.jobs
        
        if job_type:
            jobs = [j for j in jobs if j.type == job_type]
        
        if status:
            jobs = [j for j in jobs if j.status == status]
        
        return jobs
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a scheduled job"""
        for job in self.jobs:
            if job.id == job_id:
                job.status = JobStatus.CANCELLED
                job.enabled = False
                self._save_jobs()
                logger.info(f"Cancelled job {job_id}")
                return True
        return False
    
    def update_config(self, config: Dict):
        """Update scheduler configuration"""
        self.config.update(config)
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
        logger.info("Configuration updated")


# Windows Service for production deployment
class WindowsSchedulerService:
    """Windows service wrapper for the scheduler"""
    
    def __init__(self):
        self.scheduler = PayrollScheduler()
    
    def start(self):
        """Start the service"""
        logger.info("Starting Windows Scheduler Service")
        self.scheduler.start()
        
        # Keep service running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Stop the service"""
        logger.info("Stopping Windows Scheduler Service")
        self.scheduler.stop()


# CLI for managing the scheduler
def main():
    """Command line interface for the scheduler"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monaco Payroll Scheduler")
    parser.add_argument('command', choices=['start', 'stop', 'status', 'add-job', 'list-jobs'])
    parser.add_argument('--company', help='Company ID for job creation')
    parser.add_argument('--day', type=int, default=25, help='Day of month for monthly jobs')
    parser.add_argument('--type', choices=['payroll', 'email', 'backup'], help='Job type')
    
    args = parser.parse_args()
    
    scheduler = PayrollScheduler()
    
    if args.command == 'start':
        print("Starting scheduler...")
        scheduler.start()
        print("Scheduler started. Press Ctrl+C to stop.")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()
            print("\nScheduler stopped.")
    
    elif args.command == 'stop':
        scheduler.stop()
        print("Scheduler stopped.")
    
    elif args.command == 'status':
        jobs = scheduler.list_jobs()
        print(f"Total jobs: {len(jobs)}")
        
        for status in JobStatus:
            count = len([j for j in jobs if j.status == status])
            print(f"  {status.value}: {count}")
    
    elif args.command == 'add-job':
        if args.type == 'payroll' and args.company:
            job = scheduler.add_monthly_payroll_job(args.company, args.day)
            print(f"Added payroll job: {job.id}")
        else:
            print("Required arguments: --type and --company")
    
    elif args.command == 'list-jobs':
        jobs = scheduler.list_jobs()
        
        for job in jobs:
            print(f"\nJob ID: {job.id}")
            print(f"  Type: {job.type.value}")
            print(f"  Status: {job.status.value}")
            print(f"  Next run: {job.next_run}")
            print(f"  Enabled: {job.enabled}")


if __name__ == "__main__":
    main()
