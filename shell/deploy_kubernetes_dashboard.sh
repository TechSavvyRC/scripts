#!/bin/bash
# deploy_kubernetes_dashboard.sh
# This script deploys the Kubernetes Dashboard via Helm on a Minikube cluster.
# It replicates the functionality of deploy_kubernetes_dashboard.py exactly.
# It logs messages to a log file (with timestamps and log level) and to the console
# (plain text without timestamps or log level). It waits for all pods in the
# 'kubernetes-dashboard' namespace to be fully ready (READY: 1/1) before proceeding
# to patch the 'kubernetes-dashboard-kong-proxy' service.
# It then performs various post-deployment tasks as detailed in the Python script.

set -euo pipefail

#######################################
# Global Variables and Logging Setup  #
#######################################
LOG_DIR="/opt/minikube/scripts/logs"
SCRIPT_NAME=$(basename "$0")
LOG_FILE="$LOG_DIR/${SCRIPT_NAME%.*}.log"

# Create log directory if it does not exist.
mkdir -p "$LOG_DIR"

# Logging functions: log_info prints to STDOUT and appends to the log file with a timestamp.
log_info() {
    local msg="$1"
    echo "$msg" >&2
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $msg" >> "$LOG_FILE"
}

log_error() {
    local msg="$1"
    echo "$msg" >&2
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $msg" >> "$LOG_FILE"
}

# run_command: Executes a command, logs it, checks return code (if nonzero, exits).
run_command() {
    local cmd="$1"
    log_info "Executing command: $cmd"
    # Capture output (stdout and stderr)
    local output
    if ! output=$(eval "$cmd" 2>&1); then
        local rc=$?
        log_error "Command failed with code $rc: $cmd"
        log_error "Output: $output"
        exit 1
    fi
    echo "$output" | sed 's/[[:space:]]*$//'
}

#######################################
# Helper Functions                    #
#######################################

# wait_for_pods: Poll until all pods in the namespace are ready (READY exactly "1/1").
wait_for_pods() {
    local namespace="$1"
    local timeout=300
    local interval=150
	echo
    log_info "Waiting for all Kubernetes Dashboard pods to be in Ready state (READY: 1/1)..."
    local elapsed=0
    while (( elapsed < timeout )); do
        local pod_output
        pod_output=$(run_command "kubectl get pods -n $namespace --no-headers" || true)
        if [[ -n "$pod_output" ]]; then
            local all_ready=true
            while IFS= read -r line; do
                # Split line into fields; field 2 is the READY state.
                local pod_name ready
                pod_name=$(echo "$line" | awk '{print $1}')
                ready=$(echo "$line" | awk '{print $2}')
                if [[ "$ready" != "1/1" ]]; then
                    all_ready=false
                    log_error "Pod '$pod_name' is not ready: READY state is '$ready'. Full details: $line"
                fi
            done <<< "$pod_output"
            if $all_ready; then
                log_info "All pods are ready (READY: 1/1)."
                return 0
            fi
        fi
        sleep "$interval"
        (( elapsed += interval ))
    done
    log_error "Timeout reached waiting for pods to be ready."
    exit 1
}

# display_resource_status: Shows pods and services status in formatted output.
display_resource_status() {
    local namespace="$1"
    log_info "Displaying resource status:"
    local pods services divider
    pods=$(run_command "kubectl get pods -n $namespace -o wide")
    services=$(run_command "kubectl get svc -n $namespace")
    divider=$(printf '%*s' 99 | tr ' ' '-')
    echo "$divider"
    echo "## Kubernetes Dashboard - Pods Status"
    echo "$divider"
    printf "%-55s %-8s %-8s %s\n" "NAME" "READY" "STATUS" "IP"
    # Skip header; process each pod line
    echo "$pods" | tail -n +2 | while read -r line; do
        local name ready status ip
        name=$(echo "$line" | awk '{print $1}')
        ready=$(echo "$line" | awk '{print $2}')
        status=$(echo "$line" | awk '{print $3}')
        ip=$(echo "$line" | awk '{print $6}')
        [[ -z "$ip" ]] && ip="N/A"
        printf "%-55s %-8s %-8s %s\n" "$name" "$ready" "$status" "$ip"
    done
    echo "$divider"
    echo "## Kubernetes Dashboard - Services Status"
    echo "$divider"
    printf "%-38s %-11s %-17s %-13s %s\n" "NAME" "TYPE" "CLUSTER-IP" "EXTERNAL-IP" "PORT(S)"
    echo "$services" | tail -n +2 | while read -r line; do
        local name svc_type cluster_ip external_ip ports
        name=$(echo "$line" | awk '{print $1}')
        svc_type=$(echo "$line" | awk '{print $2}')
        cluster_ip=$(echo "$line" | awk '{print $3}')
        external_ip=$(echo "$line" | awk '{print $4}')
        ports=$(echo "$line" | awk '{print $5}')
        printf "%-38s %-11s %-17s %-13s %s\n" "$name" "$svc_type" "$cluster_ip" "$external_ip" "$ports"
    done
    echo "$divider"
}

