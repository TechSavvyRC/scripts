#!/usr/bin/python3

import os
import sys
import pwd
import logging
import subprocess
import time
from datetime import datetime
import git
from pathlib import Path

class DeploymentManager:
    def __init__(self):
        self.setup_logging()
        self.base_dir = Path('/opt/minikube')
        self.namespace_dir = self.base_dir / 'namespaces/database'
        self.required_files = ['debug-pod.yaml', 'init-db.sql', 'mysql.yaml', 'phpmyadmin.yaml']
        self.github_repo = 'https://github.com/TechSavvyRC/database.git'

    def setup_logging(self):
        """Configure logging to both file and console with different formats"""
        script_dir = Path('/opt/minikube/scripts/python')
        log_dir = script_dir / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Prevent duplicate logging
        self.logger.propagate = False
        
        # File handler with timestamps and log levels
        log_file = log_dir / 'deploy_mysql.log'
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        
        # Console handler with just the message
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        
        # Add both handlers to the logger
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def print_message(self, message, level='info'):
        """Print message to console and log file"""
        log_func = getattr(self.logger, level)
        log_func(message)

    def handle_kubectl_output(self, output):
        """Handle kubectl command output by logging it only once"""
        if output.strip():
            self.print_message(output.strip())

    def verify_user(self):
        """Verify that the script is being run by 'muser'"""
        current_user = pwd.getpwuid(os.getuid()).pw_name
        if current_user != 'muser':
            self.print_message(f"Error: This script must be run by 'muser'. Current user: {current_user}", 'error')
            sys.exit(1)

    def verify_directories(self):
        """Verify and create necessary directories"""
        self.namespace_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(self.namespace_dir)

    def verify_files(self):
        """Verify required files exist, fetch from GitHub if necessary"""
        missing_files = [f for f in self.required_files if not (self.namespace_dir / f).exists()]
        
        if missing_files:
            self.print_message(f"Missing files: {missing_files}. Fetching from GitHub...")
            try:
                git.Repo.clone_from(self.github_repo, self.namespace_dir)
                self.print_message("Successfully fetched files from GitHub")
            except git.exc.GitCommandError as e:
                self.print_message(f"Error fetching files: {str(e)}", 'error')
                sys.exit(1)

    def check_minikube_status(self):
        """Verify Minikube is running"""
        try:
            result = subprocess.run(['minikube', 'status'], capture_output=True, text=True)
            if "Running" not in result.stdout:
                self.print_message("Error: Minikube is not running. Please start Minikube first.", 'error')
                sys.exit(1)
        except subprocess.CalledProcessError:
            self.print_message("Error: Failed to check Minikube status", 'error')
            sys.exit(1)

    def manage_namespace(self):
        """Create or verify database namespace"""
        try:
            result = subprocess.run(['kubectl', 'get', 'namespace', 'database'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                subprocess.run(['kubectl', 'create', 'namespace', 'database'], 
                             capture_output=True, text=True, check=True)
                self.print_message("Created database namespace")
            else:
                self.print_message("Database namespace already exists")
        except subprocess.CalledProcessError as e:
            self.print_message(f"Error managing namespace: {str(e)}", 'error')
            sys.exit(1)

    def get_namespace_resources(self):
        """Get current resources in the database namespace"""
        try:
            result = subprocess.run(
                ['kubectl', 'get', 'all', '-n', 'database'],
                capture_output=True, text=True, check=True
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return ""

    def display_resources(self):
        """Display current resources in formatted table"""
        resources = self.get_namespace_resources()
        separator = "-" * 98
        self.print_message(f"\n{separator}")
        self.print_message("## Resources Running Under 'database' Namespace")
        self.print_message(separator)
        self.print_message(resources)
        self.print_message(f"{separator}\n")

    def check_existing_resources(self):
        """Check if there are any non-MySQL/PhpMyAdmin resources"""
        resources = self.get_namespace_resources()
        if not resources:
            return "empty"
        
        unexpected = False
        for line in resources.split('\n'):
            if any(x in line.lower() for x in ['mysql', 'phpmyadmin']):
                continue
            if line and not line.startswith('NAME'):
                unexpected = True
                break
        
        if unexpected:
            return "mixed"
        elif 'mysql' in resources.lower() or 'phpmyadmin' in resources.lower():
            return "expected"
        return "empty"

    def wait_for_pods_ready(self, app_label):
        """Wait for pods to be ready"""
        max_attempts = 30
        attempts = 0
        while attempts < max_attempts:
            try:
                result = subprocess.run(
                    ['kubectl', 'get', 'pods', '-n', 'database', '-l', f'app={app_label}',
                     '-o', 'custom-columns=:status.phase'],
                    capture_output=True, text=True, check=True
                )
                if 'Running' in result.stdout:
                    return True
            except subprocess.CalledProcessError:
                pass
            
            time.sleep(10)
            attempts += 1
        
        return False

    def deploy_resources(self, delete_namespace=False):
        """Deploy MySQL and PhpMyAdmin resources"""
        if delete_namespace:
            result = subprocess.run(['kubectl', 'delete', 'namespace', 'database'], 
                                  capture_output=True, text=True, check=True)
            self.handle_kubectl_output(result.stdout)
            time.sleep(10)
            self.manage_namespace()

        # Deploy MySQL
        result = subprocess.run(['kubectl', 'apply', '-f', 'mysql.yaml', '-n', 'database'], 
                              capture_output=True, text=True, check=True)
        self.handle_kubectl_output(result.stdout)
        
        if not self.wait_for_pods_ready('mysql'):
            self.print_message("Error: MySQL pods failed to reach ready state", 'error')
            sys.exit(1)

        # Deploy PhpMyAdmin
        result = subprocess.run(['kubectl', 'apply', '-f', 'phpmyadmin.yaml', '-n', 'database'], 
                              capture_output=True, text=True, check=True)
        self.handle_kubectl_output(result.stdout)
        
        if not self.wait_for_pods_ready('phpmyadmin'):
            self.print_message("Error: PhpMyAdmin pods failed to reach ready state", 'error')
            sys.exit(1)

    def run(self):
        """Main execution flow"""
        self.verify_user()
        self.verify_directories()
        self.verify_files()
        self.check_minikube_status()
        self.manage_namespace()

        resource_status = self.check_existing_resources()
        
        if resource_status == "expected":
            self.print_message("Current resources in database namespace:")
            self.display_resources()
            self.print_message("Deployment already exists with expected resources")
            return
        
        elif resource_status == "mixed":
            self.print_message("Found existing resources in database namespace:")
            self.display_resources()
            response = input("Do you want to delete the namespace and start fresh? (yes/no): ")
            if response.lower() == 'yes':
                self.deploy_resources(delete_namespace=True)
            else:
                self.deploy_resources(delete_namespace=False)
        
        else:  # empty namespace
            self.deploy_resources(delete_namespace=False)

        self.print_message("Final deployment status:")
        self.display_resources()
        self.print_message("Deployment completed successfully")

def remove_database_namespace(deployer):
    deployer.print_message("Initiating removal of 'database' namespace...")
    try:
        # Check if the namespace exists first
        result = subprocess.run(
            ['kubectl', 'get', 'namespace', 'database'],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            deployer.print_message("Namespace 'database' does not exist.")
            return
        # Delete the namespace
        delete_result = subprocess.run(
            ['kubectl', 'delete', 'namespace', 'database'],
            capture_output=True, text=True, check=True
        )
        deployer.print_message("Database namespace removed successfully.")
    except subprocess.CalledProcessError as e:
        deployer.print_message(f"Error removing namespace: {e}", 'error')

# Interactive menu system
def interactive_menu():
    deployer = DeploymentManager()
    while True:
        print("\n-------------------------------")
        print("MySQL and PhpMyAdmin Deployment Menu")
        print("-------------------------------")
        print("1. Deploy MySQL and PhpMyAdmin in Minikube Cluster")
        print("2. Remove MySQL and PhpMyAdmin from Minikube Cluster")
        print("3. Exit to resource deployment menu")
        print("-------------------------------")
        choice = input("Enter your choice [1-3]: ").strip()
        if choice == '1':
            deployer.run()  # Existing deployment logic
        elif choice == '2':
            remove_database_namespace(deployer)
        elif choice == '3':
            print("Exiting menu...")
            sys.exit(0)
        else:
            print("Invalid input. Please choose 1, 2, or 3.")

if __name__ == "__main__":
    #deployer = DeploymentManager()
    #deployer.run()
    interactive_menu()