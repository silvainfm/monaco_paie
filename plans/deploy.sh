#!/bin/bash
set -e

echo "Monaco Paie - Déploiement"
echo "=========================="

# Check Docker is installed
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker non installé. Installer d'abord:"
    echo "   curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# Check docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo "ERROR: Docker Compose non installé."
    exit 1
fi

# Ask for deployment type
echo ""
echo "Type de déploiement:"
echo "1) Développement (local, port 8501)"
echo "2) Production (nginx, SSL, auth)"
read -p "Choix [1/2]: " choice

case $choice in
    1)
        echo ""
        echo "Déploiement développement..."
        docker-compose up -d
        echo ""
        echo "OK - Application démarrée"
        echo "   Accès: http://localhost:8501"
        ;;
    2)
        echo ""
        echo "Déploiement production..."
        
        # Check SSL certificates
        if [ ! -f "ssl/cert.pem" ] || [ ! -f "ssl/key.pem" ]; then
            echo "WARN: Certificats SSL non trouvés"
            read -p "Générer certificat auto-signé? [y/n]: " gen_ssl
            if [ "$gen_ssl" = "y" ]; then
                mkdir -p ssl
                openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                    -keyout ssl/key.pem -out ssl/cert.pem \
                    -subj "/C=MC/ST=Monaco/L=Monaco/O=Cabinet/CN=paie.local"
                echo "OK - Certificat auto-signé créé"
            fi
        fi
        
        # Check .htpasswd
        if [ ! -f "nginx_data/.htpasswd" ]; then
            echo ""
            echo "WARN: Fichier auth non trouvé"
            read -p "Créer utilisateur admin? [y/n]: " create_user
            if [ "$create_user" = "y" ]; then
                mkdir -p nginx_data
                if command -v htpasswd &> /dev/null; then
                    read -p "Nom utilisateur: " username
                    htpasswd -c nginx_data/.htpasswd "$username"
                else
                    echo "ERROR: htpasswd non installé"
                    echo "   apt install apache2-utils  # Ubuntu/Debian"
                    echo "   brew install httpd          # macOS"
                    exit 1
                fi
            else
                echo "ERROR: Auth requise pour production"
                exit 1
            fi
        fi
        
        docker-compose -f docker-compose.prod.yml up -d --build
        echo ""
        echo "OK - Application production démarrée"
        echo "   Accès HTTPS: https://votre-domaine.com"
        ;;
    *)
        echo "ERROR: Choix invalide"
        exit 1
        ;;
esac

echo ""
echo "Vérifier logs:"
echo "   docker-compose logs -f"
echo ""
echo "Arrêter:"
echo "   docker-compose down"
