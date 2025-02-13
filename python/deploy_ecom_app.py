#!/usr/bin/env python3
"""
deploy_ecom_app.py

This script deploys an ecommerce application resource in a Minikube cluster.
It supports installation (deploying resources) and uninstallation (removing resources).
It prints plain messages to the screen while logging detailed messages (with timestamps and levels) to a log file.
"""

import os
import sys
import subprocess
import logging
import getpass
import shutil
import json
import time
import git

# Constants for directories and file names
BASE_DIR = "/opt/minikube/namespaces/application/"
REQUIRED_FILES = ["Dockerfile", "ecom_app.yaml", "ecom_transactions.py", "debug_pod.yaml"]
GIT_REPO_URL = "https://github.com/TechSavvyRC/application.git"

# Log file location: same name as script with .log extension, in /opt/minikube/scripts/python/logs
LOG_DIR = "/opt/minikube/scripts/python/logs"
LOG_FILE = os.path.join(LOG_DIR, os.path.splitext(os.path.basename(__file__))[0] + ".log")

def setup_logging(log_file):
    """
    Sets up logging with a file handler (including timestamps and log level) and a console handler (plain messages).
    Returns the logger.
    """
    logger = logging.getLogger("deploy_ecom_app")
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
    Verifies the script is executed only by 'muser'; exits if not.
    """
    if getpass.getuser() != "muser":
        logger.error("This script must be executed by 'muser'.")
        sys.exit(1)
    logger.info("User check passed: running as 'muser'.")

def ensure_directory(logger, directory):
    """
    Ensures the given directory exists; if not, creates it.
    """
    if not os.path.exists(directory):
        try:
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")
        except Exception as e:
            logger.error(f"Failed to create directory {directory}: {e}")
            sys.exit(1)

def change_directory(logger, directory):
    """
    Changes to the specified directory; exits if unsuccessful.
    """
    try:
        os.chdir(directory)
        logger.info(f"Changed directory to {directory}")
    except Exception as e:
        logger.error(f"Failed to change directory to {directory}: {e}")
        sys.exit(1)

def verify_files(logger):
    """
    Verifies that all required files exist in the current directory.
    Exits if any file is missing.
    """
    missing = [f for f in REQUIRED_FILES if not os.path.isfile(f)]
    if missing:
        logger.info(f"Missing files: {missing}. Fetching from GitHub repository...")
        fetch_files(logger)
    else:
        logger.info("All required files are present.")

def fetch_files(logger):
    """
    Clones the repository into a temporary directory and copies required files to the current directory.
    """
    temp_dir = "temp_repo"
    try:
        subprocess.run(["git", "clone", GIT_REPO_URL, temp_dir], check=True)
        for file in REQUIRED_FILES:
            src = os.path.join(temp_dir, file)
            if os.path.isfile(src):
                shutil.copy(src, ".")
                logger.info(f"Fetched {file} from repository.")
            else:
                logger.error(f"{file} not found in repository.")
                sys.exit(1)
        shutil.rmtree(temp_dir)
    except Exception as e:
        logger.error(f"Failed to fetch files from GitHub: {e}")
        sys.exit(1)

def check_minikube_status(logger):
    """
    Ensures Minikube is running; if not, instructs the user to start it and exits.
    """
    try:
        result = subprocess.run(["minikube", "status"], capture_output=True, text=True)
        if result.returncode != 0 or "Running" not in result.stdout:
            logger.error("Minikube is not running. Please start Minikube (e.g. 'minikube start') and try again.")
            sys.exit(1)
        logger.info("Minikube status: Running")
    except Exception as e:
        logger.error(f"Error checking Minikube status: {e}")
        sys.exit(1)

def ensure_namespace(logger, namespace):
    """
    Checks if the given Kubernetes namespace exists; if not, creates it.
    """
    try:
        subprocess.run(["kubectl", "get", "namespace", namespace], check=True, capture_output=True)
        logger.info(f"Namespace '{namespace}' exists.")
    except subprocess.CalledProcessError:
        logger.info(f"Namespace '{namespace}' does not exist. Creating it...")
        subprocess.run(["kubectl", "create", "namespace", namespace], check=True)
        logger.info(f"Namespace '{namespace}' created.")

def get_resources(logger, namespace):
    """
    Retrieves all resources running in the given namespace.
    Returns the output as a string.
    """
    try:
        output = subprocess.check_output(["kubectl", "get", "all", "-n", namespace], text=True)
        return output.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Error getting resources from namespace '{namespace}': {e}")
        return ""

def resources_belong_to_app(resources_output):
    """
    Checks if all resource names in the provided output contain 'ecommerce-application'.
    Returns True if yes; False otherwise.
    """
    lines = resources_output.splitlines()
    # Skip header lines
    for line in lines:
        if line.startswith("NAME"):
            continue
        if line.strip() == "":
            continue
        # Assume first column is resource name
        name = line.split()[0]
        if "ecommerce-application" not in name:
            return False
    return True

def display_resources(logger, resources_output):
    """
    Displays resources output with a header and footer.
    """
    header = ("-------------------------------------------------------------------------------------------------\n"
              "## Resources Running Under Application Namespace\n"
              "-------------------------------------------------------------------------------------------------")
    footer = "-------------------------------------------------------------------------------------------------"
    print(header)
    print(resources_output)
    print(footer)
    logger.info("Displayed resources under the 'application' namespace.")

def deploy_resources(logger):
    """
    Deploys the ecommerce application resource using 'kubectl apply -f ecom_app.yaml'.
    """
    try:
        subprocess.run(["kubectl", "apply", "-f", "ecom_app.yaml"], check=True)
        logger.info("Deployment command executed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to deploy ecommerce application resource: {e}")
        sys.exit(1)

def manage_existing_resources(logger, namespace):
    """
    Checks for existing resources in the namespace.
    If resources exist and all belong to 'ecommerce-application', displays them and exits.
    Otherwise, prompts the user whether to continue or delete the namespace.
    Returns True if deployment should proceed, False if not.
    """
    resources_output = get_resources(logger, namespace)
    if resources_output:
        if resources_belong_to_app(resources_output):
            logger.info("All running resources belong to 'ecommerce-application'.")
            display_resources(logger, resources_output)
            logger.info("Exiting since application resources are already running.")
            #sys.exit(0)
            return
        else:
            print("Some resources are already running under the 'application' namespace:")
            display_resources(logger, resources_output)
            choice = input("Enter 'continue' to deploy without deleting, or 'delete' to delete the namespace and deploy new resources: ").strip().lower()
            if choice == "delete":
                logger.info("User opted to delete the namespace.")
                subprocess.run(["kubectl", "delete", "namespace", namespace], check=True)
                # Wait briefly for deletion, then recreate namespace.
                time.sleep(5)
                ensure_namespace(logger, namespace)
                return True
            elif choice == "continue":
                logger.info("User opted to continue without deleting the namespace.")
                return True
            else:
                logger.info("Invalid selection. Exiting.")
                sys.exit(1)
    else:
        logger.info(f"No resources found in namespace '{namespace}'.")
        return True

def display_deployed_resources(logger, namespace):
    """
    Displays all resources running under the specified namespace in a formatted output.
    """
    resources_output = get_resources(logger, namespace)
    if resources_output:
        display_resources(logger, resources_output)
    else:
        logger.info(f"No resources found in namespace '{namespace}' after deployment.")

def perform_installation(logger):
    """
    Performs the installation workflow: checks environment, fetches files if needed, ensures namespace exists,
    verifies existing resources (and prompts if needed), deploys the ecommerce application, and displays resources.
    """
    check_user(logger)
    ensure_directory(logger, BASE_DIR)
    change_directory(logger, BASE_DIR)
    verify_files(logger)
    check_minikube_status(logger)
    ensure_namespace(logger, "application")
    # Check for existing resources and prompt accordingly.
    if not manage_existing_resources(logger, "application"):
        return
    # Deploy ecommerce application resource.
    deploy_resources(logger)
    # Display deployed resources.
    display_deployed_resources(logger, "application")
    logger.info("Ecommerce application resource deployment under the 'application' namespace is successful.")

def perform_uninstallation(logger):
    """
    Performs the uninstallation workflow: deletes the 'application' namespace.
    """
    check_user(logger)
    try:
        subprocess.run(["kubectl", "delete", "namespace", "application"], check=True)
        logger.info("Application namespace deleted successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"'application' namespace does not exist: {e}")
        #sys.exit(1)

def main():
    """
    Main entry point of the script.
    Displays a note (if run independently), then an interactive menu for installation or uninstallation.
    """
    # If this script is executed directly, display the note.
    if __name__ == "__main__":
        main_note = (
            "\n--------------------------------------------------------------------------------------\n"
            "This script deploys the ecommerce application resource in a Minikube cluster.\n"
            "It will fetch required files from GitHub if necessary and ensure proper deployment.\n"
            "It does NOT create backups of existing resources. Use with caution.\n"
            "--------------------------------------------------------------------------------------"
        )
        print(main_note)
    # Setup logging.
    ensure_directory(logging.getLogger(), LOG_DIR)  # Not used; we simply ensure LOG_DIR exists.
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    logger = setup_logging(LOG_FILE)
    
    # Display main interactive menu.
    while True:
        print("\n---------------------------------------------------------------------")
        print("Ecommerce Transasaction Application Deployment Menu")
        print("---------------------------------------------------------------------")
        print("1. Deploy Ecommerce Transasaction Application in Minikube Cluster")
        print("2. Remove Ecommerce Transasaction Application from Minikube Cluster")
        print("3. Exit to resource deployment menu")
        print("---------------------------------------------------------------------")

        choice = input("\nPlease select an option (1-3): ").strip()
        if choice == "1":
            logger.info("User selected Installation.")
            perform_installation(logger)
        elif choice == "2":
            logger.info("User selected Uninstallation.")
            perform_uninstallation(logger)
        elif choice == "3":
            logger.info("Exiting deploy_ecom_app.py")
            break
        else:
            logger.info("Invalid selection. Please try again.")

if __name__ == "__main__":
    main()
