# Monaco Paie - Guide de Déploiement

## Options de Déploiement

### Option 1: Docker sur VPS (Recommandé)
**Hébergeurs RGPD-conformes:** OVH, Scaleway, Hetzner (Europe)
**Coût:** ~10-30€/mois
**Difficulté:** Moyenne

### Option 2: Machine Locale (Cabinet)
**Hébergement:** Serveur/PC dans le cabinet
**Coût:** 0€
**Difficulté:** Facile

### Option 3: Serveur Dédié
**Pour:** Cabinets avec >100 clients
**Coût:** 50-200€/mois
**Difficulté:** Élevée

---

## Déploiement Docker sur VPS (Recommandé)

### Prérequis
- VPS Ubuntu 22.04+ (2GB RAM, 20GB stockage minimum)
- Nom de domaine (optionnel mais recommandé)
- SSH accès root

### 1. Préparer le VPS

```bash
# Se connecter au VPS
ssh root@votre-serveur.com

# Mettre à jour le système
apt update && apt upgrade -y

# Installer Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Installer Docker Compose
apt install docker-compose -y

# Créer un utilisateur non-root
adduser paie
usermod -aG docker paie
su - paie
```

### 2. Transférer l'Application

```bash
# Sur votre machine locale
rsync -avz --exclude 'data/' --exclude '.venv/' \
  /Users/brych/Documents/Cab_Brych/monaco_paie/ \
  paie@votre-serveur.com:~/monaco_paie/
```

Ou via Git:
```bash
# Sur le VPS
git clone https://votre-repo.git monaco_paie
cd monaco_paie
```

### 3. Configuration SSL

**Option A: Let's Encrypt (Gratuit)**
```bash
# Installer certbot
apt install certbot -y

# Générer certificat
certbot certonly --standalone -d votre-domaine.com

# Créer liens vers certificats
mkdir -p ssl
ln -s /etc/letsencrypt/live/votre-domaine.com/fullchain.pem ssl/cert.pem
ln -s /etc/letsencrypt/live/votre-domaine.com/privkey.pem ssl/key.pem
```

**Option B: Certificat Auto-signé (Dev/Test)**
```bash
mkdir -p ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/key.pem -out ssl/cert.pem \
  -subj "/C=MC/ST=Monaco/L=Monaco/O=Cabinet/CN=paie.local"
```

### 4. Configurer l'Authentification

```bash
# Créer fichier de mots de passe
apt install apache2-utils -y
htpasswd -c .htpasswd comptable1
# Entrer le mot de passe quand demandé

# Ajouter d'autres utilisateurs
htpasswd .htpasswd comptable2
htpasswd .htpasswd admin

# Copier dans le volume nginx
mkdir -p nginx_data
cp .htpasswd nginx_data/
```

Mettre à jour `nginx.conf`:
```nginx
auth_basic_user_file /etc/nginx/.htpasswd;
```

Et dans `docker-compose.prod.yml`, ajouter:
```yaml
volumes:
  - ./nginx_data/.htpasswd:/etc/nginx/.htpasswd:ro
```

### 5. Configurer le Pare-feu

```bash
# UFW (Ubuntu)
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable

# Vérifier
ufw status
```

### 6. Lancer l'Application

```bash
cd ~/monaco_paie

# Build et lancer
docker-compose -f docker-compose.prod.yml up -d

# Vérifier les logs
docker-compose -f docker-compose.prod.yml logs -f

# Vérifier le statut
docker-compose -f docker-compose.prod.yml ps
```

### 7. Accéder à l'Application

Ouvrir navigateur: `https://votre-domaine.com`

Login avec identifiants créés à l'étape 4.

---

## Déploiement Machine Locale (Cabinet)

**Idéal pour:** Accès local uniquement, pas d'accès distant

### 1. Installation Simple

```bash
# Dans le dossier du projet
cd /Users/brych/Documents/Cab_Brych/monaco_paie

# Lancer avec Docker
docker-compose up -d

# Ou sans Docker
uv run streamlit run app.py
```

