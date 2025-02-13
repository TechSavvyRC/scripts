#!/bin/bash

# Configuration
USER="muser"
LOG_DIR="/opt/minikube/scripts/shell/logs"
LOG_FILE="$LOG_DIR/minikube_manager.log"
BACKUP_DIR="/opt/minikube/backups"
REQUIRED_NAMESPACES=("application" "database" "streaming" "monitoring" "observability")
MINIKUBE_START_CMD="minikube start --driver=docker --apiserver-ips=192.168.29.223 --extra-config=apiserver.enable-admission-plugins=NamespaceLifecycle,LimitRanger,ServiceAccount"

# Directory initialization
initialize_directories() {
    [[ ! -d "$LOG_DIR" ]] && mkdir -p "$LOG_DIR"
    [[ ! -d "$BACKUP_DIR" ]] && mkdir -p "$BACKUP_DIR"
    [[ ! -f "$LOG_FILE" ]] && touch "$LOG_FILE"
}

# Logging function
log() {
    local timestamp
    timestamp=$(date +"%Y-%m-%d %T")
    echo -e "$@"
    echo -e "${timestamp} - $@" >> "${LOG_FILE}"
}

# User verification
verify_user() {
    if [[ "$(whoami)" != "${USER}" ]]; then
        log "ERROR: This script must be executed as user '${USER}'"
        exit 1
    fi
}

# Comprehensive backup function
backup_resources() {
    local backup_timestamp
    backup_timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="${BACKUP_DIR}/backup_${backup_timestamp}"
    
    mkdir -p "${backup_path}" || {
        log "ERROR: Failed to create backup directory"
        exit 1
    }

    log "\nStarting resource backup..."
    
    local namespaced_resources=(pods deployments services configmaps secrets ingresses networkpolicies pvc statefulsets daemonsets jobs cronjobs replicasets)
    
    for ns in $(kubectl get namespaces -o jsonpath='{.items[*].metadata.name}'); do
        ns_dir="${backup_path}/namespaces/${ns}"
        mkdir -p "${ns_dir}"
        for resource in "${namespaced_resources[@]}"; do
            kubectl get "${resource}" -n "${ns}" -o yaml > "${ns_dir}/${resource}.yaml" 2>/dev/null
        done
    done

    # Backup Minikube config
    minikube stop 2>/dev/null
    tar -czf "${backup_path}/minikube_config.tar.gz" -C "/home/${USER}" .minikube 2>/dev/null

    log "\nBackup completed: ${backup_path}"
}

# Version management functions for Minikube
get_current_version() {
    minikube version 2>/dev/null | awk '/minikube version:/ {print $3}'
}
get_latest_version() {
    minikube update-check 2>/dev/null | awk '/LatestVersion:/ {print $2}'
}

