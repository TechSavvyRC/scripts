#!/usr/bin/env python3
"""
minikube_management.py

This script provides an interactive main menu for managing Minikube. Users can choose to run the 
Minikube Manager or the Minikube Resource Manager. In the Resource Manager, users can select from several 
resource deployment tasks. After each task, control returns to the resource menu.
"""

import os
import sys
import subprocess
import logging

# Configure ANSI color codes for log file messages if needed.
# (Console messages are printed plain.)
LOG_FILE = "/opt/minikube/scripts/python/logs/minikube_management.log"

def setup_logging(log_file):
    """
    Configures logging with a file handler that includes timestamps and log level, and a console handler that prints plain messages.
    """
    logger = logging.getLogger("minikube_management")
    logger.setLevel(logging.DEBUG)
    
    # File handler: include timestamps and log level.
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)
    
    # Console handler: plain message.
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter('%(message)s')
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)
    
    return logger

def run_script(script_path, logger):
    """
    Calls and executes a subordinate script located at script_path.
    """
    #logger.info(f"Executing script: {script_path}")
    try:
        subprocess.call([sys.executable, script_path])
        logger.info("Task completed successfully.")
    except Exception as e:
        logger.error(f"Failed to execute {script_path}: {e}")

def main_menu(logger):
    """
    Displays the main menu with options for Minikube Manager and Minikube Resource Manager.
    """
    while True:
        logger.info("\nMain Menu:")
        logger.info("1. Minikube Manager")
        logger.info("2. Minikube Resource Manager")
        logger.info("3. Exit")
        choice = input("\nPlease select an option (1-3): ").strip()
        if choice == "1":
            run_script("/opt/minikube/scripts/python/minikube-manager.py", logger)
        elif choice == "2":
            resource_menu(logger)
        elif choice == "3":
            logger.info("Exiting minikube_management.py")
            break
        else:
            logger.info("Invalid selection. Please try again.")

def resource_menu(logger):
    """
    Displays the resource menu with options for various resource deployments.
    After a resource task completes, returns to this menu until the user selects Exit.
    """
    while True:
        logger.info("\nResource Menu:")
        logger.info("1. Kubernetes Dashboard")
        logger.info("2. Velero")
        logger.info("3. Database")
        logger.info("4. Application")
        logger.info("5. Streaming")
        logger.info("6. MySQL-Kafka Bridge")
        logger.info("7. Monitoring")
        logger.info("8. Observability")
        logger.info("9. Exit to Main Menu")
        choice = input("\nPlease select a resource option (1-9): ").strip()
        if choice == "1":
            run_script("/opt/minikube/scripts/python/deploy_kubernetes_dashboard.py", logger)
        elif choice == "2":
            run_script("/opt/minikube/scripts/python/deploy_velero.py", logger)
        elif choice == "3":
            run_script("/opt/minikube/scripts/python/deploy_mysql.py", logger)
        elif choice == "4":
            run_script("/opt/minikube/scripts/python/deploy_ecom_app.py", logger)
        elif choice == "5":
            run_script("/opt/minikube/scripts/python/deploy_kafka.py", logger)
        elif choice == "6":
            run_script("/opt/minikube/scripts/python/deploy_mysql_kafka_bridge.py", logger)
        elif choice == "7":
            run_script("/opt/minikube/scripts/python/deploy_prometheus.py", logger)
        elif choice == "8":
            run_script("/opt/minikube/scripts/python/deploy_elk.py", logger)
        elif choice == "9":
            logger.info("Returning to Main Menu.")
            break
        else:
            logger.info("Invalid selection. Please try again.")

def main():
    """
    Main entry point that sets up logging and displays the main menu.
    """
    logger = setup_logging(LOG_FILE)
    main_menu(logger)

if __name__ == "__main__":
    main()
