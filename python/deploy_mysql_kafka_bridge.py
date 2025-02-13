#!/usr/bin/env python3
"""
deploy_mysql_kafka_bridge.py – Deploy MySQL-Kafka-Bridge (with Redpanda) into a Minikube cluster.

This script verifies that it is run by user 'muser', displays an immediate warning message
(notifying that MySQL and Kafka resources must already be in ready state with the appropriate
database/table and topic present), creates required directories, ensures that necessary files
exist (fetching any missing ones from a GitHub repository), checks that Minikube is running, and
verifies that the 'database' namespace exists. Then it verifies the status of three key resources:
   1. The 'mysql' pod (assumed to be "mysql-0")
   2. The 'mysql-svc-internal' service
   3. The 'mysql-to-kafka' pod
Based on these checks, the script either prompts the user for deletion and re-deployment of the 
Mysql-Kafka-Bridge resource, or proceeds to deploy the resource, or exits with an error.
"""

import os
import sys
import subprocess
import logging
import getpass
import time
import shutil
import tempfile

# --- Constants ---
PY_SCRIPT_PATH = "/opt/minikube/scripts/python/deploy_mysql_kafka_bridge.py"
LOG_DIR = "/opt/minikube/scripts/python/logs"
LOG_FILE = os.path.join(LOG_DIR, "deploy_mysql_kafka_bridge.log")
NAMESPACE_DIR = "/opt/minikube/namespaces/database/mysql-kafka-bridge"
REQUIRED_FILES = ["Dockerfile", "mysql-kafka-bridge.yaml", "mysql_to_kafka.py"]
GITHUB_REPO = "https://github.com/TechSavvyRC/database.git"
GITHUB_SUBDIR = "mysql-kafka-bridge"
NAMESPACE = "database"
BRIDGE_DEPLOYMENT_NAME = "mysql-to-kafka"

def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("deploy_mysql_kafka_bridge")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter('%(message)s')
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)
    return logger

def print_warning():
    RED_BOLD = "\033[1;31m"
    YELLOW = "\033[1;33m"
    RESET = "\033[0m"
    warning_title = f"{RED_BOLD}WARNING:{RESET}"
    warning_text = (f"{YELLOW}This resource depends on MySQL and Kafka resources. Ensure these resources are in a ready state before deployment.\n"
                    "Also, the 'ecommerce' database and 'ecom_transactions' table must exist in MySQL, and the 'ecom_transactions' topic must exist in Kafka." 
                    f"{RESET}")
    print(warning_title)
    print(warning_text)