# Install Minikube
	install_minikube() {
		# MINIKUBE INSTALLATION/UPGRADE
		if command -v minikube &>/dev/null; then
		    echo "condition passed"
			local current_minikube latest_minikube
			current_minikube=$(get_current_version)
			latest_minikube=$(get_latest_version)
            echo $current_minikube
            echo $latest_minikube
			if [[ "$current_minikube" != "$latest_minikube" ]]; then
				log "\nMinikube already installed (Version: ${current_minikube})"
				log "\nNew version available: ${latest_minikube}"
				read -rp "Would you like to upgrade Minikube? [y/N] " -n 1 reply
				echo
				if [[ "$reply" =~ ^[Yy]$ ]]; then
					perform_update
					current_minikube=$(get_current_version)  # refresh the version after upgrade
				else
					read -rp "Start Minikube with the current version? [y/N] " -n 1 reply
					echo
					[[ "$reply" =~ ^[Yy]$ ]] && start_minikube
				fi
			else
			log "\nMinikube already installed (Version: ${current_minikube})"
				read -rp "Start Minikube? [y/N] " -n 1 reply
				echo
				[[ "$reply" =~ ^[Yy]$ ]] && start_minikube
			fi
		else
			log "\nInstalling Minikube..."
			curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
			sudo install minikube-linux-amd64 /usr/local/bin/minikube
			sudo chmod +x /usr/local/bin/minikube
			rm minikube-linux-amd64
			log "\nMinikube installation complete."
		fi

    # KUBECTL INSTALLATION/UPGRADE
    if command -v kubectl &>/dev/null; then
        local current_kubectl latest_kubectl
        # Get the current kubectl version using the correct command
        current_kubectl=$(kubectl version --client=true | grep 'Client Version:' | awk '{print $3}')
        latest_kubectl=$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)
        if [[ "$current_kubectl" == "$latest_kubectl" ]]; then
            log "\nThe latest version of kubectl is already installed. (Version: ${current_kubectl})"
        else
            log "\nAn updated version of kubectl is available."
            log "Current kubectl version: ${current_kubectl}"
            log "Latest kubectl version: ${latest_kubectl}"
            read -rp "Would you like to upgrade kubectl? [y/N] " -n 1 reply
            echo
            if [[ "$reply" =~ ^[Yy]$ ]]; then
                log "\nUpgrading kubectl..."
                curl -LO "https://storage.googleapis.com/kubernetes-release/release/${latest_kubectl}/bin/linux/amd64/kubectl"
                sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
                rm kubectl
                log "\nKubectl upgraded to version: $(kubectl version --client=true | grep 'Client Version:' | awk '{print $3}')"
            else
                log "\nKubectl upgrade is required to continue. Exiting process."
                exit 1
            fi
        fi
    else
        log "\nInstalling kubectl..."
        local latest_kubectl
        latest_kubectl=$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)
        curl -LO "https://storage.googleapis.com/kubernetes-release/release/${latest_kubectl}/bin/linux/amd64/kubectl"
        sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
        rm kubectl
        log "\nKubectl installation complete."
    fi

    # DISPLAY FINAL VERSIONS
    local final_minikube_version final_kubectl_version
    final_minikube_version=$(get_current_version)
    final_kubectl_version=$(kubectl version --client=true | grep 'Client Version:' | awk '{print $3}')

    echo "-----------------------------------------------------------------------"
    echo "            INSTALLATION/UPGRADATION COMPLETED SUCCESSFULLY"
    echo "-----------------------------------------------------------------------"
    echo "Minikube Version: ${final_minikube_version}"
    echo "Kubectl Version: ${final_kubectl_version}"
    echo "-----------------------------------------------------------------------"
}


# Update Minikube
perform_update() {
    local current_ver latest_ver
    current_ver=$(get_current_version)
    latest_ver=$(get_latest_version)
    
    if [[ "$current_ver" == "$latest_ver" ]]; then
        log "Minikube is already at latest version ($latest_ver). No upgrade needed."
        exit 0
    fi

    log "\nInitiating Minikube update..."
    backup_resources
    
    log "\nDownloading latest binary..."
    curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
    sudo install minikube-linux-amd64 /usr/local/bin/minikube
    sudo chmod +x /usr/local/bin/minikube
    rm minikube-linux-amd64

    log "\nRestarting cluster..."
    if minikube start; then
        post_start_configuration
    else
        log "\nUpgrade failed. Performing clean installation..."
        minikube delete && minikube start && post_start_configuration
    fi
}

# Post-start configuration
post_start_configuration() {
    log "\nConfiguring Docker environment..."
    eval "$(minikube docker-env)"
    
    #log "\nVerifying namespaces..."
    #for ns in "${REQUIRED_NAMESPACES[@]}"; do
    #    if ! kubectl get namespace "$ns" >/dev/null 2>&1; then
    #        kubectl create namespace "$ns"
    #        log "Created namespace: $ns"
    #    else
    #        log "Namespace already exists: $ns"
    #    fi
    #done
    
    enable_addons
    display_cluster_info
}

display_cluster_info() {
    local current_ver latest_ver cluster_ip status
    current_ver=$(get_current_version)
    latest_ver=$(get_latest_version)
    cluster_ip=$(minikube ip)
    status=$(minikube status | grep -E '^(type|host|kubelet|apiserver|kubeconfig):' | awk -F': ' '{print $1 "=" $2}' | sed ':a;N;$!ba;s/\n/; /g' | sed 's/; $//')
    
    echo -e "\n\n------------------------------------------------------------------------------------------------------------------------"
    echo -e "                                              MINIKUBE CLUSTER INFORMATION"
    echo -e "------------------------------------------------------------------------------------------------------------------------"
    printf "%-18s : %s\n" "Minikube Version" "${current_ver}"
    printf "%-18s : %s\n" "Current Version" "${current_ver}"
    printf "%-18s : %s\n" "Latest Version" "${latest_ver}"
    printf "%-18s : %s\n" "Cluster IP" "${cluster_ip}"
    printf "%-18s : %s\n" "Status" "${status}"
    echo -e "------------------------------------------------------------------------------------------------------------------------\n\n"
}

