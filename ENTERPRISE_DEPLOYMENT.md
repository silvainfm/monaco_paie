# Monaco Paie - Enterprise Deployment Guide

**For:** 200+ clients, 10-15 users, office + remote access

## Architecture Overview

```
                                    [Internet]
                                        |
                            [VPN Gateway / Firewall]
                                        |
                        +---------------+---------------+
                        |                               |
                  [Office LAN]                    [Remote Users]
                        |                          (via VPN)
                        |
              +---------+---------+
              |                   |
        [App Server]        [Backup Server]
       (Primary)            (Replication)
          |
    [DuckDB Storage]
```

---

## Deployment Options

### Option A: On-Premise Servers (Recommended for your setup)

**Why:** Full control, data stays in office, lower ongoing costs

**Requirements:**
- Server: 16GB RAM, 8 cores, 500GB SSD
- Backup: 8GB RAM, 500GB+ storage
- UPS for power protection
- 100Mbps+ internet with static IP or DynDNS

**Cost:** 2000-4000EUR hardware + 50-100EUR/month networking

### Option B: Private Cloud (Hybrid)

**Why:** Flexibility, managed infrastructure

**Providers (RGPD-compliant):**
- OVH Dedicated: 100-200EUR/month
- Scaleway Dedibox: 80-150EUR/month
- Hetzner Dedicated: 60-120EUR/month

**Cost:** 960-2400EUR/year

### Option C: Hybrid (Recommended for transition)

**Why:** Best of both - primary on-premise, cloud backup/DR

- Primary: Office server
- Backup: Private cloud VPS
- Sync: Daily encrypted backups to cloud

---

## 1. Server Setup (On-Premise)

### Hardware Specifications

**Primary Application Server:**
- CPU: 8 cores (Intel Xeon or AMD EPYC)
- RAM: 16GB minimum, 32GB recommended
- Storage: 500GB NVMe SSD (RAID 1 for redundancy)
- Network: 1Gbps NIC
- OS: Ubuntu Server 22.04 LTS

**Backup Server:**
- CPU: 4 cores
- RAM: 8GB
- Storage: 1TB+ HDD (RAID 1)
- Purpose: Automated backups, disaster recovery

### OS Installation

```bash
# Install Ubuntu Server 22.04 LTS
# During install:
# - Enable OpenSSH server
# - Use entire disk with LVM
# - Create admin user

# After install, update
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y \
  docker.io \
  docker-compose \
  ufw \
  fail2ban \
  unattended-upgrades \
  nginx \
  certbot \
  python3-certbot-nginx

# Enable automatic security updates
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

### Network Configuration

```bash
# Set static IP
sudo nano /etc/netplan/00-installer-config.yaml
```

```yaml
network:
  ethernets:
    ens33:  # Your interface name
      dhcp4: no
      addresses:
        - 192.168.1.100/24
      gateway4: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]
  version: 2
```

```bash
sudo netplan apply
```

---

## 2. VPN Setup for Remote Access

**3 Options:**

### Option A: WireGuard (Recommended - Fast, Secure, Simple)

**Install on server:**
```bash
sudo apt install wireguard -y

# Generate server keys
wg genkey | sudo tee /etc/wireguard/privatekey | wg pubkey | sudo tee /etc/wireguard/publickey

# Create config
sudo nano /etc/wireguard/wg0.conf
```

```ini
[Interface]
Address = 10.200.200.1/24
ListenPort = 51820
PrivateKey = <server-private-key>
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

# Add each remote user
[Peer]
PublicKey = <user1-public-key>
AllowedIPs = 10.200.200.2/32

[Peer]
PublicKey = <user2-public-key>
AllowedIPs = 10.200.200.3/32
```

```bash
# Enable IP forwarding
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Start WireGuard
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0

# Open firewall
sudo ufw allow 51820/udp
```

**Client setup (each user):**
```bash
# Install WireGuard client
# macOS: brew install wireguard-tools
# Windows: Download from wireguard.com
# Mobile: App store

# Generate client keys
wg genkey | tee privatekey | wg pubkey > publickey

# Create client config
nano comptable1.conf
```

```ini
[Interface]
PrivateKey = <client-private-key>
Address = 10.200.200.2/32
DNS = 8.8.8.8

