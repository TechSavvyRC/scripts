#!/usr/bin/env python3
"""
Simplified Velero CLI installer/uninstaller for Minikube.

This script installs the Velero CLI (if not already installed) and deploys Velero resources on a Minikube cluster,
or uninstalls them based on user choice. It does not perform any upgrade or backup of existing resources.
"""

import os
import sys
import subprocess
import logging
import getpass
import shutil
import json

# ANSI escape codes for colors.
BOLD_RED = "\033[1;31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

def print_attention_message():
    """
    Prints an attention note with "ATTENTION" in bold red and the message in yellow.
    """
    note = (
        "------------------------------------------------------------------------------------------------------\n"
        f"{BOLD_RED}ATTENTION{RESET}: {YELLOW}\n"
        "This script is designed exclusively for performing the installation and uninstallation of the\n"
        "Velero CLI, as well as the deployment and removal of Velero resources from a Kubernetes/Minikube\n"
        "cluster. Please note that this script does not create backups of any existing resources within\n"
        "the cluster. As such, it is important to exercise caution when using this script. Additionally,\n"
        "this script does not modify or update any existing Velero CLI setup or resources within the cluster.\n"
        f"{RESET}------------------------------------------------------------------------------------------------------"
    )
    print(note)

def setup_logging(log_file):
    """
    Sets up logging with a file handler (timestamps and levels) and a console handler.
    Returns the logger.
    """
    logger = logging.getLogger("velero_install")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter('%(message)s')
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)
    return logger

def check_user(logger):
    """
    Checks that the script is run by 'muser' and exits otherwise.
    """
    if getpass.getuser() != "muser":
        logger.error("Error: This script must be executed by 'muser'.")
        sys.exit(1)
    logger.info("User check passed: running as 'muser'.")

def ensure_directories(logger):
    """
    Ensures the log directory exists, creating it if needed.
    """
    logs_dir = "/opt/minikube/scripts/python/logs"
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
            logger.info("Created logs directory: " + logs_dir)
        except Exception as e:
            logger.error("Failed to create logs directory: " + str(e))
            sys.exit(1)

def change_working_directory(logger):
    """
    Changes to the /opt/minikube/namespaces/velero/ directory and exits if it fails.
    """
    target_dir = "/opt/minikube/namespaces/velero/"
    try:
        os.chdir(target_dir)
        logger.info("Changed directory to " + target_dir)
    except Exception as e:
        logger.error("Failed to change directory to " + target_dir + ": " + str(e))
        sys.exit(1)

def check_minikube_status(logger):
    """
    Checks that Minikube is running and exits if not.
    """
    try:
        result = subprocess.run(["minikube", "status"], capture_output=True, text=True)
        if result.returncode != 0 or "Running" not in result.stdout:
            logger.error("Minikube is not running. Please start Minikube (e.g. 'minikube start') and re-run this script.")
            sys.exit(1)
        logger.info("Minikube status: Running")
    except Exception as e:
        logger.error("Error checking Minikube status: " + str(e))
        sys.exit(1)

def check_required_files(logger):
    """
    Verifies that 'public.crt' and 'minio-credentials.txt' exist; exits if not.
    """
    for file in ["public.crt", "minio-credentials.txt"]:
        if not os.path.isfile(file):
            logger.error(f"Required file '{file}' is missing in {os.getcwd()}. Please ensure it exists.")
            sys.exit(1)
    logger.info("Required files are present in the directory.")

def fetch_host_ip(logger):
    """
    Fetches the HOST_IP using a shell command; returns the first reachable IP.
    """
    cmd = ("for ip in $(getent hosts techsavvyrc | awk '{print $1}'); "
           "do ping -c 1 -W 1 $ip >/dev/null 2>&1 && echo $ip && break; done")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        host_ip = result.stdout.strip()
        if not host_ip:
            logger.error("Failed to fetch HOST_IP. Ensure that 'techsavvyrc' resolves and is reachable.")
            sys.exit(1)
        logger.info("Fetched HOST_IP: " + host_ip)
        return host_ip
    except Exception as e:
        logger.error("Error fetching HOST_IP: " + str(e))
        sys.exit(1)

