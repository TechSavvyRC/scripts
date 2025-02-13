#!/usr/bin/env python3
"""
This script deploys the Kubernetes Dashboard via Helm on a Minikube cluster.
It logs messages both to a log file (with timestamps and log level) and to the
console (plain text without timestamps or log level). In addition to all previous steps,
the script now verifies that all pods are fully ready (indicated as READY: 1/1) before
patching the 'kubernetes-dashboard-kong-proxy' service. Detailed logs are recorded for
diagnostic purposes regarding pod readiness.

References:
  :contentReference[oaicite:0]{index=0} for deploying and accessing the Kubernetes Dashboard.
  :contentReference[oaicite:1]{index=1} for Helm deployments.
"""

import os
import sys
import subprocess
import logging
import time
import getpass
import re
import base64

# -------------------------------
# Helper functions
# -------------------------------
def run_command(cmd, capture_output=True, check=True, input_text=None):
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

def wait_for_pods(namespace, timeout=300, interval=150):
    """
    Poll until all pods in the given namespace are Running and have READY as '1/1'.
    Detailed readiness information is logged to help diagnose issues.
    """
    logger.info("Waiting for all Kubernetes Dashboard pods to be in Ready state (READY: 1/1)...")
    elapsed = 0
    while elapsed < timeout:
        output = run_command(f"kubectl get pods -n {namespace} --no-headers", capture_output=True, check=False)
        if output:
            all_ready = True
            lines = output.splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) < 2:
                    continue
                ready = parts[1]  # Expected format: "1/1"
                if ready != "1/1":
                    all_ready = False
                    # Log detailed readiness info for each pod not fully ready.
                    logger.error(f"Pod '{parts[0]}' is not ready: READY state is '{ready}'. Full details: {line}")
            if all_ready:
                logger.info("All pods are ready (READY: 1/1).")
                return
        time.sleep(interval)
        elapsed += interval
    logger.error("Timeout reached waiting for pods to be ready.")
    sys.exit(1)

def display_resource_status(namespace):
    """Display the pods and services status in the specified format."""
    logger.info("Displaying resource status:")
    pods = run_command(f"kubectl get pods -n {namespace} -o wide")
    services = run_command(f"kubectl get svc -n {namespace}")
    divider = "-" * 99
    print(divider)
    print("## Kubernetes Dashboard - Pods Status")
    print(divider)
    print("NAME".ljust(55) + "READY   " + "STATUS   " + "IP")
    for i, line in enumerate(pods.splitlines()):
        if i == 0:
            continue
        parts = line.split()
        name = parts[0].ljust(55)
        ready = parts[1].ljust(8)
        status = parts[2].ljust(8)
        ip = parts[5] if len(parts) > 5 else "N/A"
        print(f"{name}{ready}{status}{ip}")
    print(divider)
    print("## Kubernetes Dashboard - Services Status")
    print(divider)
    print("NAME".ljust(38) + "TYPE".ljust(11) + "CLUSTER-IP".ljust(17) + "EXTERNAL-IP".ljust(13) + "PORT(S)")
    for i, line in enumerate(services.splitlines()):
        if i == 0:
            continue
        parts = line.split()
        name = parts[0].ljust(38)
        svc_type = parts[1].ljust(11)
        cluster_ip = parts[2].ljust(17)
        external_ip = parts[3].ljust(13)
        ports = parts[4] if len(parts) > 4 else ""
        print(f"{name}{svc_type}{cluster_ip}{external_ip}{ports}")
    print(divider)

def check_and_create_sa_and_binding(namespace):
    """Verify if ServiceAccount 'dashboard-admin-sa' and its ClusterRoleBinding exist; create if missing."""
    sa_check = subprocess.run(f"kubectl get sa dashboard-admin-sa -n {namespace}", shell=True, capture_output=True, text=True)
    if sa_check.returncode != 0:
        logger.info("ServiceAccount 'dashboard-admin-sa' not found. Creating...")
        run_command(f"kubectl create serviceaccount dashboard-admin-sa -n {namespace}")
    else:
        logger.info("ServiceAccount 'dashboard-admin-sa' already exists.")
    crb_check = subprocess.run("kubectl get clusterrolebinding dashboard-admin-sa", shell=True, capture_output=True, text=True)
    if crb_check.returncode != 0:
        logger.info("ClusterRoleBinding 'dashboard-admin-sa' not found. Creating...")
        run_command("kubectl create clusterrolebinding dashboard-admin-sa --clusterrole=cluster-admin --serviceaccount=kubernetes-dashboard:dashboard-admin-sa")
    else:
        logger.info("ClusterRoleBinding 'dashboard-admin-sa' already exists.")

def patch_service(namespace):
    """Patch the 'kubernetes-dashboard-kong-proxy' service to type NodePort."""
    logger.info("Patching service 'kubernetes-dashboard-kong-proxy' to type NodePort...")
    # Escape curly braces by doubling them so that .format() does not treat them as placeholders.
    patch_cmd = ("kubectl -n {ns} patch svc kubernetes-dashboard-kong-proxy -p "
                "'{{\"spec\": {{\"type\": \"NodePort\", \"ports\": [{{\"port\": 443, \"nodePort\": 30243}}]}}}}'").format(ns=namespace)
    run_command(patch_cmd)

