#!/bin/bash
# Simplified Velero CLI installer/uninstaller for Minikube.
# This script installs the Velero CLI and deploys Velero resources on a Minikube cluster,
# or uninstalls them, without performing any update operations.
# It checks for existing Velero CLI and resources before proceeding.
 
# ANSI escape codes for colors.
BOLD_RED="\033[1;31m"
YELLOW="\033[33m"
RESET="\033[0m"
 
# Display the attention note.
echo -e "------------------------------------------------------------------------------------------------------"
echo -e "${BOLD_RED}ATTENTION${RESET}: ${YELLOW}"
echo -e "This script is designed exclusively for performing the installation and uninstallation of the"
echo -e "Velero CLI, as well as the deployment and removal of Velero resources from a Kubernetes/Minikube"
echo -e "cluster. Please note that this script does not create backups of any existing resources within"
echo -e "the cluster. As such, it is important to exercise caution when using this script. Additionally,"
echo -e "this script does not modify or update any existing Velero CLI setup or resources within the cluster."
echo -e "${RESET}------------------------------------------------------------------------------------------------------"
 
SCRIPT_NAME=$(basename "$0")
LOG_DIR="/opt/minikube/scripts/logs"
LOG_FILE="${LOG_DIR}/${SCRIPT_NAME%.*}.log"
 
# log_info: Logs an informational message.
log_info() {
    echo "$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" >> "$LOG_FILE"
}
 
# log_error: Logs an error message.
log_error() {
    echo "$1" >&2
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >> "$LOG_FILE"
}
 
# Check that the script is run as 'muser'.
if [ "$(whoami)" != "muser" ]; then
    log_error "Error: This script must be executed by 'muser'."
    exit 1
fi
 
# Create log directory if missing.
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR" || { log_error "Failed to create log directory: $LOG_DIR"; exit 1; }
    log_info "Created log directory: $LOG_DIR"
fi
 
