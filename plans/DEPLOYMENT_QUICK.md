# Monaco Paie - Déploiement Rapide

## Option 1: VPS avec Docker (Recommandé)

**Hébergeurs RGPD:** OVH, Scaleway, Hetzner (Europe)
**Coût:** 10-30EUR/mois
**Temps:** 30 min

### Prérequis
- VPS Ubuntu 22.04+ (2GB RAM min)
- Domaine (optionnel)
- SSH accès

### Commandes

```bash
# 1. Se connecter au VPS
ssh root@votre-serveur.com

# 2. Installer Docker
curl -fsSL https://get.docker.com | sh
apt install docker-compose -y

# 3. Créer utilisateur
adduser paie
usermod -aG docker paie
su - paie

# 4. Récupérer code
cd ~
git clone https://votre-repo.git monaco_paie
cd monaco_paie

# 5. Certificats SSL
mkdir -p ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/key.pem -out ssl/cert.pem \
  -subj "/C=MC/ST=Monaco/L=Monaco/O=Cabinet/CN=paie.local"

# 6. Authentification
mkdir -p nginx_data
apt install apache2-utils -y
htpasswd -c nginx_data/.htpasswd admin
# Entrer mot de passe

# 7. Pare-feu
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# 8. Lancer
docker-compose -f docker-compose.prod.yml up -d

# 9. Vérifier
docker-compose logs -f
```

### Accès
https://votre-serveur-ip (ou domaine)
Login: admin / mot-de-passe-choisi

---

## Option 2: Machine Locale

**Pour:** Cabinet avec machine dédiée
**Coût:** 0EUR
**Temps:** 5 min

```bash
cd /Users/brych/Documents/Cab_Brych/monaco_paie

# Avec Docker
docker-compose up -d

# OU sans Docker
uv run streamlit run app.py
```

Accès: http://localhost:8501

### Accès réseau local

Modifier `.streamlit/config.toml`:
```toml
[server]
address = "0.0.0.0"
```

Accès: http://192.168.X.X:8501

---

## Sauvegarde Automatique

```bash
# Créer script
cat > backup.sh << 'SCRIPT'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p backups
cp data/payroll.duckdb backups/payroll_$DATE.duckdb
ls -t backups/payroll_*.duckdb | tail -n +31 | xargs rm -f
SCRIPT

chmod +x backup.sh

# Crontab (tous les jours 2h)
crontab -e
# Ajouter: 0 2 * * * /home/paie/monaco_paie/backup.sh
```

---

## Maintenance

```bash
# Logs
docker-compose logs -f

# Stats
docker stats

# Mise à jour
git pull
docker-compose up -d --build

# Restaurer backup
cp backups/payroll_20250119.duckdb data/payroll.duckdb
docker-compose restart
```

---

## Sécurité Checklist

- [ ] SSL actif
- [ ] Auth HTTP basic
- [ ] Pare-feu configuré (80, 443, 22 only)
- [ ] Backups automatiques
- [ ] Mots de passe forts (12+ chars)
- [ ] SSH par clé uniquement
- [ ] VPS en Europe (RGPD)

---

## Dépannage

### App ne démarre pas
```bash
docker-compose logs streamlit
docker-compose down -v
docker-compose up -d --build
```

### Port déjà utilisé
```bash
# Changer port dans docker-compose.yml
ports:
  - "8502:8501"  # au lieu de 8501:8501
```

### DB corrompue
```bash
cp backups/payroll_YYYYMMDD.duckdb data/payroll.duckdb
docker-compose restart
```

---

## Coûts

### VPS
- Starter (2GB): 10EUR/mois
- Standard (4GB): 20EUR/mois

### Domaine
- .com/.fr: 10-15EUR/an
- .mc: 100EUR/an

### Total annuel
- Minimum: 140EUR/an
- Recommandé: 250EUR/an

---

## Support

Logs: `docker-compose logs -f`
Health: `curl http://localhost:8501/_stcore/health`
