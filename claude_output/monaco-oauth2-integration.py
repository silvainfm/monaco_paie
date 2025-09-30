class Microsoft365EmailManager:
    """Unified email manager for Microsoft 365 with OAuth2 and SMTP fallback"""
    
    def __init__(self, config_dir: Path = Path("config")):
        self.config = OAuth2Config(config_dir)
        self.service = Microsoft365Service(self.config)
        self.use_graph_api = True  # Prefer Graph API over SMTP
    
    def configure(self, tenant_id: str, client_id: str, client_secret: str,
                 smtp_server: str = "smtp.office365.com", smtp_port: int = 587,
                 smtp_username: str = "", smtp_password: str = "") -> bool:
        """
        Configure both OAuth2 and SMTP fallback
        
        Args:
            tenant_id: Azure AD tenant ID (use 'common' for multi-tenant)
            client_id: Application ID from Azure portal
            client_secret: Client secret value
            smtp_server: SMTP server (default: smtp.office365.com)
            smtp_port: SMTP port (default: 587)
            smtp_username: SMTP username (usually email address)
            smtp_password: SMTP password or app password
        """
        # Save OAuth2 configuration
        oauth_success = self.config.save_"""
OAuth2 Integration Module for Monaco Payroll System - Microsoft 365 Focus
==========================================================================
Provides OAuth2 authentication primarily for Microsoft 365 with SMTP fallback
"""

import os
import json
import base64
import logging
from pathlib import Path
from typing import Dict, Optional, Union, List, Tuple
from datetime import datetime, timedelta
import pickle
import time

# OAuth2 and email libraries
import streamlit as st
import msal
import requests

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

logger = logging.getLogger(__name__)