[Peer]
PublicKey = <server-public-key>
Endpoint = your-office-ip:51820
AllowedIPs = 192.168.1.0/24  # Office network
PersistentKeepalive = 25
```

### Option B: Tailscale (Easiest - Zero Config)

```bash
# Install on server and all clients
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate (opens browser)
sudo tailscale up

# Access server via Tailscale IP
# e.g., https://100.x.y.z:8501
```

**Pros:** Free, automatic mesh VPN, no port forwarding
**Cons:** Third-party service (but E2E encrypted)

### Option C: OpenVPN (Traditional)

```bash
# Use easy-rsa scripts
curl -O https://raw.githubusercontent.com/angristan/openvpn-install/master/openvpn-install.sh
chmod +x openvpn-install.sh
sudo ./openvpn-install.sh
```

---

## 3. Application Deployment

### Docker Production Stack

```bash
# Clone repository
cd /opt
sudo git clone https://your-repo.git monaco_paie
cd monaco_paie
sudo chown -R $USER:$USER .

# Create environment file
cat > .env << 'EOF'
# Session timeout (seconds)
SESSION_TIMEOUT=3600

# Backup retention (days)
BACKUP_RETENTION_DAYS=90

# Max upload size (MB)
MAX_UPLOAD_SIZE=100

# Enable audit logging
ENABLE_AUDIT=true
EOF

# Create SSL certificates (Let's Encrypt)
sudo certbot certonly --standalone -d paie.votre-domaine.com

# Or generate self-signed for internal use
mkdir -p ssl
openssl req -x509 -nodes -days 730 -newkey rsa:4096 \
  -keyout ssl/key.pem -out ssl/cert.pem \
  -subj "/C=MC/ST=Monaco/L=Monaco/O=Cabinet Comptable/CN=paie.local"

# Create user database
mkdir -p nginx_data
sudo apt install apache2-utils -y

# Add users (repeat for each of 10-15 users)
htpasswd -c nginx_data/.htpasswd admin
htpasswd nginx_data/.htpasswd comptable1
htpasswd nginx_data/.htpasswd comptable2
# ... add all 15 users

# Launch production stack
docker-compose -f docker-compose.prod.yml up -d

# Verify
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs -f
```

### Resource Limits (for 200+ clients)

Update `docker-compose.prod.yml`:

```yaml
services:
  streamlit:
    deploy:
      resources:
        limits:
          cpus: '8'      # Use most cores
          memory: 12G    # Adequate for large dataset
        reservations:
          cpus: '4'
          memory: 4G
```

---

## 4. Automated Backups

### Local Backup Script

```bash
cat > /opt/monaco_paie/backup-local.sh << 'EOF'
#!/bin/bash
set -e

APP_DIR="/opt/monaco_paie"
BACKUP_DIR="/backup/monaco_paie"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=90

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database
echo "Backing up database..."
cp "$APP_DIR/data/payroll.duckdb" "$BACKUP_DIR/payroll_$DATE.duckdb"

# Backup config
echo "Backing up config..."
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" -C "$APP_DIR" config

# Backup users
echo "Backing up users..."
cp "$APP_DIR/data/users.parquet" "$BACKUP_DIR/users_$DATE.parquet"

# Backup audit logs
echo "Backing up audit logs..."
cp "$APP_DIR/data/audit_log.parquet" "$BACKUP_DIR/audit_$DATE.parquet"

# Delete old backups
echo "Cleaning old backups..."
find "$BACKUP_DIR" -name "*.duckdb" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.parquet" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $DATE"
EOF

chmod +x /opt/monaco_paie/backup-local.sh
```

### Remote Backup Script (Cloud sync)

```bash
cat > /opt/monaco_paie/backup-remote.sh << 'EOF'
#!/bin/bash
set -e

LOCAL_BACKUP="/backup/monaco_paie"
REMOTE_SERVER="backup.votre-cloud.com"
REMOTE_USER="backup"
REMOTE_DIR="/backups/monaco_paie"

# Sync to remote via rsync over SSH
rsync -avz --progress \
  -e "ssh -i /root/.ssh/backup_key" \
  "$LOCAL_BACKUP/" \
  "$REMOTE_USER@$REMOTE_SERVER:$REMOTE_DIR/"

echo "Remote sync completed"
EOF