### 2. Accès

Ouvrir: `http://localhost:8501`

### 3. Rendre Accessible sur Réseau Local

Modifier `.streamlit/config.toml`:
```toml
[server]
address = "0.0.0.0"  # Au lieu de localhost
port = 8501
```

Accès depuis autres PC: `http://192.168.X.X:8501`

### 4. Sécuriser avec VPN

Si accès distant nécessaire:
- Installer Tailscale (gratuit, facile): https://tailscale.com
- Ou WireGuard pour plus de contrôle

---

## Maintenance

### Sauvegardes Automatiques

```bash
# Créer script de backup
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/app/backups"
mkdir -p $BACKUP_DIR

# Backup DuckDB
cp /app/data/payroll.duckdb $BACKUP_DIR/payroll_$DATE.duckdb

# Garder seulement les 30 derniers backups
cd $BACKUP_DIR
ls -t payroll_*.duckdb | tail -n +31 | xargs rm -f
EOF

chmod +x backup.sh

# Ajouter au crontab (tous les jours à 2h)
crontab -e
# Ajouter: 0 2 * * * /home/paie/monaco_paie/backup.sh
```

### Mises à Jour

```bash
cd ~/monaco_paie

# Arrêter l'application
docker-compose -f docker-compose.prod.yml down

# Récupérer dernières modifications
git pull

# Reconstruire et relancer
docker-compose -f docker-compose.prod.yml up -d --build

# Vérifier
docker-compose -f docker-compose.prod.yml logs -f
```

### Monitoring

```bash
# Logs en temps réel
docker-compose -f docker-compose.prod.yml logs -f streamlit

# Stats ressources
docker stats monaco_paie

# Santé de l'application
curl http://localhost:8501/_stcore/health
```

---

## Sécurité - Checklist

- [ ] SSL/HTTPS activé
- [ ] Authentification HTTP Basic configurée
- [ ] Pare-feu configuré (ports 80, 443, 22 seulement)
- [ ] Sauvegardes automatiques actives
- [ ] Mots de passe forts (min 12 caractères)
- [ ] Accès SSH par clé (désactiver password)
- [ ] Logs régulièrement vérifiés
- [ ] VPS en Europe (RGPD)
- [ ] Fail2ban installé (optionnel)

### Configuration Fail2ban (Optionnel)

```bash
apt install fail2ban -y

# Configurer pour nginx
cat > /etc/fail2ban/jail.local << 'EOF'
[nginx-limit-req]
enabled = true
filter = nginx-limit-req
logpath = /var/log/nginx/error.log
maxretry = 5
findtime = 600
bantime = 3600
EOF

systemctl restart fail2ban
```

---

## Dépannage

### L'application ne démarre pas
```bash
# Vérifier les logs
docker-compose logs streamlit

# Vérifier les ports
netstat -tulpn | grep 8501

# Reconstruire from scratch
docker-compose down -v
docker-compose up -d --build
```

### Problèmes de performance
```bash
# Augmenter ressources dans docker-compose.prod.yml
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 4G
```

### Base de données corrompue
```bash
# Restaurer depuis backup
cp /app/backups/payroll_YYYYMMDD.duckdb /app/data/payroll.duckdb
docker-compose restart
```

---

## Coûts Estimés

### VPS (OVH, Scaleway, Hetzner)
- **Starter:** 2GB RAM, 20GB SSD → ~10€/mois
- **Standard:** 4GB RAM, 40GB SSD → ~15-20€/mois
- **Pro:** 8GB RAM, 80GB SSD → ~30-40€/mois

### Nom de Domaine
- .com / .fr → ~10-15€/an
- .mc (Monaco) → ~100€/an

### Total Annuel
- **Minimum:** ~140€/an (VPS starter + .fr)
- **Recommandé:** ~250€/an (VPS standard + .fr + backups)

---

## Support

Pour questions:
1. Vérifier logs: `docker-compose logs`
2. Consulter ce guide
3. GitHub Issues si projet open source
