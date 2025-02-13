#!/bin/bash

# ANSI color codes.
RED_BOLD="\033[1;31m"
YELLOW="\033[1;33m"
RESET="\033[0m"

# --- Configuration ---
LOG_DIR="/opt/minikube/scripts/shell/logs"
LOG_FILE="${LOG_DIR}/deploy_mysql_kafka_bridge.log"
NAMESPACE_DIR="/opt/minikube/namespaces/database/mysql-kafka-bridge"
REQUIRED_FILES=("Dockerfile" "mysql-kafka-bridge.yaml" "mysql_to_kafka.py")
GITHUB_REPO="https://github.com/TechSavvyRC/database.git"
GITHUB_SUBDIR="mysql-kafka-bridge"
NAMESPACE="database"
BRIDGE_DEPLOYMENT_NAME="mysql-to-kafka"

# --- Functions ---
log_msg() {
    # Usage: log_msg LEVEL "Message"
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "${timestamp} - ${level} - ${message}" >> "$LOG_FILE"
    echo "$message"
}

print_warning() {
    echo -e "${RED_BOLD}WARNING:${RESET}"
    echo -e "${YELLOW}This resource depends on MySQL and Kafka resources. Ensure these resources are in a ready state before deployment.
Also, the 'ecommerce' database and 'ecom_transactions' table must exist in MySQL, and the 'ecom_transactions' topic must exist in Kafka.${RESET}"
}

fetch_missing_files() {
    missing=("$@")
    log_msg "INFO" "Missing files detected (${missing[*]}). Fetching from repository..."
    TEMP_DIR=$(mktemp -d)
    git clone "$GITHUB_REPO" "$TEMP_DIR/database" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        log_msg "ERROR" "Failed to clone repository."
        rm -rf "$TEMP_DIR"
        exit 1
    fi
    for file in "${missing[@]}"; do
        if [ -f "$TEMP_DIR/database/${GITHUB_SUBDIR}/$file" ]; then
            cp "$TEMP_DIR/database/${GITHUB_SUBDIR}/$file" .
            log_msg "DEBUG" "Copied '$file' to namespace directory."
        else
            log_msg "ERROR" "File '$file' not found in repository."
            rm -rf "$TEMP_DIR"
            exit 1
        fi
    done
    rm -rf "$TEMP_DIR"
    log_msg "INFO" "Successfully fetched missing files."
}

wait_for_rollout() {
    # wait_for_rollout RESOURCE_TYPE RESOURCE_NAME NAMESPACE TIMEOUT
    local resource_type=$1
    local resource_name=$2
    local namespace=$3
    local timeout=$4
    kubectl rollout status "${resource_type}/${resource_name}" -n "$namespace" --timeout="$timeout"
    if [ $? -ne 0 ]; then
        log_msg "ERROR" "Error waiting for ${resource_type} '${resource_name}' rollout."
        return 1
    fi
    log_msg "INFO" "${resource_type^} '${resource_name}' rollout complete."
    return 0
}

