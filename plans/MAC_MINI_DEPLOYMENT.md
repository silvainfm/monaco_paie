# Mac Mini Server Deployment Guide

Deploy Monaco Payroll on Mac Mini for 10-15 users with remote access.

---

## Hardware Requirements

**Minimum:**
- Mac Mini 2014+ (Intel or M1/M2)
- 8GB RAM (16GB recommended)
- 256GB SSD minimum
- Ethernet connection (not WiFi)
- UPS backup power (recommended)

**Your Mac Mini specs:**
- Check: Apple Menu → About This Mac

---

## Phase 1: Mac Preparation (1-2 hours)

### 1. Clean macOS Install (Optional but Recommended)

```bash
# Backup existing data first
# Then: Recovery Mode → Disk Utility → Erase → Reinstall macOS
```

### 2. System Settings

```bash
# Prevent sleep
sudo pmset -a sleep 0
sudo pmset -a displaysleep 0
sudo pmset -a disksleep 0

# Enable SSH
sudo systemsetup -setremotelogin on

# Set computer name
sudo scutil --set ComputerName "monaco-payroll-server"
sudo scutil --set HostName "monaco-payroll-server"
sudo scutil --set LocalHostName "monaco-payroll-server"

# Disable screen saver
defaults -currentHost write com.apple.screensaver idleTime 0

# Auto-restart after power failure
sudo pmset -a autorestart 1

# Check settings
pmset -g
```

### 3. Network Configuration

**Static IP (Critical):**
1. System Settings → Network → Ethernet → Details
2. TCP/IP tab → Configure IPv4: Using DHCP with manual address
3. Set static IP (e.g., 192.168.1.100)
4. Note: IP, Subnet, Router, DNS

**Router port forwarding (for remote access):**
- Port 443 → Mac Mini IP:443 (HTTPS)
- Port 51820 → Mac Mini IP:51820 (WireGuard VPN)

---

## Phase 2: Install Dependencies (30 min)

### 1. Homebrew

```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Add to PATH (M1/M2 Macs)
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### 2. Docker

```bash
# Install Docker Desktop
brew install --cask docker

# Start Docker (or open Docker.app)
open /Applications/Docker.app

# Wait for Docker to start, then verify
docker --version
docker-compose --version

# Configure Docker to start on boot
# Docker Desktop → Settings → General → Start Docker Desktop when you log in
```

### 3. nginx

```bash
# Install nginx
brew install nginx

# Configure to start on boot
brew services start nginx

# Verify
nginx -v
```

### 4. Python & uv (for development/maintenance)

```bash
# Install Python
brew install python@3.11

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify
python3 --version
uv --version
```

---

## Phase 3: Deploy Application (1 hour)

### 1. Clone/Copy Application

```bash
# Create app directory
sudo mkdir -p /opt/monaco_paie
sudo chown $(whoami) /opt/monaco_paie