def extract_nodeport(namespace):
    """Extract NodePort from the 'kubernetes-dashboard-kong-proxy' service output."""
    logger.info("Extracting NodePort from service 'kubernetes-dashboard-kong-proxy'...")
    output = run_command(f"kubectl get svc -n {namespace} kubernetes-dashboard-kong-proxy", capture_output=True)
    match = re.search(r":(\d+)/TCP", output)
    if match:
        nodeport = match.group(1)
        logger.info(f"Extracted NodePort: {nodeport}")
        return nodeport
    else:
        logger.error("Failed to extract NodePort from service output.")
        sys.exit(1)

def open_firewall(nodeport):
    """Open firewall port for NodePort if applicable (Linux only)."""
    if os.name != 'posix':
        logger.warning("Firewall configuration skipped on non-posix platform.")
        return
    encoded_pw = "MTIzNA=="  # base64 encoding of "1234"
    password = base64.b64decode(encoded_pw).decode('utf-8')
    logger.info("Opening firewall port for NodePort (requires root access)...")
    cmd1 = f'echo "{password}" | sudo -S firewall-cmd --add-port={nodeport}/tcp --permanent'
    cmd2 = f'echo "{password}" | sudo -S firewall-cmd --reload'
    run_command(cmd1)
    run_command(cmd2)

def call_secret_script():
    """Call the external Python script for secret generation and wait for its completion."""
    secret_script = "/opt/minikube/scripts/python/kd-secrete-generate.py"
    if not os.path.isfile(secret_script):
        logger.error(f"Secret generation script not found: {secret_script}")
        sys.exit(1)
    logger.info(f"Calling secret generation script: {secret_script}")
    ret = subprocess.run([sys.executable, secret_script])
    if ret.returncode != 0:
        logger.error("Secret generation script failed.")
        sys.exit(1)

def verify_and_apply_yaml():
    """Verify YAML files exist and apply them via kubectl."""
    required_files = ["kubernetes-dashboard-ingress.yaml", "kubernetes-dashboard-secret.yaml"]
    missing = []
    for f in required_files:
        if not os.path.isfile(f):
            missing.append(f)
    if missing:
        logger.error(f"Missing YAML file(s): {', '.join(missing)}. Exiting.")
        sys.exit(1)
    for f in required_files:
        logger.info(f"Applying YAML file: {f}")
        run_command(f"kubectl apply -f {f}")

def restart_ingress():
    """Restart the Nginx Ingress Pods."""
    logger.info("Restarting Nginx Ingress Pods...")
    run_command("kubectl rollout restart deployment ingress-nginx-controller -n ingress-nginx")

#def post_deployment(nodeport, tasks):
def post_deployment(tasks):
    """Display post-deployment steps, including nginx configuration update instructions,
       the access token, and the Dashboard URL."""
    logger.info("Post-deployment steps completed successfully.")
    print("\nTasks performed:")
    for t in tasks:
        print(f" - {t}")
    token = run_command("kubectl -n kubernetes-dashboard create token dashboard-admin-sa --duration=48h")
    print("\nDashboard Access Token (valid for 48h):")
    print(token)
    print("\nAccess the Kubernetes Dashboard UI at:")
    print("   https://kubernetes.marvel.com")

def remove_namespace():
    """New function to remove the 'kubernetes-dashboard' namespace."""
    print("Initiating removal of Kubernetes Dashboard namespace...")
    ret = subprocess.run("kubectl get ns kubernetes-dashboard", shell=True, capture_output=True, text=True)
    if ret.returncode != 0:
        print("Namespace 'kubernetes-dashboard' does not exist.")
        return
    ret = subprocess.run("kubectl delete ns kubernetes-dashboard", shell=True, capture_output=True, text=True)
    if ret.returncode == 0:
        print("Kubernetes Dashboard namespace removed successfully.")
    else:
        print("Error: Failed to remove Kubernetes Dashboard namespace.")
        print(ret.stderr)

def deploy_dashboard():
    """Wrapper to invoke the existing deployment logic."""
    # Assuming your main() function contains all your deployment logic.
    main()