class OAuth2Config:
    """OAuth2 Configuration Manager - Microsoft 365 Focused"""
    
    # Microsoft OAuth2 endpoints
    MICROSOFT_AUTHORITY = 'https://login.microsoftonline.com/{tenant}'
    MICROSOFT_SCOPES = [
        'https://graph.microsoft.com/Mail.Send',
        'https://graph.microsoft.com/Mail.ReadWrite',
        'https://graph.microsoft.com/User.Read'
    ]
    
    # Common Microsoft 365 tenant IDs
    TENANT_COMMON = 'common'  # Multi-tenant
    TENANT_ORGANIZATIONS = 'organizations'  # Work/School accounts only
    TENANT_CONSUMERS = 'consumers'  # Personal accounts only
    
    def __init__(self, config_dir: Path = Path("config")):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.microsoft_config_file = self.config_dir / "microsoft_oauth.json"
        self.token_cache_file = self.config_dir / "token_cache.json"
        self.smtp_config_file = self.config_dir / "smtp_fallback.json"
    
    def save_microsoft_config(self, tenant_id: str, client_id: str, 
                            client_secret: str, use_certificate: bool = False,
                            certificate_thumbprint: str = "") -> bool:
        """
        Save Microsoft 365 OAuth2 configuration
        
        Args:
            tenant_id: Azure AD tenant ID or 'common'/'organizations'
            client_id: Application (client) ID
            client_secret: Client secret value
            use_certificate: Use certificate authentication instead of secret
            certificate_thumbprint: Certificate thumbprint if using cert auth
        """
        try:
            config = {
                "tenant_id": tenant_id,
                "client_id": client_id,
                "client_secret": client_secret if not use_certificate else "",
                "authority": self.MICROSOFT_AUTHORITY.format(tenant=tenant_id),
                "use_certificate": use_certificate,
                "certificate_thumbprint": certificate_thumbprint,
                "redirect_uri": "http://localhost:8501/callback",
                "scopes": self.MICROSOFT_SCOPES
            }
            
            with open(self.microsoft_config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info("Microsoft 365 OAuth2 configuration saved")
            return True
            
        except Exception as e:
            logger.error(f"Error saving Microsoft config: {e}")
            return False
    
    def save_smtp_fallback(self, smtp_server: str, smtp_port: int,
                          username: str, password: str, use_tls: bool = True) -> bool:
        """Save SMTP fallback configuration for Microsoft 365"""
        try:
            config = {
                "smtp_server": smtp_server,
                "smtp_port": smtp_port,
                "username": username,
                "password": base64.b64encode(password.encode()).decode(),  # Basic encoding
                "use_tls": use_tls
            }
            
            with open(self.smtp_config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info("SMTP fallback configuration saved")
            return True
            
        except Exception as e:
            logger.error(f"Error saving SMTP config: {e}")
            return False
    
    def load_microsoft_config(self) -> Optional[Dict]:
        """Load Microsoft OAuth2 configuration"""
        if self.microsoft_config_file.exists():
            with open(self.microsoft_config_file, 'r') as f:
                return json.load(f)
        return None
    
    def load_smtp_config(self) -> Optional[Dict]:
        """Load SMTP fallback configuration"""
        if self.smtp_config_file.exists():
            with open(self.smtp_config_file, 'r') as f:
                config = json.load(f)
                # Decode password
                if 'password' in config:
                    config['password'] = base64.b64decode(config['password']).decode()
                return config
        return None


class Microsoft365Service:
    """Microsoft 365 OAuth2 Service with Graph API and SMTP fallback"""
    
    def __init__(self, config: OAuth2Config):
        self.config = config
        self.app = None
        self.token_cache = msal.SerializableTokenCache()
        self._load_token_cache()
    
    def _load_token_cache(self):
        """Load token cache from file"""
        if self.config.token_cache_file.exists():
            with open(self.config.token_cache_file, 'r') as f:
                self.token_cache.deserialize(f.read())
    
    def _save_token_cache(self):
        """Save token cache to file"""
        if self.token_cache.has_state_changed:
            with open(self.config.token_cache_file, 'w') as f:
                f.write(self.token_cache.serialize())
    
    def initialize_app(self) -> bool:
        """Initialize MSAL confidential client application"""
        try:
            config_data = self.config.load_microsoft_config()
            if not config_data:
                logger.error("Microsoft 365 configuration not found")
                return False
            
            # Create MSAL app with token cache
            if config_data.get('use_certificate'):
                # Certificate-based authentication (more secure for production)
                self.app = msal.ConfidentialClientApplication(
                    config_data['client_id'],
                    authority=config_data['authority'],
                    client_certificate={
                        "thumbprint": config_data['certificate_thumbprint'],
                        "private_key": self._load_certificate_key()
                    },
                    token_cache=self.token_cache
                )
            else:
                # Client secret authentication
                self.app = msal.ConfidentialClientApplication(
                    config_data['client_id'],
                    authority=config_data['authority'],
                    client_credential=config_data['client_secret'],
                    token_cache=self.token_cache
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing MSAL app: {e}")
            return False
    
    def _load_certificate_key(self) -> str:
        """Load certificate private key for certificate-based auth"""
        cert_file = self.config.config_dir / "certificate.pem"
        if cert_file.exists():
            with open(cert_file, 'r') as f:
                return f.read()
        return ""
    
    def get_auth_url(self, state: Optional[str] = None) -> Optional[str]:
        """Get Microsoft 365 OAuth2 authorization URL"""
        try:
            if not self.app:
                if not self.initialize_app():
                    return None
            
            config_data = self.config.load_microsoft_config()
            
            auth_url = self.app.get_authorization_request_url(
                scopes=config_data['scopes'],
                state=state or str(datetime.now().timestamp()),
                redirect_uri=config_data['redirect_uri'],
                prompt='select_account'  # Always show account selection
            )
            
            return auth_url
            
        except Exception as e:
            logger.error(f"Error generating Microsoft auth URL: {e}")
            return None
    
    def acquire_token_by_auth_code(self, auth_code: str) -> Optional[Dict]:
        """Exchange authorization code for access token"""
        try:
            if not self.app:
                if not self.initialize_app():
                    return None
            
            config_data = self.config.load_microsoft_config()
            
            result = self.app.acquire_token_by_authorization_code(
                auth_code,
                scopes=config_data['scopes'],
                redirect_uri=config_data['redirect_uri']
            )
            
            if "access_token" in result:
                self._save_token_cache()
                logger.info("Successfully acquired Microsoft 365 token")
                return result
            else:
                logger.error(f"Failed to acquire token: {result.get('error_description', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error acquiring token: {e}")
            return None
    
    def get_token_silent(self) -> Optional[Dict]:
        """Get token silently from cache or refresh if needed"""
        try:
            if not self.app:
                if not self.initialize_app():
                    return None
            
            config_data = self.config.load_microsoft_config()
            accounts = self.app.get_accounts()
            
            if accounts:
                # Try to get token silently for the first account
                result = self.app.acquire_token_silent(
                    config_data['scopes'],
                    account=accounts[0]
                )
                
                if result and "access_token" in result:
                    return result
            
            # If no cached token, return None (user needs to authenticate)
            return None
            
        except Exception as e:
            logger.error(f"Error getting token silently: {e}")
            return None
    
    def send_email_graph_api(self, to_email: str, subject: str, body_html: str,
                            attachments: Optional[List[Tuple[str, bytes]]] = None,
                            cc: Optional[List[str]] = None,
                            bcc: Optional[List[str]] = None,
                            importance: str = "normal") -> bool:
        """
        Send email via Microsoft Graph API
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body_html: HTML body content
            attachments: List of (filename, content_bytes) tuples
            cc: List of CC recipients
            bcc: List of BCC recipients
            importance: "low", "normal", or "high"
        """
        try:
            # Get access token
            token_response = self.get_token_silent()
            if not token_response:
                logger.error("No valid token available. User needs to authenticate.")
                return False
            
            access_token = token_response['access_token']
            
            # Prepare message
            message = {
                "subject": subject,
                "importance": importance,
                "body": {
                    "contentType": "HTML",
                    "content": body_html
                },
                "toRecipients": [
                    {"emailAddress": {"address": to_email}}
                ]
            }
            
            # Add CC recipients
            if cc:
                message["ccRecipients"] = [
                    {"emailAddress": {"address": email}} for email in cc
                ]
            
            # Add BCC recipients
            if bcc:
                message["bccRecipients"] = [
                    {"emailAddress": {"address": email}} for email in bcc
                ]
            
            # Add attachments
            if attachments:
                message["attachments"] = []
                for filename, content in attachments:
                    # For large attachments (>3MB), should use upload session
                    if len(content) > 3 * 1024 * 1024:
                        logger.warning(f"Large attachment {filename} may fail. Consider using upload session.")
                    
                    attachment = {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": filename,
                        "contentType": "application/octet-stream",
                        "contentBytes": base64.b64encode(content).decode('utf-8')
                    }
                    message["attachments"].append(attachment)
            
            # Send email
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                'https://graph.microsoft.com/v1.0/me/sendMail',
                headers=headers,
                json={"message": message, "saveToSentItems": True}
            )
            
            if response.status_code == 202:
                logger.info(f"Email sent successfully to {to_email}")
                return True
            else:
                logger.error(f"Failed to send email. Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email via Graph API: {e}")
            return False
    
    def send_email_smtp_fallback(self, to_email: str, subject: str, body_html: str,
                                attachments: Optional[List[Tuple[str, bytes]]] = None) -> bool:
        """
        Fallback to SMTP for sending emails (works with app passwords)
        
        This is useful when Graph API permissions are restricted or
        when using legacy authentication with app passwords.
        """
        try:
            import smtplib
            from email.utils import formatdate
            
            smtp_config = self.config.load_smtp_config()
            if not smtp_config:
                logger.error("SMTP fallback configuration not found")
                return False
            
            # Create message
            msg = MIMEMultipart('mixed')
            msg['From'] = smtp_config['username']
            msg['To'] = to_email
            msg['Date'] = formatdate(localtime=True)
            msg['Subject'] = subject
            
            # Add HTML body
            msg.attach(MIMEText(body_html, 'html'))
            
            # Add attachments
            if attachments:
                for filename, content in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(content)
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                    msg.attach(part)
            
            # Send email
            with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port']) as server:
                if smtp_config.get('use_tls', True):
                    server.starttls()
                server.login(smtp_config['username'], smtp_config['password'])
                server.send_message(msg)
            
            logger.info(f"Email sent successfully via SMTP to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email via SMTP: {e}")
            return False
    
    def test_connection(self) -> Dict[str, bool]:
        """Test both Graph API and SMTP connections"""
        results = {
            'graph_api': False,
            'smtp': False,
            'graph_api_error': None,
            'smtp_error': None
        }
        
        # Test Graph API
        try:
            token = self.get_token_silent()
            if token:
                # Test with a simple API call
                headers = {'Authorization': f'Bearer {token["access_token"]}'}
                response = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers)
                results['graph_api'] = response.status_code == 200
                if not results['graph_api']:
                    results['graph_api_error'] = f"Status: {response.status_code}"
        except Exception as e:
            results['graph_api_error'] = str(e)
        
        # Test SMTP
        try:
            import smtplib
            smtp_config = self.config.load_smtp_config()
            if smtp_config:
                with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port']) as server:
                    if smtp_config.get('use_tls', True):
                        server.starttls()
                    server.login(smtp_config['username'], smtp_config['password'])
                    results['smtp'] = True
        except Exception as e:
            results['smtp_error'] = str(e)
        
        return results
            
            if "access_token" in result:
                self.token = result
                
                # Save token to file
                with open(self.token_file, 'w') as f:
                    json.dump(result, f, indent=2)
                
                logger.info("Microsoft OAuth2 tokens saved successfully")
                return True
            else:
                logger.error(f"Failed to acquire token: {result.get('error_description')}")
                return False
                
        except Exception as e:
            logger.error(f"Error handling Microsoft OAuth callback: {e}")
            return False
    
    def load_token(self) -> bool:
        """Load saved token"""
        try:
            if self.token_file.exists():
                with open(self.token_file, 'r') as f:
                    self.token = json.load(f)
                
                # Check if token needs refresh
                if self.is_token_expired():
                    return self.refresh_token()
                
                return True
                
        except Exception as e:
            logger.error(f"Error loading Microsoft token: {e}")
        
        return False
    
    def is_token_expired(self) -> bool:
        """Check if token is expired"""
        if not self.token or 'expires_in' not in self.token:
            return True
        
        # Simple expiration check (should track actual expiry time)
        return False
    
    def refresh_token(self) -> bool:
        """Refresh access token"""
        try:
            if not self.app:
                if not self.initialize_app():
                    return False
            
            if not self.token or 'refresh_token' not in self.token:
                return False
            
            result = self.app.acquire_token_by_refresh_token(
                self.token['refresh_token'],
                scopes=OAuth2Config.MICROSOFT_SCOPES
            )
            
            if "access_token" in result:
                self.token = result
                
                # Save refreshed token
                with open(self.token_file, 'w') as f:
                    json.dump(result, f, indent=2)
                
                return True
                
        except Exception as e:
            logger.error(f"Error refreshing Microsoft token: {e}")
        
        return False
    
    def send_email(self, to_email: str, subject: str, body_html: str,
                  attachments: Optional[List[tuple]] = None) -> bool:
        """
        Send email via Microsoft Graph API
        
        Args:
            to_email: Recipient email
            subject: Email subject
            body_html: HTML body
            attachments: List of (filename, content_bytes) tuples
        """
        try:
            if not self.token:
                if not self.load_token():
                    logger.error("No valid token available")
                    return False
            
            # Prepare message
            message = {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_email
                        }
                    }
                ]
            }
            
            # Add attachments
            if attachments:
                message["attachments"] = []
                for filename, content in attachments:
                    attachment = {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": filename,
                        "contentType": "application/octet-stream",
                        "contentBytes": base64.b64encode(content).decode()
                    }
                    message["attachments"].append(attachment)
            
            # Send email
            headers = {
                'Authorization': f'Bearer {self.token["access_token"]}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                'https://graph.microsoft.com/v1.0/me/sendMail',
                headers=headers,
                json={"message": message}
            )
            
            if response.status_code == 202:
                logger.info("Email sent successfully via Microsoft Graph")
                return True
            else:
                logger.error(f"Failed to send email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email via Microsoft: {e}")
            return False
    
    def revoke_access(self) -> bool:
        """Revoke OAuth2 access"""
        try:
            # Delete token file
            if self.token_file.exists():
                self.token_file.unlink()
            
            self.token = None
            logger.info("Microsoft OAuth2 access revoked")
            return True
            
        except Exception as e:
            logger.error(f"Error revoking Microsoft access: {e}")
            return False


