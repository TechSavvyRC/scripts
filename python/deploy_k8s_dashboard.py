import re
import os
import subprocess
import base64
import logging
import time
from datetime import datetime
from typing import Optional

# Script Configuration
CONFIG = {
    'LOG_FILE': "/opt/minikube/scripts/logs/deploy_k8s_dashboard.log",
    'NAMESPACE': "kubernetes-dashboard",
    'CERT_DIR': "/opt/minikube/namespaces/kubernetes-dashboard/certs",
    'NGINX_CONF': "/etc/nginx/conf.d/marvel.conf",
    'USER': "muser",
    'INGRESS_YAML': "/opt/minikube/namespaces/kubernetes-dashboard/kubernetes-dashboard-ingress.yaml"
}

class DashboardSetup:
    def __init__(self):
        """Initialize the dashboard setup with logging configuration."""
        # Configure logging
        logging.basicConfig(
            filename=CONFIG['LOG_FILE'],
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
        
    def display_status(self, message: str) -> None:
        """
        Display and log a status message with consistent formatting.
        
        Args:
            message: The status message to display and log
        """
        formatted_message = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(formatted_message)
        self.logger.info(message)

    def execute_command(self, command: str, wait: bool = True) -> str:
        """
        Execute a shell command with proper error handling and waiting period.
        
        Args:
            command: The shell command to execute
            wait: Whether to wait after command execution (default: True)
            
        Returns:
            The command output as a string
        
        Raises:
            SystemExit: If the command execution fails
        """
        try:
            self.display_status(f"Executing: {command}")
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if wait:
                self.display_status("Waiting 15 seconds for command completion...")
                time.sleep(15)
                
            return result.stdout.strip()
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Command failed: {e.stderr}")
            raise SystemExit(f"Error executing command: {e.stderr}")

    def check_user(self) -> None:
        """Verify the script is being executed by the correct user."""
        if os.getenv("USER") != CONFIG['USER']:
            raise SystemExit(f"Error: Script must be run as user '{CONFIG['USER']}'")
        self.display_status(f"Verified execution user: {CONFIG['USER']}")

    def ensure_namespace(self) -> None:
        """Create the Kubernetes namespace if it doesn't exist."""
        self.display_status(f"Checking namespace: {CONFIG['NAMESPACE']}")
        try:
            self.execute_command(f"kubectl get namespace {CONFIG['NAMESPACE']}")
            self.display_status(f"Namespace {CONFIG['NAMESPACE']} exists")
        except SystemExit:
            self.display_status(f"Creating namespace: {CONFIG['NAMESPACE']}")
            self.execute_command(f"kubectl create namespace {CONFIG['NAMESPACE']}")

    def deploy_dashboard(self) -> None:
        """Deploy the Kubernetes dashboard using Helm."""
        self.display_status("Deploying Kubernetes Dashboard")
        cmd = (
            f"helm upgrade --install kubernetes-dashboard "
            f"kubernetes-dashboard/kubernetes-dashboard "
            f"--create-namespace --namespace {CONFIG['NAMESPACE']}"
        )
        self.execute_command(cmd)

    def patch_service(self) -> None:
        """Patch the dashboard service to use NodePort."""
        self.display_status("Configuring dashboard service as NodePort")
        cmd = (
            f"kubectl -n {CONFIG['NAMESPACE']} patch svc "
            f"kubernetes-dashboard-kong-proxy -p '{{\"spec\": {{\"type\": \"NodePort\"}}}}'"
        )
        self.execute_command(cmd)

    def get_nodeport(self) -> str:
        """
        Extract the NodePort value from the service.
        
        Returns:
            The extracted NodePort value
        """
        self.display_status("Extracting NodePort value")
        cmd = (
            f"kubectl get svc -n {CONFIG['NAMESPACE']} "
            f"kubernetes-dashboard-kong-proxy -o wide"
        )
        output = self.execute_command(cmd)
        
        for line in output.splitlines():
            if '443:' in line:
                port = line.split(':')[1].split('/')[0]
                self.display_status(f"NodePort value: {port}")
                return port
                
        raise SystemExit("Failed to extract NodePort value")

    def configure_firewall(self, port: str) -> None:
        """
        Configure firewall rules for the specified port.
        
        Args:
            port: The port number to configure
        """
        self.display_status(f"Configuring firewall for port: {port}")
        self.execute_command(f"sudo firewall-cmd --add-port={port}/tcp --permanent")
        self.execute_command("sudo firewall-cmd --reload")

    def generate_certificates(self) -> None:
        """Generate SSL certificates if they don't exist."""
        self.display_status("Checking SSL certificates")
        
        key_path = os.path.join(CONFIG['CERT_DIR'], "kd-tls.key")
        crt_path = os.path.join(CONFIG['CERT_DIR'], "kd-tls.crt")
        
        if not (os.path.exists(key_path) and os.path.exists(crt_path)):
            self.display_status("Generating new SSL certificates")
            os.makedirs(CONFIG['CERT_DIR'], exist_ok=True)
            
            cmd = (
                f"openssl req -x509 -nodes -days 3000 -newkey rsa:2048 "
                f"-keyout {key_path} -out {crt_path} "
                f"-subj '/CN=kubernetes.marvel.com' "
                f"-addext 'subjectAltName=DNS:kubernetes.marvel.com'"
            )
            self.execute_command(cmd)
            
            # Generate base64 encoded versions
            for suffix in [key_path, crt_path]:
                with open(suffix, "rb") as input_file:
                    with open(f"{suffix}.base64", "wb") as output_file:
                        base64.encode(input_file, output_file)
        else:
            self.display_status("SSL certificates already exist")

    def apply_ingress(self) -> None:
        """Apply the Ingress configuration."""
        self.display_status("Applying Ingress configuration")
        self.execute_command(f"kubectl apply -f {CONFIG['INGRESS_YAML']}")

    def restart_nginx_ingress(self) -> None:
        """Restart the Nginx Ingress controller."""
        self.display_status("Restarting Nginx Ingress controller")
        cmd = (
            "kubectl rollout restart deployment "
            "ingress-nginx-controller -n ingress-nginx"
        )
        self.execute_command(cmd)

    def update_nginx_conf(self, port: str) -> None:
        """
        Update the Nginx configuration with the new port.
        
        Args:
            port: The new port number to configure
        """
        self.display_status("Updating Nginx configuration")
        backup_conf = f"{CONFIG['NGINX_CONF']}.backup"
        
        # Create backup
        self.execute_command(f"sudo cp {CONFIG['NGINX_CONF']} {backup_conf}")
        self.display_status(f"Created backup: {backup_conf}")
        
        # Update configuration
        with open(CONFIG['NGINX_CONF'], "r") as file:
            content = file.read()
            
        pattern = r"(?<=server_name kubernetes\.marvel\.com;).*?proxy_pass https://192\.168\.49\.2:\d+;"
        updated_content = re.sub(
            pattern,
            lambda m: re.sub(
                r"https://192\.168\.49\.2:\d+",
                f"https://192.168.49.2:{port}",
                m.group(0)
            ),
            content,
            flags=re.DOTALL
        )
        
        with open(CONFIG['NGINX_CONF'], "w") as file:
            file.write(updated_content)
            
        self.display_status("Restarting Nginx service")
        self.execute_command("sudo systemctl restart nginx")

    def generate_access_token(self) -> None:
        """Generate and display the dashboard access token."""
        self.display_status("Generating dashboard access token")
        cmd = (
            f"kubectl -n {CONFIG['NAMESPACE']} create token "
            f"dashboard-admin-sa --duration=2h"
        )
        token = self.execute_command(cmd)
        
        self.display_status("\nDashboard Access Information:")
        self.display_status("-----------------------------")
        self.display_status("Access Token:")
        print(token)
        self.display_status("\nAccess URL: https://kubernetes.marvel.com")

    def setup(self) -> None:
        """Execute the complete dashboard setup process."""
        try:
            self.display_status("Starting Kubernetes Dashboard Setup")
            self.check_user()
            self.ensure_namespace()
            self.deploy_dashboard()
            self.patch_service()
            port = self.get_nodeport()
            self.configure_firewall(port)
            self.generate_certificates()
            self.apply_ingress()
            self.restart_nginx_ingress()
            self.update_nginx_conf(port)
            self.generate_access_token()
            self.display_status("Kubernetes Dashboard Setup Complete")
            
        except Exception as e:
            self.logger.error(f"Setup failed: {str(e)}")
            raise SystemExit(f"Setup failed: {str(e)}")

if __name__ == "__main__":
    dashboard = DashboardSetup()
    dashboard.setup()