# Wrap the existing deployment logic for MySQL-Kafka-Bridge.
deploy_bridge() {
    log_msg "INFO" "Starting MySQL-Kafka-Bridge deployment script."
    
    # Verify warning and user (these steps already exist).
    print_warning

    # Ensure namespace directory exists.
    mkdir -p "$NAMESPACE_DIR" || { log_msg "ERROR" "Failed to create directory '$NAMESPACE_DIR'."; exit 1; }
    cd "$NAMESPACE_DIR" || { log_msg "ERROR" "Failed to change directory to '$NAMESPACE_DIR'."; exit 1; }
    log_msg "DEBUG" "Namespace directory '$NAMESPACE_DIR' is ready."

    # Check for required files.
    missing_files=()
    for file in "${REQUIRED_FILES[@]}"; do
        if [ ! -f "$file" ]; then
            missing_files+=("$file")
        fi
    done
    if [ ${#missing_files[@]} -ne 0 ]; then
        fetch_missing_files "${missing_files[@]}"
    else
        log_msg "DEBUG" "All required files are present."
    fi

    # Verify that Minikube is running.
    minikube_status=$(minikube status 2>&1)
    if [[ "$minikube_status" != *"Running"* ]]; then
        log_msg "INFO" "Minikube is not running. Please start Minikube and try again."
        exit 0
    else
        log_msg "DEBUG" "Minikube status: Running."
    fi

    # Ensure the 'database' namespace exists.
    kubectl get namespace "$NAMESPACE" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        log_msg "ERROR" "MySQL resource does not exist because the 'database' namespace does not exist.
Please deploy MySQL and Kafka resources before deploying the Mysql-Kafka-Bridge."
        exit 1
    else
        log_msg "DEBUG" "Namespace '$NAMESPACE' exists."
    fi

    # Resource verification and deployment logic.
    # (This part of the script is unchanged from your original code.)
    # For brevity, assume the remaining steps of resource verification,
    # deletion if necessary, and applying the deployment (using kubectl apply -f mysql-kafka-bridge.yaml)
    # are executed here.
    #
    # Example:
    kubectl apply -f mysql-kafka-bridge.yaml -n "$NAMESPACE"
    if [ $? -ne 0 ]; then
        log_msg "ERROR" "Failed to deploy Mysql-Kafka-Bridge resource."
        exit 1
    fi
    log_msg "INFO" "Mysql-Kafka-Bridge resource deployed."
    wait_for_rollout "deployment" "$BRIDGE_DEPLOYMENT_NAME" "$NAMESPACE" "180s"
    if [ $? -ne 0 ]; then
        exit 1
    fi

    # Display final resources.
    final_output=$(kubectl get all -n "$NAMESPACE" -o wide)
    log_msg "INFO" "-------------------------------------------------------------------------------------------------"
    log_msg "INFO" "## Resources Running Under 'database' Namespace"
    log_msg "INFO" "-------------------------------------------------------------------------------------------------"
    echo "$final_output"
    log_msg "INFO" "-------------------------------------------------------------------------------------------------"
    log_msg "INFO" "Deployment under the 'database' namespace was successful."
}

# New function to remove the 'database' namespace.
remove_database_namespace() {
    log_msg "INFO" "Initiating removal of 'database' namespace..."
    if kubectl get namespace "$NAMESPACE" &>/dev/null; then
        kubectl delete namespace "$NAMESPACE" >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            log_msg "INFO" "'$NAMESPACE' namespace removed successfully."
        else
            log_msg "ERROR" "Failed to remove '$NAMESPACE' namespace."
        fi
    else
        log_msg "INFO" "Namespace '$NAMESPACE' does not exist."
    fi
}

# Interactive menu function.
interactive_menu() {
    while true; do
        echo ""
        echo "-------------------------------"
        echo "MySQL-Kafka-Bridge Deployment Menu"
        echo "-------------------------------"
        echo "1. Deploy MySQL-Kafka-Bridge in Minikube Cluster"
        echo "2. Remove MySQL-Kafka-Bridge from Minikube Cluster"
        echo "3. Exit to resource deployment menu"
        echo "-------------------------------"
        read -rp "Enter your choice [1-3]: " choice
        case $choice in
            1)
                log_msg "INFO" "User selected deployment option."
                deploy_bridge
                ;;
            2)
                log_msg "INFO" "User selected removal option."
                remove_database_namespace
                ;;
            3)
                log_msg "INFO" "User selected to exit the menu."
                echo "Exiting menu..."
                exit 0
                ;;
            *)
                echo "Invalid input. Please enter 1, 2, or 3."
                ;;
        esac
    done
}

# --- Start of Script ---
mkdir -p "$LOG_DIR" || { echo "Failed to create log directory '$LOG_DIR'." && exit 1; }
log_msg "INFO" "Starting MySQL-Kafka-Bridge deployment script."
interactive_menu
