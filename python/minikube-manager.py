#!/usr/bin/env python3
"""
Minikube Manager

This Python script replicates the functionality of the provided shell script.
It performs tasks such as verifying the user, initializing directories, backing up
Kubernetes resources, installing/upgrading/stopping/deleting Minikube and kubectl,
configuring the cluster (namespaces and addons), and providing an interactive menu
for the user.

Console messages are displayed without timestamps or log level information,
while detailed logs (including timestamps, log levels, and backend details) are written
to a log file named the same as this script (with a .log extension).

Each section and function is documented for clarity.
"""

import os
import sys
import subprocess
import logging
import time
import getpass
import re
import tarfile
import datetime
import shutil
import base64

# Configuration
EXPECTED_USER = "muser"
LOG_DIR = "/opt/minikube/scripts/python/logs"
BACKUP_DIR = "/opt/minikube/backups"
VELERO_BACKUP_DIR = "/opt/minikube/velero"
REQUIRED_NAMESPACES = ["application", "database", "streaming", "monitoring", "observability", "velero"]
MINIKUBE_START_CMD = ("minikube start --driver=docker --apiserver-ips=192.168.29.223 "
                      "--extra-config=apiserver.enable-admission-plugins=NamespaceLifecycle,LimitRanger,ServiceAccount")

# Global logger; will be configured in setup_logging()
logger = None

##################################################################
##                      Initial Functions                       ##
##################################################################
def setup_logging():
    """
    Set up logging with two handlers:
      - Console handler: displays only plain user-relevant messages (INFO level)
      - File handler: writes all log messages (DEBUG level and above) with timestamps and log level.
    The log file is named after this script with a '.log' extension and is placed in LOG_DIR.
    """
    global logger
    logger = logging.getLogger("minikube_manager")
    logger.setLevel(logging.DEBUG)  # Log all levels to file

    os.makedirs(LOG_DIR, exist_ok=True)
    script_name = os.path.basename(__file__)
    log_filename = os.path.splitext(script_name)[0] + ".log"
    log_file_path = os.path.join(LOG_DIR, log_filename)

    # File handler: detailed logging (DEBUG)
    file_handler = logging.FileHandler(log_file_path)
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)

    # Console handler: only INFO and above (no extra details)
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("\nLogger initialized.")

def initialize_directories():
    """
    Ensure that required directories exist:
      - LOG_DIR, BACKUP_DIR, VELERO_BACKUP_DIR.
    """
    for directory in [LOG_DIR, BACKUP_DIR, VELERO_BACKUP_DIR]:
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
    logger.info("Directories initialized.")

def log_message(message):
    """
    Log a message using logger.info().
    """
    logger.info(message)


def verify_user():
    """
    Verify that the script is executed as the expected user.
    """
    if getpass.getuser() != EXPECTED_USER:
        log_message(f"ERROR: This script must be executed as user '{EXPECTED_USER}'")
        sys.exit(1)
    log_message("User verification passed.")

