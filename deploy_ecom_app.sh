#!/bin/bash
# deploy_ecom_app.sh
#
# This script deploys an ecommerce application resource in a Minikube cluster.
# It ensures that the script is run only by 'muser', verifies required directories and files,
# fetches missing files from the GitHub repository, checks Minikube status and the 'application' namespace,
# and then deploys or uninstalls the application resource.
#
# Messages are displayed on screen (without timestamps) and written to a log file (with timestamps and log levels).
# The script can be executed independently or called by another script (returning control when done).

LOG_DIR="/opt/minikube/scripts/shell/logs"
SCRIPT_NAME=$(basename "$0")
LOG_FILE="${LOG_DIR}/${SCRIPT_NAME%.*}.log"
BASE_DIR="/opt/minikube/namespaces/application"
REQUIRED_FILES=("Dockerfile" "ecom_app.yaml" "ecom_transactions.py" "debug_pod.yaml")
GIT_REPO_URL="https://github.com/TechSavvyRC/application.git"
NAMESPACE="application"

# log_info: Logs an informational message to the console (plain) and to the log file (with timestamp and level).
log_info() {
    echo "$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" >> "$LOG_FILE"
}

# log_error: Logs an error message to stderr and to the log file.
log_error() {
    echo "$1" >&2
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >> "$LOG_FILE"
}

# Check that the script is run by 'muser'.
if [ "$(whoami)" != "muser" ]; then
    log_error "This script must be executed by 'muser'."
    exit 1
fi

# Ensure log directory exists.
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR" || { log_error "Failed to create log directory: $LOG_DIR"; exit 1; }
    log_info "Created log directory: $LOG_DIR"
fi

# ensure_directory: Ensures that a directory exists; creates it if missing.
ensure_directory() {
    if [ ! -d "$1" ]; then
        mkdir -p "$1" || { log_error "Failed to create directory: $1"; exit 1; }
        log_info "Created directory: $1"
    fi
}

# change_directory: Changes to the specified directory.
change_directory() {
    cd "$1" || { log_error "Failed to change directory to $1"; exit 1; }
    log_info "Changed directory to $1"
}

# verify_files: Checks if all required files exist; if not, fetch them.
verify_files() {
    local missing=0
    for file in "${REQUIRED_FILES[@]}"; do
        if [ ! -f "$file" ]; then
            log_info "Missing file: $file"
            missing=1
        fi
    done
    if [ $missing -eq 1 ]; then
        log_info "Fetching required files from GitHub repository..."
        git clone "$GIT_REPO_URL" temp_repo || { log_error "Git clone failed."; exit 1; }
        for file in "${REQUIRED_FILES[@]}"; do
            if [ -f "temp_repo/$file" ]; then
                cp "temp_repo/$file" .
                log_info "Fetched $file."
            else
                log_error "$file not found in repository."
                rm -rf temp_repo
                exit 1
            fi
        done
        rm -rf temp_repo
    else
        log_info "All required files are present."
    fi
}

# check_minikube_status: Verifies that Minikube is running.
check_minikube_status() {
    if ! minikube status | grep -q "Running"; then
        log_error "Minikube is not running. Please start Minikube (e.g. 'minikube start') and try again."
        exit 1
    fi
    log_info "Minikube is running."
}

# ensure_namespace: Checks if a namespace exists; if not, creates it.
ensure_namespace() {
    if ! kubectl get namespace "$1" >/dev/null 2>&1; then
        log_info "Namespace '$1' does not exist. Creating it..."
        kubectl create namespace "$1" || { log_error "Failed to create namespace '$1'"; exit 1; }
        log_info "Namespace '$1' created."
    else
        log_info "Namespace '$1' exists."
    fi
}

# get_resources: Gets resources in the given namespace.
get_resources() {
    kubectl get all -n "$1" 2>/dev/null
}

# resources_belong_to_app: Checks if all resource names contain 'ecommerce-application'.
resources_belong_to_app() {
    local output
    output=$(get_resources "$1")
    # Skip header; check each non-header line.
    while read -r line; do
        if [[ $line == NAME* ]] || [[ -z $line ]]; then
            continue
        fi
        local res_name
        res_name=$(echo "$line" | awk '{print $1}')
        if [[ $res_name != *"ecommerce-application"* ]]; then
            return 1
        fi
    done <<< "$output"
    return 0
}

# display_resources: Displays the resources in the specified format.
display_resources() {
    local output
    output=$(get_resources "$1")
    echo "-------------------------------------------------------------------------------------------------"
    echo "## Resources Running Under Application Namespace"
    echo "-------------------------------------------------------------------------------------------------"
    echo "$output"
    echo "-------------------------------------------------------------------------------------------------"
    log_info "Displayed resources in namespace '$1'."
}

# deploy_resources: Deploys the ecommerce application resource using 'kubectl apply -f ecom_app.yaml'.
deploy_resources() {
    kubectl apply -f ecom_app.yaml || { log_error "Deployment failed."; exit 1; }
    log_info "Deployment command executed successfully."
}

# manage_existing_resources: Checks if resources exist in the namespace and handles them.
manage_existing_resources() {
    local output
    output=$(get_resources "$NAMESPACE")
    if [ -n "$output" ]; then
        if resources_belong_to_app "$NAMESPACE"; then
            log_info "All running resources belong to 'ecommerce-application'."
            display_resources "$NAMESPACE"
            log_info "Exiting since application resources are already running."
            exit 0
        else
            echo "Some resources are already running under the '$NAMESPACE' namespace:"
            display_resources "$NAMESPACE"
            read -p "Enter 'c' to continue without deleting the namespace, or 'd' to delete the namespace and deploy fresh resources: " choice
            if [[ "$choice" =~ ^(d|D)$ ]]; then
                log_info "User opted to delete the namespace."
                kubectl delete namespace "$NAMESPACE" || { log_error "Failed to delete namespace."; exit 1; }
                sleep 5
                ensure_namespace "$NAMESPACE"
            elif [[ "$choice" =~ ^(c|C)$ ]]; then
                log_info "User opted to continue without deleting the namespace."
            else
                log_error "Invalid selection. Exiting."
                exit 1
            fi
        fi
    else
        log_info "No resources found in namespace '$NAMESPACE'."
    fi
}

# perform_installation: Executes the full installation workflow.
perform_installation() {
    change_directory "$BASE_DIR"
    verify_files
    check_minikube_status
    ensure_namespace "$NAMESPACE"
    manage_existing_resources
    deploy_resources
    display_resources "$NAMESPACE"
    log_info "Ecommerce application resource deployment under the 'application' namespace is successful."
}

# perform_uninstallation: Deletes the 'application' namespace.
perform_uninstallation() {
    kubectl delete namespace "$NAMESPACE" || { log_error "Failed to delete namespace '$NAMESPACE'."; exit 1; }
    log_info "Namespace '$NAMESPACE' deleted successfully."
}

# Main interactive menu.
while true; do
    echo ""
    echo "Ecommerce Application Deployment Menu:"
    echo "1. Installation"
    echo "2. Uninstallation"
    echo "3. Exit"
    read -p "Please select an option (1-3): " choice
    case "$choice" in
        1)
            log_info "User selected Installation."
            ensure_directory "$BASE_DIR"
            perform_installation
            ;;
        2)
            log_info "User selected Uninstallation."
            perform_uninstallation
            ;;
        3)
            log_info "Exiting deploy_ecom_app.sh."
            exit 0
            ;;
        *)
            log_info "Invalid selection. Please try again."
            ;;
    esac
done