# Enhanced Status Display
show_status() {
    if ! command -v minikube &>/dev/null; then
        log "Minikube is not installed."
        return 1
    fi

    local current_ver latest_ver status cluster_ip
    current_ver=$(get_current_version)
    latest_ver=$(get_latest_version)

    if ! minikube status --format='{{.Host}}' &>/dev/null; then
        log "Minikube is installed, but no cluster exists (deleted or never created)."
        echo -e "\n------------------------------------------------------------------------------------------------------------------------"
        echo -e "                                              MINIKUBE CLUSTER INFORMATION"
        echo -e "------------------------------------------------------------------------------------------------------------------------"
        printf "%-17s : %s\n" "Minikube Version" "${current_ver}"
        printf "%-17s : %s\n" "Latest Version" "${latest_ver}"
        printf "%-17s : %s\n" "Cluster IP" "Inactive"
        printf "%-17s : %s\n" "Status" "Minikube Cluster Deleted"
        echo -e "------------------------------------------------------------------------------------------------------------------------\n"
        return 1
    fi

    status=$(minikube status --format='{{.Host}}' 2>/dev/null)
    if [[ "$status" == "Running" ]]; then
        cluster_ip=$(minikube ip)
        mstatus=$(minikube status | grep -E '^(type|host|kubelet|apiserver|kubeconfig):' | awk -F': ' '{print $1 "=" $2}' | sed ':a;N;$!ba;s/\n/; /g')
        echo -e "\n------------------------------------------------------------------------------------------------------------------------"
        echo -e "                                              MINIKUBE CLUSTER INFORMATION"
        echo -e "------------------------------------------------------------------------------------------------------------------------"
        printf "%-17s : %s\n" "Minikube Version" "${current_ver}"
        printf "%-17s : %s\n" "Latest Version" "${latest_ver}"
        printf "%-17s : %s\n" "Cluster IP" "${cluster_ip}"
        printf "%-17s : %s\n" "Status" "${mstatus}"
        echo -e "------------------------------------------------------------------------------------------------------------------------\n"
    elif [[ "$status" == "Stopped" ]]; then
        mstatus=$(minikube status | grep -E '^(type|host|kubelet|apiserver|kubeconfig):' | awk -F': ' '{print $1 "=" $2}' | sed ':a;N;$!ba;s/\n/; /g')
        echo -e "\n------------------------------------------------------------------------------------------------------------------------"
        echo -e "                                              MINIKUBE CLUSTER INFORMATION"
        echo -e "------------------------------------------------------------------------------------------------------------------------"
        printf "%-17s : %s\n" "Minikube Version" "${current_ver}"
        printf "%-17s : %s\n" "Latest Version" "${latest_ver}"
        printf "%-17s : %s\n" "Cluster IP" "Inactive"
        printf "%-17s : %s\n" "Status" "${mstatus}"
        echo -e "------------------------------------------------------------------------------------------------------------------------\n"
    fi
}

# Addon management
enable_addons() {
    local addons=("ingress" "metrics-server" "dashboard")
    log "\nEnabling addons..."
    for addon in "${addons[@]}"; do
        minikube addons enable "${addon}"
        log "Enabled: ${addon}"
    done
}

# Start Minikube with version check
start_minikube() {
    if ! command -v minikube &>/dev/null; then
        log "Minikube is not installed. Please use 'Install Minikube' option first."
        return 1
    fi

    local status
    status=$(minikube status --format='{{.Host}}' 2>/dev/null)
    if [[ "$status" == "Running" ]]; then
        log "Minikube is already running. Exiting."
        exit 0
    fi

    local current_ver latest_ver
    current_ver=$(get_current_version)
    latest_ver=$(get_latest_version)
    
    if [[ "${current_ver}" != "${latest_ver}" ]]; then
        log "Update available: ${latest_ver}"
        read -rp "Update before starting? [y/N] " -n 1 reply
        echo
        [[ "${reply}" =~ ^[Yy]$ ]] && perform_update
    fi
    
    log "\nStarting cluster..."
    eval "${MINIKUBE_START_CMD}" && post_start_configuration || {
        log "ERROR: Cluster start failed"
        exit 1
    }
}

