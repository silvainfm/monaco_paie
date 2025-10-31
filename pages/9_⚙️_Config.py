"""
Config Page - Configuration (admin only)
"""
import streamlit as st
import polars as pl
import json
import time
import smtplib
import ssl
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.shared_utils import get_payroll_system
from services.auth import AuthManager
from services.email_archive import EmailConfig, EmailConfigManager
from services.payslip_helpers import audit_log_page

CONFIG_DIR = Path("config")

st.set_page_config(page_title="Config", page_icon="⚙️", layout="wide")

st.header("⚙️ Configuration")

if st.session_state.get('role') != 'admin':
    st.error("Accès réservé aux administrateurs")
    st.stop()

system = get_payroll_system()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Entreprise", "Utilisateurs", "Admin", "Configuration Emails", "Log Audit"])

with tab1:
    st.subheader("Informations de l'entreprise")

    with st.form("company_form"):
        name = st.text_input("Nom de l'entreprise", value=system.company_info.get('name', ''))
        siret = st.text_input("SIRET", value=system.company_info.get('siret', ''))
        address = st.text_area("Adresse", value=system.company_info.get('address', ''))
        phone = st.text_input("Téléphone", value=system.company_info.get('phone', ''))
        email = st.text_input("Email", value=system.company_info.get('email', ''))

        st.markdown("---")
        st.markdown("**Déclaration Monaco (DSM)**")
        employer_number_monaco = st.text_input(
            "Numéro d'employeur Monaco",
            value=system.company_info.get('employer_number_monaco', ''),
            help="Numéro d'enregistrement auprès des Caisses Sociales de Monaco (5 chiffres requis)"
        )

        if st.form_submit_button("💾 Sauvegarder"):
            # Validate employer number is 5 digits
            if employer_number_monaco and (not employer_number_monaco.isdigit() or len(employer_number_monaco) != 5):
                st.error("Le numéro d'employeur Monaco doit être exactement 5 chiffres")
            else:
                updated_info = {
                    'name': name,
                    'siret': siret,
                    'address': address,
                    'phone': phone,
                    'email': email,
                    'employer_number_monaco': employer_number_monaco
                }

                config_file = CONFIG_DIR / "company_info.json"
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(updated_info, f, indent=2)

                system.company_info = updated_info
                st.success("Informations mises à jour")

with tab2:
    st.subheader("Gestion des utilisateurs")

    # Use the new AuthManager
    users = AuthManager.list_users()
    if users:
        users_df = pl.DataFrame(users)
        st.dataframe(users_df.select(['username', 'name', 'role']), use_container_width=True)
    else:
        st.info("Aucun utilisateur trouvé")

    # Show security stats
    stats = AuthManager.get_stats()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total utilisateurs", stats.get('total_users', 0))
    with col2:
        st.metric("Administrateurs", stats.get('admin_users', 0))
    with col3:
        st.metric("Comptables", stats.get('comptable_users', 0))

