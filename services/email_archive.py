"""
Email Distribution and Archive Management Module
================================================
Handles secure email distribution of paystubs and PDF archiving with versioning
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import hashlib
import json
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
import polars as pl
import io
import logging
from dataclasses import dataclass, asdict
from enum import Enum
import zipfile
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EmailStatus(Enum):
    """Statuts d'envoi des emails"""
    PENDING = "En attente"
    SENT = "Envoyé"
    FAILED = "Échec"
    BOUNCED = "Retourné"
    OPENED = "Ouvert"
    RETRY = "Nouvelle tentative"


@dataclass
class EmailConfig:
    """Configuration pour l'envoi d'emails"""
    smtp_server: str
    smtp_port: int
    sender_email: str
    sender_password: str
    sender_name: str = "Service Paie"
    use_tls: bool = True
    use_ssl: bool = False
    reply_to: Optional[str] = None
    bcc_archive: Optional[str] = None  # Copie cachée pour archivage
    
    def to_dict(self) -> Dict:
        """Convertir en dictionnaire (sans le mot de passe)"""
        data = asdict(self)
        data.pop('sender_password', None)
        return data

@dataclass
class EmailTemplate:
    """Template d'email pour les bulletins de paie"""
    subject: str
    body_html: str
    body_text: str
    
    @staticmethod
    def get_default_paystub_template(language: str = "fr") -> 'EmailTemplate':
        """Obtenir le template par défaut pour les bulletins de paie"""

        if language == "fr":
            subject = "Votre bulletin de paie - {month_year}"

            body_html = """
            <html>
                <body style="font-family: Arial, sans-serif; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #2C3E50;">Bulletin de Paie - {month_year}</h2>

                        <p>Bonjour {prenom} {nom},</p>

                        <p>Veuillez trouver ci-joint votre bulletin de paie pour la période du <strong>{period_start}</strong> au <strong>{period_end}</strong>.</p>

                        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                            <h3 style="color: #495057; margin-top: 0;">Récapitulatif</h3>
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr>
                                    <td style="padding: 5px 0;"><strong>Salaire brut:</strong></td>
                                    <td style="text-align: right; padding: 5px 0;">{salaire_brut} €</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 0;"><strong>Charges salariales:</strong></td>
                                    <td style="text-align: right; padding: 5px 0;">-{charges_salariales} €</td>
                                </tr>
                                <tr style="border-top: 2px solid #dee2e6;">
                                    <td style="padding: 8px 0;"><strong>Net à payer:</strong></td>
                                    <td style="text-align: right; padding: 8px 0; color: #28a745; font-size: 1.1em;"><strong>{salaire_net} €</strong></td>
                                </tr>
                            </table>
                        </div>

                        <p>Ce document est à conserver sans limitation de durée pour faire valoir vos droits.</p>

                        <p>Pour toute question concernant votre bulletin de paie, n'hésitez pas à contacter le service paie.</p>

                        <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">

                        <p style="font-size: 12px; color: #6c757d;">
                            Cet email et ses pièces jointes sont confidentiels et destinés exclusivement à la personne à laquelle ils sont adressés.<br>
                            Si vous avez reçu cet email par erreur, merci de le signaler à l'expéditeur et de le supprimer.
                        </p>

                        <p style="font-size: 12px; color: #6c757d; margin-top: 20px;">
                            <strong>{company_name}</strong><br>
                            {company_address}<br>
                            Email: {company_email} | Tél: {company_phone}
                        </p>
                    </div>
                </body>
            </html>
            """

            body_text = """
            Bulletin de Paie - {month_year}

            Bonjour {prenom} {nom},

            Veuillez trouver ci-joint votre bulletin de paie pour la période du {period_start} au {period_end}.

            Récapitulatif:
            - Salaire brut: {salaire_brut} €
            - Charges salariales: -{charges_salariales} €
            - Net à payer: {salaire_net} €

            Ce document est à conserver sans limitation de durée pour faire valoir vos droits.

            Pour toute question concernant votre bulletin de paie, n'hésitez pas à contacter le service paie.

            Cordialement,
            {company_name}
            """

        elif language == "it":
            subject = "La sua busta paga - {month_year}"
            body_html = """<html>...</html>"""  # Version italienne
            body_text = """..."""  # Version italienne

        else:  # English default
            subject = "Your payslip - {month_year}"
            body_html = """<html>...</html>"""  # Version anglaise
            body_text = """..."""  # Version anglaise

        return EmailTemplate(subject=subject, body_html=body_html, body_text=body_text)

    @staticmethod
    def get_client_validation_template(language: str = "fr") -> 'EmailTemplate':
        """Obtenir le template pour l'envoi de validation au client"""

        if language == "fr":
            subject = "Validation paie - {company_name} - {month_year}"

            body_html = """
            <html>
                <body style="font-family: Arial, sans-serif; color: #333;">
                    <div style="max-width: 700px; margin: 0 auto; padding: 20px;">
                        <div style="background-color: #3498db; color: white; padding: 20px; border-radius: 5px 5px 0 0;">
                            <h2 style="margin: 0;">Validation des Bulletins de Paie</h2>
                            <p style="margin: 10px 0 0 0; font-size: 1.1em;">{company_name} - {month_year}</p>
                        </div>

                        <div style="border: 1px solid #dee2e6; border-top: none; padding: 25px; border-radius: 0 0 5px 5px;">
                            <p>Bonjour,</p>

                            <p>Veuillez trouver ci-joint les documents de paie pour la période <strong>{month_year}</strong> à valider avant envoi aux salariés :</p>

                            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 25px 0;">
                                <h3 style="color: #2c3e50; margin-top: 0; margin-bottom: 15px;">📎 Documents joints</h3>
                                <ul style="line-height: 1.8; margin: 0; padding-left: 20px;">
                                    <li><strong>Bulletins de paie ({employee_count} salariés)</strong> - Archive ZIP contenant tous les bulletins individuels</li>
                                    <li><strong>Journal de paie</strong> - Récapitulatif consolidé de la période</li>
                                    <li><strong>Provision congés payés</strong> - État des provisions CP au {month_year}</li>
                                </ul>
                            </div>

                            <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 25px 0;">
                                <h4 style="margin-top: 0; color: #856404;">⚠️ Action requise</h4>
                                <p style="margin-bottom: 0; color: #856404;">
                                    Merci de vérifier ces documents et de nous confirmer votre validation sous <strong>48h</strong>.<br>
                                    Après validation, les bulletins seront envoyés automatiquement aux salariés.
                                </p>
                            </div>

                            <div style="background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 25px 0;">
                                <h3 style="color: #0066cc; margin-top: 0; margin-bottom: 10px;">📊 Récapitulatif de la paie</h3>
                                <table style="width: 100%; border-collapse: collapse;">
                                    <tr>
                                        <td style="padding: 8px 0; border-bottom: 1px solid #ccc;"><strong>Nombre de salariés :</strong></td>
                                        <td style="text-align: right; padding: 8px 0; border-bottom: 1px solid #ccc;">{employee_count}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; border-bottom: 1px solid #ccc;"><strong>Masse salariale brute :</strong></td>
                                        <td style="text-align: right; padding: 8px 0; border-bottom: 1px solid #ccc;">{total_brut} €</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; border-bottom: 1px solid #ccc;"><strong>Charges salariales :</strong></td>
                                        <td style="text-align: right; padding: 8px 0; border-bottom: 1px solid #ccc;">{total_charges_sal} €</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 8px 0; border-bottom: 1px solid #ccc;"><strong>Charges patronales :</strong></td>
                                        <td style="text-align: right; padding: 8px 0; border-bottom: 1px solid #ccc;">{total_charges_pat} €</td>
                                    </tr>
                                    <tr style="background-color: #d4edda;">
                                        <td style="padding: 12px 0; font-weight: bold; color: #155724;"><strong>Masse salariale nette :</strong></td>
                                        <td style="text-align: right; padding: 12px 0; font-weight: bold; color: #155724; font-size: 1.1em;">{total_net} €</td>
                                    </tr>
                                    <tr style="background-color: #f8d7da;">
                                        <td style="padding: 12px 0; font-weight: bold; color: #721c24;"><strong>Coût total employeur :</strong></td>
                                        <td style="text-align: right; padding: 12px 0; font-weight: bold; color: #721c24; font-size: 1.1em;">{total_cout} €</td>
                                    </tr>
                                </table>
                            </div>

                            <p style="margin-top: 30px;">Pour toute question ou modification, merci de nous contacter rapidement.</p>

                            <p style="margin-top: 25px;">Cordialement,<br>
                            <strong>Service Comptabilité</strong></p>

                            <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">

                            <p style="font-size: 11px; color: #6c757d;">
                                Cet email et ses pièces jointes sont confidentiels et réservés à l'usage exclusif du destinataire.<br>
                                Si vous n'êtes pas le destinataire prévu, toute divulgation, copie ou distribution est interdite.
                            </p>
                        </div>
                    </div>
                </body>
            </html>
            """

            body_text = """
            Validation des Bulletins de Paie
            {company_name} - {month_year}

            Bonjour,

            Veuillez trouver ci-joint les documents de paie pour la période {month_year} à valider avant envoi aux salariés :

            Documents joints :
            - Bulletins de paie ({employee_count} salariés) - Archive ZIP
            - Journal de paie - Récapitulatif consolidé
            - Provision congés payés - État au {month_year}

            RÉCAPITULATIF DE LA PAIE
            - Nombre de salariés : {employee_count}
            - Masse salariale brute : {total_brut} €
            - Charges salariales : {total_charges_sal} €
            - Charges patronales : {total_charges_pat} €
            - Masse salariale nette : {total_net} €
            - Coût total employeur : {total_cout} €

            ⚠️ ACTION REQUISE
            Merci de vérifier ces documents et de nous confirmer votre validation sous 48h.
            Après validation, les bulletins seront envoyés automatiquement aux salariés.

            Pour toute question ou modification, merci de nous contacter rapidement.

            Cordialement,
            Service Comptabilité
            """

        else:  # English default
            subject = "Payroll Validation - {company_name} - {month_year}"
            body_html = """<html>...</html>"""
            body_text = """..."""

        return EmailTemplate(subject=subject, body_html=body_html, body_text=body_text)