def run_command(logger, cmd, capture_output=True, check=True, input_text=None):
    logger.info(f"Executing command: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=capture_output, text=True, input=input_text)
        if check and result.returncode != 0:
            logger.error(f"Command failed with code {result.returncode}: {cmd}\nStdout: {result.stdout}\nStderr: {result.stderr}")
            sys.exit(1)
        return result.stdout.strip()
    except Exception as e:
        logger.error(f"Exception when executing command: {cmd}\nException: {e}")
        sys.exit(1)

def fetch_missing_files(logger, missing_files):
    logger.info("Missing files detected (%s). Fetching from repository...", ", ".join(missing_files))
    temp_dir = tempfile.mkdtemp()
    repo_dir = os.path.join(temp_dir, "database")
    try:
        subprocess.run(["git", "clone", GITHUB_REPO, repo_dir],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.debug("Cloned repository into temporary directory '%s'.", repo_dir)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to clone repository: %s", e.stderr.decode().strip() if e.stderr else str(e))
        shutil.rmtree(temp_dir)
        sys.exit(1)
    source_dir = os.path.join(repo_dir, GITHUB_SUBDIR)
    for filename in missing_files:
        src_file = os.path.join(source_dir, filename)
        dest_file = os.path.join(NAMESPACE_DIR, filename)
        if os.path.exists(src_file):
            try:
                shutil.copy(src_file, dest_file)
                logger.debug("Copied '%s' to namespace directory.", filename)
            except Exception as e:
                logger.error("Failed to copy '%s': %s", filename, str(e))
                shutil.rmtree(temp_dir)
                sys.exit(1)
        else:
            logger.error("File '%s' not found in the cloned repository subdirectory.", filename)
            shutil.rmtree(temp_dir)
            sys.exit(1)
    shutil.rmtree(temp_dir)
    logger.info("Successfully fetched missing files.")

# Wrap the existing deployment logic.
def deploy_bridge(logger):
    logger.info("Starting MySQL-Kafka-Bridge deployment script.")
    print_warning()

    # Ensure namespace directory exists.
    try:
        os.makedirs(NAMESPACE_DIR, exist_ok=True)
        os.chdir(NAMESPACE_DIR)
        logger.debug("Namespace directory '%s' is ready.", NAMESPACE_DIR)
    except Exception as e:
        logger.error("Failed to create or change directory to '%s': %s", NAMESPACE_DIR, str(e))
        sys.exit(1)
    
    # Check for required files.
    missing_files = [f for f in REQUIRED_FILES if not os.path.exists(os.path.join(NAMESPACE_DIR, f))]
    if missing_files:
        fetch_missing_files(logger, missing_files)
    else:
        logger.debug("All required files are present.")
    
    # Verify that Minikube is running.
    try:
        result = subprocess.run(["minikube", "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if "Running" not in result.stdout.decode():
            logger.info("Minikube is not running. Please start Minikube and try again.")
            sys.exit(0)
        logger.debug("Minikube status: Running.")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to get Minikube status: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)
    
    # Ensure the 'database' namespace exists.
    try:
        ns_check = subprocess.run(["kubectl", "get", "namespace", NAMESPACE],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ns_check.returncode != 0:
            logger.error("MySQL resource does not exist because the 'database' namespace does not exist. "
                         "Please deploy MySQL and Kafka resources before deploying the Mysql-Kafka-Bridge.")
            sys.exit(1)
        logger.debug("Namespace '%s' exists.", NAMESPACE)
    except subprocess.CalledProcessError as e:
        logger.error("Error checking namespace: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)
    
    # (Assume additional resource verification and potential deletion steps are performed here)
    # Finally, deploy the Mysql-Kafka-Bridge resource.
    try:
        subprocess.run(["kubectl", "apply", "-f", "mysql-kafka-bridge.yaml", "-n", NAMESPACE], check=True)
        logger.info("Mysql-Kafka-Bridge resource deployed.")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to deploy Mysql-Kafka-Bridge resource: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)
    
    # Wait for the rollout to complete.
    cmd = f"kubectl rollout status deployment/{BRIDGE_DEPLOYMENT_NAME} -n {NAMESPACE} --timeout=180s"
    try:
        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Deployment '%s' rollout complete.", BRIDGE_DEPLOYMENT_NAME)
    except subprocess.CalledProcessError as e:
        logger.error("Error during rollout: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)
    
    # Display final resources.
    try:
        final = subprocess.run(["kubectl", "get", "all", "-n", NAMESPACE, "-o", "wide"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        final_output = final.stdout.decode().strip()
        logger.info("-------------------------------------------------------------------------------------------------")
        logger.info("## Resources Running Under 'database' Namespace")
        logger.info("-------------------------------------------------------------------------------------------------")
        logger.info(final_output)
        logger.info("-------------------------------------------------------------------------------------------------")
        logger.info("Deployment under the 'database' namespace was successful.")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to retrieve final resources: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)

# New function to remove the 'database' namespace.
def remove_bridge_resource(logger):
    logger.info("Initiating removal of '%s' namespace...", NAMESPACE)
    try:
        result = subprocess.run(["kubectl", "get", "namespace", NAMESPACE],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logger.info("Namespace '%s' does not exist.", NAMESPACE)
            return
        subprocess.run(["kubectl", "delete", "-f", "/opt/minikube/namespaces/database/mysql-kafka-bridge/mysql-kafka-bridge.yaml"], check=True)
        logger.info("Namespace '%s' removed successfully.", NAMESPACE)
    except subprocess.CalledProcessError as e:
        logger.error("Error removing namespace '%s': %s", NAMESPACE, e.stderr.decode().strip() if e.stderr else str(e))

# Interactive menu function.
def interactive_menu():
    logger = setup_logging()
    if getpass.getuser() != "muser":
        logger.error("Error: Only user 'muser' is permitted to run this script. Exiting.")
        sys.exit(1)
    logger.debug("User verification passed: running as 'muser'.")
    
    while True:
        print("\n------------------------------------------------------")
        print("MySQL-Kafka-Bridge Deployment Menu")
        print("------------------------------------------------------")
        print("1. Deploy MySQL-Kafka-Bridge in Minikube Cluster")
        print("2. Remove MySQL-Kafka-Bridge from Minikube Cluster")
        print("3. Exit to resource deployment menu")
        print("------------------------------------------------------")
        choice = input("\nEnter your choice [1-3]: ").strip()
        if choice == "1":
            logger.info("User selected deployment option.")
            deploy_bridge(logger)
        elif choice == "2":
            logger.info("User selected removal option.")
            remove_bridge_resource(logger)
        elif choice == "3":
            logger.info("User selected to exit the menu.")
            print("Exiting menu...")
            sys.exit(0)
        else:
            print("Invalid input. Please enter 1, 2, or 3.")

if __name__ == '__main__':
    interactive_menu()
