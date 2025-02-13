#!/bin/bash
# deploy_kafka.sh – Deploy Kafka (with Redpanda) into a Minikube cluster.
#
# This script verifies that it is run by user 'muser', creates required directories,
# ensures that necessary YAML files exist (fetching any missing ones from GitHub),
# checks that Minikube is running, verifies the 'streaming' namespace and its resources,
# and then deploys Kafka and Redpanda accordingly.
#
# After deploying Kafka, the script waits for the Kafka StatefulSet rollout to complete,
# creates the 'ecom_transactions' topic, and then deploys Redpanda by waiting for the
# Deployment rollout to complete. Finally, it displays current resources and returns control.

# --- Configuration ---
LOG_DIR="/opt/minikube/scripts/shell/logs"
LOG_FILE="${LOG_DIR}/deploy_kafka.log"
NAMESPACE_DIR="/opt/minikube/namespaces/streaming"
REQUIRED_FILES=("kafka.yaml" "redpanda.yaml")
GITHUB_REPO="https://github.com/TechSavvyRC/streaming.git"
NAMESPACE="streaming"
TOPIC_NAME="ecom_transactions"

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

fetch_missing_files() {
    missing=("$@")
    log_msg "INFO" "Missing files detected (${missing[*]}). Fetching from repository..."
    TEMP_DIR=$(mktemp -d)
    git clone "$GITHUB_REPO" "$TEMP_DIR/streaming" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        log_msg "ERROR" "Failed to clone repository."
        rm -rf "$TEMP_DIR"
        exit 1
    fi
    for file in "${missing[@]}"; do
        if [ -f "$TEMP_DIR/streaming/$file" ]; then
            cp "$TEMP_DIR/streaming/$file" .
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

# run_command: Executes a command, logs it, checks return code (if nonzero, exits).
run_command() {
    local cmd="$1"
    log_msg "Executing command: $cmd"
    # Capture output (stdout and stderr)
    local output
    if ! output=$(eval "$cmd" 2>&1); then
        local rc=$?
        log_msg "Command failed with code $rc: $cmd"
        log_msg "Output: $output"
        exit 1
    fi
    echo "$output" | sed 's/[[:space:]]*$//'
}

# wait_for_pods: Poll until all pods in the namespace are ready (READY exactly "1/1").
wait_for_pods() {
    local namespace="$1"
    local timeout=300
    local interval=10
	echo
    log_msg  "INFO" "Waiting for all streaming pods to be in Ready state (READY: 1/1)..."
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
                ready_num=$(echo "$ready" | cut -d'/' -f1)
                ready_den=$(echo "$ready" | cut -d'/' -f2)
                #if [[ "$ready" != "1/1" ]]; then
                if [[ "$ready_num" -ne "$ready_den" ]]; then
                    all_ready=false
                    log_msg "INFO" "Pod '$pod_name' is not ready: READY state is '$ready'. Full details: $line"
                fi
            done <<< "$pod_output"
            if $all_ready; then
                log_msg "DEBUG" "All pods are ready (READY: 1/1)."
                return 0
            fi
        fi
        sleep "$interval"
        (( elapsed += interval ))
    done
    log_msg "ERROR" "Timeout reached waiting for pods to be ready."
    exit 1
}

deploy_kafka_and_redpanda() {
    # 1. Ensure the namespace directory exists and change into it.
    mkdir -p "$NAMESPACE_DIR" || { log_msg "ERROR" "Failed to create directory '$NAMESPACE_DIR'."; exit 1; }
    cd "$NAMESPACE_DIR" || { log_msg "ERROR" "Failed to change directory to '$NAMESPACE_DIR'."; exit 1; }
    log_msg "DEBUG" "Namespace directory '$NAMESPACE_DIR' is ready."

    # 2. Check for required files; if missing, fetch them.
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

    # 3. Verify that Minikube is running.
    minikube_status=$(minikube status 2>&1)
    if [[ "$minikube_status" != *"Running"* ]]; then
        log_msg "INFO" "Minikube is not running. Please start Minikube and try again."
        exit 0
    else
        log_msg "DEBUG" "Minikube status: Running."
    fi

    # 4. Ensure the 'streaming' namespace exists.
    kubectl get namespace "$NAMESPACE" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        log_msg "INFO" "Namespace '$NAMESPACE' does not exist. Creating..."
        kubectl create namespace "$NAMESPACE" >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            log_msg "ERROR" "Failed to create namespace '$NAMESPACE'."
            exit 1
        fi
        log_msg "INFO" "Namespace '$NAMESPACE' created successfully."
    else
        log_msg "DEBUG" "Namespace '$NAMESPACE' exists."
    fi

    # 5. Check existing resources in the namespace.
    resources_output=$(kubectl get all -n "$NAMESPACE" 2>&1)
    mapfile -t lines <<< "$resources_output"
    if [ ${#lines[@]} -le 1 ]; then
        log_msg "DEBUG" "No resources found in namespace '$NAMESPACE'. Proceeding with deployment."
        extraneous=false
    else
        extraneous=false
        for (( i=1; i<${#lines[@]}; i++ )); do
            line="${lines[$i]}"
            if [[ "$line" != *kafka* && "$line" != *redpanda* ]]; then
                extraneous=true
                break
            fi
        done
    fi

    if [ "$extraneous" = false ] && [ ${#lines[@]} -gt 1 ]; then
        log_msg "INFO" "-------------------------------------------------------------------------------------------------"
        log_msg "INFO" "## Resources Running Under 'streaming' Namespace"
        log_msg "INFO" "-------------------------------------------------------------------------------------------------"
        echo "$resources_output"
        log_msg "INFO" "-------------------------------------------------------------------------------------------------"
        log_msg "INFO" "Expected resources already running. Exiting deployment script."
        exit 0
    fi

    # 6. If extraneous resources exist, prompt the user.
    if [ "$extraneous" = true ]; then
        log_msg "INFO" "Unexpected resources found in namespace '$NAMESPACE':"
        log_msg "INFO" "-------------------------------------------------------------------------------------------------"
        echo "$resources_output"
        log_msg "INFO" "-------------------------------------------------------------------------------------------------"
        log_msg "INFO" "Options:"
        log_msg "INFO" "1. Continue deployment without deleting the existing namespace."
        log_msg "INFO" "2. Delete the namespace and perform a fresh deployment."
        while true; do
            read -p "Enter your choice (1 or 2): " choice
            if [ "$choice" = "1" ] || [ "$choice" = "2" ]; then
                break
            else
                log_msg "INFO" "Invalid input. Please enter 1 or 2."
            fi
        done
    fi

    # 7. Handle namespace deletion if requested.
    if [ "$extraneous" = true ] && [ "$choice" = "2" ]; then
        log_msg "INFO" "Deleting namespace '$NAMESPACE'..."
        kubectl delete namespace "$NAMESPACE" >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            log_msg "ERROR" "Failed to delete namespace '$NAMESPACE'."
            exit 1
        fi
        for i in {1..30}; do
            sleep 2
            kubectl get namespace "$NAMESPACE" >/dev/null 2>&1
            if [ $? -ne 0 ]; then
                log_msg "DEBUG" "Namespace '$NAMESPACE' deleted."
                break
            fi
        done
        kubectl create namespace "$NAMESPACE" >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            log_msg "ERROR" "Failed to create namespace '$NAMESPACE' after deletion."
            exit 1
        fi
        log_msg "INFO" "Namespace '$NAMESPACE' re-created for fresh deployment."
    fi

    # 8. Deploy Kafka resource.
    log_msg "INFO" "Deploying Kafka resource..."
    kubectl apply -f kafka.yaml -n "$NAMESPACE"
    if [ $? -ne 0 ]; then
        log_msg "ERROR" "Failed to deploy Kafka resource."
        exit 1
    fi

    # 9. Wait until Kafka StatefulSet rollout is complete.
    #wait_for_rollout "statefulset" "kafka" "$NAMESPACE" "180s"
    wait_for_pods "streaming"
    if [ $? -ne 0 ]; then
        exit 1
    fi

    # 10. Create Kafka topic.
    log_msg "INFO" "Creating Kafka topic '$TOPIC_NAME'..."
    kubectl exec -n "$NAMESPACE" kafka-0 -- kafka-topics --create --topic "$TOPIC_NAME" --bootstrap-server kafka.streaming.svc.cluster.local:9092 --replication-factor 1 --partitions 1 >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        log_msg "ERROR" "Failed to create Kafka topic."
        exit 1
    fi
    log_msg "INFO" "Kafka topic '$TOPIC_NAME' created successfully."

    # 11. Deploy Redpanda resource.
    log_msg "INFO" "Deploying Redpanda resource..."
    kubectl apply -f redpanda.yaml -n "$NAMESPACE"
    if [ $? -ne 0 ]; then
        log_msg "ERROR" "Failed to deploy Redpanda resource."
        exit 1
    fi

    # 12. Wait until Redpanda Deployment rollout is complete.
    #wait_for_rollout "deployment" "redpanda-console" "$NAMESPACE" "180s"
    wait_for_pods "streaming"
    if [ $? -ne 0 ]; then
        exit 1
    fi

    # 13. Display the current resources in a formatted table.
    final_output=$(kubectl get all -n "$NAMESPACE" -o wide)
    log_msg "INFO" "-------------------------------------------------------------------------------------------------"
    log_msg "INFO" "## Resources Running Under 'streaming' Namespace"
    log_msg "INFO" "-------------------------------------------------------------------------------------------------"
    echo "$final_output"
    log_msg "INFO" "-------------------------------------------------------------------------------------------------"
    log_msg "INFO" "Deployment under the 'streaming' namespace was successful."

    exit 0
}

# This new function removes the 'streaming' namespace.
remove_streaming_namespace() {
    log_msg "INFO" "Initiating removal of 'streaming' namespace..."

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

# This is the interactive menu function.
interactive_menu() {
    current_user=$(whoami)
    if [ "$current_user" != "muser" ]; then
        log_msg "ERROR" "Error: Only user 'muser' is permitted to run this script. (Current user: $current_user)"
        exit 1
    fi

    while true; do
        echo ""
        echo "-----------------------------------------------------"
        echo "Kafka and Redpanda Deployment Menu"
        echo "-----------------------------------------------------"
        echo "1. Deploy Kafka and Redpanda in Minikube Cluster"
        echo "2. Remove Kafka and Redpanda from Minikube Cluster"
        echo "3. Exit to resource deployment menu"
        echo "-----------------------------------------------------"
        echo ""
        read -rp "Enter your choice [1-3]: " choice
        case $choice in
            1)
                log_msg "INFO" "User selected deployment option."
                deploy_kafka_and_redpanda
                ;;
            2)
                log_msg "INFO" "User selected removal option."
                remove_streaming_namespace
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
log_msg "INFO" "Starting Kafka and Redpanda deployment script."

# Instead of auto-running deployment logic immediately, call the interactive menu.
interactive_menu