class OAuth2EmailManager:
    """Unified OAuth2 Email Manager"""
    
    def __init__(self, config_dir: Path = Path("config")):
        self.config = OAuth2Config(config_dir)
        self.google_service = GoogleOAuth2Service(self.config)
        self.microsoft_service = MicrosoftOAuth2Service(self.config)
        self.active_service = None
    
    def configure_google(self, client_id: str, client_secret: str) -> bool:
        """Configure Google OAuth2"""
        return self.config.save_google_config(client_id, client_secret)
    
    def configure_microsoft(self, tenant_id: str, client_id: str, 
                          client_secret: str) -> bool:
        """Configure Microsoft OAuth2"""
        return self.config.save_microsoft_config(tenant_id, client_id, client_secret)
    
    def get_auth_url(self, provider: str) -> Optional[str]:
        """Get authorization URL for provider"""
        if provider == 'google':
            return self.google_service.get_auth_url()
        elif provider == 'microsoft':
            return self.microsoft_service.get_auth_url()
        return None
    
    def handle_callback(self, provider: str, auth_response: str) -> bool:
        """Handle OAuth2 callback"""
        if provider == 'google':
            success = self.google_service.handle_callback(auth_response)
            if success:
                self.active_service = 'google'
            return success
        elif provider == 'microsoft':
            # Extract code from response
            import urllib.parse
            parsed = urllib.parse.urlparse(auth_response)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get('code', [None])[0]
            
            if code:
                success = self.microsoft_service.handle_callback(code)
                if success:
                    self.active_service = 'microsoft'
                return success
        return False
    
    def send_email(self, to_email: str, subject: str, body_html: str,
                  attachments: Optional[List[tuple]] = None,
                  provider: Optional[str] = None) -> bool:
        """
        Send email using OAuth2
        
        Args:
            to_email: Recipient email
            subject: Email subject
            body_html: HTML body
            attachments: List of (filename, content_bytes) tuples
            provider: Force specific provider (optional)
        """
        # Use specified provider or active service
        service = provider or self.active_service
        
        if service == 'google':
            return self.google_service.send_email(to_email, subject, body_html, attachments)
        elif service == 'microsoft':
            return self.microsoft_service.send_email(to_email, subject, body_html, attachments)
        else:
            logger.error("No active OAuth2 service")
            return False
    
    def check_authentication(self) -> Dict[str, bool]:
        """Check authentication status for each provider"""
        return {
            'google': self.google_service.load_credentials(),
            'microsoft': self.microsoft_service.load_token()
        }
    
    def revoke_access(self, provider: str) -> bool:
        """Revoke OAuth2 access for provider"""
        if provider == 'google':
            return self.google_service.revoke_access()
        elif provider == 'microsoft':
            return self.microsoft_service.revoke_access()
        return False