# Stop Minikube
stop_minikube() {
    if ! command -v minikube &>/dev/null; then
        log "Minikube is not installed. Please use 'Install Minikube' option first."
        return 1
    fi

    local status
    status=$(minikube status --format='{{.Host}}' 2>/dev/null)
    if [[ "$status" == "Stopped" ]]; then
        log "Minikube is already stopped. Exiting."
        exit 0
    elif [[ "$status" == "Running" ]]; then
        backup_resources
        log "\nStopping cluster..."
        minikube stop
    else
        log "Minikube is not running or not installed or deleted. Exiting."
        return 1
    fi
}

# Delete Minikube
delete_minikube() {
    if ! command -v minikube &>/dev/null; then
        log "Minikube is not installed. Exiting."
        return 1
    fi

    if ! minikube status --format='{{.Host}}' &>/dev/null; then
        log "Minikube is installed, but no cluster exists (deleted or never created). Exiting Minikube delete process.."
        return 1
    fi

    local status
    status=$(minikube status --format='{{.Host}}' 2>/dev/null)
    if [[ "$status" == "Running" ]]; then
        log "Performing backup before deletion..."
        backup_resources
    else
        log "Cluster is stopped. Deleting without backup..."
    fi

    log "\nDeleting cluster..."
    minikube delete
}

uninstall_minikube() {
    # Display warning message with colored output
    echo -e "\033[1;31mATTENTION!!\033[0m \033[33mMinikube and Kubectl will be uninstalled completely. If a backup of the existing environment has not been taken already, please exit this step and take a backup first.\033[0m"
    echo ""
    
    # Prompt the user to confirm whether to proceed with uninstallation
    read -rp "Do you want to proceed with the uninstallation? [y/N]: " -n 1 reply
    echo
    if [[ "$reply" =~ ^[Nn]$ ]]; then
        echo "Uninstallation cancelled. Please ensure you have taken a backup before proceeding."
        return 1
    fi

    log "\nStarting complete uninstallation of Minikube and Kubectl..."

    # Check and uninstall Minikube
    if ! command -v minikube &>/dev/null; then
        log "Minikube is already uninstalled."
    else
        log "Deleting Minikube cluster..."
        minikube delete --all --purge >/dev/null 2>&1

        log "Removing Minikube binaries and configuration..."
        sudo rm -f /usr/local/bin/minikube /usr/bin/minikube
        rm -rf "/home/${USER}/.minikube"
        sudo rm -rf /var/lib/minikube
        rm -rf "/home/${USER}/.cache/minikube"
        rm -rf "/tmp/minikube*"
        sudo rm -f /etc/systemd/system/minikube.service /var/log/minikube.log
        log "Minikube uninstalled successfully."
    fi

    # Check and uninstall Kubectl
    if ! command -v kubectl &>/dev/null; then
        log "Kubectl is already uninstalled."
    else
        log "Removing Kubectl binaries and configuration..."
        sudo rm -f /usr/local/bin/kubectl /usr/bin/kubectl
        sudo rm -f /usr/local/bin/kubectl
        sudo rm -f /usr/bin/kubectl
        rm -rf "/home/${USER}/.kube"
        sudo rm -rf /var/lib/kubelet
        sudo rm -f /var/log/kubelet.log
        log "Kubectl uninstalled successfully."
    fi

    log "Complete uninstallation finished. Removed:"
}

# Interactive menu
show_menu() {
    PS3=$'\nSelect operation: '
    options=("Install Minikube" "Minikube Status" "Start Minikube" "Stop Minikube" "Upgrade Minikube" "Delete Minikube" "Backup Resources" "Restore Resources" "Uninstall Minikube" "Quit")
    
    select opt in "${options[@]}"; do
        case "${opt}" in
            "Install Minikube")
                install_minikube
                break
                ;;
            "Minikube Status")
                show_status
                break
                ;;
            "Start Minikube")
                start_minikube
                break
                ;;
            "Stop Minikube")
                stop_minikube
                break
                ;;
            "Upgrade Minikube")
                perform_update
                break
                ;;
            "Delete Minikube")
                delete_minikube
                break
                ;;
            "Backup Resources")
                backup_resources
                break
                ;;
            "Restore Resources")
                # Placeholder: Implement restore_backup if needed.
                log "Restore Resources option selected (not implemented)."
                break
                ;;
            "Uninstall Minikube")
                uninstall_minikube
                break
                ;;
            "Quit")
                exit 0
                ;;
            *) 
                echo "Invalid option"
                ;;
        esac
    done
}

# Main execution flow
main() {
    verify_user
    initialize_directories
    log "Starting Minikube Manager"
    
    while true; do
        show_menu
        echo
        log "\nOperation completed. Ready for next command."
    done
}

main