with tab3:
    st.title("Admin • Users")

    # List users
    with st.expander("Current users", expanded=True):
        users = AuthManager.list_users()
        if not users:
            st.info("No users yet.")
        else:
            c1, c2, c3, c4 = st.columns([2, 2, 1, 2])
            c1.markdown("**Username**")
            c2.markdown("**Name**")
            c3.markdown("**Role**")
            c4.markdown("**Created**")
            for u in sorted(users, key=lambda x: x["username"]):
                c1.write(u["username"])
                c2.write(u.get("name", ""))
                c3.write(u.get("role", "comptable"))
                c4.write(u.get("created_at", ""))

    st.divider()

    # Add / reset user
    st.subheader("Ajouter / Réinitialiser un utilisateur")
    with st.form("add_reset_user", clear_on_submit=False):
        username = st.text_input("Nom d'utilisateur")
        name = st.text_input("Nom (facultatif)")
        role = st.selectbox("Rôle", options=["comptable", "admin"])
        password = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Enregistrer / Mettre à jour"):
            if not username or not password:
                st.error("Le nom d'utilisateur et le mot de passe sont requis.")
            else:
                try:
                    AuthManager.add_or_update_user(username, password, role, name)
                    st.success(f"Utilisateur '{username}' enregistré.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    # Remove users
    st.subheader("Supprimer des utilisateurs")
    existing = [u["username"] for u in AuthManager.list_users()]
    sel = st.multiselect("Sélectionner les utilisateurs à supprimer", options=existing)
    if st.button("Supprimer la sélection"):
        if not sel:
            st.warning("Aucun utilisateur sélectionné.")
        else:
            AuthManager.remove_users(sel)
            st.success(f"Supprimé : {', '.join(sel)}")
            st.rerun()

with tab4:
    config_manager = EmailConfigManager(Path("config/email_config.json"))

    # Charger la configuration existante
    existing_config = config_manager.load_config()

    st.info("Configurez les paramètres SMTP pour l'envoi des emails de paie")

    # Preset providers
    col1, col2 = st.columns([2, 1])
    with col1:
        provider = st.selectbox(
            "Fournisseur email",
            ["Gmail", "Outlook", "Office 365", "Autre (personnalisé)"]
        )

    # Default configs based on provider
    defaults = {
        "Gmail": {"server": "smtp.gmail.com", "port": 587, "use_tls": True, "use_ssl": False},
        "Outlook": {"server": "smtp-mail.outlook.com", "port": 587, "use_tls": True, "use_ssl": False},
        "Office 365": {"server": "smtp.office365.com", "port": 587, "use_tls": True, "use_ssl": False},
        "Autre (personnalisé)": {"server": "", "port": 587, "use_tls": True, "use_ssl": False}
    }

    preset = defaults.get(provider, defaults["Autre (personnalisé)"])

    st.markdown("---")

    with st.form("email_config_form"):
        col1, col2 = st.columns(2)

        with col1:
            smtp_server = st.text_input(
                "Serveur SMTP",
                value=existing_config.smtp_server if existing_config else preset["server"],
                help="ex: smtp.gmail.com"
            )

            smtp_port = st.number_input(
                "Port SMTP",
                value=existing_config.smtp_port if existing_config else preset["port"],
                min_value=1,
                max_value=65535
            )

            sender_email = st.text_input(
                "Adresse email expéditeur",
                value=existing_config.sender_email if existing_config else "",
                help="ex: paie@monentreprise.com"
            )

            sender_password = st.text_input(
                "Mot de passe / App Password",
                type="password",
                help="Pour Gmail/Outlook, utilisez un 'App Password' généré"
            )

        with col2:
            sender_name = st.text_input(
                "Nom de l'expéditeur",
                value=existing_config.sender_name if existing_config else "Service Paie",
                help="Nom affiché dans les emails"
            )

            use_tls = st.checkbox(
                "Utiliser TLS (StartTLS)",
                value=existing_config.use_tls if existing_config else preset["use_tls"]
            )

            use_ssl = st.checkbox(
                "Utiliser SSL",
                value=existing_config.use_ssl if existing_config else preset["use_ssl"]
            )

            reply_to = st.text_input(
                "Adresse de réponse (optionnel)",
                value=existing_config.reply_to if existing_config and existing_config.reply_to else ""
            )

            bcc_archive = st.text_input(
                "BCC pour archivage (optionnel)",
                value=existing_config.bcc_archive if existing_config and existing_config.bcc_archive else "",
                help="Copie cachée pour archivage automatique"
            )

        col1, col2, col3 = st.columns([1, 1, 2])

        with col1:
            save_button = st.form_submit_button("💾 Sauvegarder", use_container_width=True)

        with col2:
            test_button = st.form_submit_button("🧪 Tester", use_container_width=True)

    if save_button:
        try:
            # Créer la configuration
            config = EmailConfig(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                sender_email=sender_email,
                sender_password=sender_password or (existing_config.sender_password if existing_config else ""),
                sender_name=sender_name,
                use_tls=use_tls,
                use_ssl=use_ssl,
                reply_to=reply_to if reply_to else None,
                bcc_archive=bcc_archive if bcc_archive else None
            )

            # Sauvegarder
            if config_manager.save_config(config, encrypt_password=True):
                st.success("✅ Configuration sauvegardée avec succès!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Erreur lors de la sauvegarde")

        except Exception as e:
            st.error(f"❌ Erreur: {str(e)}")

    if test_button:
        try:
            # Tester la connexion SMTP
            context = ssl.create_default_context()

            with st.spinner("Test de connexion SMTP..."):
                if use_ssl:
                    server = smtplib.SMTP_SSL(smtp_server, smtp_port, context=context)
                else:
                    server = smtplib.SMTP(smtp_server, smtp_port)
                    if use_tls:
                        server.starttls(context=context)

                server.login(sender_email, sender_password or (existing_config.sender_password if existing_config else ""))
                server.quit()

            st.success("✅ Connexion SMTP réussie!")

        except Exception as e:
            st.error(f"❌ Échec du test: {str(e)}")

    # Afficher la config actuelle
    if existing_config:
        st.markdown("---")
        st.subheader("Configuration actuelle")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Serveur SMTP", f"{existing_config.smtp_server}:{existing_config.smtp_port}")
            st.metric("Expéditeur", existing_config.sender_email)

        with col2:
            st.metric("TLS/SSL", f"TLS: {existing_config.use_tls} | SSL: {existing_config.use_ssl}")
            st.metric("Nom affiché", existing_config.sender_name)

with tab5:
    audit_log_page()