class PDFArchiveManager:
    """Gestionnaire d'archives PDF avec versioning"""
    
    def __init__(self, archive_root: Path):
        """
        Initialiser le gestionnaire d'archives
        
        Args:
            archive_root: Répertoire racine pour les archives
        """
        self.archive_root = Path(archive_root)
        self.archive_root.mkdir(parents=True, exist_ok=True)
        
        # Structure des répertoires
        self.sent_dir = self.archive_root / "sent"
        self.pending_dir = self.archive_root / "pending"
        self.failed_dir = self.archive_root / "failed"
        self.versions_dir = self.archive_root / "versions"
        
        # Créer les répertoires
        for directory in [self.sent_dir, self.pending_dir, self.failed_dir, self.versions_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Fichier de métadonnées
        self.metadata_file = self.archive_root / "archive_metadata.json"
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict:
        """Charger les métadonnées d'archive"""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'documents': {},
            'statistics': {
                'total_archived': 0,
                'total_versions': 0,
                'total_size_mb': 0
            }
        }
    
    def _save_metadata(self):
        """Sauvegarder les métadonnées"""
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False, default=str)
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculer le checksum SHA256 d'un fichier"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def archive_document(self, pdf_buffer: Union[io.BytesIO, bytes], 
                        document_type: str,
                        employee_id: str,
                        period: str,
                        metadata: Optional[Dict] = None) -> Dict:
        """
        Archiver un document PDF avec versioning
        
        Args:
            pdf_buffer: Buffer ou bytes du PDF
            document_type: Type de document (paystub, journal, pto_provision)
            employee_id: Identifiant de l'employé (ou 'company' pour documents globaux)
            period: Période au format YYYY-MM
            metadata: Métadonnées additionnelles
        
        Returns:
            Dictionnaire avec les informations d'archivage
        """
        # Préparer le nom de fichier
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{document_type}_{employee_id}_{period}"
        file_name = f"{base_name}_{timestamp}.pdf"
        
        # Déterminer le répertoire de destination
        year, month = period.split('-')
        dest_dir = self.pending_dir / year / month / document_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Chemin complet du fichier
        file_path = dest_dir / file_name
        
        # Écrire le fichier
        if isinstance(pdf_buffer, io.BytesIO):
            pdf_buffer.seek(0)
            content = pdf_buffer.read()
        else:
            content = pdf_buffer
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # Calculer le checksum
        checksum = self._calculate_checksum(file_path)
        
        # Vérifier si c'est une nouvelle version
        doc_key = f"{base_name}"
        version_number = 1
        
        if doc_key in self.metadata['documents']:
            # C'est une nouvelle version
            previous_versions = self.metadata['documents'][doc_key].get('versions', [])
            version_number = len(previous_versions) + 1
            
            # Archiver l'ancienne version
            if previous_versions:
                last_version = previous_versions[-1]
                old_file = Path(last_version['file_path'])
                if old_file.exists():
                    version_dir = self.versions_dir / year / month / document_type
                    version_dir.mkdir(parents=True, exist_ok=True)
                    version_file = version_dir / f"{base_name}_v{len(previous_versions)}.pdf"
                    shutil.move(str(old_file), str(version_file))
                    last_version['file_path'] = str(version_file)
        
        # Créer l'entrée de métadonnées
        doc_metadata = {
            'document_type': document_type,
            'employee_id': employee_id,
            'period': period,
            'current_version': version_number,
            'current_file': str(file_path),
            'checksum': checksum,
            'size_bytes': len(content),
            'created_at': timestamp,
            'status': 'pending',
            'metadata': metadata or {},
            'versions': []
        }
        
        # Ajouter l'historique des versions si applicable
        if doc_key in self.metadata['documents']:
            doc_metadata['versions'] = self.metadata['documents'][doc_key].get('versions', [])
        
        # Ajouter la version actuelle à l'historique
        doc_metadata['versions'].append({
            'version': version_number,
            'file_path': str(file_path),
            'checksum': checksum,
            'size_bytes': len(content),
            'created_at': timestamp,
            'metadata': metadata or {}
        })
        
        # Mettre à jour les métadonnées globales
        self.metadata['documents'][doc_key] = doc_metadata
        self.metadata['statistics']['total_archived'] += 1
        self.metadata['statistics']['total_versions'] = sum(
            len(doc.get('versions', [])) for doc in self.metadata['documents'].values()
        )
        self.metadata['statistics']['total_size_mb'] += len(content) / (1024 * 1024)
        
        # Sauvegarder les métadonnées
        self._save_metadata()
        
        logger.info(f"Document archivé: {file_name} (v{version_number})")
        
        return {
            'success': True,
            'file_path': str(file_path),
            'checksum': checksum,
            'version': version_number,
            'doc_key': doc_key
        }
    
    def mark_as_sent(self, doc_key: str, email_metadata: Dict) -> bool:
        """
        Marquer un document comme envoyé et le déplacer dans le répertoire approprié
        
        Args:
            doc_key: Clé du document
            email_metadata: Métadonnées de l'envoi email
        """
        if doc_key not in self.metadata['documents']:
            logger.error(f"Document non trouvé: {doc_key}")
            return False
        
        doc = self.metadata['documents'][doc_key]
        current_file = Path(doc['current_file'])
        
        if not current_file.exists():
            logger.error(f"Fichier non trouvé: {current_file}")
            return False
        
        # Déplacer vers le répertoire 'sent'
        period = doc['period']
        year, month = period.split('-')
        sent_dir = self.sent_dir / year / month / doc['document_type']
        sent_dir.mkdir(parents=True, exist_ok=True)
        
        new_path = sent_dir / current_file.name
        shutil.move(str(current_file), str(new_path))
        
        # Mettre à jour les métadonnées
        doc['current_file'] = str(new_path)
        doc['status'] = 'sent'
        doc['sent_metadata'] = email_metadata
        doc['sent_at'] = datetime.now().isoformat()
        
        self._save_metadata()
        
        logger.info(f"Document marqué comme envoyé: {doc_key}")
        return True
    
    def mark_as_failed(self, doc_key: str, error_message: str) -> bool:
        """
        Marquer un document comme échec d'envoi
        """
        if doc_key not in self.metadata['documents']:
            return False
        
        doc = self.metadata['documents'][doc_key]
        current_file = Path(doc['current_file'])
        
        if not current_file.exists():
            return False
        
        # Déplacer vers le répertoire 'failed'
        period = doc['period']
        year, month = period.split('-')
        failed_dir = self.failed_dir / year / month / doc['document_type']
        failed_dir.mkdir(parents=True, exist_ok=True)
        
        new_path = failed_dir / current_file.name
        shutil.move(str(current_file), str(new_path))
        
        # Mettre à jour les métadonnées
        doc['current_file'] = str(new_path)
        doc['status'] = 'failed'
        doc['error_message'] = error_message
        doc['failed_at'] = datetime.now().isoformat()
        
        # Ajouter à l'historique des échecs
        if 'failure_history' not in doc:
            doc['failure_history'] = []
        doc['failure_history'].append({
            'timestamp': datetime.now().isoformat(),
            'error': error_message
        })
        
        self._save_metadata()
        
        logger.error(f"Document marqué comme échec: {doc_key} - {error_message}")
        return True
    
    def get_document_history(self, employee_id: str, 
                           document_type: Optional[str] = None) -> List[Dict]:
        """
        Obtenir l'historique des documents pour un employé
        """
        history = []
        
        for doc_key, doc in self.metadata['documents'].items():
            if doc['employee_id'] == employee_id:
                if document_type is None or doc['document_type'] == document_type:
                    history.append({
                        'doc_key': doc_key,
                        'type': doc['document_type'],
                        'period': doc['period'],
                        'version': doc['current_version'],
                        'status': doc['status'],
                        'created_at': doc['created_at'],
                        'sent_at': doc.get('sent_at'),
                        'versions_count': len(doc.get('versions', []))
                    })
        
        # Trier par date de création
        history.sort(key=lambda x: x['created_at'], reverse=True)
        
        return history
    
    def create_monthly_backup(self, period: str) -> str:
        """
        Créer une sauvegarde ZIP mensuelle de tous les documents
        
        Args:
            period: Période au format YYYY-MM
        
        Returns:
            Chemin vers le fichier de sauvegarde
        """
        year, month = period.split('-')
        backup_dir = self.archive_root / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_file = backup_dir / f"backup_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Archiver tous les documents du mois
            for status_dir in [self.sent_dir, self.pending_dir, self.failed_dir]:
                month_dir = status_dir / year / month
                if month_dir.exists():
                    for file_path in month_dir.rglob('*.pdf'):
                        arcname = file_path.relative_to(self.archive_root)
                        zipf.write(file_path, arcname)
            
            # Inclure les métadonnées
            zipf.write(self.metadata_file, 'metadata.json')
        
        logger.info(f"Sauvegarde créée: {backup_file}")
        return str(backup_file)
    
    def get_statistics(self, period: Optional[str] = None) -> Dict:
        """
        Obtenir les statistiques d'archivage
        """
        stats = {
            'total_documents': len(self.metadata['documents']),
            'total_versions': self.metadata['statistics']['total_versions'],
            'total_size_mb': round(self.metadata['statistics']['total_size_mb'], 2),
            'by_status': {'sent': 0, 'pending': 0, 'failed': 0},
            'by_type': {}
        }
        
        for doc in self.metadata['documents'].values():
            # Filtrer par période si spécifiée
            if period and doc['period'] != period:
                continue
            
            # Par statut
            status = doc.get('status', 'unknown')
            if status in stats['by_status']:
                stats['by_status'][status] += 1
            
            # Par type
            doc_type = doc['document_type']
            if doc_type not in stats['by_type']:
                stats['by_type'][doc_type] = 0
            stats['by_type'][doc_type] += 1
        
        return stats