# Copy your application files
# Option A: From USB drive
cp -r /Volumes/USB/monaco_paie/* /opt/monaco_paie/

# Option B: From git (if using)
cd /opt/monaco_paie
git clone <your-repo-url> .

# Option C: Already have it locally
cp -r ~/Documents/Cab_Brych/monaco_paie/* /opt/monaco_paie/
```

### 2. Configuration

```bash
cd /opt/monaco_paie

# Create production environment file
cat > .env.production << 'EOF'
# Production settings
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
STREAMLIT_SERVER_MAX_UPLOAD_SIZE=200
STREAMLIT_SERVER_ENABLE_CORS=false
STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true

# Database
DB_PATH=/app/data/payroll.duckdb

# Logging
LOG_LEVEL=INFO
EOF

# Set permissions
chmod 600 .env.production
```

### 3. Docker Setup

```bash
# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  app:
    build: .
    container_name: monaco_paie
    restart: unless-stopped
    ports:
      - "8501:8501"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - STREAMLIT_SERVER_PORT=8501
      - STREAMLIT_SERVER_ADDRESS=0.0.0.0
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G

networks:
  default:
    name: monaco_network
EOF

# Create Dockerfile if not exists
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy application files
COPY . .

# Install Python dependencies
RUN uv pip install --system -r requirements.txt

# Create data directory
RUN mkdir -p /app/data /app/logs

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
EOF

# Build and start
docker-compose build
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs -f
```

### 4. Verify Application

```bash
# Check if running
curl http://localhost:8501

# Access from Mac browser
open http://localhost:8501

# Test login with your credentials
```

---

## Phase 4: nginx Reverse Proxy (30 min)

### 1. SSL Certificate (Let's Encrypt)

```bash
# Install certbot
brew install certbot

# Get domain name first (free options):
# - DuckDNS: https://www.duckdns.org/
# - No-IP: https://www.noip.com/
# Example: monaco-paie.duckdns.org pointing to your public IP

# Generate certificate (replace with your domain)
sudo certbot certonly --standalone \
  -d monaco-paie.duckdns.org \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email

# Certificates will be in:
# /etc/letsencrypt/live/monaco-paie.duckdns.org/
```

### 2. Configure nginx

```bash
# Backup default config
sudo cp /opt/homebrew/etc/nginx/nginx.conf /opt/homebrew/etc/nginx/nginx.conf.backup

# Create new config
sudo tee /opt/homebrew/etc/nginx/nginx.conf > /dev/null << 'EOF'
user nobody;
worker_processes auto;

events {
    worker_connections 1024;
}

http {
    include mime.types;
    default_type application/octet-stream;

    sendfile on;
    keepalive_timeout 65;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=app:10m rate=10r/s;

    # Redirect HTTP to HTTPS
    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name monaco-paie.duckdns.org;  # Change to your domain

        ssl_certificate /etc/letsencrypt/live/monaco-paie.duckdns.org/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/monaco-paie.duckdns.org/privkey.pem;

        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        client_max_body_size 200M;

        # Rate limiting
        limit_req zone=app burst=20 nodelay;

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

        location /_stcore/stream {
            proxy_pass http://localhost:8501/_stcore/stream;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_read_timeout 86400;
        }
    }
}
EOF

# Test config
sudo nginx -t

# Restart nginx
sudo brew services restart nginx

# Check status
sudo brew services list
```

---

## Phase 5: VPN for Remote Access (1 hour)

### Option A: Tailscale (Easiest)

```bash
# Install Tailscale
brew install --cask tailscale

# Open Tailscale and sign in
open /Applications/Tailscale.app

# Enable on startup
# Tailscale menu bar → Preferences → Launch at login

# Get your Tailscale IP
tailscale ip -4

# On remote computers:
# 1. Install Tailscale
# 2. Sign in with same account
# 3. Access: https://<tailscale-ip>:8501
```

### Option B: WireGuard (More Control)

```bash
# Install WireGuard
brew install wireguard-tools

# Generate server keys
cd /opt/homebrew/etc/wireguard
umask 077
wg genkey | tee server_private.key | wg pubkey > server_public.key

# Create server config
sudo tee /opt/homebrew/etc/wireguard/wg0.conf > /dev/null << 'EOF'
[Interface]
Address = 10.0.0.1/24
ListenPort = 51820
PrivateKey = <paste server_private.key contents>
PostUp = pfctl -E
PostDown = pfctl -d

# Client 1
[Peer]
PublicKey = <client1_public_key>
AllowedIPs = 10.0.0.2/32

# Client 2
[Peer]
PublicKey = <client2_public_key>
AllowedIPs = 10.0.0.3/32
EOF

# Start WireGuard
sudo wg-quick up wg0

# Enable on boot (create LaunchDaemon)
sudo tee /Library/LaunchDaemons/com.wireguard.wg0.plist > /dev/null << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.wireguard.wg0</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/wg-quick</string>
        <string>up</string>
        <string>wg0</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF

sudo launchctl load /Library/LaunchDaemons/com.wireguard.wg0.plist
```

**Client Configuration (WireGuard):**

```bash
# Generate client keys (on client machine or server)
wg genkey | tee client1_private.key | wg pubkey > client1_public.key

# Create client config file (client1.conf)
[Interface]
Address = 10.0.0.2/32
PrivateKey = <client1_private.key>
DNS = 1.1.1.1

[Peer]
PublicKey = <server_public.key>
Endpoint = <your-public-ip>:51820
AllowedIPs = 10.0.0.0/24, 192.168.1.0/24
PersistentKeepalive = 25

# Import into WireGuard app on client device
# Access app via: https://192.168.1.100 (or Tailscale IP)
```

---

## Phase 6: Automated Backups (30 min)

### 1. Local Backup Script

```bash
# Create backup script
sudo tee /opt/monaco_paie/backup.sh > /dev/null << 'EOF'
#!/bin/bash
set -e

# Configuration
BACKUP_DIR="/Volumes/Backup/monaco_paie"  # External drive
APP_DIR="/opt/monaco_paie"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database and config
tar -czf "$BACKUP_DIR/backup_$DATE.tar.gz" \
    "$APP_DIR/data/" \
    "$APP_DIR/data/config/"

# Remove old backups
find "$BACKUP_DIR" -name "backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Log
echo "[$DATE] Backup completed: backup_$DATE.tar.gz"
EOF

chmod +x /opt/monaco_paie/backup.sh

# Test backup
/opt/monaco_paie/backup.sh
```

### 2. Schedule with cron

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /opt/monaco_paie/backup.sh >> /opt/monaco_paie/logs/backup.log 2>&1
```

### 3. Cloud Backup (Optional)

```bash
# Install rclone for cloud sync
brew install rclone

# Configure (follow prompts)
rclone config

# Example: Sync to Google Drive
rclone sync /opt/monaco_paie/data/ gdrive:monaco_paie_backup/ \
    --exclude "*.wal" \
    --exclude "*.log" \
    --log-file=/opt/monaco_paie/logs/rclone.log
```

---

## Phase 7: Monitoring (30 min)

### 1. Health Check Script

```bash
# Create health check
sudo tee /opt/monaco_paie/health_check.sh > /dev/null << 'EOF'
#!/bin/bash

# Check Docker container
if ! docker ps | grep -q monaco_paie; then
    echo "ALERT: Monaco Paie container is down!"
    docker-compose -f /opt/monaco_paie/docker-compose.yml up -d
fi

# Check nginx
if ! pgrep nginx > /dev/null; then
    echo "ALERT: nginx is down!"
    sudo brew services restart nginx
fi

# Check disk space
USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $USAGE -gt 80 ]; then
    echo "ALERT: Disk usage is ${USAGE}%"
fi

# Check memory
MEMORY=$(vm_stat | grep "Pages free" | awk '{print $3}' | sed 's/\.//')
if [ $MEMORY -lt 100000 ]; then
    echo "ALERT: Low memory"
fi
EOF

chmod +x /opt/monaco_paie/health_check.sh

# Schedule every 5 minutes
crontab -e
# Add:
*/5 * * * * /opt/monaco_paie/health_check.sh >> /opt/monaco_paie/logs/health.log 2>&1
```

### 2. Log Rotation

```bash
# Create log rotation script
sudo tee /opt/monaco_paie/rotate_logs.sh > /dev/null << 'EOF'
#!/bin/bash
LOG_DIR="/opt/monaco_paie/logs"
find $LOG_DIR -name "*.log" -size +100M -exec gzip {} \;
find $LOG_DIR -name "*.log.gz" -mtime +30 -delete
EOF

