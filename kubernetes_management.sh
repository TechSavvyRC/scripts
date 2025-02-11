#!/bin/bash
# minikube_management.sh
#
# This script provides an interactive main menu for managing Minikube.
# Users can choose the Minikube Manager or the Minikube Resource Manager.
# The Resource Manager displays a list of resource deployment options, each calling its own script.
# After each task, the script returns to the resource menu until the user selects Exit to return to the main menu.

LOG_FILE="/opt/minikube/scripts/shell/minikube_management.log"

# log_info: Writes a message to the console (plain) and appends it with timestamp and level to the log file.
log_info() {
    echo "$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" >> "$LOG_FILE"
}

# log_error: Writes an error message to stderr and appends it with timestamp and level to the log file.
log_error() {
    echo "$1" >&2
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >> "$LOG_FILE"
}

# run_script: Executes a subordinate script given its full path.
run_script() {
    local script_path="$1"
    log_info "Executing script: ${script_path}"
    if [[ "${script_path}" == *.py ]]; then
        python "${script_path}"
    else
        bash "${script_path}"
    fi
    log_info "Task completed successfully."
}

# resource_menu: Displays the resource menu and calls the appropriate subordinate script.
resource_menu() {
    while true; do
	    echo
        log_info "Resource Menu:"
        log_info "1. Kubernetes Dashboard"
        log_info "2. Velero"
        log_info "3. Database"
        log_info "4. Application"
        log_info "5. Streaming"
        log_info "6. Monitoring"
        log_info "7. Observability"
        log_info "8. Exit to Main Menu"
	    echo
        read -p "Please select a resource option (1-8): " choice
        case "$choice" in
            1) run_script "/opt/minikube/scripts/shell/deploy_kubernetes_dashboard.sh" ;;
            2) run_script "/opt/minikube/scripts/shell/deploy_velero.sh" ;;
            3) run_script "/opt/minikube/scripts/shell/deploy_mysql.sh" ;;
            4) run_script "/opt/minikube/scripts/shell/deploy_ecom_app.sh" ;;
            5) run_script "/opt/minikube/scripts/shell/deploy_kafka.sh" ;;
            6) run_script "/opt/minikube/scripts/shell/deploy_prometheus.sh" ;;
            7) run_script "/opt/minikube/scripts/shell/deploy_elk.sh" ;;
            8) log_info "Returning to Main Menu." ; break ;;
            *) log_info "Invalid selection. Please try again." ;;
        esac
    done
}

# main_menu: Displays the main menu with options for Minikube Manager and Minikube Resource Manager.
main_menu() {
    while true; do
	    echo
        log_info "Main Menu:"
        log_info "1. Minikube Manager"
        log_info "2. Minikube Resource Manager"
        log_info "3. Exit"
		echo
        read -p "Please select an option (1-3): " choice
        case "$choice" in
            1) run_script "/opt/minikube/scripts/shell/minikube-manager.sh" ;;
            2) resource_menu ;;
            3) log_info "Exiting minikube_management.sh" ; exit 0 ;;
            *) log_info "Invalid selection. Please try again." ;;
        esac
    done
}

# Main execution starts here.
main_menu
