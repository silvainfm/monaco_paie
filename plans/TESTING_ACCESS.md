# Monaco Payroll - Testing Access Instructions

## Status: Running in Docker

The application is now running in a Docker container and accessible on your local network.

---

## Access URLs

### Local (on this Mac):
```
http://localhost:8501
```

### Network (from other devices on same WiFi):
```
http://192.168.1.166:8501
```

---

## For Your Administrator to Test

Send them this URL:
**http://192.168.1.166:8501**

**Requirements:**
- Must be on the same WiFi network as your Mac
- Your Mac must stay on during testing
- Port 8501 must not be blocked by firewall

---

## Test Login Credentials

Use the credentials defined in your `services/auth.py` file.

Default users (check auth.py for actual credentials):
- **Admin**: Full access
- **Comptable**: Regular user access

---

## Docker Commands

### Check status:
```bash
docker ps
```

### View logs:
```bash
docker logs monaco_paie -f
```

### Stop application:
```bash
docker-compose down
```

### Restart application:
```bash
docker-compose restart
```

### Start application (if stopped):
```bash
docker-compose up -d
```

---

## Troubleshooting

### Admin can't access the URL:

1. **Check if container is running:**
   ```bash
   docker ps | grep monaco_paie
   ```

2. **Check Mac firewall:**
   - System Settings → Network → Firewall
   - Allow incoming connections on port 8501

3. **Check if admin is on same network:**
   - Admin's device must be on same WiFi as your Mac

4. **Test from your Mac first:**
   ```bash
   curl http://localhost:8501
   ```

### Container won't start:

```bash
# Check logs
docker logs monaco_paie

# Rebuild if needed
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Port 8501 already in use:

```bash
# Find what's using the port
lsof -i :8501

# Kill the process or change port in docker-compose.yml
```

---

## Data Persistence

Data is stored in:
```
./data/payroll.duckdb
./data/config/
```

These folders are mounted into the container, so data persists even if you restart/rebuild the container.

---

## Production Deployment

Once testing is complete, follow `MAC_MINI_DEPLOYMENT.md` for permanent production setup with:
- VPN for secure remote access
- Automated backups
- Monitoring
- Auto-restart on reboot

---

## Quick Commands Reference

```bash
# Status
docker ps

# Logs (live)
docker logs -f monaco_paie

# Stop
docker-compose down

# Start
docker-compose up -d

# Restart
docker-compose restart

# Rebuild
docker-compose build
docker-compose up -d

# Remove everything and start fresh
docker-compose down
docker system prune -a
docker-compose up -d --build
```

---

## Network Info

**Your Mac IP:** 192.168.1.166
**Container Port:** 8501
**Container Status:** Running ✓

Application accessible at: **http://192.168.1.166:8501**