def create_oauth2_setup_ui():
    """Create Streamlit UI for OAuth2 setup"""
    
    st.header("🔐 Configuration OAuth2")
    
    oauth_manager = OAuth2EmailManager()
    
    # Check current authentication status
    auth_status = oauth_manager.check_authentication()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Gmail (Google OAuth2)")
        
        if auth_status['google']:
            st.success("✅ Authentifié avec Google")
            if st.button("🔓 Révoquer l'accès Google"):
                if oauth_manager.revoke_access('google'):
                    st.success("Accès Google révoqué")
                    st.rerun()
        else:
            with st.form("google_oauth_form"):
                st.info("Configurez OAuth2 pour Gmail")
                
                client_id = st.text_input("Client ID")
                client_secret = st.text_input("Client Secret", type="password")
                
                if st.form_submit_button("Configurer Google OAuth2"):
                    if client_id and client_secret:
                        if oauth_manager.configure_google(client_id, client_secret):
                            st.success("Configuration sauvegardée")
                            
                            # Get auth URL
                            auth_url = oauth_manager.get_auth_url('google')
                            if auth_url:
                                st.markdown(f"[🔗 Autoriser l'accès Gmail]({auth_url})")
                                st.info("Cliquez sur le lien ci-dessus pour autoriser l'accès")
                    else:
                        st.error("Veuillez remplir tous les champs")
    
    with col2:
        st.subheader("Office 365 (Microsoft OAuth2)")
        
        if auth_status['microsoft']:
            st.success("✅ Authentifié avec Microsoft")
            if st.button("🔓 Révoquer l'accès Microsoft"):
                if oauth_manager.revoke_access('microsoft'):
                    st.success("Accès Microsoft révoqué")
                    st.rerun()
        else:
            with st.form("microsoft_oauth_form"):
                st.info("Configurez OAuth2 pour Office 365")
                
                tenant_id = st.text_input("Tenant ID")
                client_id_ms = st.text_input("Client ID", key="ms_client_id")
                client_secret_ms = st.text_input("Client Secret", type="password", key="ms_client_secret")
                
                if st.form_submit_button("Configurer Microsoft OAuth2"):
                    if tenant_id and client_id_ms and client_secret_ms:
                        if oauth_manager.configure_microsoft(tenant_id, client_id_ms, client_secret_ms):
                            st.success("Configuration sauvegardée")
                            
                            # Get auth URL
                            auth_url = oauth_manager.get_auth_url('microsoft')
                            if auth_url:
                                st.markdown(f"[🔗 Autoriser l'accès Office 365]({auth_url})")
                                st.info("Cliquez sur le lien ci-dessus pour autoriser l'accès")
                    else:
                        st.error("Veuillez remplir tous les champs")
    
    # Handle OAuth2 callback
    st.markdown("---")
    st.subheader("📥 Callback OAuth2")
    
    with st.expander("Coller l'URL de callback après autorisation"):
        callback_url = st.text_input("URL de callback", key="oauth_callback_url")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Valider callback Google"):
                if callback_url:
                    if oauth_manager.handle_callback('google', callback_url):
                        st.success("✅ Authentification Google réussie!")
                        st.rerun()
                    else:
                        st.error("Échec de l'authentification")
        
        with col2:
            if st.button("Valider callback Microsoft"):
                if callback_url:
                    if oauth_manager.handle_callback('microsoft', callback_url):
                        st.success("✅ Authentification Microsoft réussie!")
                        st.rerun()
                    else:
                        st.error("Échec de l'authentification")


