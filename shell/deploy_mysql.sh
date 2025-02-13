#!/bin/bash

# Log file setup
SCRIPT_DIR="/opt/minikube/scripts/shell"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/deploy_mysql.log"

# Create log directory if it doesn't exist
mkdir -p "${LOG_DIR}"

# Logging function
log_message() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "${message}"
    echo "${timestamp} - ${level} - ${message}" >> "${LOG_FILE}"
}

# Check if user is muser
check_user() {
    if [[ $(whoami) != "muser" ]]; then
        log_message "ERROR" "This script must be run by 'muser'. Current user: $(whoami)"
        exit 1
    fi
}

# Verify and create directories
setup_directories() {
    local namespace_dir="/opt/minikube/namespaces/database"
    mkdir -p "${namespace_dir}"
    cd "${namespace_dir}" || exit 1
}

# Check for required files and fetch if missing
verify_files() {
    local namespace_dir="/opt/minikube/namespaces/database"
    local required_files=("debug-pod.yaml" "init-db.sql" "mysql.yaml" "phpmyadmin.yaml")
    local missing_files=false

    for file in "${required_files[@]}"; do
        if [[ ! -f "${namespace_dir}/${file}" ]]; then
            missing_files=true
            break
        fi
    done

    if [[ "${missing_files}" == true ]]; then
        log_message "INFO" "Fetching required files from GitHub..."
        git clone https://github.com/TechSavvyRC/database.git "${namespace_dir}" || {
            log_message "ERROR" "Failed to fetch files from GitHub"
            exit 1
        }
    fi
}

# Check if Minikube is running
check_minikube() {
    if ! minikube status | grep -q "Running"; then
        log_message "ERROR" "Minikube is not running. Please start Minikube first."
        exit 1
    fi
}

# Create or verify database namespace
manage_namespace() {
    if ! kubectl get namespace database &>/dev/null; then
        kubectl create namespace database || {
            log_message "ERROR" "Failed to create database namespace"
            exit 1
        }
        log_message "INFO" "Created database namespace"
    else
        log_message "INFO" "Database namespace already exists"
    fi
}

# Display resources in formatted table
display_resources() {
    echo -e "\n-------------------------------------------------------------------------------------------------"
    echo "## Resources Running Under 'database' Namespace"
    echo "-------------------------------------------------------------------------------------------------"
    kubectl get all -n database
    echo "-------------------------------------------------------------------------------------------------"
}

# Check existing resources
check_existing_resources() {
    local resources
    resources=$(kubectl get all -n database 2>/dev/null)
    
    if [[ -z "${resources}" ]]; then
        echo "empty"
        return
    fi

    local unexpected=false
    while IFS= read -r line; do
        if [[ -n "${line}" && ! "${line}" =~ mysql|phpmyadmin|NAME ]]; then
            unexpected=true
            break
        fi
    done <<< "${resources}"

    if [[ "${unexpected}" == true ]]; then
        echo "mixed"
    elif echo "${resources}" | grep -qiE 'mysql|phpmyadmin'; then
        echo "expected"
    else
        echo "empty"
    fi
}

# Wait for pods to be ready
wait_for_pods() {
    local app_label=$1
    local max_attempts=30
    local attempt=0

    while ((attempt < max_attempts)); do
        if kubectl get pods -n database -l "app=${app_label}" -o custom-columns=:status.phase | grep -q "Running"; then
            return 0
        fi
        sleep 10
        ((attempt++))
    done

    return 1
}

# Deploy resources
deploy_resources() {
    local delete_namespace=$1

    if [[ "${delete_namespace}" == true ]]; then
        kubectl delete namespace database
        sleep 10
        manage_namespace
    fi

    # Deploy MySQL
    kubectl apply -f mysql.yaml -n database || {
        log_message "ERROR" "Failed to deploy MySQL"
        exit 1
    }

    if ! wait_for_pods "mysql"; then
        log_message "ERROR" "MySQL pods failed to reach ready state"
        exit 1
    fi

    # Deploy PhpMyAdmin
    kubectl apply -f phpmyadmin.yaml -n database || {
        log_message "ERROR" "Failed to deploy PhpMyAdmin"
        exit 1
    }

    if ! wait_for_pods "phpmyadmin"; then
        log_message "ERROR" "PhpMyAdmin pods failed to reach ready state"
        exit 1
	fi
}

# Remove Database Namespace
remove_namespace() {
    log_message "Initiating removal of database namespace..."
    if kubectl get ns database &>/dev/null; then
        if kubectl delete ns database; then
            log_message "Database namespace removed successfully."
            echo "Database namespace removed successfully."
            return 0
        else
            log_message "Failed to remove Database namespace."
            echo "Error: Failed to remove the namespace."
            return 1
        fi
    else
        echo "Namespace 'Database' does not exist."
    fi
}

# Interactive Menu
interactive_menu() {
    while true; do
        echo ""
        echo "-------------------------------"
        echo "Kubernetes Dashboard Menu"
        echo "-------------------------------"
        echo "1. Deploy MySQL and PhpMyAdmin in Minikube Cluster"
        echo "2. Remove MySQL and PhpMyAdmin from Minikube Cluster"
        echo "3. Exit to resource deployment menu"
        echo "-------------------------------"
        echo ""
        read -rp "Enter your choice [1-3]: " choice
        case $choice in
            1)
                log_message "User selected deployment option."
                # Call existing main deployment function
                main
                ;;
            2)
                log_message "User selected removal option."
                remove_namespace
                ;;
            3)
                log_message "User selected to exit the menu."
                echo "Exiting..."
                exit 0
                ;;
            *)
                echo "Invalid input. Please enter 1, 2, or 3."
                ;;
        esac
    done
}

# Main execution
main() {
    check_user
    setup_directories
    verify_files
    check_minikube
    manage_namespace

    local resource_status
    resource_status=$(check_existing_resources)

    case "${resource_status}" in
        "expected")
            log_message "INFO" "Current resources in database namespace:"
            display_resources
            log_message "INFO" "Deployment already exists with expected resources"
            ;;
        "mixed")
            log_message "INFO" "Found existing resources in database namespace:"
            display_resources
            read -p "Do you want to delete the namespace and start fresh? (yes/no): " response
            if [[ "${response}" == "yes" ]]; then
                deploy_resources true
            else
                deploy_resources false
            fi
            ;;
        "empty")
            deploy_resources false
            ;;
    esac

    log_message "INFO" "Final deployment status:"
    display_resources
    log_message "INFO" "Deployment completed successfully"
}

# Instead of calling main directly, call the interactive menu.
interactive_menu

# Execute main function
#main