def fetch_latest_version(logger):
    """
    Fetches the latest Velero version from the GitHub API and returns it.
    """
    try:
        result = subprocess.run(["curl", "-s", "https://api.github.com/repos/vmware-tanzu/velero/releases/latest"],
                                  capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        latest_version = data["tag_name"]
        logger.info("Fetched latest Velero version: " + latest_version)
        return latest_version
    except Exception as e:
        logger.error("Failed to fetch latest Velero version: " + str(e))
        sys.exit(1)

def install_velero(logger, version):
    """
    Downloads and installs the Velero CLI for the given version.
    Moves the binary to /usr/local/bin.
    """
    try:
        tarball = f"velero-{version}-linux-amd64.tar.gz"
        download_url = f"https://github.com/vmware-tanzu/velero/releases/download/{version}/{tarball}"
        logger.info("Downloading Velero from " + download_url)
        subprocess.run(["curl", "-LO", download_url], check=True)
        logger.info("Extracting tarball " + tarball)
        subprocess.run(["tar", "xvf", tarball], check=True)
        binary_path = f"velero-{version}-linux-amd64/velero"
        logger.info("Installing Velero CLI to /usr/local/bin/velero (requires sudo)")
        subprocess.run(["sudo", "mv", binary_path, "/usr/local/bin/velero"], check=True)
        os.remove(tarball)
        subprocess.run(["rm", "-rf", f"velero-{version}-linux-amd64"], check=True)
        logger.info("Velero CLI installed successfully. Installed version: " + version)
    except Exception as e:
        logger.error("Failed to install Velero CLI: " + str(e))
        sys.exit(1)

def deploy_velero_resource(logger, host_ip):
    """
    Deploys Velero resources on the Minikube cluster.
    Prompts for a bucket name (with default) and deploys using that bucket.
    """
    default_bucket = "minikubevelero"
    choice = input(f"The current bucket name is '{default_bucket}'. Do you want to use it? (yes/no): ").strip().lower()
    if choice not in ["yes", "y"]:
        bucket = input("Please enter the desired bucket name (must already exist in MinIO): ").strip()
    else:
        bucket = default_bucket
    logger.info(f"Using bucket: {bucket} (Note: the bucket must already exist in MinIO, or deployment will fail.)")
    install_cmd = [
        "velero", "install",
        "--provider", "aws",
        "--plugins", "velero/velero-plugin-for-aws:v1.8.0",
        "--bucket", bucket,
        "--secret-file", "./minio-credentials.txt",
        "--use-volume-snapshots=false",
        "--backup-location-config", f"region=minio,s3ForcePathStyle=true,s3Url=https://{host_ip}:9000,insecureSkipTLSVerify=true",
        "--cacert", "./public.crt"
    ]
    try:
        logger.info("Deploying Velero resource with the following command:")
        logger.info(" ".join(install_cmd))
        subprocess.run(install_cmd, check=True)
        logger.info("Velero resource deployed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error("Velero resource deployment failed: " + str(e))
        sys.exit(1)

def verify_velero_deployment(logger):
    """
    Verifies deployment by creating a test backup and displays example backup/restore commands.
    """
    test_cmd = ["velero", "backup", "create", "test-backup", "--include-namespaces", "default"]
    try:
        logger.info("Verifying Velero deployment by creating a test backup...")
        subprocess.run(test_cmd, check=True)
        logger.info("Test backup created successfully.")
        logger.info("\nVelero resource is deployed and ready for use on the Minikube cluster.")
        logger.info("\nExample Backup Commands:")
        logger.info("  1. Backup a specific namespace:")
        logger.info("     velero backup create my-backup --include-namespaces mynamespace")
        logger.info("  2. Backup the entire cluster:")
        logger.info("     velero backup create full-backup")
        logger.info("  3. Backup only pods:")
        logger.info("     velero backup create pods-backup --include-resources pods")
        logger.info("  4. Backup only services:")
        logger.info("     velero backup create services-backup --include-resources services")
        logger.info("  5. Backup only statefulsets:")
        logger.info("     velero backup create statefulsets-backup --include-resources statefulsets")
        logger.info("  6. Backup only deployments:")
        logger.info("     velero backup create deployments-backup --include-resources deployments")
        logger.info("\nExample Restore Commands:")
        logger.info("  a. Restore from a backup:")
        logger.info("     velero restore create --from-backup my-backup")
        logger.info("  b. Restore a specific namespace from a backup:")
        logger.info("     velero restore create --from-backup my-backup --include-namespaces mynamespace")
    except subprocess.CalledProcessError:
        logger.error("Verification failed: Test backup creation was unsuccessful.")
        logger.error("Please check Velero Pod logs using 'kubectl get pods -n velero' and 'kubectl logs -f <Velero_Pod_Name> -n velero'.")
        sys.exit(1)

def uninstall_velero(logger):
    """
    Uninstalls Velero resources by deleting the Velero namespace and removing the Velero CLI.
    """
    try:
        logger.info("Uninstalling Velero resources...")
        subprocess.run(["kubectl", "delete", "namespace", "velero"], check=False)
        logger.info("Velero namespace deletion initiated.")
        logger.info("Removing Velero CLI from /usr/local/bin (requires sudo)...")
        subprocess.run(["sudo", "rm", "-f", "/usr/local/bin/velero"], check=False)
        logger.info("Velero CLI and resources uninstalled successfully.")
    except Exception as e:
        logger.error("Uninstallation failed: " + str(e))
        sys.exit(1)

def perform_installation(logger):
    """
    Executes the installation workflow by checking the environment and installing the Velero CLI and resources.
    If the Velero CLI is already installed, it is reused; if Velero resources exist, deployment is skipped.
    """
    check_user(logger)
    ensure_directories(logger)
    change_working_directory(logger)
    check_minikube_status(logger)
    check_required_files(logger)
    host_ip = fetch_host_ip(logger)
    latest_version = fetch_latest_version(logger)
    
    if not shutil.which("velero"):
        logger.info("Velero CLI not found. Installing version " + latest_version)
        install_velero(logger, latest_version)
    else:
        logger.info("Velero CLI is already installed. Skipping CLI installation.")
    
    # Check if Velero resources (deployment) already exist.
    try:
        subprocess.run(["kubectl", "get", "deployment", "velero", "-n", "velero"],
                       check=True, capture_output=True, text=True)
        logger.info("Velero resources already exist in the cluster. Skipping resource deployment.")
    except subprocess.CalledProcessError:
        logger.info("No existing Velero resources found. Proceeding with resource deployment.")
        deploy_velero_resource(logger, host_ip)
    
    verify_velero_deployment(logger)

def perform_uninstallation(logger):
    """
    Executes the uninstallation workflow by removing Velero resources and the Velero CLI.
    """
    check_user(logger)
    uninstall_velero(logger)

def main():
    """
    Main entry point that prints the attention note and interactive menu.
    Calls the installation or uninstallation workflow based on user selection.
    """
    print_attention_message()
    log_dir = "/opt/minikube/scripts/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, os.path.splitext(os.path.basename(__file__))[0] + ".log")
    logger = setup_logging(log_file)

    print("\nVelero CLI Management Menu:")
    print("  1. Installation")
    print("  2. Uninstallation")
    choice = input("Please select an option (1 or 2): ").strip()

    if choice == "1":
        logger.info("User selected Installation.")
        perform_installation(logger)
    elif choice == "2":
        logger.info("User selected Uninstallation.")
        perform_uninstallation(logger)
    else:
        logger.error("Invalid selection. Please run the script again and choose either 1 or 2.")
        sys.exit(1)

if __name__ == "__main__":
    main()
