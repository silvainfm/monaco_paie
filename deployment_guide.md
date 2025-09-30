# Monaco Payroll System - Production Deployment Guide

## Table of Contents
1. [System Requirements](#system-requirements)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Server Setup](#server-setup)
4. [Application Installation](#application-installation)
5. [Database Configuration](#database-configuration)
6. [Security Configuration](#security-configuration)
7. [Scheduler Setup](#scheduler-setup)
8. [Monitoring & Maintenance](#monitoring-maintenance)
9. [Backup & Recovery](#backup-recovery)
10. [Troubleshooting](#troubleshooting)

---

## 1. System Requirements {#system-requirements}

### Minimum Hardware Requirements
- **CPU**: 4 cores (8 cores recommended)
- **RAM**: 8 GB minimum (16 GB recommended)
- **Storage**: 100 GB SSD (500 GB recommended for archives)
- **Network**: Stable internet connection with static IP

### Software Requirements
- **Operating System**: 
  - Windows Server 2019/2022 (recommended)
  - Ubuntu Server 20.04/22.04 LTS (alternative)
- **Python**: 3.9 or higher
- **Database**: PostgreSQL 13+ (optional, for future migration)
- **Web Server**: Nginx (reverse proxy)
- **SSL Certificate**: For HTTPS

### Network Requirements
- **Ports**:
  - 8501 (Streamlit application)
  - 443 (HTTPS)
  - 587 (SMTP for email)
  - 5432 (PostgreSQL if used)

---

## 2. Pre-Deployment Checklist {#pre-deployment-checklist}

### Legal & Compliance
- [ ] GDPR compliance verified
- [ ] Data processing agreements signed
- [ ] Employee consent forms collected
- [ ] Data retention policies documented

### Technical Preparation
- [ ] Server provisioned and accessible
- [ ] Domain name configured
- [ ] SSL certificate obtained
- [ ] Backup storage configured
- [ ] Email service credentials ready
- [ ] Microsoft 365 OAuth2 app registered

### Data Preparation
- [ ] Company information verified
- [ ] Employee data cleaned and validated
- [ ] Historical data migrated (if applicable)
- [ ] Test data removed

---

## 3. Server Setup {#server-setup}

### Windows Server Setup

```powershell
# 1. Update Windows Server
Install-WindowsUpdate -AcceptAll -AutoReboot

# 2. Install IIS (optional, for reverse proxy)
Install-WindowsFeature -Name Web-Server -IncludeManagementTools

# 3. Install Python
# Download from python.org and install
# Or use Chocolatey:
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
choco install python --version=3.9.13

# 4. Create application directory
New-Item -ItemType Directory -Path "C:\MonacoPayroll"

# 5. Set up firewall rules
New-NetFirewallRule -DisplayName "Monaco Payroll" -Direction Inbound -LocalPort 8501 -Protocol TCP -Action Allow
```

### Linux Server Setup

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install Python and dependencies
sudo apt install python3.9 python3-pip python3-venv nginx certbot python3-certbot-nginx -y

# 3. Create application user
sudo useradd -m -s /bin/bash monacopayroll
sudo usermod -aG sudo monacopayroll

# 4. Create application directory
sudo mkdir -p /opt/monacopayroll
sudo chown -R monacopayroll:monacopayroll /opt/monacopayroll

# 5. Configure firewall
sudo ufw allow 22/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8501/tcp
sudo ufw enable
```

---

## 4. Application Installation {#application-installation}

### Step 1: Clone/Upload Application Files

```bash
# Windows PowerShell
cd C:\MonacoPayroll

# Linux
cd /opt/monacopayroll

# Create directory structure
mkdir -p {config,data,archives,logs,temp,backups}
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux:
source venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip
```

### Step 3: Install Dependencies

Create `requirements.txt`:

```txt
streamlit==1.28.0
pandas==2.0.3
numpy==1.24.3
pyarrow==12.0.1
openpyxl==3.1.2
xlsxwriter==3.1.2
reportlab==4.0.4
Pillow==10.0.0
msal==1.24.1
requests==2.31.0
python-dateutil==2.8.2
schedule==1.2.0
cryptography==41.0.4
python-dotenv==1.0.0
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Step 4: Environment Configuration

Create `.env` file:

```env
# Application Settings
APP_ENV=production
APP_DEBUG=False
APP_SECRET_KEY=your-secret-key-here

# Server Settings
SERVER_HOST=0.0.0.0
SERVER_PORT=8501
SERVER_BASE_URL=https://payroll.yourcompany.mc

# Database (for future use)
DATABASE_URL=postgresql://user:password@localhost/monacopayroll

# Email Settings
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=noreply@yourcompany.mc
SMTP_PASSWORD=your-app-password

# Microsoft OAuth2
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret

# Security
SESSION_COOKIE_SECURE=True
CSRF_PROTECTION=True

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
```

### Step 5: Configure Streamlit

Create `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#2C3E50"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"

[server]
port = 8501
address = "0.0.0.0"
baseUrlPath = ""
enableCORS = false
enableXsrfProtection = true
maxUploadSize = 200
headless = true

[browser]
serverAddress = "payroll.yourcompany.mc"
gatherUsageStats = false
serverPort = 443

[logger]
level = "info"
messageFormat = "%(asctime)s %(message)s"

[client]
showErrorDetails = false
toolbarMode = "minimal"
```

---

## 5. Database Configuration {#database-configuration}

### Current: Parquet Files

The system currently uses Parquet files. Ensure proper directory structure:

```bash
data/
├── consolidated/
│   └── 2024/
│       ├── 01/
│       ├── 02/
│       └── ...
├── companies/
│   └── companies.parquet
└── email_archives/
    ├── sent/
    ├── pending/
    └── failed/
```

### Future: PostgreSQL Migration

For production scalability, consider migrating to PostgreSQL:

```sql
-- Create database
CREATE DATABASE monacopayroll;

-- Create user
CREATE USER payrollapp WITH PASSWORD 'secure-password';
GRANT ALL PRIVILEGES ON DATABASE monacopayroll TO payrollapp;

-- Create schema
\c monacopayroll;

CREATE SCHEMA payroll;

-- Create tables
CREATE TABLE payroll.companies (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    siret VARCHAR(20),
    address TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE payroll.employees (
    id SERIAL PRIMARY KEY,
    matricule VARCHAR(20) UNIQUE NOT NULL,
    company_id VARCHAR(50) REFERENCES payroll.companies(id),
    nom VARCHAR(100),
    prenom VARCHAR(100),
    email VARCHAR(200),
    pays_residence VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE payroll.payslips (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES payroll.employees(id),
    period VARCHAR(7),
    salaire_base DECIMAL(10,2),
    salaire_brut DECIMAL(10,2),
    salaire_net DECIMAL(10,2),
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_payslips_period ON payroll.payslips(period);
CREATE INDEX idx_payslips_employee ON payroll.payslips(employee_id);
```

---

## 6. Security Configuration {#security-configuration}

### SSL/TLS Setup with Nginx

```nginx
# /etc/nginx/sites-available/monacopayroll
server {
    listen 80;
    server_name payroll.yourcompany.mc;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name payroll.yourcompany.mc;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/payroll.yourcompany.mc/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/payroll.yourcompany.mc/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Proxy to Streamlit
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
    
    # Limit file upload size
    client_max_body_size 100M;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
    location /login {
        limit_req zone=login burst=5;
    }
}
```

### Application Security

1. **User Authentication Enhancement**

```python
# config/security.py
import hashlib
import secrets
from datetime import datetime, timedelta

class SecurityConfig:
    PASSWORD_MIN_LENGTH = 12
    PASSWORD_REQUIRE_UPPERCASE = True
    PASSWORD_REQUIRE_LOWERCASE = True
    PASSWORD_REQUIRE_DIGITS = True
    PASSWORD_REQUIRE_SPECIAL = True
    
    SESSION_TIMEOUT_MINUTES = 30
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15
    
    @staticmethod
    def hash_password(password: str, salt: str = None) -> tuple:
        if not salt:
            salt = secrets.token_hex(32)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', 
                                       password.encode('utf-8'), 
                                       salt.encode('utf-8'), 
                                       100000)
        return pwd_hash.hex(), salt
```

2. **Data Encryption**

```python
# config/encryption.py
from cryptography.fernet import Fernet

class DataEncryption:
    def __init__(self, key_file='config/encryption.key'):
        self.key_file = key_file
        self.cipher = self._load_or_create_key()
    
    def _load_or_create_key(self):
        try:
            with open(self.key_file, 'rb') as f:
                key = f.read()
        except FileNotFoundError:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
        return Fernet(key)
    
    def encrypt_sensitive_data(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        return self.cipher.decrypt(encrypted_data.encode()).decode()
```

---

## 7. Scheduler Setup {#scheduler-setup}

### Windows Task Scheduler

```powershell
# Create scheduled task for monthly payroll
$action = New-ScheduledTaskAction -Execute "C:\MonacoPayroll\venv\Scripts\python.exe" `
    -Argument "C:\MonacoPayroll\scheduler.py start" `
    -WorkingDirectory "C:\MonacoPayroll"

$trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM

$principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" `
    -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName "MonacoPayrollScheduler" `
    -Action $action -Trigger $trigger -Principal $principal `
    -Description "Monaco Payroll Automatic Processing"
```

### Linux Systemd Service

Create `/etc/systemd/system/monacopayroll.service`:

```ini
[Unit]
Description=Monaco Payroll System
After=network.target

[Service]
Type=simple
User=monacopayroll
Group=monacopayroll
WorkingDirectory=/opt/monacopayroll
Environment="PATH=/opt/monacopayroll/venv/bin"
ExecStart=/opt/monacopayroll/venv/bin/streamlit run app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/monacopayroll-scheduler.service`:

```ini
[Unit]
Description=Monaco Payroll Scheduler
After=network.target

[Service]
Type=simple
User=monacopayroll
Group=monacopayroll
WorkingDirectory=/opt/monacopayroll
Environment="PATH=/opt/monacopayroll/venv/bin"
ExecStart=/opt/monacopayroll/venv/bin/python scheduler.py start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable monacopayroll monacopayroll-scheduler
sudo systemctl start monacopayroll monacopayroll-scheduler
```

### Configure Scheduler

```python
# config/scheduler_config.json
{
  "companies": [
    {
      "id": "CARAX_MONACO",
      "name": "CARAX MONACO",
      "payroll_day": 25,
      "email_delay_hours": 24
    },
    {
      "id": "RG_CAPITAL_SERVICES",
      "name": "RG CAPITAL SERVICES",
      "payroll_day": 28,
      "email_delay_hours": 24
    }
  ],
  "notifications": {
    "enabled": true,
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "sender": "scheduler@yourcompany.mc",
    "recipients": ["admin@yourcompany.mc", "hr@yourcompany.mc"],
    "on_success": true,
    "on_failure": true,
    "on_edge_cases": true
  },
  "backup": {
    "enabled": true,
    "schedule": "daily",
    "time": "03:00",
    "retention_days": 90,
    "remote_backup": true,
    "remote_path": "\\\\backup-server\\payroll"
  }
}
```

---

## 8. Monitoring & Maintenance {#monitoring-maintenance}

### Application Monitoring

1. **Health Check Endpoint**

```python
# healthcheck.py
from flask import Flask, jsonify
import psutil
import os

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'cpu_percent': psutil.cpu_percent(),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_usage': psutil.disk_usage('/').percent,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    app.run(port=8080)
```

2. **Log Rotation**

Create `/etc/logrotate.d/monacopayroll`:

```
/opt/monacopayroll/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 monacopayroll monacopayroll
    sharedscripts
    postrotate
        systemctl reload monacopayroll
    endscript
}
```

3. **Performance Monitoring**

```bash
# Install monitoring tools
pip install prometheus-client

# Add to application
from prometheus_client import Counter, Histogram, generate_latest

# Metrics
payroll_processed = Counter('payroll_processed_total', 'Total payrolls processed')
processing_time = Histogram('payroll_processing_seconds', 'Time spent processing payroll')
```

### Maintenance Tasks

#### Daily
- [ ] Check application logs for errors
- [ ] Verify scheduler job status
- [ ] Monitor disk space
- [ ] Check backup completion

#### Weekly
- [ ] Review edge cases and validation errors
- [ ] Update employee data if needed
- [ ] Test email delivery
- [ ] Review security logs

#### Monthly
- [ ] Verify payroll calculations
- [ ] Archive old logs
- [ ] Update SSL certificates if needed
- [ ] Review and optimize performance

---

## 9. Backup & Recovery {#backup-recovery}

### Backup Strategy

1. **Automated Daily Backups**

```python
# backup_script.py
import shutil
import os
from datetime import datetime
from pathlib import Path

def create_backup():
    backup_dir = Path('/backups/monacopayroll')
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'backup_{timestamp}'
    
    # Directories to backup
    dirs_to_backup = [
        '/opt/monacopayroll/data',
        '/opt/monacopayroll/config',
        '/opt/monacopayroll/archives'
    ]
    
    for dir_path in dirs_to_backup:
        if os.path.exists(dir_path):
            dest = backup_dir / backup_name / Path(dir_path).name
            shutil.copytree(dir_path, dest)
    
    # Create archive
    archive = shutil.make_archive(
        str(backup_dir / backup_name),
        'zip',
        backup_dir / backup_name
    )
    
    # Clean up
    shutil.rmtree(backup_dir / backup_name)
    
    # Upload to remote storage (optional)
    upload_to_cloud(archive)
    
    return archive
```

2. **Recovery Procedure**

```bash
# 1. Stop services
sudo systemctl stop monacopayroll monacopayroll-scheduler

# 2. Backup current state
mv /opt/monacopayroll/data /opt/monacopayroll/data.corrupted

# 3. Extract backup
unzip /backups/monacopayroll/backup_20240125_020000.zip -d /opt/monacopayroll/

# 4. Verify permissions
chown -R monacopayroll:monacopayroll /opt/monacopayroll/

# 5. Restart services
sudo systemctl start monacopayroll monacopayroll-scheduler

# 6. Verify functionality
curl https://payroll.yourcompany.mc/health
```

---

## 10. Troubleshooting {#troubleshooting}

### Common Issues and Solutions

#### Application Won't Start

```bash
# Check logs
tail -f /opt/monacopayroll/logs/app.log

# Common fixes:
# 1. Check Python version
python --version

# 2. Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# 3. Check permissions
ls -la /opt/monacopayroll/

# 4. Verify environment variables
printenv | grep APP_
```

#### Email Delivery Failures

```python
# Test email configuration
from email_distribution import create_email_distribution_system

system = create_email_distribution_system()
result = system['email_service'].test_connection()
print(result)
```

#### Database Connection Issues

```sql
-- Test PostgreSQL connection
psql -U payrollapp -d monacopayroll -h localhost

-- Check active connections
SELECT * FROM pg_stat_activity WHERE datname = 'monacopayroll';
```

#### Performance Issues

```bash
# Monitor resource usage
htop

# Check disk I/O
iotop

# Analyze slow queries (if using PostgreSQL)
SELECT query, calls, total_time, mean_time 
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;
```

### Support Contacts

- **Technical Support**: tech-support@yourcompany.mc
- **System Administrator**: sysadmin@yourcompany.mc
- **Emergency Contact**: +377 XX XX XX XX

---

## Appendix: Deployment Checklist

### Pre-Production
- [ ] All dependencies installed
- [ ] Configuration files created
- [ ] SSL certificates installed
- [ ] Firewall rules configured
- [ ] Backup system tested
- [ ] Monitoring configured
- [ ] Security scan completed

### Go-Live
- [ ] DNS records updated
- [ ] Services started and enabled
- [ ] Health checks passing
- [ ] Test payroll processed
- [ ] Email delivery verified
- [ ] User accounts created
- [ ] Training completed

### Post-Deployment
- [ ] Performance baseline established
- [ ] Backup verification completed
- [ ] Documentation updated
- [ ] Incident response plan tested
- [ ] User feedback collected

---

## Version History

- **v1.0.0** - Initial deployment (January 2024)
- **v1.1.0** - Added OAuth2 support (February 2024)
- **v1.2.0** - Scheduler implementation (March 2024)

---

*Last Updated: January 2024*
*Document Version: 1.0*