##################################################################
##                        Menu Functions                        ##
##################################################################
##--------------------- 1. Install Minikube --------------------##
def install_minikube():
    """
    Install or upgrade Minikube and kubectl as needed.
    """
    if shutil.which("minikube"):
        current = get_current_version()
        latest = get_latest_version()
        log_message(f"\nMinikube already installed (Version: {current})")
        if current != latest:
            log_message(f"New version available: {latest}")
            reply = input("Would you like to upgrade Minikube? [y/N] ").strip().lower()
            if reply.startswith("y"):
                perform_update()
                current = get_current_version()  # Refresh version
            else:
                reply = input("Start Minikube with the current version? [y/N] ").strip().lower()
                if reply.startswith("y"):
                    start_minikube()
        else:
            reply = input("Start Minikube? [y/N] ").strip().lower()
            if reply.startswith("y"):
                start_minikube()
    else:
        log_message("\nInstalling Minikube...")
        run_command("curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64")
        run_command("sudo install minikube-linux-amd64 /usr/local/bin/minikube")
        run_command("sudo chmod +x /usr/local/bin/minikube")
        os.remove("minikube-linux-amd64")
        log_message("\nMinikube installation complete.")

    if shutil.which("kubectl"):
        output = run_command("kubectl version --client=true", capture_output=True)
        current_kubectl = re.search(r'Client Version:\s*([^\s]+)', output)
        current_kubectl = current_kubectl.group(1) if current_kubectl else "unknown"
        latest_kubectl = run_command("curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt")
        if current_kubectl == latest_kubectl:
            log_message(f"\nThe latest version of kubectl is installed (Version: {current_kubectl})")
        else:
            log_message(f"\nUpdated kubectl version available.\nCurrent: {current_kubectl}\nLatest: {latest_kubectl}")
            reply = input("Would you like to upgrade kubectl? [y/N] ").strip().lower()
            if reply.startswith("y"):
                log_message("\nUpgrading kubectl...")
                run_command(f"curl -LO https://storage.googleapis.com/kubernetes-release/release/{latest_kubectl}/bin/linux/amd64/kubectl")
                run_command("sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl")
                os.remove("kubectl")
                log_message("\nKubectl upgraded.")
            else:
                log_message("\nKubectl upgrade is required to continue. Exiting.")
                sys.exit(1)
    else:
        log_message("\nInstalling kubectl...")
        latest_kubectl = run_command("curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt")
        run_command(f"curl -LO https://storage.googleapis.com/kubernetes-release/release/{latest_kubectl}/bin/linux/amd64/kubectl")
        run_command("sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl")
        os.remove("kubectl")
        log_message("\nKubectl installation complete.")

    final_minikube = get_current_version()
    final_kubectl_out = run_command("kubectl version --client=true", capture_output=True)
    print("\n" + "-" * 71)
    print("            INSTALLATION/UPGRADATION COMPLETED SUCCESSFULLY")
    print("-" * 71)
    print(f"Minikube Version: {final_minikube}")
    print(f"Kubectl Version: {final_kubectl_out}")
    print("-" * 71 + "\n")

##--------------------- 2. Minikube Status ---------------------##
def show_status():
    """
    Display enhanced status information for the Minikube cluster.
    If the 'minikube status --format='{{.Host}}'' command fails (e.g., when the cluster is deleted),
    display a friendly message.
    """
    if not shutil.which("minikube"):
        log_message("Minikube is not installed.")
        return
    current = get_current_version()
    latest = get_latest_version()
    status_output = run_command("minikube status --format='{{.Host}}'", check=False)
    # Check if the output is empty or contains "not found" (case-insensitive)
    if not status_output or "not found" in status_output.lower():
        log_message("Minikube is installed, but no cluster exists. (Deleted or never created)")
        print("\n" + "-" * 110)
        print("                                              MINIKUBE CLUSTER INFORMATION")
        print("-" * 110)
        print(f"Minikube Version : {current}")
        print(f"Latest Version   : {latest}")
        print("Cluster IP       : Inactive")
        print("Status           : Minikube Cluster Deleted")
        print("-" * 110 + "\n")
        return

    if status_output == "Running":
        cluster_ip = run_command("minikube ip", check=False)
        mstatus = run_command("minikube status | grep -E '^(type|host|kubelet|apiserver|kubeconfig):' | awk -F': ' '{print $1 \"=\" $2}' | tr '\n' '; '", check=False)
        print("\n" + "-" * 110)
        print("                                              MINIKUBE CLUSTER INFORMATION")
        print("-" * 110)
        print(f"Minikube Version : {current}")
        print(f"Latest Version   : {latest}")
        print(f"Cluster IP       : {cluster_ip}")
        print(f"Status           : {mstatus}")
        print("-" * 110 + "\n")
    elif status_output == "Stopped":
        mstatus = run_command("minikube status | grep -E '^(type|host|kubelet|apiserver|kubeconfig):' | awk -F': ' '{print $1 \"=\" $2}' | tr '\n' '; '", check=False)
        print("\n" + "-" * 110)
        print("                                              MINIKUBE CLUSTER INFORMATION")
        print("-" * 110)
        print(f"Minikube Version : {current}")
        print(f"Latest Version   : {latest}")
        print("Cluster IP       : Inactive")
        print(f"Status           : {mstatus}")
        print("-" * 110 + "\n")