chmod +x /opt/monaco_paie/rotate_logs.sh

# Weekly rotation
crontab -e
# Add:
0 0 * * 0 /opt/monaco_paie/rotate_logs.sh
```

---

## Phase 8: Security Hardening (30 min)

### 1. Firewall

```bash
# Enable macOS firewall
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on

# Allow specific services
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /opt/homebrew/bin/nginx
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /Applications/Docker.app/Contents/MacOS/Docker

# Check status
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
```

### 2. Fail2ban Alternative

```bash
# Install denyhosts
brew install denyhosts

# Configure
sudo cp /opt/homebrew/etc/denyhosts.conf /opt/homebrew/etc/denyhosts.conf.backup

# Edit config
sudo nano /opt/homebrew/etc/denyhosts.conf
# Set: SECURE_LOG = /var/log/system.log
# Set: DENY_THRESHOLD_ROOT = 3

# Start service
sudo brew services start denyhosts
```

### 3. Auto-Updates

```bash
# Enable automatic security updates
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled -bool true
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticDownload -bool true
sudo defaults write /Library/Preferences/com.apple.commerce AutoUpdate -bool true
```

---

## Phase 9: Startup Script (15 min)

Create script to ensure everything starts on boot/restart:

```bash
# Create startup script
sudo tee /opt/monaco_paie/startup.sh > /dev/null << 'EOF'
#!/bin/bash
set -e

echo "Starting Monaco Payroll System..."

# Wait for network
sleep 10

# Start Docker (if not running)
if ! docker info > /dev/null 2>&1; then
    open -a Docker
    sleep 30
fi

# Start application
cd /opt/monaco_paie
docker-compose up -d

# Start nginx (if not running)
if ! pgrep nginx > /dev/null; then
    sudo brew services start nginx
fi

echo "Monaco Payroll System started successfully"
EOF

chmod +x /opt/monaco_paie/startup.sh

# Create LaunchDaemon
sudo tee /Library/LaunchDaemons/com.monaco.payroll.plist > /dev/null << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.monaco.payroll</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/monaco_paie/startup.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/opt/monaco_paie/logs/startup.log</string>
    <key>StandardErrorPath</key>
    <string>/opt/monaco_paie/logs/startup_error.log</string>
</dict>
</plist>
EOF

sudo launchctl load /Library/LaunchDaemons/com.monaco.payroll.plist
```

---

## Testing & Go-Live

### 1. Local Testing

```bash
# Access locally
http://192.168.1.100:8501
https://192.168.1.100