def send_paystub_with_oauth2(employee_data: Dict, pdf_buffer: bytes,
                            period: str, provider: str = 'google') -> bool:
    """
    Send paystub using OAuth2 authentication
    
    Args:
        employee_data: Employee data dictionary
        pdf_buffer: PDF content as bytes
        period: Period (YYYY-MM)
        provider: 'google' or 'microsoft'
    """
    
    oauth_manager = OAuth2EmailManager()
    
    # Prepare email content
    period_date = datetime.strptime(period, "%Y-%m")
    month_year = period_date.strftime("%B %Y")
    
    subject = f"Votre bulletin de paie - {month_year}"
    
    body_html = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Bulletin de Paie - {month_year}</h2>
            
            <p>Bonjour {employee_data.get('prenom', '')} {employee_data.get('nom', '')},</p>
            
            <p>Veuillez trouver ci-joint votre bulletin de paie pour la période de {month_year}.</p>
            
            <div style="background: #f5f5f5; padding: 15px; margin: 20px 0;">
                <strong>Récapitulatif:</strong><br>
                Salaire brut: {employee_data.get('salaire_brut', 0):,.2f} €<br>
                Salaire net: {employee_data.get('salaire_net', 0):,.2f} €
            </div>
            
            <p>Ce document est à conserver sans limitation de durée.</p>
            
            <p>Cordialement,<br>
            Service Paie</p>
        </body>
    </html>
    """
    
    # Prepare attachment
    filename = f"bulletin_{employee_data.get('matricule', '')}_{period}.pdf"
    attachments = [(filename, pdf_buffer)]
    
    # Send email
    return oauth_manager.send_email(
        employee_data.get('email', ''),
        subject,
        body_html,
        attachments,
        provider
    )


# Test function
def test_oauth2_email():
    """Test OAuth2 email functionality"""
    
    oauth_manager = OAuth2EmailManager()
    
    # Check authentication
    auth_status = oauth_manager.check_authentication()
    print(f"Authentication status: {auth_status}")
    
    if auth_status['google'] or auth_status['microsoft']:
        # Test email
        test_email = "test@example.com"
        subject = "Test OAuth2 Email"
        body = "<h1>Test</h1><p>This is a test email sent via OAuth2.</p>"
        
        # Use whichever service is authenticated
        provider = 'google' if auth_status['google'] else 'microsoft'
        
        success = oauth_manager.send_email(
            test_email,
            subject,
            body,
            provider=provider
        )
        
        if success:
            print(f"Test email sent successfully via {provider}")
        else:
            print(f"Failed to send test email via {provider}")
    else:
        print("No OAuth2 service authenticated")


if __name__ == "__main__":
    # Run test
    test_oauth2_email()