chmod +x /opt/monaco_paie/backup-remote.sh
```

### Cron Schedule

```bash
sudo crontab -e
```

```cron
# Backup every 6 hours
0 */6 * * * /opt/monaco_paie/backup-local.sh >> /var/log/monaco_backup.log 2>&1

# Remote sync daily at 2 AM
0 2 * * * /opt/monaco_paie/backup-remote.sh >> /var/log/monaco_remote_backup.log 2>&1

# Weekly cleanup
0 3 * * 0 docker system prune -af >> /var/log/docker_cleanup.log 2>&1
```

---

## 5. Monitoring and Alerts

### System Monitoring

```bash
# Install monitoring tools
sudo apt install -y htop iotop nethogs

# Install Netdata (real-time monitoring dashboard)
bash <(curl -Ss https://my-netdata.io/kickstart.sh) --dont-wait

# Access monitoring: http://server-ip:19999
# Configure firewall
sudo ufw allow from 192.168.1.0/24 to any port 19999
```

### Health Check Script

```bash
cat > /opt/monaco_paie/health-check.sh << 'EOF'
#!/bin/bash

HEALTHCHECK_URL="http://localhost:8501/_stcore/health"
LOG_FILE="/var/log/monaco_health.log"

# Check application health
if curl -sf "$HEALTHCHECK_URL" > /dev/null; then
    echo "$(date): OK" >> "$LOG_FILE"
else
    echo "$(date): FAILED - Restarting" >> "$LOG_FILE"
    cd /opt/monaco_paie
    docker-compose -f docker-compose.prod.yml restart streamlit

    # Send alert (configure email)
    echo "Monaco Paie health check failed at $(date)" | \
      mail -s "ALERT: Monaco Paie Down" admin@votre-domaine.com
fi
EOF

chmod +x /opt/monaco_paie/health-check.sh

# Run every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/monaco_paie/health-check.sh") | crontab -
```

### Alert Configuration

```bash
# Install mail utilities
sudo apt install -y mailutils

# Configure SMTP (example for Gmail)
sudo nano /etc/ssmtp/ssmtp.conf
```

```ini
root=admin@votre-domaine.com
mailhub=smtp.gmail.com:587
AuthUser=votre-email@gmail.com
AuthPass=app-specific-password
UseSTARTTLS=YES
```

---

## 6. Security Hardening

### Firewall Configuration

```bash
# Reset and configure UFW
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH (restrict to office IP if possible)
sudo ufw limit 22/tcp comment 'SSH'

# HTTP/HTTPS
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'

# VPN (WireGuard)
sudo ufw allow 51820/udp comment 'WireGuard'

# Enable
sudo ufw enable
sudo ufw status numbered
```

### Fail2Ban Configuration

```bash
# Configure Fail2Ban for SSH and nginx
sudo nano /etc/fail2ban/jail.local
```

```ini
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = 22
logpath = /var/log/auth.log

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
logpath = /var/log/nginx/error.log
maxretry = 5
findtime = 600
bantime = 7200
```

```bash
sudo systemctl restart fail2ban
sudo fail2ban-client status
```

### SSH Hardening

```bash
sudo nano /etc/ssh/sshd_config
```

```ini
# Disable root login
PermitRootLogin no

# Use keys only (disable password)
PasswordAuthentication no
PubkeyAuthentication yes

# Other security settings
X11Forwarding no
MaxAuthTries 3
MaxSessions 2
```

```bash
sudo systemctl restart sshd
```

### Application Users

Create dedicated app users in Monaco Paie:

```bash
# Access shell in container
docker exec -it monaco_paie bash

# Create admin user
python3 << 'EOF'
from services.auth import AuthManager

# Add admin
AuthManager.add_or_update_user(
    username='admin',
    password='STRONG_PASSWORD_HERE',
    role='admin',
    name='Administrateur'
)

# Add comptables (repeat for each user)
AuthManager.add_or_update_user(
    username='comptable1',
    password='STRONG_PASSWORD',
    role='comptable',
    name='Comptable 1'
)
EOF
```

---

## 7. High Availability (Optional)

For mission-critical 24/7 operations:

### Load Balancer Setup

```yaml
# docker-compose.ha.yml
version: '3.8'

services:
  streamlit1:
    <<: *streamlit-base
    container_name: monaco_paie_1

  streamlit2:
    <<: *streamlit-base
    container_name: monaco_paie_2

  nginx-lb:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx-lb.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - streamlit1
      - streamlit2
```

---

## 8. Disaster Recovery Plan

### Scenario 1: Server Failure

```bash
# On backup server
cd /opt/monaco_paie
docker-compose -f docker-compose.prod.yml up -d

# Restore latest backup
cp /backup/monaco_paie/payroll_latest.duckdb data/payroll.duckdb
docker-compose restart
```

### Scenario 2: Data Corruption

```bash
# Stop application
docker-compose down

# Restore from backup
cd /opt/monaco_paie
cp /backup/monaco_paie/payroll_YYYYMMDD_HHMMSS.duckdb data/payroll.duckdb

# Restart
docker-compose up -d
```

### Recovery Time Objective (RTO)

- Local restore: < 15 minutes
- Full disaster recovery: < 2 hours

---

## 9. Compliance and Audit

### RGPD Compliance

**Features included:**
- Audit logging (all user actions tracked)
- Data encryption at rest (server full-disk encryption)
- Data encryption in transit (SSL/TLS)
- Access control (role-based authentication)
- Data retention policies (automated cleanup)

### Audit Log Access

```bash
# View audit logs
docker exec -it monaco_paie python3 << 'EOF'
from services.audit_log import AuditLogger
import polars as pl

# Last 100 actions
logs = AuditLogger.get_logs(limit=100)
print(logs)

# Failed logins last 24h
failed = AuditLogger.get_failed_logins(hours=24)
print(failed)

# Export for compliance audit
AuditLogger.export_logs(
    Path('audit_export_2025.csv'),
    start_date=datetime(2025, 1, 1),
    end_date=datetime(2025, 12, 31)
)
EOF
```

---

## 10. Maintenance Procedures

### Weekly Tasks

```bash
# Check disk space
df -h

# Check logs
docker-compose logs --tail=100 streamlit

# Review failed logins
docker exec -it monaco_paie python3 -c "from services.audit_log import AuditLogger; print(AuditLogger.get_failed_logins(hours=168))"
```

### Monthly Tasks

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Update containers
cd /opt/monaco_paie
git pull
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --build

# Verify backups
ls -lh /backup/monaco_paie/
```

### Quarterly Tasks

```bash
# Test disaster recovery
# Security audit
# Review user access (remove departed employees)
# Update SSL certificates
sudo certbot renew
```

---

## Cost Summary

### On-Premise Setup

**Initial (Year 1):**
- Server hardware: 2500EUR
- Backup hardware: 800EUR
- UPS: 300EUR
- Network equipment: 200EUR
- Setup/consulting: 500-1000EUR
- **Total: 4300-4800EUR**

**Ongoing (Yearly):**
- Internet (static IP): 600EUR
- Domain: 15EUR
- Electricity: 200EUR
- Maintenance: 300EUR
- **Total: 1115EUR/year**

### Hybrid (On-Premise + Cloud Backup)

**Additional ongoing:**
- Cloud VPS backup: 120EUR/year
- **Total: 1235EUR/year**

### Private Cloud Only

**Ongoing:**
- Dedicated server: 1200-2400EUR/year
- Domain: 15EUR
- **Total: 1215-2415EUR/year**

---

## Support and Troubleshooting

### Common Issues

**App won't start:**
```bash
docker-compose logs streamlit
docker-compose down && docker-compose up -d --build
```

**VPN connectivity:**
```bash
# Check WireGuard status
sudo wg show
# Restart
sudo systemctl restart wg-quick@wg0
```

**Performance issues:**
```bash
# Check resources
docker stats
# Increase limits in docker-compose.yml
```

**Database locked:**
```bash
# Stop app
docker-compose down
# Remove WAL file
rm data/payroll.duckdb.wal
# Restart
docker-compose up -d
```

---

## Next Steps

1. **Week 1:** Server setup, OS hardening
2. **Week 2:** VPN configuration, test remote access
3. **Week 3:** Application deployment, user creation
4. **Week 4:** Backup configuration, monitoring
5. **Week 5:** Load testing with sample data
6. **Week 6:** User training, go-live

**Contact for enterprise support:**
- Setup assistance
- Custom integrations
- SLA support contracts
