#!/usr/bin/env python3

import os
import sys
import logging
import base64
import getpass
import yaml
from datetime import datetime, timedelta
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
#from cryptography.x509.oid import NameOID, NameAttribute
#from cryptography.x509 import Name, CertificateBuilder, random_serial_number
from cryptography.x509 import Name, CertificateBuilder, random_serial_number, NameOID, NameAttribute

# ======================
# Configuration
# ======================
NAMESPACE_DIR = "/opt/minikube/namespaces/kubernetes-dashboard"
CERTS_DIR = os.path.join(NAMESPACE_DIR, "certs")
SECRETS_FILE = os.path.join(NAMESPACE_DIR, "kubernetes-dashboard-secret.yaml")

SCRIPT_NAME = os.path.basename(__file__)
LOG_DIR = "/opt/minikube/scripts/logs"
LOG_FILE = os.path.join(LOG_DIR, f"{os.path.splitext(SCRIPT_NAME)[0]}.log")

# ======================
# Logging Setup
# ======================
def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # File handler with timestamp and level
    file_handler = logging.FileHandler(LOG_FILE)
    file_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_format)

    # Stream handler without timestamp/level
    stream_handler = logging.StreamHandler()
    stream_format = logging.Formatter("%(message)s")
    stream_handler.setFormatter(stream_format)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger

logger = setup_logging()

# ======================
# Security Checks
# ======================
def verify_user():
    if getpass.getuser() != "muser":
        logger.error("ERROR: Script must be executed by user 'muser'")
        sys.exit(1)

# ======================
# Certificate Generation
# ======================
def generate_certificates():
    try:
        # Generate private key
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Generate self-signed cert
        #subject = Name([NameAttribute(NameOID.COMMON_NAME, "kubernetes-dashboard")])
        #subject = Name([NameOID.COMMON_NAME, "kubernetes-dashboard"])
        subject = Name([
            NameAttribute(NameOID.COMMON_NAME, "kubernetes-dashboard")
        ])

        issuer = Name([  # Issuer needs to be a Name object too
            NameAttribute(NameOID.COMMON_NAME, "kubernetes-dashboard")
        ])

        cert = (
            CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=365))
            .sign(key, hashes.SHA256(), default_backend())
        )

        return (
            cert.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
    except Exception as e:
        logger.error(f"Certificate generation failed: {str(e)}")
        sys.exit(1)

# ======================
# File Operations
# ======================
def backup_existing_certs():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    for cert_file in ["tls.crt", "tls.key"]:
        src = os.path.join(CERTS_DIR, cert_file)
        if os.path.exists(src):
            dest = os.path.join(CERTS_DIR, f"{cert_file}.bak_{timestamp}")
            os.rename(src, dest)

def write_new_certs(cert_pem, key_pem):
    os.makedirs(CERTS_DIR, exist_ok=True)
    with open(os.path.join(CERTS_DIR, "tls.crt"), "wb") as f:
        f.write(cert_pem)
    with open(os.path.join(CERTS_DIR, "tls.key"), "wb") as f:
        f.write(key_pem)

# ======================
# YAML File Management
# ======================
def create_secrets_file(cert_b64, key_b64):
    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "kubernetes-dashboard-secret",
            "namespace": "kubernetes-dashboard"
        },
        "type": "kubernetes.io/tls",
        "data": {
            "tls.crt": cert_b64,
            "tls.key": key_b64
        }
    }
    
    with open(SECRETS_FILE, "w") as f:
        yaml.dump(secret, f, default_flow_style=False)
    logger.info(f"Created new secrets file at {SECRETS_FILE}")

def update_secrets_file(cert_b64, key_b64):
    with open(SECRETS_FILE, "r") as f:
        secret = yaml.safe_load(f)
    
    secret["data"]["tls.crt"] = cert_b64
    secret["data"]["tls.key"] = key_b64
    
    with open(SECRETS_FILE, "w") as f:
        yaml.dump(secret, f, default_flow_style=False)
    logger.info(f"Updated existing secrets file at {SECRETS_FILE}")

# ======================
# Main Logic
# ======================
def main():
    verify_user()
    
    # Generate new certificates
    cert_pem, key_pem = generate_certificates()
    cert_b64 = base64.b64encode(cert_pem).decode("utf-8")
    key_b64 = base64.b64encode(key_pem).decode("utf-8")
    
    # Handle existing files
    if os.path.exists(SECRETS_FILE):
        logger.info("Existing secrets file detected")
        choice = input("Update existing file? [y/N]: ").strip().lower()
        
        if choice == "y":
            backup_existing_certs()
            write_new_certs(cert_pem, key_pem)
            update_secrets_file(cert_b64, key_b64)
            logger.info("Secrets updated with new certificates")
        else:
            logger.info("Using existing certificates (no changes made)")
    else:
        os.makedirs(NAMESPACE_DIR, exist_ok=True)
        write_new_certs(cert_pem, key_pem)
        create_secrets_file(cert_b64, key_b64)

if __name__ == "__main__":
    main()