# -------------------------------
# Main execution flow
# -------------------------------
def main():
    tasks_performed = []
    
    # 1. Ensure script is executed only by user 'muser'
    current_user = getpass.getuser()
    if current_user != "muser":
        print("Error: This script must be executed only by 'muser'.")
        sys.exit(1)
    tasks_performed.append("User check passed (executed as 'muser')")

    # 2. Logging and directory setup will follow.
    try:
        os.makedirs("/opt/minikube/scripts/logs", exist_ok=True)
    except Exception as e:
        print(f"Error creating logs directory: {e}")
        sys.exit(1)

    global logger
    logger = logging.getLogger("deployDashboard")
    logger.setLevel(logging.INFO)

    # Console handler: message only, no timestamp or log level
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    # File handler: include timestamps and log level
    script_name = os.path.basename(__file__)
    log_file = os.path.join("/opt/minikube/scripts/logs", os.path.splitext(script_name)[0] + ".log")
    file_handler = logging.FileHandler(log_file)
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(file_formatter)

    # Remove any default handlers and add our own
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.info("Logger initialized.")
    tasks_performed.append("Logging configured")

    # 3. Change directory to /opt/minikube/namespaces/kubernetes-dashboard/
    target_dir = "/opt/minikube/namespaces/kubernetes-dashboard/"
    try:
        os.chdir(target_dir)
        logger.info(f"Changed directory to {target_dir}")
    except Exception as e:
        logger.error(f"Failed to change directory to {target_dir}: {e}")
        sys.exit(1)
    tasks_performed.append(f"Changed directory to {target_dir}")

    # 4. Check Minikube status
    status_output = run_command("minikube status", capture_output=True)
    if "Running" not in status_output:
        print("Minikube is not running. Please start Minikube before executing the script.")
        sys.exit(1)
    logger.info("Minikube is running.")
    tasks_performed.append("Minikube status verified")

    # 5. Check if 'kubernetes-dashboard' namespace exists
    ns_check = subprocess.run("kubectl get ns kubernetes-dashboard", shell=True, capture_output=True, text=True)
    ns_exists = (ns_check.returncode == 0)
    logger.info(f"Namespace 'kubernetes-dashboard' exists: {ns_exists}")

    # 6. If namespace exists, check for resources and prompt user
    delete_ns = False
    if ns_exists:
        resources = run_command("kubectl get all -n kubernetes-dashboard", capture_output=True)
        if len(resources.splitlines()) > 1:
            print("Resources are running under the 'kubernetes-dashboard' namespace.")
            choice = input("Enter 'delete' to delete the namespace, or 'continue' to proceed without deleting: ").strip().lower()
            if choice == "delete":
                delete_ns = True
                logger.info("User opted to delete the namespace.")
                run_command("kubectl delete ns kubernetes-dashboard")
                logger.info("Waiting for namespace deletion...")
                while True:
                    ns_check = subprocess.run("kubectl get ns kubernetes-dashboard", shell=True, capture_output=True, text=True)
                    if ns_check.returncode != 0:
                        break
                    time.sleep(5)
                tasks_performed.append("Existing 'kubernetes-dashboard' namespace deleted")
            else:
                logger.info("User opted to continue without deleting namespace.")
                tasks_performed.append("Existing resources detected; continuing without deletion")
        else:
            logger.info("No resources found in the existing namespace.")
    else:
        logger.info("Namespace 'kubernetes-dashboard' does not exist.")

    # 7. Deploy Dashboard using Helm
    if ns_exists and not delete_ns:
        helm_cmd = ("helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard "
                    "--namespace kubernetes-dashboard")
    else:
        helm_cmd = ("helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard "
                    "--create-namespace --namespace kubernetes-dashboard")
    run_command(helm_cmd)
    tasks_performed.append("Kubernetes Dashboard deployed via Helm")
    
    # 8. Wait until all pods are fully ready (READY: 1/1)
    wait_for_pods("kubernetes-dashboard")
    tasks_performed.append("Dashboard resources reached full Ready state")

    # 9. Display pods and services status
    display_resource_status("kubernetes-dashboard")
    tasks_performed.append("Resource status displayed")

    # 10. Verify ServiceAccount and ClusterRoleBinding
    check_and_create_sa_and_binding("kubernetes-dashboard")
    tasks_performed.append("ServiceAccount and ClusterRoleBinding verified/created")

    # 11. Patch service to NodePort (only after ensuring pods are ready)
    patch_service("kubernetes-dashboard")
    tasks_performed.append("Service 'kubernetes-dashboard-kong-proxy' patched to NodePort")

    # 12. Call the external secret generation script
    call_secret_script()
    tasks_performed.append("Secret generation script executed")

    # 13. Verify YAML files exist and apply them
    verify_and_apply_yaml()
    tasks_performed.append("YAML files verified and applied")

    # 14. Restart Nginx Ingress Pods
    restart_ingress()
    tasks_performed.append("Nginx Ingress Pods restarted")

    # 15. Post-deployment summary: instruct update of nginx config, show token and URL
    post_deployment(tasks_performed)

    pass

def interactive_menu():
    """Display an interactive menu to choose deployment, removal, or exit."""
    while True:
        print("\n--------------------------------------------------------")
        print("Kubernetes Dashboard Menu")
        print("--------------------------------------------------------")
        print("1. Deploy Kubernetes Dashboard in Minikube Cluster")
        print("2. Remove Kubernetes Dashboard from Minikube Cluster")
        print("3. Exit to resource deployment menu")
        print("--------------------------------------------------------")
        choice = input("Enter your choice [1-3]: ").strip()
        if choice == "1":
            logging.info("User selected deployment option.")
            deploy_dashboard()
        elif choice == "2":
            logging.info("User selected removal option.")
            remove_namespace()
        elif choice == "3":
            logging.info("User selected to exit the menu.")
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid input. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    interactive_menu()
