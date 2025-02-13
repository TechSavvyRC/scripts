#!/usr/bin/env python3
"""
deploy_kafka.py – Deploy Kafka (with Redpanda) into a Minikube cluster.

This script verifies that it is run by user 'muser', creates required directories,
ensures that necessary resource files exist (fetching any missing ones from GitHub),
checks that Minikube is running, verifies the 'streaming' namespace and its resources,
and then deploys Kafka and Redpanda accordingly.

After deploying Kafka, the script waits for the Kafka StatefulSet to complete its rollout,
creates the 'ecom_transactions' topic, and then deploys Redpanda by waiting for its
Deployment to complete its rollout. Finally, it displays the current namespace resources.
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
PY_SCRIPT_PATH = "/opt/minikube/scripts/python/deploy_kafka.py"
LOG_DIR = "/opt/minikube/scripts/python/logs"
LOG_FILE = os.path.join(LOG_DIR, "deploy_kafka.log")
NAMESPACE_DIR = "/opt/minikube/namespaces/streaming"
REQUIRED_FILES = ["kafka.yaml", "redpanda.yaml"]
GITHUB_REPO = "https://github.com/TechSavvyRC/streaming.git"
NAMESPACE = "streaming"

# Topic creation command parameters.
TOPIC_NAME = "ecom_transactions"
KAFKA_EXEC_CMD = [
    "kubectl", "exec", "-n", NAMESPACE, "kafka-0", "--",
    "kafka-topics", "--create",
    "--topic", TOPIC_NAME,
    "--bootstrap-server", "kafka.streaming.svc.cluster.local:9092",
    "--replication-factor", "1",
    "--partitions", "1"
]

def setup_logging():
    """Set up logging with a detailed file handler and a simplified console handler."""
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("deploy_kafka")
    logger.setLevel(logging.DEBUG)
    
    # File handler (detailed)
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)
    
    # Console handler (clean)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter('%(message)s')
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)
    
    return logger

def run_command(logger, cmd, capture_output=True, check=True, input_text=None):
    """Run a shell command and return its output; log errors on failure."""
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
    """Clone the GitHub repository and copy missing files into the namespace directory."""
    logger.info("Missing files detected (%s). Fetching from repository...", ", ".join(missing_files))
    temp_dir = tempfile.mkdtemp()
    repo_dir = os.path.join(temp_dir, "streaming")
    try:
        subprocess.run(["git", "clone", GITHUB_REPO, repo_dir],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.debug("Cloned repository into temporary directory '%s'.", repo_dir)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to clone repository: %s", e.stderr.decode().strip() if e.stderr else str(e))
        shutil.rmtree(temp_dir)
        sys.exit(1)
    for filename in missing_files:
        src_file = os.path.join(repo_dir, filename)
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
            logger.error("File '%s' not found in the cloned repository.", filename)
            shutil.rmtree(temp_dir)
            sys.exit(1)
    shutil.rmtree(temp_dir)
    logger.info("Successfully fetched missing files.")

def wait_for_pods(logger, namespace, timeout=300, interval=10):
    """
    Poll until all pods in the given namespace are Running and have READY state where
    the number of ready containers equals the total number of containers.
    Detailed readiness information is logged to help diagnose issues.
    """
    logger.info("Waiting for Streaming pods to be in Ready state (all containers ready)...")
    elapsed = 0
    while elapsed < timeout:
        output = run_command(logger, f"kubectl get pods -n {namespace} --no-headers", capture_output=True, check=False)
        if output:
            all_ready = True
            lines = output.splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) < 2:
                    continue
                ready = parts[1]  # Expected format: "x/y"
                try:
                    ready_num, ready_den = map(int, ready.split('/'))
                except ValueError:
                    logger.error(f"Pod '{parts[0]}' has an unexpected READY format: '{ready}'. Full details: {line}")
                    all_ready = False
                    continue
                if ready_num != ready_den:
                    all_ready = False
                    logger.error(f"Pod '{parts[0]}' is not ready: READY state is '{ready}'. Full details: {line}")
            if all_ready:
                logger.info("All pods are ready (all containers in each pod are running).")
                return True
        time.sleep(interval)
        elapsed += interval
    logger.error("Timeout reached waiting for pods to be ready.")
    sys.exit(1)

def deploy_kafka_and_redpanda(logger):
    #logger = setup_logging()
    logger.info("Starting Kafka and Redpanda deployment script.")

    # 1. Ensure namespace directory exists and switch to it.
    try:
        os.makedirs(NAMESPACE_DIR, exist_ok=True)
        os.chdir(NAMESPACE_DIR)
        logger.debug("Namespace directory '%s' is ready.", NAMESPACE_DIR)
    except Exception as e:
        logger.error("Failed to create or change directory to '%s': %s", NAMESPACE_DIR, str(e))
        sys.exit(1)

    # 2. Check for required files; if missing, fetch them.
    missing_files = [f for f in REQUIRED_FILES if not os.path.exists(os.path.join(NAMESPACE_DIR, f))]
    if missing_files:
        fetch_missing_files(logger, missing_files)
    else:
        logger.debug("All required files are present.")

    # 3. Verify that Minikube is running.
    try:
        result = subprocess.run(["minikube", "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        if "Running" not in result.stdout.decode():
            logger.info("Minikube is not running. Please start Minikube and try again.")
            sys.exit(0)
        logger.debug("Minikube status: Running.")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to get Minikube status: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)

    # 4. Ensure the 'streaming' namespace exists.
    try:
        result = subprocess.run(["kubectl", "get", "namespace", NAMESPACE],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            logger.debug("Namespace '%s' exists.", NAMESPACE)
        else:
            logger.info("Namespace '%s' does not exist. Creating...", NAMESPACE)
            subprocess.run(["kubectl", "create", "namespace", NAMESPACE], check=True)
            logger.info("Namespace '%s' created successfully.", NAMESPACE)
    except subprocess.CalledProcessError as e:
        logger.error("Error checking/creating namespace: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)

    # 5. Check existing resources in the 'streaming' namespace.
    try:
        result = subprocess.run(["kubectl", "get", "all", "-n", NAMESPACE],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        resources_output = result.stdout.decode().strip()
    except subprocess.CalledProcessError as e:
        logger.error("Error retrieving resources in namespace '%s': %s", NAMESPACE, e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)
    
    resource_lines = resources_output.splitlines()
    if len(resource_lines) <= 1:
        logger.debug("No resources found in namespace '%s'. Proceeding with deployment.", NAMESPACE)
        extraneous = False
    else:
        data_lines = resource_lines[1:]
        extraneous = False
        for line in data_lines:
            if not any(app in line for app in ["kafka", "redpanda"]):
                extraneous = True
                break
        if not extraneous:
            logger.info("-------------------------------------------------------------------------------------------------")
            logger.info("## Resources Running Under 'streaming' Namespace")
            logger.info("-------------------------------------------------------------------------------------------------")
            logger.info(resources_output)
            logger.info("-------------------------------------------------------------------------------------------------")
            logger.info("Expected resources already running. Exiting deployment script.")
            sys.exit(0)
    
    # 6. If extraneous resources exist, prompt the user.
    if extraneous:
        logger.info("Unexpected resources found in namespace '%s':", NAMESPACE)
        logger.info("-------------------------------------------------------------------------------------------------")
        logger.info(resources_output)
        logger.info("-------------------------------------------------------------------------------------------------")
        logger.info("Options:")
        logger.info("1. Continue deployment without deleting the existing namespace.")
        logger.info("2. Delete the namespace and perform a fresh deployment.")
        choice = None
        while True:
            try:
                choice = input("Enter your choice (1 or 2): ").strip()
            except EOFError:
                logger.error("No input provided. Exiting.")
                sys.exit(1)
            if choice in ["1", "2"]:
                break
            else:
                logger.info("Invalid input. Please enter 1 or 2.")
    else:
        choice = "1"  # Default if no extraneous resources.

    # 7. Handle namespace deletion if requested.
    if extraneous and choice == "2":
        logger.info("Deleting namespace '%s'...", NAMESPACE)
        try:
            subprocess.run(["kubectl", "delete", "namespace", NAMESPACE], check=True)
            # Wait until namespace deletion is complete.
            for i in range(30):
                time.sleep(2)
                result = subprocess.run(["kubectl", "get", "namespace", NAMESPACE],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    logger.debug("Namespace '%s' deleted.", NAMESPACE)
                    break
            subprocess.run(["kubectl", "create", "namespace", NAMESPACE], check=True)
            logger.info("Namespace '%s' re-created for fresh deployment.", NAMESPACE)
        except subprocess.CalledProcessError as e:
            logger.error("Failed to delete or re-create namespace '%s': %s", NAMESPACE, e.stderr.decode().strip() if e.stderr else str(e))
            sys.exit(1)

    # 8. Deploy Kafka resource.
    logger.info("Deploying Kafka resource...")
    try:
        subprocess.run(["kubectl", "apply", "-f", "kafka.yaml", "-n", NAMESPACE], check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to deploy Kafka resource: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)

    # 9. Wait until Kafka StatefulSet rollout is complete.
    if not wait_for_pods(logger, "streaming"):
        sys.exit(1)

    # 10. Create Kafka topic.
    logger.info("Creating Kafka topic '%s'...", TOPIC_NAME)
    try:
        subprocess.run(KAFKA_EXEC_CMD, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Kafka topic '%s' created successfully.", TOPIC_NAME)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to create Kafka topic: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)

    # 11. Deploy Redpanda resource.
    logger.info("Deploying Redpanda resource...")
    try:
        subprocess.run(["kubectl", "apply", "-f", "redpanda.yaml", "-n", NAMESPACE], check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to deploy Redpanda resource: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)

    # 12. Wait until Redpanda Deployment rollout is complete.
    if not wait_for_pods(logger, "streaming"):
        sys.exit(1)

    # 13. Display the final resources.
    try:
        result = subprocess.run(["kubectl", "get", "all", "-n", NAMESPACE, "-o", "wide"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        final_output = result.stdout.decode().strip()
        logger.info("-------------------------------------------------------------------------------------------------")
        logger.info("## Resources Running Under 'streaming' Namespace")
        logger.info("-------------------------------------------------------------------------------------------------")
        logger.info(final_output)
        logger.info("-------------------------------------------------------------------------------------------------")
        logger.info("Deployment under the 'streaming' namespace was successful.")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to retrieve final resources: %s", e.stderr.decode().strip() if e.stderr else str(e))
        sys.exit(1)

    return

# New function to remove the 'streaming' namespace.
def remove_streaming_namespace(logger):
    logger.info("Initiating removal of '%s' namespace...", NAMESPACE)
    try:
        result = subprocess.run(["kubectl", "get", "namespace", NAMESPACE],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logger.info("Namespace '%s' does not exist.", NAMESPACE)
            return
        subprocess.run(["kubectl", "delete", "namespace", NAMESPACE], check=True)
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
        print("\n-------------------------------")
        print("Kafka and Redpanda Deployment Menu")
        print("-------------------------------")
        print("1. Deploy Kafka and Redpanda in Minikube Cluster")
        print("2. Remove Kafka and Redpanda from Minikube Cluster")
        print("3. Exit to resource deployment menu")
        print("-------------------------------")
        choice = input("Enter your choice [1-3]: ").strip()
        if choice == "1":
            logger.info("User selected deployment option.")
            deploy_kafka_and_redpanda(logger)
        elif choice == "2":
            logger.info("User selected removal option.")
            remove_streaming_namespace(logger)
        elif choice == "3":
            logger.info("User selected to exit the menu.")
            print("Exiting menu...")
            sys.exit(0)
        else:
            print("Invalid input. Please enter 1, 2, or 3.")

if __name__ == '__main__':
    interactive_menu()