# Check logs
docker-compose logs -f
tail -f /opt/homebrew/var/log/nginx/access.log
tail -f /opt/homebrew/var/log/nginx/error.log
```

### 2. Remote Testing

```bash
# VPN connection test
# Tailscale: https://<tailscale-ip>:8501
# WireGuard: https://192.168.1.100 (via VPN)

# Test from remote device:
# 1. Connect VPN
# 2. Open browser
# 3. Navigate to server IP
# 4. Login and test workflow
```

### 3. Load Testing

```bash
# Install load testing tool
brew install apache-bench

# Test concurrent users
ab -n 100 -c 10 http://localhost:8501/

# Monitor resources during test
docker stats
htop
```

---

## Daily Operations

### Start/Stop

```bash
# Stop
cd /opt/monaco_paie
docker-compose down

# Start
docker-compose up -d

# Restart
docker-compose restart

# View logs
docker-compose logs -f
```

### Updates

```bash
# Pull latest code
cd /opt/monaco_paie
git pull  # or copy new files

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# Verify
docker-compose ps
```

### Backup Management

```bash
# Manual backup
/opt/monaco_paie/backup.sh

# Restore from backup
cd /opt/monaco_paie
docker-compose down
tar -xzf /Volumes/Backup/monaco_paie/backup_20250115_020000.tar.gz -C /
docker-compose up -d
```

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs

# Rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Can't access remotely

```bash
# Check VPN
tailscale status  # or
sudo wg show

# Check nginx
sudo nginx -t
sudo brew services restart nginx

# Check port forwarding on router
# Ensure ports 443 and 51820 forwarded

# Check firewall
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --listapps
```

### Performance issues

```bash
# Check resources
docker stats
htop

# Check disk space
df -h

# Optimize Docker
docker system prune -a

# Increase Docker memory
# Docker Desktop → Settings → Resources → Memory: 8GB
```

### Database corruption

```bash
# Stop app
docker-compose down

# Check WAL file
cd /opt/monaco_paie/data
ls -lh payroll.duckdb*

# Remove WAL if corrupted
rm payroll.duckdb.wal

# Restore from backup if needed
tar -xzf /Volumes/Backup/monaco_paie/backup_latest.tar.gz

# Restart
docker-compose up -d
```

---

## Maintenance Schedule

**Daily:**
- Automated backups (2 AM)
- Health checks (every 5 min)

**Weekly:**
- Review logs
- Check disk space
- Test remote access

**Monthly:**
- Update macOS security patches
- Update Docker images
- Test backup restore
- Review user activity logs

**Quarterly:**
- Full system backup to external drive
- Review security settings
- Update documentation

---

## Cost Summary

**Hardware:**
- Mac Mini (reusing old): 0€
- External HDD (backup): 50€
- UPS (optional): 150€
- Total: 50-200€

**Annual:**
- Internet (existing): 0€
- Domain (DuckDNS): 0€
- Electricity (~20W 24/7): ~35€/year
- Total: ~35€/year

**Total 5-year cost: 200 + (35 × 5) = 375€**

Compare to:
- Cloud hosting: ~9000€
- Professional server: ~10000€

---

## Quick Reference Commands

```bash
# Application
cd /opt/monaco_paie
docker-compose up -d          # Start
docker-compose down           # Stop
docker-compose restart        # Restart
docker-compose logs -f        # View logs

# nginx
sudo brew services start nginx
sudo brew services stop nginx
sudo brew services restart nginx
sudo nginx -t                 # Test config

# Backup
/opt/monaco_paie/backup.sh    # Manual backup

# Monitoring
docker stats                  # Container resources
docker-compose ps            # Container status
htop                         # System resources
df -h                        # Disk space

# VPN
tailscale status             # Tailscale
sudo wg show                 # WireGuard

# Logs
tail -f /opt/monaco_paie/logs/*.log
tail -f /opt/homebrew/var/log/nginx/*.log
```

---

## Security Checklist

- [ ] Static IP configured
- [ ] Router port forwarding setup
- [ ] SSL certificate installed
- [ ] nginx HTTPS configured
- [ ] VPN setup and tested
- [ ] Firewall enabled
- [ ] Auto-updates enabled
- [ ] Automated backups working
- [ ] External backup drive connected
- [ ] Strong user passwords
- [ ] SSH key-only access (optional)
- [ ] fail2ban/denyhosts configured

---

## Next Steps

1. **Test locally** - Access from office network
2. **Setup VPN** - Test remote access from home
3. **Train users** - Show how to connect via VPN
4. **Monitor for 1 week** - Check logs, performance
5. **Document issues** - Keep maintenance log
6. **Go live** - Migrate production data

Your Mac Mini is now a production payroll server for 10-15 users with secure remote access.