##---------------------- 3. Start Minikube ---------------------##
def start_minikube():
    """
    Start the Minikube cluster if not already running.
    """
    if not shutil.which("minikube"):
        log_message("Minikube is not installed. Please install it first.")
        return
    status = run_command("minikube status --format='{{.Host}}'", check=False)
    if status == "Running":
        log_message("Minikube is already running. Exiting.")
        #sys.exit(0)
        return
    current = get_current_version()
    latest = get_latest_version()
    if current != latest:
        log_message(f"Update available: {latest}")
        reply = input("Update before starting? [y/N] ").strip().lower()
        if reply.startswith("y"):
            perform_update()
    log_message("\nStarting cluster...")
    if run_command(MINIKUBE_START_CMD, check=False):
        post_start_configuration()
    else:
        log_message("ERROR: Cluster start failed")
        #sys.exit(1)
        return

##---------------------- 4. Stop Minikube ----------------------##
def stop_minikube():
    """
    Stop the Minikube cluster (backup resources before stopping).
    """
    if not shutil.which("minikube"):
        log_message("Minikube is not installed. Please install it first.")
        return
    status = run_command("minikube status --format='{{.Host}}'", check=False)
    if status == "Stopped":
        log_message("Minikube is already stopped. Exiting.")
        return
        #sys.exit(0)
    elif status == "Running":
        backup_resources()
        log_message("\nStopping cluster...")
        run_command("minikube stop")
    else:
        log_message("Minikube is not running or already deleted. Exiting.")
        return

##-------------------- 5. Upgrade Minikube ---------------------##
def perform_update():
    """
    Upgrade Minikube by backing up resources, downloading the latest binary,
    installing it, and restarting the cluster.
    """
    current = get_current_version()
    latest = get_latest_version()
    if current == latest:
        log_message(f"Minikube is already at the latest version ({latest}). No upgrade needed.")
        #sys.exit(0)
        return
    log_message("\nInitiating Minikube update...")
    backup_resources()
    log_message("\nDownloading latest binary...")
    run_command("curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64")
    run_command("sudo install minikube-linux-amd64 /usr/local/bin/minikube")
    run_command("sudo chmod +x /usr/local/bin/minikube")
    os.remove("minikube-linux-amd64")
    log_message("\nRestarting cluster...")
    if run_command("minikube start", check=False):
        post_start_configuration()
    else:
        log_message("\nUpgrade failed. Performing clean installation...")
        run_command("minikube delete && minikube start")
        post_start_configuration()

##--------------------- 6. Delete Minikube ---------------------##
def delete_minikube():
    """
    Delete the Minikube cluster, backing up if the cluster is running.
    """
    if not shutil.which("minikube"):
        log_message("Minikube is not installed. Exiting.")
        return
    try:
        status = run_command("minikube status --format='{{.Host}}'", check=False)
    except Exception:
        log_message("Minikube is installed but no cluster exists. Exiting delete process.")
        return
    if status == "Running":
        log_message("Performing backup before deletion...")
        backup_resources()
    else:
        log_message("Cluster is stopped. Deleting without backup...")
    log_message("\nDeleting cluster...")
    run_command("minikube delete")

