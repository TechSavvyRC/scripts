#!/bin/bash

# Script to deploy Kubernetes resources for a streaming setup.
# This script must be run as the 'muser' user.

# Check if the script is run by the correct user
if [[ "$(whoami)" != "muser" ]]; then
  echo "Error: This script must be run as user 'muser'." >&2
  exit 1
fi

# Log file location
LOG_FILE="/opt/scripts/logs/deploy_kafka_streaming.log"

# Namespace to create
NAMESPACE="streaming"

# Wait time in seconds
WAIT_TIME=30

# Function to log messages to both console and log file
log() {
  local message="$1"
  timestamp=$(date +"%Y-%m-%d %H:%M:%S")
  echo "$timestamp: $message"
  echo "$timestamp: $message" >> "$LOG_FILE"
}

log "Starting streaming deployment..."

# Create the namespace
log "Creating namespace: $NAMESPACE"
if ! kubectl create namespace "$NAMESPACE" 2>/dev/null; then # Suppress "already exists" error
    if [[ $(kubectl get namespace "$NAMESPACE" -o jsonpath='{.status.phase}') == "Active" ]]; then
        log "Namespace '$NAMESPACE' already exists and is active. Continuing."
    else
        log "Error: Failed to create namespace '$NAMESPACE'."
        exit 1
    fi
else
  log "Namespace '$NAMESPACE' created successfully."
fi

log "Waiting for $WAIT_TIME seconds after namespace creation..."
sleep "$WAIT_TIME"
log "Resuming deployment."

# Array of kubectl commands
declare -a commands=(
  "kubectl apply -f /opt/minikube/namespaces/streaming/streaming-volume.yaml"
  "kubectl apply -f /opt/minikube/namespaces/streaming/zookeeper.yaml"
  "kubectl apply -f /opt/minikube/namespaces/streaming/kafka.yaml"
  "kubectl apply -f /opt/minikube/namespaces/streaming/redpanda.yaml"
  "kubectl apply -f /opt/minikube/namespaces/streaming/redpanda-ingress.yaml"
)

# Iterate through the commands and execute them
for command in "${commands[@]}"; do
  log "Executing command: $command"
  if ! eval "$command"; then
    log "Error: Command '$command' failed. Exiting."
    exit 1
  else
    log "Command '$command' executed successfully."
    log "Waiting for $WAIT_TIME seconds before proceeding..."
    sleep "$WAIT_TIME" # Wait for the specified time
    log "Resuming deployment."
  fi
done

log "Streaming deployment completed successfully."

exit 0