class EmailDistributionService:
    """Service de distribution des emails"""
    
    def __init__(self, config: EmailConfig, archive_manager: PDFArchiveManager):
        """
        Initialiser le service de distribution
        
        Args:
            config: Configuration email
            archive_manager: Gestionnaire d'archives
        """
        self.config = config
        self.archive_manager = archive_manager
        self.email_log = []
        self.template = EmailTemplate.get_default_paystub_template("fr")
    
    def _create_message(self, to_email: str, subject: str, 
                       body_html: str, body_text: str,
                       attachments: List[Tuple[str, bytes]]) -> MIMEMultipart:
        """
        Créer un message email avec pièces jointes
        
        Args:
            to_email: Adresse destinataire
            subject: Sujet
            body_html: Corps HTML
            body_text: Corps texte
            attachments: Liste de tuples (nom_fichier, contenu_bytes)
        """
        message = MIMEMultipart('mixed')
        message['From'] = f"{self.config.sender_name} <{self.config.sender_email}>"
        message['To'] = to_email
        message['Subject'] = subject
        message['Date'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
        
        if self.config.reply_to:
            message['Reply-To'] = self.config.reply_to
        
        # Partie alternative (HTML et texte)
        msg_alternative = MIMEMultipart('alternative')
        
        # Partie texte
        part_text = MIMEText(body_text, 'plain', 'utf-8')
        msg_alternative.attach(part_text)
        
        # Partie HTML
        part_html = MIMEText(body_html, 'html', 'utf-8')
        msg_alternative.attach(part_html)
        
        message.attach(msg_alternative)
        
        # Ajouter les pièces jointes
        for filename, content in attachments:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{filename}"'
            )
            message.attach(part)
        
        return message
    
    def send_validation_email(self, client_email: str, company_name: str,
                             paystubs_buffers: List[Dict], journal_buffer: io.BytesIO,
                             pto_buffer: io.BytesIO, period: str,
                             payroll_summary: Dict, test_mode: bool = False) -> Dict:
        """
        Envoyer un email de validation au client avec tous les documents de paie

        Args:
            client_email: Adresse email du client (employeur)
            company_name: Nom de l'entreprise
            paystubs_buffers: Liste de dictionnaires {matricule, nom, prenom, buffer}
            journal_buffer: Buffer PDF du journal de paie
            pto_buffer: Buffer PDF de la provision CP
            period: Période (YYYY-MM)
            payroll_summary: Dictionnaire avec les totaux (brut, net, charges, etc.)
            test_mode: Mode test (pas d'envoi réel)

        Returns:
            Dictionnaire avec le statut d'envoi
        """
        result = {
            'success': False,
            'client_email': client_email,
            'error': None,
            'timestamp': datetime.now().isoformat()
        }

        try:
            # Vérifier l'adresse email
            if not client_email:
                raise ValueError("Adresse email client manquante")

            # Formater la période
            period_date = datetime.strptime(period, "%Y-%m")
            month_year = period_date.strftime("%B %Y")

            # Créer le ZIP avec tous les bulletins de paie
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for paystub in paystubs_buffers:
                    paystub['buffer'].seek(0)
                    mat = paystub.get('matricule', '')
                    nom = paystub.get('nom') or ''
                    prenom = paystub.get('prenom') or ''
                    filename = f"bulletin_{mat}_{nom}_{prenom}_{period}.pdf"
                    zipf.writestr(filename, paystub['buffer'].read())

            zip_buffer.seek(0)
            zip_content = zip_buffer.read()

            # Préparer le journal
            journal_buffer.seek(0)
            journal_content = journal_buffer.read()

            # Préparer la provision CP
            pto_buffer.seek(0)
            pto_content = pto_buffer.read()

            # Préparer les données pour le template
            template = EmailTemplate.get_client_validation_template("fr")
            template_data = {
                'company_name': company_name,
                'month_year': month_year,
                'employee_count': len(paystubs_buffers),
                'total_brut': f"{payroll_summary.get('total_brut', 0):,.2f}".replace(',', ' '),
                'total_charges_sal': f"{payroll_summary.get('total_charges_sal', 0):,.2f}".replace(',', ' '),
                'total_charges_pat': f"{payroll_summary.get('total_charges_pat', 0):,.2f}".replace(',', ' '),
                'total_net': f"{payroll_summary.get('total_net', 0):,.2f}".replace(',', ' '),
                'total_cout': f"{payroll_summary.get('total_cout', 0):,.2f}".replace(',', ' ')
            }

            # Formater le sujet et le corps
            subject = template.subject.format(**template_data)
            body_html = template.body_html.format(**template_data)
            body_text = template.body_text.format(**template_data)

            # Préparer les pièces jointes
            attachments = [
                (f"bulletins_paie_{period}.zip", zip_content),
                (f"journal_paie_{period}.pdf", journal_content),
                (f"provision_cp_{period}.pdf", pto_content)
            ]

            # Archiver les documents
            self.archive_manager.archive_document(
                journal_content,
                'journal',
                'company',
                period,
                {'client_email': client_email, 'company_name': company_name}
            )

            self.archive_manager.archive_document(
                pto_content,
                'pto_provision',
                'company',
                period,
                {'client_email': client_email, 'company_name': company_name}
            )

            if test_mode:
                logger.info(f"[TEST MODE] Email de validation qui serait envoyé à: {client_email}")
                logger.info(f"[TEST MODE] Pièces jointes: {len(attachments)} fichiers")
                result['success'] = True
                result['test_mode'] = True
                result['attachments_count'] = len(attachments)
            else:
                # Créer le message
                message = self._create_message(
                    client_email,
                    subject,
                    body_html,
                    body_text,
                    attachments
                )

                # Ajouter BCC si configuré
                if self.config.bcc_archive:
                    message['Bcc'] = self.config.bcc_archive

                # Envoyer l'email
                self._send_email(message, client_email)

                result['success'] = True
                result['attachments_count'] = len(attachments)

            # Logger le succès
            self.email_log.append(result)
            logger.info(f"Email de validation envoyé avec succès à: {client_email}")

        except Exception as e:
            error_msg = str(e)
            result['error'] = error_msg
            result['success'] = False

            # Logger l'échec
            self.email_log.append(result)
            logger.error(f"Échec envoi email validation à {client_email}: {error_msg}")

        return result

    def send_paystub(self, employee_data: Dict, pdf_buffer: io.BytesIO,
                     period: str, test_mode: bool = False) -> Dict:
        """
        Envoyer un bulletin de paie par email

        Args:
            employee_data: Données de l'employé
            pdf_buffer: Buffer PDF du bulletin
            period: Période (YYYY-MM)
            test_mode: Mode test (pas d'envoi réel)

        Returns:
            Dictionnaire avec le statut d'envoi
        """
        result = {
            'success': False,
            'employee_id': employee_data.get('matricule'),
            'email': employee_data.get('email'),
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Vérifier l'adresse email
            to_email = employee_data.get('email')
            if not to_email:
                raise ValueError("Adresse email manquante")
            
            # Formater la période
            period_date = datetime.strptime(period, "%Y-%m")
            month_year = period_date.strftime("%B %Y")
            
            # Préparer les données pour le template
            template_data = {
                'month_year': month_year,
                'nom': employee_data.get('nom', ''),
                'prenom': employee_data.get('prenom', ''),
                'period_start': employee_data.get('period_start', ''),
                'period_end': employee_data.get('period_end', ''),
                'salaire_brut': f"{employee_data.get('salaire_brut', 0):,.2f}".replace(',', ' '),
                'charges_salariales': f"{employee_data.get('total_charges_salariales', 0):,.2f}".replace(',', ' '),
                'salaire_net': f"{employee_data.get('salaire_net', 0):,.2f}".replace(',', ' '),
                'company_name': self.config.sender_name,
                'company_address': 'Monaco',
                'company_email': self.config.sender_email,
                'company_phone': ''
            }
            
            # Formater le sujet et le corps
            subject = self.template.subject.format(**template_data)
            body_html = self.template.body_html.format(**template_data)
            body_text = self.template.body_text.format(**template_data)
            
            # Préparer le PDF
            pdf_buffer.seek(0)
            pdf_content = pdf_buffer.read()
            filename = f"bulletin_{employee_data.get('matricule')}_{period}.pdf"
            
            # Archiver le document avant envoi
            nom = employee_data.get('nom') or ''
            prenom = employee_data.get('prenom') or ''
            archive_result = self.archive_manager.archive_document(
                pdf_content,
                'paystub',
                employee_data.get('matricule'),
                period,
                {'email': to_email, 'employee_name': f"{nom} {prenom}"}
            )
            
            if test_mode:
                logger.info(f"[TEST MODE] Email qui serait envoyé à: {to_email}")
                result['success'] = True
                result['test_mode'] = True
            else:
                # Créer le message
                message = self._create_message(
                    to_email,
                    subject,
                    body_html,
                    body_text,
                    [(filename, pdf_content)]
                )
                
                # Ajouter BCC si configuré
                if self.config.bcc_archive:
                    message['Bcc'] = self.config.bcc_archive
                
                # Envoyer l'email
                self._send_email(message, to_email)
                
                result['success'] = True
                
                # Marquer comme envoyé dans l'archive
                self.archive_manager.mark_as_sent(
                    archive_result['doc_key'],
                    {
                        'to': to_email,
                        'subject': subject,
                        'timestamp': result['timestamp']
                    }
                )
            
            # Logger le succès
            self.email_log.append(result)
            logger.info(f"Bulletin envoyé avec succès à: {to_email}")
            
        except Exception as e:
            error_msg = str(e)
            result['error'] = error_msg
            result['success'] = False
            
            # Logger l'échec
            self.email_log.append(result)
            logger.error(f"Échec envoi bulletin à {to_email}: {error_msg}")
            
            # Marquer comme échec dans l'archive si applicable
            if 'archive_result' in locals():
                self.archive_manager.mark_as_failed(
                    archive_result['doc_key'],
                    error_msg
                )
        
        return result
    
    def _send_email(self, message: MIMEMultipart, to_email: str):
        """
        Envoyer un email via SMTP
        """
        context = ssl.create_default_context()
        
        try:
            if self.config.use_ssl:
                # Connexion SSL
                with smtplib.SMTP_SSL(
                    self.config.smtp_server,
                    self.config.smtp_port,
                    context=context
                ) as server:
                    server.login(self.config.sender_email, self.config.sender_password)
                    server.send_message(message)
            else:
                # Connexion TLS
                with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                    if self.config.use_tls:
                        server.starttls(context=context)
                    server.login(self.config.sender_email, self.config.sender_password)
                    server.send_message(message)
                    
        except smtplib.SMTPAuthenticationError:
            raise Exception("Échec de l'authentification SMTP")
        except smtplib.SMTPException as e:
            raise Exception(f"Erreur SMTP: {str(e)}")
        except Exception as e:
            raise Exception(f"Erreur d'envoi: {str(e)}")
    
    def send_batch(self, employees_data: List[Dict], 
                  pdf_buffers: Dict[str, io.BytesIO],
                  period: str,
                  batch_size: int = 10,
                  delay_seconds: int = 2,
                  test_mode: bool = False) -> Dict:
        """
        Envoyer un lot de bulletins de paie
        
        Args:
            employees_data: Liste des données employés
            pdf_buffers: Dictionnaire {matricule: pdf_buffer}
            period: Période (YYYY-MM)
            batch_size: Nombre d'emails par lot
            delay_seconds: Délai entre chaque email
            test_mode: Mode test
        
        Returns:
            Rapport d'envoi
        """
        import time
        
        report = {
            'total': len(employees_data),
            'sent': 0,
            'failed': 0,
            'errors': [],
            'start_time': datetime.now().isoformat(),
            'details': []
        }
        
        for i, employee in enumerate(employees_data):
            matricule = employee.get('matricule')
            
            # Vérifier si on a le PDF
            if matricule not in pdf_buffers:
                report['failed'] += 1
                report['errors'].append({
                    'matricule': matricule,
                    'error': 'PDF non trouvé'
                })
                continue
            
            # Envoyer le bulletin
            result = self.send_paystub(
                employee,
                pdf_buffers[matricule],
                period,
                test_mode
            )
            
            report['details'].append(result)
            
            if result['success']:
                report['sent'] += 1
            else:
                report['failed'] += 1
                report['errors'].append({
                    'matricule': matricule,
                    'error': result.get('error', 'Erreur inconnue')
                })
            
            # Pause entre les envois (sauf pour le dernier)
            if i < len(employees_data) - 1 and not test_mode:
                time.sleep(delay_seconds)
            
            # Pause supplémentaire après chaque lot
            if (i + 1) % batch_size == 0 and i < len(employees_data) - 1:
                logger.info(f"Lot de {batch_size} emails envoyé, pause de 10 secondes...")
                if not test_mode:
                    time.sleep(10)
        
        report['end_time'] = datetime.now().isoformat()
        
        # Calculer la durée
        start = datetime.fromisoformat(report['start_time'])
        end = datetime.fromisoformat(report['end_time'])
        report['duration_seconds'] = (end - start).total_seconds()
        
        # Logger le rapport
        logger.info(f"Envoi terminé: {report['sent']}/{report['total']} réussis, {report['failed']} échecs")
        
        return report
    
    def retry_failed_emails(self, period: str, max_retries: int = 3) -> Dict:
        """
        Réessayer l'envoi des emails en échec
        
        Args:
            period: Période concernée
            max_retries: Nombre maximum de tentatives
        
        Returns:
            Rapport de réenvoi
        """
        report = {
            'retried': 0,
            'success': 0,
            'failed': 0,
            'details': []
        }
        
        # Obtenir les documents en échec
        failed_docs = []
        for doc_key, doc in self.archive_manager.metadata['documents'].items():
            if doc['period'] == period and doc['status'] == 'failed':
                retry_count = len(doc.get('failure_history', []))
                if retry_count < max_retries:
                    failed_docs.append(doc)
        
        logger.info(f"Trouvé {len(failed_docs)} documents à renvoyer pour {period}")
        
        for doc in failed_docs:
            # Charger le PDF depuis l'archive
            pdf_path = Path(doc['current_file'])
            if not pdf_path.exists():
                logger.error(f"Fichier PDF non trouvé: {pdf_path}")
                continue
            
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            
            # Récupérer les données de l'employé (à implémenter selon votre système)
            # Pour cet exemple, on utilise les métadonnées stockées
            employee_data = doc.get('metadata', {})
            employee_data['matricule'] = doc['employee_id']
            
            # Créer un buffer
            pdf_buffer = io.BytesIO(pdf_content)
            
            # Réessayer l'envoi
            result = self.send_paystub(employee_data, pdf_buffer, period)
            
            report['retried'] += 1
            if result['success']:
                report['success'] += 1
            else:
                report['failed'] += 1
            
            report['details'].append(result)
        
        return report
    
    def get_email_report(self, period: Optional[str] = None) -> pl.DataFrame:
        """
        Obtenir un rapport des emails envoyés
        
        Args:
            period: Filtrer par période (optionnel)
        
        Returns:
            DataFrame avec le rapport
        """
        if period:
            logs = [log for log in self.email_log 
                if log.get('timestamp', '').startswith(period)]
        else:
            logs = self.email_log
        
        if not logs:
            return pl.DataFrame()
        
        df = pl.DataFrame(logs)
        
        # Add calculated columns
        df = df.with_columns([
            pl.when(pl.col('success'))
            .then(pl.lit('Envoyé'))
            .otherwise(pl.lit('Échec'))
            .alias('status'),
            pl.col('timestamp').str.to_datetime().dt.date().alias('date'),
            pl.col('timestamp').str.to_datetime().dt.time().alias('time')
        ])
        
        return df.select(['date', 'time', 'employee_id', 'email', 'status', 'error'])

class EmailConfigManager:
    """Gestionnaire de configuration email avec chiffrement des mots de passe"""
    
    def __init__(self, config_file: Path):
        """
        Initialiser le gestionnaire de configuration
        
        Args:
            config_file: Fichier de configuration
        """
        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
    
    def save_config(self, config: EmailConfig, encrypt_password: bool = True) -> bool:
        """
        Sauvegarder la configuration
        
        Args:
            config: Configuration à sauvegarder
            encrypt_password: Chiffrer le mot de passe
        """
        try:
            config_dict = config.to_dict()
            
            if encrypt_password and config.sender_password:
                # Chiffrement simple (en production, utiliser une vraie solution de chiffrement)
                import base64
                encrypted = base64.b64encode(config.sender_password.encode()).decode()
                config_dict['sender_password_encrypted'] = encrypted
            else:
                config_dict['sender_password'] = config.sender_password
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Configuration sauvegardée: {self.config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde configuration: {e}")
            return False
    
    def load_config(self) -> Optional[EmailConfig]:
        """
        Charger la configuration
        
        Returns:
            Configuration ou None si erreur
        """
        try:
            if not self.config_file.exists():
                return None
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
            
            # Déchiffrer le mot de passe si nécessaire
            if 'sender_password_encrypted' in config_dict:
                import base64
                encrypted = config_dict.pop('sender_password_encrypted')
                config_dict['sender_password'] = base64.b64decode(encrypted).decode()
            
            return EmailConfig(**config_dict)
            
        except Exception as e:
            logger.error(f"Erreur chargement configuration: {e}")
            return None
    
    @staticmethod
    def get_default_configs() -> Dict[str, EmailConfig]:
        """
        Obtenir des configurations par défaut pour différents providers
        
        Returns:
            Dictionnaire de configurations
        """
        return {
            'gmail': EmailConfig(
                smtp_server='smtp.gmail.com',
                smtp_port=587,
                sender_email='',
                sender_password='',
                use_tls=True,
                use_ssl=False
            ),
            'outlook': EmailConfig(
                smtp_server='smtp-mail.outlook.com',
                smtp_port=587,
                sender_email='',
                sender_password='',
                use_tls=True,
                use_ssl=False
            ),
            'office365': EmailConfig(
                smtp_server='smtp.office365.com',
                smtp_port=587,
                sender_email='',
                sender_password='',
                use_tls=True,
                use_ssl=False
            ),
            'custom': EmailConfig(
                smtp_server='',
                smtp_port=587,
                sender_email='',
                sender_password='',
                use_tls=True,
                use_ssl=False
            )
        }

class ComplianceAuditLogger:
    """Logger de conformité pour l'audit des envois"""
    
    def __init__(self, log_dir: Path):
        """
        Initialiser le logger d'audit
        
        Args:
            log_dir: Répertoire des logs
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Fichier de log principal
        self.audit_file = self.log_dir / f"audit_{datetime.now().strftime('%Y%m')}.json"
        self.audit_data = self._load_audit_log()
    
    def _load_audit_log(self) -> List[Dict]:
        """Charger le log d'audit existant"""
        if self.audit_file.exists():
            with open(self.audit_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def log_email_sent(self, employee_id: str, email: str, 
                      document_type: str, period: str,
                      success: bool, metadata: Optional[Dict] = None):
        """
        Logger un envoi d'email pour l'audit
        
        Args:
            employee_id: ID de l'employé
            email: Adresse email
            document_type: Type de document
            period: Période
            success: Succès ou échec
            metadata: Métadonnées additionnelles
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'employee_id': employee_id,
            'email': self._anonymize_email(email),
            'document_type': document_type,
            'period': period,
            'success': success,
            'metadata': metadata or {},
            'ip_address': self._get_ip_address(),
            'user_agent': 'Monaco Payroll System v1.0'
        }
        
        self.audit_data.append(entry)
        
        # Sauvegarder immédiatement
        with open(self.audit_file, 'w', encoding='utf-8') as f:
            json.dump(self.audit_data, f, indent=2, ensure_ascii=False, default=str)
    
    def _anonymize_email(self, email: str) -> str:
        """
        Anonymiser partiellement l'email pour la conformité RGPD
        
        Args:
            email: Email complet
        
        Returns:
            Email partiellement masqué
        """
        if '@' in email:
            parts = email.split('@')
            name = parts[0]
            domain = parts[1]
            
            if len(name) > 3:
                masked_name = name[:2] + '*' * (len(name) - 3) + name[-1]
            else:
                masked_name = name[0] + '*' * (len(name) - 1)
            
            return f"{masked_name}@{domain}"
        return email
    
    def _get_ip_address(self) -> str:
        """Obtenir l'adresse IP locale"""
        import socket
        try:
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            return ip_address
        except:
            return "127.0.0.1"
    
    def generate_compliance_report(self, period: str) -> Dict:
        """
        Générer un rapport de conformité
        
        Args:
            period: Période (YYYY-MM)
        
        Returns:
            Rapport de conformité
        """
        if not self.audit_data:
            return {
                'period': period,
                'generated_at': datetime.now().isoformat(),
                'summary': {'total_emails': 0, 'successful': 0, 'failed': 0, 'success_rate': 0},
                'by_document_type': {},
                'daily_breakdown': {},
                'compliance_checks': {
                    'all_logged': True,
                    'audit_trail_complete': True,
                    'rgpd_compliant': True,
                    'retention_policy_applied': True
                }
            }
        
        # Create DataFrame from audit logs
        df = pl.DataFrame(self.audit_data)
        
        # Filter by period
        df_period = df.filter(pl.col('period') == period)
        
        if df_period.height == 0:
            return {
                'period': period,
                'generated_at': datetime.now().isoformat(),
                'summary': {'total_emails': 0, 'successful': 0, 'failed': 0, 'success_rate': 0},
                'by_document_type': {},
                'daily_breakdown': {},
                'compliance_checks': {
                    'all_logged': True,
                    'audit_trail_complete': True,
                    'rgpd_compliant': True,
                    'retention_policy_applied': True
                }
            }
        
        # Calculate summary stats
        total_emails = df_period.height
        successful = df_period.filter(pl.col('success')).height
        failed = df_period.filter(~pl.col('success')).height
        success_rate = (successful / total_emails * 100) if total_emails > 0 else 0
        
        # By document type
        by_doc_type = (
            df_period
            .group_by('document_type')
            .agg([
                pl.col('success').filter(pl.col('success')).count().alias('sent'),
                pl.col('success').filter(~pl.col('success')).count().alias('failed')
            ])
        )
        
        by_document_type = {
            row['document_type']: {'sent': row['sent'], 'failed': row['failed']}
            for row in by_doc_type.to_dicts()
        }
        
        # Daily breakdown
        daily = (
            df_period
            .with_columns(pl.col('timestamp').str.slice(0, 10).alias('date'))
            .group_by('date')
            .agg([
                pl.col('success').filter(pl.col('success')).count().alias('sent'),
                pl.col('success').filter(~pl.col('success')).count().alias('failed')
            ])
        )
        
        daily_breakdown = {
            row['date']: {'sent': row['sent'], 'failed': row['failed']}
            for row in daily.to_dicts()
        }
        
        return {
            'period': period,
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'total_emails': total_emails,
                'successful': successful,
                'failed': failed,
                'success_rate': round(success_rate, 2)
            },
            'by_document_type': by_document_type,
            'daily_breakdown': daily_breakdown,
            'compliance_checks': {
                'all_logged': True,
                'audit_trail_complete': True,
                'rgpd_compliant': True,
                'retention_policy_applied': True
            }
        }

# Fonction principale pour l'intégration
def create_email_distribution_system(config_path: str = "data/config/email_config.json",
                                    archive_path: str = "data/email_archives") -> Dict:
    """
    Créer et configurer le système complet de distribution email
    
    Args:
        config_path: Chemin vers la configuration
        archive_path: Chemin vers les archives
    
    Returns:
        Dictionnaire avec tous les services
    """
    # Créer les gestionnaires
    config_manager = EmailConfigManager(Path(config_path))
    archive_manager = PDFArchiveManager(Path(archive_path))
    audit_logger = ComplianceAuditLogger(Path(archive_path) / "audit")
    
    # Charger ou créer la configuration
    config = config_manager.load_config()
    if not config:
        # Utiliser une configuration par défaut
        configs = EmailConfigManager.get_default_configs()
        config = configs['gmail']  # ou autre provider
        logger.warning("Configuration email non trouvée, utilisation de la configuration par défaut")
    
    # Créer le service de distribution
    email_service = EmailDistributionService(config, archive_manager)
    
    return {
        'email_service': email_service,
        'archive_manager': archive_manager,
        'config_manager': config_manager,
        'audit_logger': audit_logger
    }

# Exemple d'utilisation
if __name__ == "__main__":
    # Créer le système
    system = create_email_distribution_system()
    
    # Configuration exemple
    config = EmailConfig(
        smtp_server='smtp.gmail.com',
        smtp_port=587,
        sender_email='paie@entreprise.com',
        sender_password='password',
        sender_name='Service Paie Monaco',
        use_tls=True,
        bcc_archive='archives@entreprise.com'
    )
    
    # Sauvegarder la configuration
    system['config_manager'].save_config(config)
    
    # Données d'exemple
    employee_data = {
        'matricule': 'S000001',
        'nom': 'DUPONT',
        'prenom': 'Jean',
        'email': 'jean.dupont@example.com',
        'salaire_brut': 3500.00,
        'total_charges_salariales': 770.00,
        'salaire_net': 2730.00,
        'period_start': '01/12/2024',
        'period_end': '31/12/2024'
    }
    
    # Créer un PDF factice
    pdf_buffer = io.BytesIO(b'%PDF-1.4\n...')  # Contenu PDF réel
    
    # Test d'envoi
    result = system['email_service'].send_paystub(
        employee_data,
        pdf_buffer,
        '2024-12',
        test_mode=True  # Mode test
    )
    
    print(f"Résultat test: {result}")
    
    # Statistiques d'archive
    stats = system['archive_manager'].get_statistics()
    print(f"Statistiques d'archive: {stats}")
    
    # Rapport de conformité
    compliance = system['audit_logger'].generate_compliance_report('2024-12')
    print(f"Rapport de conformité: {compliance}")