##-------------------- 7. Backup Resources ---------------------##
def backup_resources():
    """
    Back up Kubernetes resources and Minikube configuration.
    """
    backup_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"backup_{backup_timestamp}")
    try:
        os.makedirs(backup_path, exist_ok=True)
    except Exception as e:
        log_message(f"ERROR: Failed to create backup directory: {e}")
        sys.exit(1)
    log_message("\nStarting resource backup...")

    namespaced_resources = ["pods", "deployments", "services", "configmaps", "secrets",
                            "ingresses", "networkpolicies", "pvc", "statefulsets", "daemonsets",
                            "jobs", "cronjobs", "replicasets"]
    ns_output = run_command("kubectl get namespaces -o jsonpath='{.items[*].metadata.name}'")
    for ns in ns_output.split():
        ns_dir = os.path.join(backup_path, "namespaces", ns)
        os.makedirs(ns_dir, exist_ok=True)
        for resource in namespaced_resources:
            cmd = f"kubectl get {resource} -n {ns} -o yaml > {os.path.join(ns_dir, resource)}.yaml 2>/dev/null"
            subprocess.run(cmd, shell=True)
    run_command("minikube stop 2>/dev/null", check=False)
    minikube_config_dir = os.path.join("/home", EXPECTED_USER, ".minikube")
    archive_path = os.path.join(backup_path, "minikube_config.tar.gz")
    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(minikube_config_dir, arcname=".minikube")
    except Exception as e:
        log_message(f"ERROR: Failed to backup Minikube config: {e}")
    log_message(f"\nBackup completed: {backup_path}")

##-------------------- 8. Restore Resources --------------------##

##-------------------- 9. Uninstall Minikube -------------------##
def uninstall_minikube():
    """
    Uninstall Minikube and Kubectl completely after user confirmation.
    """
    print("\033[1;31mATTENTION!!\033[0m \033[33mMinikube and Kubectl will be uninstalled completely. Ensure you have taken a backup first.\033[0m\n")
    reply = input("Do you want to proceed with the uninstallation? [y/N]: ").strip().lower()
    if not reply.startswith("y"):
        print("Uninstallation cancelled. Please take a backup before proceeding.")
        return
    log_message("\nStarting complete uninstallation of Minikube and Kubectl...")
    if not shutil.which("minikube"):
        log_message("Minikube is already uninstalled.")
    else:
        log_message("Deleting Minikube cluster...")
        run_command("minikube delete --all --purge", check=False)
        log_message("Removing Minikube binaries and configuration...")
        run_command("sudo rm -f /usr/local/bin/minikube /usr/bin/minikube", check=False)
        shutil.rmtree(os.path.join("/home", EXPECTED_USER, ".minikube"), ignore_errors=True)
        run_command("sudo rm -rf /var/lib/minikube", check=False)
        shutil.rmtree(os.path.join("/home", EXPECTED_USER, ".cache/minikube"), ignore_errors=True)
        run_command("rm -rf /tmp/minikube*", check=False)
        run_command("sudo rm -f /etc/systemd/system/minikube.service /var/log/minikube.log", check=False)
        log_message("Minikube uninstalled successfully.")
    if not shutil.which("kubectl"):
        log_message("Kubectl is already uninstalled.")
    else:
        log_message("Removing Kubectl binaries and configuration...")
        run_command("sudo rm -f /usr/local/bin/kubectl /usr/bin/kubectl", check=False)
        shutil.rmtree(os.path.join("/home", EXPECTED_USER, ".kube"), ignore_errors=True)
        run_command("sudo rm -rf /var/lib/kubelet", check=False)
        run_command("sudo rm -f /var/log/kubelet.log", check=False)
        log_message("Kubectl uninstalled successfully.")
    log_message("Complete uninstallation finished.")