# check_and_create_sa_and_binding: Checks for ServiceAccount and ClusterRoleBinding; creates if missing.
check_and_create_sa_and_binding() {
    local namespace="$1"
    if ! kubectl get sa dashboard-admin-sa -n "$namespace" >/dev/null 2>&1; then
        log_info "ServiceAccount 'dashboard-admin-sa' not found. Creating..."
        run_command "kubectl create serviceaccount dashboard-admin-sa -n $namespace"
    else
        log_info "ServiceAccount 'dashboard-admin-sa' already exists."
    fi
    if ! kubectl get clusterrolebinding dashboard-admin-sa >/dev/null 2>&1; then
        log_info "ClusterRoleBinding 'dashboard-admin-sa' not found. Creating..."
        run_command "kubectl create clusterrolebinding dashboard-admin-sa --clusterrole=cluster-admin --serviceaccount=kubernetes-dashboard:dashboard-admin-sa"
    else
        log_info "ClusterRoleBinding 'dashboard-admin-sa' already exists."
    fi
}

# patch_service: Patches the 'kubernetes-dashboard-kong-proxy' service to type NodePort.
patch_service() {
    local namespace="$1"
    log_info "Patching service 'kubernetes-dashboard-kong-proxy' to type NodePort..."
    # Use double braces to escape for shell formatting.
    local patch_cmd
    #patch_cmd="kubectl -n $namespace patch svc kubernetes-dashboard-kong-proxy -p '{\"spec\": {\"type\": \"NodePort\"}}'"
    patch_cmd="kubectl -n $namespace patch svc kubernetes-dashboard-kong-proxy -p '{\"spec\": {\"type\": \"NodePort\", \"ports\": [{\"port\": 443, \"nodePort\": 30243}]}}'"
    run_command "$patch_cmd"
}

# call_secret_script: Calls the external secret generation script.
call_secret_script() {
    local secret_script="/opt/minikube/scripts/python/kd-secrete-generate.py"
    if [[ ! -f "$secret_script" ]]; then
        log_error "Secret generation script not found: $secret_script"
        exit 1
    fi
    log_info "Calling secret generation script: $secret_script"
    python3 "$secret_script"
    if [[ $? -ne 0 ]]; then
        log_error "Secret generation script failed."
        exit 1
    fi
}

# verify_and_apply_yaml: Verifies required YAML files exist and applies them.
verify_and_apply_yaml() {
    local required_files=("kubernetes-dashboard-ingress.yaml" "kubernetes-dashboard-secret.yaml")
    local missing=()
    for f in "${required_files[@]}"; do
        if [[ ! -f "$f" ]]; then
            missing+=("$f")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing YAML file(s): ${missing[*]}. Exiting."
        exit 1
    fi
    for f in "${required_files[@]}"; do
        log_info "Applying YAML file: $f"
        run_command "kubectl apply -f $f"
    done
}

# restart_ingress: Restarts the Nginx Ingress Pods.
restart_ingress() {
    log_info "Restarting Nginx Ingress Pods..."
    run_command "kubectl rollout restart deployment ingress-nginx-controller -n ingress-nginx"
}

# post_deployment: Displays post-deployment summary and instructions.
post_deployment() {
    #local nodeport="$1"
    shift
    local tasks=("$@")
    log_info "Post-deployment steps completed successfully."
    echo -e "\nTasks performed:"
    for t in "${tasks[@]}"; do
        echo " - $t"
    done
    local token
    token=$(run_command "kubectl -n kubernetes-dashboard create token dashboard-admin-sa --duration=48h")
    echo -e "\nDashboard Access Token (valid for 48h):"
    echo "$token"
    echo -e "\nAccess the Kubernetes Dashboard UI at:"
    echo "   https://kubernetes.marvel.com"
}

# Remove Dashboard Namespace
remove_namespace() {
    log_info "Initiating removal of Kubernetes Dashboard namespace..."
    if kubectl get ns kubernetes-dashboard &>/dev/null; then
        if run_command "kubectl delete ns kubernetes-dashboard"; then
            log_info "Kubernetes Dashboard namespace removed successfully."
            echo "Kubernetes Dashboard namespace removed successfully."
        else
            log_error "Failed to remove Kubernetes Dashboard namespace."
            echo "Error: Failed to remove the namespace."
        fi
    else
        echo "Namespace 'kubernetes-dashboard' does not exist."
    fi
}