# fetch_latest_version: Uses the GitHub API to get the latest Velero version.
fetch_latest_version() {
    LATEST_VERSION=$(curl -s https://api.github.com/repos/vmware-tanzu/velero/releases/latest | jq -r .tag_name)
    if [ -z "$LATEST_VERSION" ]; then
        log_error "Failed to fetch the latest Velero version."
        exit 1
    fi
    log_info "Fetched latest Velero version: $LATEST_VERSION"
    echo "$LATEST_VERSION"
}
 
# install_velero: Downloads and installs the Velero CLI for a specified version.
install_velero() {
    local version="$1"
    local tarball="velero-${version}-linux-amd64.tar.gz"
    local download_url="https://github.com/vmware-tanzu/velero/releases/download/${version}/${tarball}"
    log_info "Downloading Velero from ${download_url}"
    curl -LO "${download_url}" || { log_error "Failed to download Velero tarball."; exit 1; }
    log_info "Extracting ${tarball}"
    tar xvf "${tarball}" || { log_error "Failed to extract tarball."; exit 1; }
    local binary_path="velero-${version}-linux-amd64/velero"
    log_info "Installing Velero CLI to /usr/local/bin/velero (requires sudo)"
    sudo mv "$binary_path" /usr/local/bin/velero || { log_error "Failed to move Velero binary."; exit 1; }
    rm -rf "${tarball}" "velero-${version}-linux-amd64"
    log_info "Velero CLI installed successfully, version ${version}"
}
 
# deploy_velero_resource: Deploys Velero resources on the Minikube cluster after prompting for a bucket name.
deploy_velero_resource() {
    local host_ip="$1"
    local default_bucket="minikubevelero"
    echo "The current bucket name is '${default_bucket}'."
    read -p "Do you want to use the default bucket name? (yes/no): " bucket_choice
    if [[ "$bucket_choice" =~ ^(no|n)$ ]]; then
        read -p "Please enter the desired bucket name (must already exist in MinIO): " user_bucket
        bucket="$user_bucket"
    else
        bucket="$default_bucket"
    fi
    log_info "Using bucket: ${bucket} (Note: the bucket must already exist in MinIO, or deployment will fail.)"
    local install_cmd="velero install --provider aws --plugins velero/velero-plugin-for-aws:v1.8.0 --bucket ${bucket} --secret-file ./minio-credentials.txt --use-volume-snapshots=false --backup-location-config region=minio,s3ForcePathStyle=true,s3Url=https://${host_ip}:9000,insecureSkipTLSVerify=true --cacert ./public.crt"
    log_info "Deploying Velero resource with the following command:"
    log_info "${install_cmd}"
    eval ${install_cmd} || { log_error "Velero resource deployment failed."; exit 1; }
    log_info "Velero resource deployed successfully."
}
 
# verify_velero_deployment: Verifies the deployment by creating a test backup and displays example commands.
verify_velero_deployment() {
    if velero backup create test-backup --include-namespaces default; then
        log_info "Test backup created successfully."
        log_info "\nVelero resource is deployed and ready for use on the Minikube cluster."
        log_info "\nExample Backup Commands:"
        log_info "  1. Backup a specific namespace:"
        log_info "     velero backup create my-backup --include-namespaces mynamespace"
        log_info "  2. Backup the entire cluster:"
        log_info "     velero backup create full-backup"
        log_info "  3. Backup only pods:"
        log_info "     velero backup create pods-backup --include-resources pods"
        log_info "  4. Backup only services:"
        log_info "     velero backup create services-backup --include-resources services"
        log_info "  5. Backup only statefulsets:"
        log_info "     velero backup create statefulsets-backup --include-resources statefulsets"
        log_info "  6. Backup only deployments:"
        log_info "     velero backup create deployments-backup --include-resources deployments"
        log_info "\nExample Restore Commands:"
        log_info "  a. Restore from a backup:"
        log_info "     velero restore create --from-backup my-backup"
        log_info "  b. Restore a specific namespace from a backup:"
        log_info "     velero restore create --from-backup my-backup --include-namespaces mynamespace"
    else
        log_error "Verification failed: Test backup creation was unsuccessful."
        log_error "Please check Velero Pod logs using 'kubectl get pods -n velero' and 'kubectl logs -f <Velero_Pod_Name> -n velero'."
        exit 1
    fi
}
 
# uninstall_velero: Deletes the Velero namespace and removes the Velero CLI.
uninstall_velero() {
    log_info "Uninstalling Velero resources..."
    kubectl delete namespace velero
    log_info "Velero namespace deletion initiated."
    log_info "Removing Velero CLI from /usr/local/bin (requires sudo)..."
    sudo rm -f /usr/local/bin/velero
    log_info "Velero CLI and resources uninstalled successfully."
}
 
# perform_installation: Executes the installation workflow.
# It checks if Velero CLI is installed and if Velero resources exist; if resources exist, it skips deployment.
perform_installation() {
    TARGET_DIR="/opt/minikube/namespaces/velero/"
    cd "$TARGET_DIR" || { log_error "Failed to change directory to ${TARGET_DIR}"; exit 1; }
    log_info "Changed directory to ${TARGET_DIR}"
 
    if ! minikube status | grep -q "Running"; then
        log_error "Minikube is not running. Please start Minikube (e.g. 'minikube start') before executing the script."
        exit 1
    fi
    log_info "Minikube is running."
 
    for file in public.crt minio-credentials.txt; do
        if [ ! -f "$file" ]; then
            log_error "Required file missing: ${file}"
            exit 1
        fi
    done
    log_info "Required files are present."
 
    HOST_IP=$(for ip in $(getent hosts techsavvyrc | awk '{print $1}'); do 
        if ping -c 1 -W 1 "$ip" >/dev/null 2>&1; then 
            echo "$ip"; break; 
        fi; 
    done)
    if [ -z "$HOST_IP" ]; then
        log_error "Failed to fetch HOST_IP."
        exit 1
    fi
    log_info "Fetched HOST_IP: $HOST_IP"
 
    LATEST_VERSION=$(fetch_latest_version)
    if ! command -v velero >/dev/null 2>&1; then
        log_info "Velero CLI not found. Installing version ${LATEST_VERSION}"
        install_velero "$LATEST_VERSION"
    else
        log_info "Velero CLI is already installed. Skipping CLI installation."
    fi
 
    # Check if Velero resources already exist.
    if kubectl get deployment velero -n velero >/dev/null 2>&1; then
        log_info "Velero resources already exist in the cluster. Skipping resource deployment."
    else
        log_info "No existing Velero resources found. Proceeding with resource deployment."
        deploy_velero_resource "$HOST_IP"
    fi
 
    verify_velero_deployment
}
 
# perform_uninstallation: Executes the uninstallation workflow.
perform_uninstallation() {
    log_info "User selected Uninstallation."
    uninstall_velero
}
 
# Main interactive menu.
echo ""
echo "Velero CLI Management Menu:"
echo "  1. Installation"
echo "  2. Uninstallation"
read -p "Please select an option (1 or 2): " choice
 
if [ "$choice" != "1" ] && [ "$choice" != "2" ]; then
    log_error "Invalid selection. Please run the script again and choose either 1 or 2."
    exit 1
fi
 
if [ "$choice" == "1" ]; then
    log_info "User selected Installation."
    perform_installation
elif [ "$choice" == "2" ]; then
    perform_uninstallation
fi
 
exit 0