##################################################################
##                       Other Functions                        ##
##################################################################
def run_command(cmd, capture_output=True, check=True, input_text=None):
    """
    Execute a shell command using subprocess.run.
    Returns the command's standard output as a string.
    Detailed backend messages are logged at DEBUG level.
    """
    logger.debug(f"Executing command: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=capture_output, text=True, input=input_text)
        if check and result.returncode != 0:
            logger.error(f"Command failed ({cmd}): {result.stderr}")
            sys.exit(1)
        logger.debug(f"Command output: {result.stdout.strip()}")
        return result.stdout.strip()
    except Exception as e:
        logger.error(f"Exception during command '{cmd}': {e}")
        sys.exit(1)

def get_current_version():
    """
    Retrieve the current installed version of Minikube.
    """
    output = run_command("minikube version 2>/dev/null")
    match = re.search(r"minikube version:\s*([\S]+)", output)
    return match.group(1) if match else "unknown"

def get_latest_version():
    """
    Retrieve the latest available version of Minikube.
    """
    output = run_command("minikube update-check 2>/dev/null")
    match = re.search(r"LatestVersion:\s*([\S]+)", output)
    return match.group(1) if match else "unknown"

def post_start_configuration():
    """
    Configure Docker environment for Minikube, ensure required namespaces exist,
    enable addons, and display cluster information.
    """
    log_message("\nConfiguring Docker environment...")
    docker_env_output = run_command("minikube docker-env", capture_output=True)

    # Parse lines starting with 'export'
    for line in docker_env_output.splitlines():
        line = line.strip()
        if line.startswith("export "):
            # Remove "export " and split at the first '=' character.
            key_value = line[len("export "):]
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                # Strip any surrounding quotes from the value.
                value = value.strip().strip('"')
                os.environ[key] = value
                logger.debug(f"Set env var {key}={value}")
    
    log_message("\nVerifying required namespaces...")
    for ns in REQUIRED_NAMESPACES:
        if subprocess.run(f"kubectl get namespace {ns}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
            run_command(f"kubectl create namespace {ns}")
            log_message(f"Created namespace: {ns}")
        else:
            logger.debug(f"Namespace exists: {ns}")
    
    enable_addons()
    display_cluster_info()

def enable_addons():
    """
    Enable selected Minikube addons.
    """
    addons = ["ingress", "metrics-server", "dashboard"]
    log_message("\nEnabling addons...")
    for addon in addons:
        run_command(f"minikube addons enable {addon}")
        logger.debug(f"Enabled addon: {addon}")

def display_cluster_info():
    """
    Display cluster information.
    """
    current = get_current_version()
    latest = get_latest_version()
    cluster_ip = run_command("minikube ip")
    status = run_command("minikube status | grep -E '^(type|host|kubelet|apiserver|kubeconfig):' | awk -F': ' '{print $1 \"=\" $2}' | tr '\n' '; '")
    
    print("\n" + "-" * 120)
    print("                                              MINIKUBE CLUSTER INFORMATION")
    print("-" * 120)
    print(f"Minikube Version  : {current}")
    print(f"Latest Version    : {latest}")
    print(f"Cluster IP        : {cluster_ip}")
    print(f"Status            : {status}")
    print("-" * 120 + "\n")

def show_menu():
    """
    Display an interactive menu for user operations.
    """
    options = [
        "Install Minikube", "Minikube Status", "Start Minikube", "Stop Minikube",
        "Upgrade Minikube", "Delete Minikube", "Backup Resources", "Restore Resources",
        "Uninstall Minikube", "Quit"
    ]
    print("\nSelect operation:")
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt}")
    try:
        choice = int(input("\nEnter choice number: ").strip())
    except ValueError:
        print("Invalid input. Please enter a number.")
        return
    if choice == 1:
        install_minikube()
    elif choice == 2:
        show_status()
    elif choice == 3:
        start_minikube()
    elif choice == 4:
        stop_minikube()
    elif choice == 5:
        perform_update()
    elif choice == 6:
        delete_minikube()
    elif choice == 7:
        backup_resources()
    elif choice == 8:
        log_message("Restore Resources option selected (not implemented).")
    elif choice == 9:
        uninstall_minikube()
    elif choice == 10:
        sys.exit(0)
    else:
        print("Invalid option.")

def main():
    """
    Main execution flow: verify user, initialize directories, log startup,
    and enter an interactive loop displaying the menu.
    """
    verify_user()
    initialize_directories()
    log_message("Starting Minikube Manager")
    while True:
        show_menu()
        #print("\nOperation completed. Ready for next command.\n")
        #log_message("Operation completed. Ready for next command.\n")

if __name__ == "__main__":
    setup_logging()
    main()