# Interactive Menu
interactive_menu() {
    while true; do
        echo ""
        echo "-------------------------------------------------------"
        echo "Kubernetes Dashboard Menu"
        echo "-------------------------------------------------------"
        echo "1. Deploy Kubernetes Dashboard in Minikube Cluster"
        echo "2. Remove Kubernetes Dashboard from Minikube Cluster"
        echo "3. Exit to resource deployment menu"
        echo "-------------------------------------------------------"
        read -rp "Enter your choice [1-3]: " choice
        case $choice in
            1)
                log_info "User selected deployment option."
                # Call existing main deployment function
                main
                ;;
            2)
                log_info "User selected removal option."
                remove_namespace
                ;;
            3)
                log_info "User selected to exit the menu."
                echo "Exiting..."
                exit 0
                ;;
            *)
                echo "Invalid input. Please enter 1, 2, or 3."
                ;;
        esac
    done
}

#######################################
# Main Execution Flow                 #
#######################################
main() {
    local tasks_performed=()

    # 1. Ensure the script is executed only by user 'muser'
    if [[ "$(whoami)" != "muser" ]]; then
        echo "Error: This script must be executed only by 'muser'." >&2
        exit 1
    fi
    tasks_performed+=("User check passed (executed as 'muser')")

    # 2. Logging directory has been created above.
    log_info "Logger initialized."
    tasks_performed+=("Logging configured")

    # 3. Change directory to /opt/minikube/namespaces/kubernetes-dashboard/
    local target_dir="/opt/minikube/namespaces/kubernetes-dashboard/"
    if ! cd "$target_dir"; then
        log_error "Failed to change directory to $target_dir"
        exit 1
    fi
    log_info "Changed directory to $target_dir"
    tasks_performed+=("Changed directory to $target_dir")

    # 4. Check Minikube status
    local status_output
    status_output=$(run_command "minikube status" )
    if [[ "$status_output" != *"Running"* ]]; then
        echo "Minikube is not running. Please start Minikube before executing the script."
        exit 1
    fi
    log_info "Minikube is running."
    tasks_performed+=("Minikube status verified")

    # 5. Check if 'kubernetes-dashboard' namespace exists.
    local ns_exists=false
    if kubectl get ns kubernetes-dashboard >/dev/null 2>&1; then
        ns_exists=true
        log_info "Namespace 'kubernetes-dashboard' exists: true"
    else
        log_info "Namespace 'kubernetes-dashboard' does not exist."
    fi

    # 6. If namespace exists, check for resources and prompt user.
    local delete_ns=false
    if $ns_exists; then
        local resources
        resources=$(run_command "kubectl get all -n kubernetes-dashboard")
        if [[ $(echo "$resources" | wc -l) -gt 1 ]]; then
            echo "Resources are running under the 'kubernetes-dashboard' namespace."
            read -p "Enter 'delete' to delete the namespace, or 'continue' to proceed without deleting: " choice
            if [[ "$choice" == "delete" ]]; then
                delete_ns=true
                log_info "User opted to delete the namespace."
                run_command "kubectl delete ns kubernetes-dashboard"
                log_info "Waiting for namespace deletion..."
                while kubectl get ns kubernetes-dashboard >/dev/null 2>&1; do
                    sleep 5
                done
                tasks_performed+=("Existing 'kubernetes-dashboard' namespace deleted")
            else
                log_info "User opted to continue without deleting namespace."
                tasks_performed+=("Existing resources detected; continuing without deletion")
            fi
        else
            log_info "No resources found in the existing namespace."
        fi
    fi

    # 7. Deploy Dashboard using Helm.
    local helm_cmd=""
    if $ns_exists && ! $delete_ns; then
        helm_cmd="helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard --namespace kubernetes-dashboard"
    else
        helm_cmd="helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard --create-namespace --namespace kubernetes-dashboard"
    fi
    run_command "$helm_cmd"
    tasks_performed+=("Kubernetes Dashboard deployed via Helm")

    # 8. Wait until all pods are fully ready (READY: 1/1)
    wait_for_pods "kubernetes-dashboard"
    tasks_performed+=("Dashboard resources reached full Ready state")

    # 9. Display pods and services status
    display_resource_status "kubernetes-dashboard"
    tasks_performed+=("Resource status displayed")

    # 10. Verify ServiceAccount and ClusterRoleBinding.
    check_and_create_sa_and_binding "kubernetes-dashboard"
    tasks_performed+=("ServiceAccount and ClusterRoleBinding verified/created")

    # 11. Patch service to NodePort (only after ensuring pods are ready).
    patch_service "kubernetes-dashboard"
    tasks_performed+=("Service 'kubernetes-dashboard-kong-proxy' patched to NodePort")

    # 12. Call the external secret generation script.
    call_secret_script
    tasks_performed+=("Secret generation script executed")

    # 13. Verify YAML files exist and apply them.
    verify_and_apply_yaml
    tasks_performed+=("YAML files verified and applied")

    # 14. Restart Nginx Ingress Pods.
    restart_ingress
    tasks_performed+=("Nginx Ingress Pods restarted")

    # 15. Post-deployment summary: display tasks, instruct Nginx config update,
    # retrieve token, and show Dashboard URL.
    post_deployment "${tasks_performed[@]}"
}

# Instead of calling main directly, call the interactive menu.
interactive_menu
