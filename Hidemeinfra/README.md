# Hide Me Application - Terraform Infrastructure 
[![Build Status](https://img.shields.io/badge/Status-development-yellow)]()
[![Terraform Version](https://img.shields.io/badge/1.0.0%2B-blue)]()
[![hashicorp/google Version](https://img.shields.io/badge/4.0%2B-blue)]()

## Project Overview

This repository contains the Terraform configuration for deploying the "Hide Me" application infrastructure on Google Cloud Platform (GCP). The infrastructure is designed to be scalable, secure, and maintainable, leveraging various GCP services orchestrated through modular Terraform code.

The primary goal is to provide a robust backend environment consisting of compute instances running the application code (main backend and a Go backend), a managed PostgreSQL database, a secure network environment using a Virtual Private Cloud (VPC), and a global HTTP(S) load balancer to distribute traffic and provide SSL termination.

This README provides a comprehensive guide to understanding the infrastructure components, the logic behind their implementation, the structure of the Terraform code, best practices followed, and instructions for usage.



## Infrastructure Breakdown 

This Terraform configuration, organized into modules, provisions the following core components within your Google Cloud Platform project for the Hide Me application:

### Root Module (`/`)

*   **Purpose:** Orchestrates the deployment of all other modules and defines providers.
*   **Key Resources:**
    *   `terraform`: Defines required provider versions (Google ~> 4.0) and includes commented-out configuration for a GCS remote backend.
    *   `provider "google"`, `provider "google-beta"`: Configures the Google Cloud providers with project, region, zone, and credentials.
    *   `module "vpc"`, `module "security"`, `module "database"`, `module "compute"`, `module "load_balancer"`, `module "dns"`: Calls each specific module, passing necessary variables and establishing dependencies.
    *   `module "monitoring"`: (Commented out in `main.tf`) Intended to call the monitoring module.

### VPC Module (`./modules/vpc`)

*   **Purpose:** Creates the network foundation.
*   **Key Resources:**
    *   `google_compute_network "vpc"`: Creates the custom VPC network (`hide-me-vpc-<env>`) with regional routing and auto-subnetwork creation disabled.
    *   `google_compute_subnetwork "public_subnet"`, `google_compute_subnetwork "private_subnet"`: Defines public (for LBs) and private (for instances, DB) subnets with specific CIDR ranges and Private Google Access enabled.
    *   `google_compute_router "router"`, `google_compute_router_nat "nat"`: Sets up a Cloud Router and Cloud NAT to allow instances in the private subnet egress internet access.
    *   `google_compute_global_address "private_service_connect"`, `google_service_networking_connection "private_service_connection"`: Configures Private Service Connect for accessing Google APIs privately.
    *   `google_dns_managed_zone "private_zone"`: Creates a private DNS zone (`internal.hide-me.<env>.`) for internal service discovery within the VPC.
    *   `google_dns_policy "default"`: Defines a DNS policy for the VPC, forcing outbound DNS through Google's public DNS servers.

### Security Module (`./modules/security`)

*   **Purpose:** Manages service accounts, IAM permissions, and firewall rules.
*   **Key Resources:**
    *   `google_service_account "app_service_account"`, `google_service_account "db_service_account"`: Creates dedicated service accounts for application instances and the database.
    *   `google_project_iam_member`: Assigns necessary IAM roles (e.g., logging, monitoring, secret access, Cloud SQL client/editor) to the service accounts.
    *   `google_compute_firewall`: Defines several firewall rules:
        *   `allow_health_checks`: Allows ingress TCP traffic on the health check port from Google's official health check IP ranges.
        *   `allow_internal`: Allows all TCP/UDP/ICMP traffic originating from within the private subnet.
        *   `allow_ssh`: Allows ingress TCP traffic on port 22 only from Google's IAP (Identity-Aware Proxy) IP ranges.
        *   `allow_backend`: Allows ingress TCP traffic on backend ports (8000, 8080) only from Google's official Load Balancer IP ranges.
        *   `allow_specific_egress`: Allows egress TCP traffic on port 443 to Google API IP ranges.
        *   `deny_all_egress`: Denies all other egress traffic (priority 65534).
    *   `google_secret_manager_secret "db_credentials"`, `google_secret_manager_secret_version "db_credentials_version"`: Creates a secret in Secret Manager to store database credentials (username, password, dbname).
    *   `google_compute_security_policy "security_policy"`: (Commented out in `security/main.tf` and `root/main.tf`) Defines a Cloud Armor policy with rules for default deny, allow specific IPs, rate limiting, XSS, SQLi, RCE, and LFI protection.

### Database Module (`./modules/database`)

*   **Purpose:** Provisions the Cloud SQL database instance.
*   **Key Resources:**
    *   `google_compute_global_address "private_ip_address"`, `google_service_networking_connection "private_vpc_connection"`: Sets up the private IP address range for the SQL instance connection within the VPC.
    *   `google_sql_database_instance "postgres"`: Creates the primary PostgreSQL instance (`db-f1-micro` tier by default) with specified version, region, disk settings (SSD, autoresize), backup configuration, maintenance window, private network configuration (no public IP), database flags, and labels. Uses `random_id` for unique naming.
    *   `google_sql_database "database"`: Creates the specific database (`hide-me-db-ea7a2c79` by default) within the instance.
    *   `google_sql_user "user"`: Creates the database user (`hidemedba` by default) with the specified password.
    *   `google_sql_database_instance "read_replica"`: (Commented out) Defines a read replica instance, intended for the `prod` environment.

### Compute Module (`./modules/compute`)

*   **Purpose:** Manages the application compute instances.
*   **Key Resources:**
    *   `google_compute_instance_template "app_template"`: Defines the template for compute instances, specifying machine type, disk image (Ubuntu 20.04 LTS), service account, network interface (in private subnet with ephemeral public IP for setup), startup script (`scripts/startup.sh`), tags, scheduling (preemptible for non-prod), and shielded VM settings.
    *   `google_compute_health_check "app_health_check"`: Defines an HTTP health check targeting the application's `/status` endpoint on port 8000.
    *   `google_compute_region_instance_group_manager "app_instance_group"`: Creates a managed instance group (MIG) based on the template, distributing instances across zones in the region, configuring auto-healing based on the health check, setting an update policy, and defining named ports (`http`, `gohttp`).
    *   `google_compute_region_autoscaler "app_autoscaler"`: Configures autoscaling for the MIG based on CPU utilization (target 70%) and load balancing utilization (target 80%), with cooldown and scale-in controls.
    *   `google_secret_manager_secret`, `google_secret_manager_secret_version`: Creates secrets and versions for storing the GitHub SSH key, Gemini API key, and GitHub token securely.

### Load Balancer Module (`./modules/load_balancer`)

*   **Purpose:** Configures the external HTTP(S) load balancer.
*   **Key Resources:**
    *   `google_compute_global_address "lb_static_ip"`: Reserves a global static IP address for the load balancer frontend.
    *   `google_compute_managed_ssl_certificate "api_certificate"`, `google_compute_managed_ssl_certificate "go_api_certificate"`: Creates Google-managed SSL certificates for `api.<domain>` and `goapi.<domain>`.
    *   `google_compute_health_check "lb_health_check"`: Defines a separate health check used by the backend service (same config as compute health check).
    *   `google_compute_backend_service "lb_backend_service"`, `google_compute_backend_service "go_backend_service"`: Defines backend services for the main app and the Go app, linking them to the instance group via named ports, setting timeouts, attaching the health check, and optionally attaching the Cloud Armor policy (commented out in root `main.tf`).
    *   `google_compute_url_map "lb_url_map"`: Defines URL mapping rules, routing traffic based on host (`api.<domain>`, `goapi.<domain>`) to the appropriate backend service.
    *   `google_compute_target_http_proxy "lb_http_proxy"`, `google_compute_target_https_proxy "lb_https_proxy"`: Creates target proxies for HTTP and HTTPS traffic, linking the URL map and the SSL certificates (for HTTPS).
    *   `google_compute_global_forwarding_rule "lb_http_forwarding_rule"`, `google_compute_global_forwarding_rule "lb_https_forwarding_rule"`: Creates forwarding rules to direct external traffic on ports 80 and 443 from the static IP to the respective target proxies.

### DNS Module (`./modules/dns`)

*   **Purpose:** Manages public DNS records for the application domain.
*   **Key Resources:**
    *   `google_dns_managed_zone "main_zone"`: Creates the public DNS zone for the root domain (`hidemeai.com` by default) with DNSSEC enabled.
    *   `google_dns_record_set`: Defines DNS records within the zone:
        *   `apex_a_record`: 'A' record for the root domain (`@`) pointing to the load balancer IP.
        *   `api_a_record`: 'A' record for `api.<domain>` pointing to the load balancer IP.
        *   `go_api_a_record`: 'A' record for `goapi.<domain>` pointing to the load balancer IP.
        *   `mx_records`: Standard Google Workspace MX records for email.
        *   `domain_verification`: TXT record for SPF email verification.

### Monitoring Module (`./modules/monitoring`)

*   **Purpose:** Sets up monitoring dashboards and alert policies (Note: Module call is commented out in root `main.tf`).
*   **Key Resources:**
    *   `google_monitoring_notification_channel "email_channel"`: Creates an email notification channel if `var.alert_email` is provided.
    *   `google_monitoring_alert_policy`: Defines alert policies for high CPU, memory, and disk utilization on compute instances; high CPU, memory, and disk utilization on the database instance; high latency and error rates on the load balancer.
    *   `google_monitoring_dashboard "app_dashboard"`: Defines a custom dashboard with widgets visualizing key metrics (CPU, memory, disk, network for instances; CPU, memory for DB).



## Infrastructure Logic and Implementation 

This section details the reasoning behind the design choices and how the different components are implemented and interact within the Terraform configuration.

### Networking (VPC Module)

*   **Custom VPC:** A custom Virtual Private Cloud (`hide-me-vpc-<env>`) is created instead of using the default VPC. This provides better control over the network topology, IP addressing, and security policies. Auto-creation of subnets is disabled for explicit control.
*   **Subnetting:** The VPC is divided into a public subnet (`hide-me-vpc-public-<env>`) and a private subnet (`hide-me-vpc-private-<env>`).
    *   The public subnet is intended for resources that need direct internet access or exposure, such as load balancer frontends (though the LB itself is global, its health checks might originate here) or potential bastion hosts (not currently implemented).
    *   The private subnet houses the core application components: Compute Engine instances (via the MIG) and the Cloud SQL database instance. Instances in the private subnet do not have direct public IP addresses, enhancing security.
*   **Egress Control (NAT):** A Cloud Router and Cloud NAT (`hide-me-vpc-nat-<env>`) are configured for the private subnet. This allows instances within the private subnet to initiate outbound connections to the internet (e.g., for pulling code from GitHub, accessing external APIs like Gemini, installing packages) without having public IP addresses themselves.
*   **Private Google Access:** Enabled on both subnets, allowing instances to reach Google APIs and services (like Secret Manager, Cloud SQL APIs) without traversing the public internet.
*   **Private Service Connect:** A global address and service networking connection are established (`servicenetworking.googleapis.com`) to allow the Cloud SQL instance to connect privately within the VPC.
*   **Internal DNS:** A private DNS zone (`internal.hide-me.<env>.`) is created for potential future internal service discovery, although no records are currently defined within it in the module.
*   **DNS Policy:** A DNS policy forces instances within the VPC to use Google's public DNS servers (8.8.8.8, 8.8.4.4) for external lookups, ensuring consistent resolution.

### Security (Security Module)

*   **Service Accounts:** Dedicated service accounts (`hide-me-app-<env>`, `hide-me-db-<env>`) are created for the application instances and the database, following the principle of least privilege. Specific IAM roles are granted to these accounts (e.g., `roles/cloudsql.client` for the app, `roles/cloudsql.editor` for the DB SA, plus logging/monitoring/secret access roles).
*   **Firewall Rules:** A strict set of firewall rules controls traffic flow:
    *   Ingress is tightly controlled: Health checks are allowed only from Google's official ranges, SSH is allowed only via Google's IAP ranges, and backend traffic (ports 8000, 8080) is allowed only from Google's Load Balancer ranges. No other public ingress is permitted by default.
    *   Internal traffic within the private subnet is allowed.
    *   Egress is restricted: Only HTTPS traffic (TCP/443) to Google API ranges is explicitly allowed. All other egress traffic is denied by a low-priority rule (`hide-me-deny-all-egress-<env>`).
*   **Secret Management:** Database credentials (`db_credentials`) are stored securely in Google Secret Manager. The application service account is granted permission to access this secret.
*   **Cloud Armor:** A `google_compute_security_policy` resource (`hide-me-security-policy-<env>`) is defined within the security module, including rules for rate limiting and protection against common web attacks (XSS, SQLi, RCE, LFI). However, the attachment of this policy to the load balancer's backend services is **commented out** in both the `load_balancer/main.tf` and the root `main.tf`. The user mentioned this is temporary due to potential quota limitations. When enabled, this policy would provide an additional layer of security at the edge.

### Database (Database Module)

*   **Managed PostgreSQL:** A Cloud SQL for PostgreSQL instance is used, providing a managed database service that handles patching, backups, and replication.
*   **Private IP:** The instance is configured with a private IP address only, accessible solely from within the VPC via the established private service connection. It does not have a public IP address.
*   **High Availability (HA):** The `availability_type` is set to `REGIONAL` for both prod and non-prod environments in the current code, providing resilience across multiple zones within the region. (The comment `//todo: change to Zonal if needed` suggests this might be reviewed).
*   **Configuration:** Includes settings for disk type (SSD), size (with autoresize), automated backups (with Point-in-Time Recovery), a defined maintenance window, and specific database flags for enhanced logging.
*   **Security:** Deletion protection can be enabled via `var.db_deletion_protection`. Access requires the configured user (`hidemedba`) and password (stored in Secret Manager).
*   **Read Replica:** The configuration for a read replica (`google_sql_database_instance "read_replica"`) is present but **commented out**. The user indicated this is to minimize costs currently but is available for future use, likely in the production environment (`count = var.environment == "prod" ? 1 : 0`).

### Compute (Compute Module)

*   **Managed Instance Group (MIG):** A regional MIG (`hide-me-app-instance-group-manager`) is used to manage the application instances. This provides scalability, high availability (distributing instances across zones), and auto-healing.
*   **Instance Template:** A versioned instance template (`hide-me-app-template-1-0-0-*`) defines the configuration for each instance, including machine type, OS image (Ubuntu 20.04 LTS), disk settings, service account, network settings (private subnet), and metadata.
*   **Startup Script:** The instance template utilizes a startup script (`scripts/startup.sh`) sourced via `templatefile`. This script is responsible for:
    *   Installing dependencies (git, python, pip, go).
    *   Configuring SSH access for GitHub.
    *   Cloning the backend application repositories (main and Go) from GitHub using the specified branch.
    *   Installing Python dependencies (`requirements.txt`).
    *   Building the Go application.
    *   Setting environment variables (including secrets fetched via metadata passed from Terraform, like DB credentials and API keys - **Note:** Using Secret Manager access within the script would be more secure than passing secrets via metadata).
    *   Launching the main Python backend and the Go backend applications (using `nohup`).
*   **Autoscaling:** A regional autoscaler (`hide-me-app-autoscaler`) is attached to the MIG, configured to scale based on CPU utilization (target 70%) and load balancing utilization (target 80%) within the defined min/max instance limits.
*   **Health Checking:** An HTTP health check (`hide-me-app-health-check`) verifies instance health by querying the `/status` endpoint on port 8000. The MIG uses this for auto-healing.
*   **Security:** Instances use Shielded VM features (Secure Boot, vTPM, Integrity Monitoring). Secrets like GitHub SSH key, Gemini API key, and GitHub token are stored in Secret Manager and referenced by the compute module (though the startup script appears to expect them via metadata).

### Load Balancing (Load Balancer Module)

*   **Global HTTP(S) Load Balancer:** A global external load balancer distributes traffic to the backend instances.
*   **Static IP:** A global static IP address (`hide-me-lb-static-ip`) is reserved and assigned to the load balancer's forwarding rules.
*   **SSL Termination:** Google-managed SSL certificates are created for `api.<domain>` and `goapi.<domain>`. The HTTPS target proxy uses these certificates to terminate SSL/TLS connections.
*   **Backend Services:** Separate backend services (`hide-me-backend-service-<env>`, `hide-me-go-backend-service-<env>`) are defined for the main application and the Go application. They link to the MIG via named ports (`http`, `gohttp`), utilize a health check, and have connection draining configured.
*   **Host/Path Routing:** A URL map (`hide-me-url-map-<env>`) uses host rules to direct traffic for `api.<domain>` to the main backend service and traffic for `goapi.<domain>` to the Go backend service.
*   **Forwarding Rules:** Global forwarding rules direct traffic from the static IP on port 80 (HTTP) and port 443 (HTTPS) to the respective target proxies (HTTP and HTTPS).
*   **Security Policy Attachment:** The backend services have configuration to attach the Cloud Armor security policy (`var.security_policy_name`), but this is **commented out** in the root module's call to the load balancer module.

### DNS (DNS Module)

*   **Cloud DNS:** A public Cloud DNS managed zone (`hide-me-zone-<env>`) is created for the specified domain (`hidemeai.com`).
*   **DNS Records:**
    *   'A' records are created for the root domain (`@`), `api.<domain>`, and `goapi.<domain>`, all pointing to the load balancer's static IP address.
    *   Standard Google Workspace MX records are created for email handling.
    *   An SPF TXT record is created for email verification.
*   **Nameservers:** The module outputs the Google Cloud DNS nameservers, which need to be configured at the domain registrar (e.g., Namecheap) to delegate DNS control to Cloud DNS.

### Monitoring (Monitoring Module)

*   **Purpose:** Intended to provide observability into the infrastructure (Note: This module's invocation is **commented out** in the root `main.tf`, likely for cost reasons as mentioned by the user).
*   **Resources Defined (when enabled):**
    *   Email Notification Channel: Sends alerts to a specified email address.
    *   Alert Policies: Trigger alerts based on thresholds for CPU, memory, disk utilization (instances and DB), and load balancer latency/error rates.
    *   Custom Dashboard: Provides a visual overview of key metrics for instances and the database.



## Package Structure and Best Practices 

### Package Structure

The Terraform configuration is organized using a modular approach to promote reusability, maintainability, and clarity. The structure is as follows:

```
.
├── main.tf                 # Root module: Orchestrates all other modules
├── variables.tf            # Root module: Input variables for the entire infrastructure
├── outputs.tf              # Root module: Outputs from the entire infrastructure
├── terraform.tfvars        # Example variable definitions (sensitive values should be managed securely)
├── modules/
│   ├── vpc/                # VPC network module
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── security/           # Security resources module (Firewalls, SA, IAM, Secrets)
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── database/           # Cloud SQL database module
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── compute/            # Compute Engine (MIG, Template, Autoscaler) module
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── scripts/
│   │       └── startup.sh  # Startup script for instances
│   ├── load_balancer/      # HTTP(S) Load Balancer module
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── dns/                # Cloud DNS module
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── monitoring/         # Monitoring and Alerting module (currently unused)
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
├── *.json                  # Service account key files (e.g., credentials_file)
└── README.md               # This file
```

*   **Root Module:** The files in the root directory (`main.tf`, `variables.tf`, `outputs.tf`) define the providers, backend configuration (commented out), and orchestrate the calls to the various sub-modules.
*   **Modules (`modules/`):** Each subdirectory within `modules/` represents a logical grouping of related resources (e.g., `vpc`, `compute`, `database`). This encapsulation makes the infrastructure easier to understand and manage. Each module has its own `main.tf`, `variables.tf`, and `outputs.tf`.
*   **Scripts (`modules/compute/scripts/`):** Contains helper scripts, such as the `startup.sh` script used by compute instances.

### Best Practices Followed

Several best practices are evident in this Terraform configuration:

1.  **Modularity:** The use of modules (`vpc`, `security`, `compute`, etc.) breaks down the infrastructure into manageable, reusable components.
2.  **Variable-Driven Configuration:** Key settings (project ID, region, machine types, names, etc.) are defined as variables (`variables.tf`, `terraform.tfvars`), making the configuration flexible and adaptable to different environments.
3.  **Explicit Dependencies:** `depends_on` attributes are used where necessary (e.g., database depends on VPC and security) to ensure resources are created in the correct order, although Terraform often infers dependencies correctly through resource references.
4.  **Least Privilege:** Dedicated service accounts are created for the application and database, with specific IAM roles assigned, rather than using default service accounts with broader permissions.
5.  **Security Focus:**
    *   Use of a custom VPC with private subnets for core components.
    *   Strict firewall rules controlling ingress and egress traffic.
    *   Use of Secret Manager for sensitive data like database passwords, API keys, and SSH keys.
    *   Definition of a Cloud Armor policy (though currently commented out).
    *   Use of Shielded VM features for compute instances.
    *   Private IP configuration for the Cloud SQL instance.
6.  **Naming Conventions:** Resources generally follow a consistent naming convention, often including the resource type, application name (`hide-me`), and environment (`<env>`).
7.  **Resource Labeling:** Resources like the Cloud SQL instance and DNS zone include labels (`environment`, `application`, `managed-by`) for better organization and cost tracking.
8.  **High Availability:** Use of a regional MIG, regional Cloud SQL setting (currently), and distribution across multiple zones aims for high availability.
9.  **Scalability:** The use of a MIG with an autoscaler allows the application tier to scale automatically based on load.
10. **Infrastructure as Code (IaC):** Defining the entire infrastructure in code allows for version control, repeatability, and automated provisioning.
11. **Startup Script Templating:** The `templatefile` function is used to inject Terraform variables into the `startup.sh` script, making it dynamic.

### Areas for Potential Improvement/Consideration

*   **Secret Handling in Startup Script:** The startup script currently receives secrets (DB password, API keys, tokens) via instance metadata passed from Terraform variables. A more secure approach would be for the script to fetch these secrets directly from Secret Manager using the instance's service account permissions.
*   **State Management:** The remote backend configuration for Terraform state (using GCS) is currently commented out. While this is acceptable for a single developer working on the project, using a remote backend is essential for team collaboration and production environments to ensure state consistency and reliability.*   **Cloud Armor/Monitoring:** The Cloud Armor policy attachment and the entire monitoring module are currently commented out, likely for cost/quota reasons. Enabling these would significantly enhance security and observability.



## Example Usage 

This section provides guidance on how to deploy the Hide Me infrastructure using this Terraform configuration.

### Prerequisites

1.  **Terraform:** Ensure you have Terraform installed (version >= 1.0.0 is recommended, as specified in `main.tf`).
2.  **GCP Account:** You need a Google Cloud Platform account with billing enabled.
3.  **GCP Project:** Create a GCP project where the infrastructure will be deployed.
4.  **Service Account Key:** Create a GCP service account with sufficient permissions (e.g., Editor role for simplicity during initial setup, but refine to least privilege for production) and download its JSON key file.
5.  **Domain Name:** You need a registered domain name (e.g., `hidemeai.com`) that you can manage DNS for (e.g., via Namecheap, Google Domains, etc.).
6.  **GitHub Access:** Ensure you have appropriate access (either via SSH key or Personal Access Token) to the GitHub repositories specified in the variables (`github_repo`, `go_github_repo`).

### Configuration

1.  **Clone the Repository:** Clone the repository containing this Terraform code to your local machine.
2.  **Credentials File:** Place the downloaded GCP service account JSON key file within the root directory of the Terraform project (or update the path in `terraform.tfvars`). Ensure the filename matches the value provided for `credentials_file`.
3.  **Create `terraform.tfvars`:** Create a file named `terraform.tfvars` in the root directory. This file will contain the specific values for your deployment. You can use the provided example `terraform.tfvars` (which was uploaded alongside the initial request) as a template. **Crucially, manage sensitive values like `db_password`, `github_ssh_key`, `gemini_api_key`, and `github_token` securely. Do not commit them directly to version control.** Consider using environment variables (`TF_VAR_name`), a secure secrets management tool (like HashiCorp Vault or GCP Secret Manager for Terraform variables), or Terraform Cloud/Enterprise for sensitive variable management.

    *Example `terraform.tfvars` structure (based on the provided file and root `variables.tf`):*

    ```terraform
    # --- GCP Configuration ---
    project          = "your-gcp-project-id" # Replace with your Project ID
    region           = "us-central1"
    zone             = "us-central1-a"
    credentials_file = "./your-credentials-file.json" # Replace with your key file name/path

    # --- Environment ---
    environment = "dev" # Or "staging", "prod"

    # --- Networking ---
    network_name = "hide-me-vpc"

    # --- Compute ---
    instance_name = "hide-me-app"
    machine_type  = "e2-medium" # Adjust as needed
    disk_size     = 20
    min_instances = 1
    max_instances = 3
    backend_port  = 8000
    go_backend_port = 8080

    # --- Database ---
    db_instance_name       = "hide-me-db"
    db_version             = "POSTGRES_14"
    db_tier                = "db-f1-micro" # Adjust as needed, consider higher tiers for prod
    db_name                = "hide-me-db-ea7a2c79" # Or your preferred DB name
    db_user                = "hidemedba"
    db_password            = "YOUR_SECURE_DB_PASSWORD" # Replace with a strong password, manage securely!
    db_deletion_protection = false # Set to true for production
    db_host                = "10.45.0.2" # This seems hardcoded, review if it should be dynamic
    db_port                = 5432

    # --- Load Balancer & DNS ---
    static_ip_name = "hide-me-lb-static-ip"
    domain_name    = "hidemeai.com" # Your root domain
    domain         = "api.hidemeai.com" # Your API subdomain
    go_domain      = "goapi.hidemeai.com" # Your Go API subdomain
    ssl_email      = "your-email@example.com" # For SSL certificate notifications

    # --- Application & Deployment ---
    github_repo    = "git@github.com:yasinhessnawi1/Hideme_Backend.git"
    go_github_repo = "git@github.com:yasinhessnawi1/Hideme_Backend.git" # Adjust if Go code is separate
    github_branch  = "main"
    repo_owner     = "yasinhessnawi1"
    repo_name      = "Hideme_Backend"
    github_ssh_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nYOUR_SSH_PRIVATE_KEY_CONTENT\n-----END OPENSSH PRIVATE KEY-----" # Replace, manage securely!
    github_token   = "YOUR_GITHUB_PAT" # Optional fallback, manage securely!
    gemini_api_key = "YOUR_GEMINI_API_KEY" # Replace, manage securely!

    # --- Monitoring (Optional) ---
    # alert_email = "your-alert-email@example.com"
    ```

### Deployment Steps

1.  **Initialize Terraform:** Open a terminal in the root directory of the Terraform project and run:
    ```bash
    terraform init
    ```
    This command initializes the backend, downloads provider plugins, and sets up the modules.

2.  **Plan Deployment:** Generate an execution plan to see what resources Terraform will create, modify, or destroy:
    ```bash
    terraform plan -out=tfplan
    ```
    Review the plan carefully to ensure it matches your expectations.

3.  **Apply Deployment:** Apply the changes to create the infrastructure:
    ```bash
    terraform apply tfplan
    ```
    Terraform will prompt for confirmation before proceeding. Type `yes` to approve.

4.  **DNS Configuration:** After `terraform apply` completes, Terraform will output the Google Cloud DNS nameservers (`dns_name_servers`). You need to log in to your domain registrar (e.g., Namecheap) and update the nameserver records for your domain (`hidemeai.com`) to use these Google nameservers. DNS propagation can take some time (minutes to 48 hours).

5.  **SSL Provisioning:** Once DNS propagation is complete, Google Cloud will automatically provision the managed SSL certificates for `api.hidemeai.com` and `goapi.hidemeai.com`. This can also take some time (up to 24 hours after DNS propagates).

6.  **Access Application:** Once SSL certificates are active, your application should be accessible via:
    *   `https://api.hidemeai.com` (Main Backend)
    *   `https://goapi.hidemeai.com` (Go Backend)

### Destroying Infrastructure

To tear down all the resources created by this Terraform configuration, run:

```bash
terraform destroy
```

Review the plan and type `yes` to confirm the destruction of resources. **Note:** Resources like the Cloud SQL instance might have deletion protection enabled (`db_deletion_protection = true`), which would need to be disabled manually or via Terraform before destruction can succeed.



## Example Compute Engine Startup Script (Sanitized for GitHub)

This section provides a sanitized version of the example startup script (`modules/compute/scripts/startup.sh`) used by the Compute Engine instances. This version replaces sensitive information like default passwords, API keys, and specific hostnames/domains with placeholders, making it suitable for inclusion in a public repository like GitHub.

**Note:** This script relies on metadata passed from the Terraform instance template for configuration values. For production environments, it is strongly recommended to modify the script to fetch secrets directly from Google Secret Manager using the instance's service account permissions instead of passing them via metadata.

```bash
#!/bin/bash

# Define variables with defaults (will be overridden by terraform)
# Sensitive defaults are replaced with placeholders
if [ -z "$port" ]; then
  port=8000
fi
if [ -z "$go_port" ]; then
  go_port=8080
fi
if [ -z "$env" ]; then
  env="dev" # Example: dev, staging, prod
fi
if [ -z "$branch" ]; then
  branch="main"
fi
if [ -z "$dbuser" ]; then
  dbuser="hidemedba"
fi
if [ -z "$dbpass" ]; then
  dbpass="YOUR_DB_PASSWORD" # Placeholder - Set via Terraform variable
fi
if [ -z "$dbname" ]; then
  dbname="hide-me-db"
fi
if [ -z "$dbconn" ]; then
  dbconn="" # Connection string if needed
fi
if [ -z "$dbport" ]; then
  dbport="5432"
fi
if [ -z "$dbhost" ]; then
  dbhost="YOUR_PRIVATE_DB_HOST_IP" # Placeholder - Set via Terraform variable
fi
if [ -z "$gemini_api_key" ]; then
  gemini_api_key="YOUR_GEMINI_API_KEY" # Placeholder - Set via Terraform variable
fi
if [ -z "$repo" ]; then
  repo="git@github.com:YOUR_GITHUB_USERNAME/YOUR_REPO_NAME.git" # Placeholder
fi
if [ -z "$go_repo" ]; then
  go_repo="git@github.com:YOUR_GITHUB_USERNAME/YOUR_GO_REPO_NAME.git" # Placeholder
fi
if [ -z "$domain" ]; then
  domain="api.yourdomain.com" # Placeholder
fi
if [ -z "$go_domain" ]; then
  go_domain="goapi.yourdomain.com" # Placeholder
fi

echo "Starting setup for environment: $env, branch: $branch"

#############################################
# PHASE 1: System Preparation and Software Installation
#############################################

echo "Phase 1: System preparation and software installation"

# Update the system
echo "Updating system packages..."
sudo apt-get update

# Install dependencies
echo "Installing dependencies..."
sudo apt-get install -y ca-certificates curl ufw nginx git apt-transport-https gnupg

# Install Google Cloud SDK if not present
if ! command -v gcloud &> /dev/null; then
  echo "Installing Google Cloud SDK..."
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
  curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
  sudo apt-get update && sudo apt-get install -y google-cloud-sdk
fi

echo "Expanding System Limits"
echo "Configuring system limits for large connections..."
sudo tee /etc/sysctl.d/99-network-tuning.conf > /dev/null << EOF
fs.file-max = 65535
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.core.optmem_max = 65536
net.ipv4.tcp_mem = 8388608 12582912 16777216
net.core.somaxconn = 65535
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_keepalive_time = 1800
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 10
net.core.netdev_max_backlog = 10000
EOF

# Apply the new sysctl settings
sudo sysctl --system
sudo snap install go --classic


# Adjust Docker settings for long-running containers
echo "Configuring Docker for long-running containers..."
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json > /dev/null << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  },
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 65536,
      "Soft": 65536
    }
  },
  "live-restore": true,
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 10
}
EOF

# Restart Docker to apply the changes
sudo systemctl restart docker

# Install Docker
echo "Installing Docker..."
sudo apt-get remove -y docker docker-engine docker.io containerd runc || true
sudo apt-get install -y docker.io

# Install Docker Compose
echo "Installing Docker Compose..."
sudo apt-get install -y docker-compose

# Ensure Docker is running
sudo systemctl enable docker
sudo systemctl start docker

#############################################
# PHASE 2: GitHub Authentication and Repositories Clone
#############################################

echo "Phase 2: GitHub authentication and repository clone"

# Clean up existing directories if they exist
if [ -d "/opt/hide-me" ]; then
  echo "Cleaning up existing hide-me directory..."
  sudo rm -rf /opt/hide-me
fi


# Create application directories
echo "Creating application directories..."
sudo mkdir -p /opt/hide-me
sudo chown -R $(whoami):$(whoami) /opt/hide-me

# Extract repository owner and name for better URL construction
REPO_OWNER="YOUR_GITHUB_USERNAME" # Placeholder
REPO_NAME="YOUR_REPO_NAME" # Placeholder
CLONE_SUCCESS=0
# Securely retrieve GitHub token from Secret Manager
echo "Fetching GitHub token from Secret Manager..."
GITHUB_TOKEN=$(gcloud secrets versions access latest --secret="hide-me-github-token-${env}" 2>/dev/null)

if [ ! -z "$GITHUB_TOKEN" ]; then
  echo "Retrieved GitHub token successfully."

  # Use the token securely without exposing it in logs
  echo "Cloning repository using token authentication..."
  # The set +x prevents the token from being logged
  set +x
  if git clone "https://${GITHUB_TOKEN}@github.com/${REPO_OWNER}/${REPO_NAME}.git" --branch "${branch}" /opt/hide-me; then
    set -x  # Turn logging back on
    echo "Repository cloned successfully with token!"
    CLONE_SUCCESS=0
  else
    set -x  # Turn logging back on
    echo "Token-based clone failed. Trying SSH..."
    CLONE_SUCCESS=1
  fi
else
  echo "Failed to retrieve GitHub token. Trying SSH key authentication..."
  CLONE_SUCCESS=1
fi

# If token-based clone failed, try SSH key authentication
if [ "$CLONE_SUCCESS" != "0" ]; then
  echo "Setting up SSH for GitHub..."

  # Fetch the SSH key from Secret Manager
  if SSH_KEY=$(gcloud secrets versions access latest --secret="hide-me-github-ssh-key-${env}" 2>/dev/null) && [ ! -z "$SSH_KEY" ]; then
    echo "Retrieved SSH key successfully."

    # Set up SSH configuration securely
    mkdir -p ~/.ssh
    echo "$SSH_KEY" > ~/.ssh/id_github
    chmod 600 ~/.ssh/id_github

    # Configure SSH to use this key for GitHub
    cat > ~/.ssh/config << EOF
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_github
  StrictHostKeyChecking no
EOF
    chmod 600 ~/.ssh/config

    # Try cloning with SSH
    if git clone "git@github.com:${REPO_OWNER}/${REPO_NAME}.git" --branch "${branch}" /opt/hide-me; then
      echo "Repository cloned successfully with SSH!"
      CLONE_SUCCESS=0
    else
      echo "SSH clone failed. Trying public HTTPS clone..."
      CLONE_SUCCESS=1
    fi
  else
    echo "Failed to retrieve SSH key. Trying public HTTPS clone..."
    CLONE_SUCCESS=1
  fi
fi

# Last resort - try public HTTPS if it's a public repository
if [ "$CLONE_SUCCESS" != "0" ]; then
  echo "Trying public HTTPS clone as last resort..."
  if git clone "https://github.com/${REPO_OWNER}/${REPO_NAME}.git" --branch "${branch}" /opt/hide-me; then
    echo "Repository cloned successfully with public HTTPS!"
    CLONE_SUCCESS=0
  else
    echo "All clone attempts failed."
    CLONE_SUCCESS=1
  fi
fi

# If all cloning methods failed, create minimal structure
if [ "$CLONE_SUCCESS" != "0" ]; then
  echo "All GitHub authentication methods failed. Creating minimal structure..."

  # Create minimal application structure
  mkdir -p /opt/hide-me/backend/html/status

  # Create a simple docker-compose.yml file
  cat > /opt/hide-me/backend/docker-compose.yml << EOF
version: '3'
services:
  app:
    image: nginx:alpine
    ports:
      - "${port}:80"
    volumes:
      - ./html:/usr/share/nginx/html
EOF

  # Create basic HTML files
  cat > /opt/hide-me/backend/html/index.html << EOF
<!DOCTYPE html>
<html>
<head>
  <title>Hide Me App</title>
</head>
<body>
  <h1>Hide Me Application</h1>
  <p>The application is running.</p>
  <p>GitHub repository access failed. This is a fallback page.</p>
</body>
</html>
EOF

  echo '{"status":"ok","repository":"access_failed"}' > /opt/hide-me/backend/html/status/index.html
fi

#############################################
# PHASE 3: Application Configuration
#############################################

echo "Phase 3: Application configuration"

# Set up environment variables for main backend
cd /opt/hide-me/backend
echo "Creating .env file for main backend..."

cat > .env << EOF
GEMINI_API_KEY=${gemini_api_key}
EOF

# Set up environment variables for Go backend
cd /opt/hide-me/gobackend
echo "Creating .env file for Go backend..."

cat > .env << EOF
APP_ENV=${env}
DB_HOST=${dbhost}
DB_PORT=${dbport}
DB_NAME=${dbname}
DB_USER=${dbuser}
DB_PASSWORD=${dbpass}
SERVER_HOST=0.0.0.0
SERVER_PORT=${go_port}
DB_CONNECTION=${dbconn}
EOF



  # Create a basic config.yaml for Go app (with placeholders for sensitive defaults)
cat > /opt/hide-me/gobackend/internal/config/config.yaml << EOF
app:
  environment: ${env} # Set dynamically
  name: HideMe
  version: 1.0.0

server:
  host: "127.0.0.1"
  port: ${go_port} # Set dynamically
  read_timeout: 15s
  write_timeout: 10s
  shutdown_timeout: 30s

database:
  host: "${dbhost}" # Set dynamically
  port: ${dbport} # Set dynamically
  name: ${dbname} # Set dynamically
  user: ${dbuser} # Set dynamically
  password: ${dbpass} # Set dynamically
  max_conns: 20
  min_conns: 5

jwt:
  secret: "YOUR_JWT_SECRET_KEY" # Placeholder - Should be managed securely
  expiry: 15m
  refresh_expiry: 168h
  issuer: "hideme-api"

api_key:
  default_expiry: 2160h

logging:
  level: info
  format: json
  request_log: true

cors:
  allowed_origins:
    - "*" # Adjust for production
  allow_credentials: true

password_hash:
  memory: 16384
  iterations: 1
  parallelism: 2
  salt_length: 16
  key_length: 32
EOF



# Stop any running containers
echo "Stopping any running containers..."
sudo docker ps -q | xargs -r sudo docker stop || true

# Build and start Docker containers for main backend
echo "Building and starting Docker containers for main backend..."
cd /opt/hide-me/backend
sudo docker-compose build
sudo docker-compose up -d

# Build and start Docker containers for Go backend
echo "Building and starting Docker containers for Go backend..."
cd /opt/hide-me/gobackend
sudo go mod tidy
sudo go mod download
sudo docker-compose build
sudo docker-compose up -d

#############################################
# PHASE 4: Nginx Configuration for Backend Services
#############################################

echo "Phase 4: Nginx configuration"

# Make sure Nginx is stopped before reconfiguring
sudo systemctl stop nginx || true

# Remove any existing configuration
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-available/backend
sudo rm -f /etc/nginx/sites-available/gobackend

# Create a new Nginx configuration for the main backend
MAIN_NGINX_CONF="/etc/nginx/sites-available/backend"

sudo tee $MAIN_NGINX_CONF > /dev/null << EOF
server {
    listen 80;
    server_name ${domain}; # Set dynamically

    large_client_header_buffers 8 32k;
    client_max_body_size 100M;
    proxy_connect_timeout 1200s;
    proxy_send_timeout 1200s;
    proxy_read_timeout 1200s;
    send_timeout 1200s;
    keepalive_timeout 1200s;

    location / {
        proxy_pass http://127.0.0.1:${port}; # Set dynamically
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_connect_timeout 1200s;
        proxy_send_timeout 1200s;
        proxy_read_timeout 1200s;
        proxy_buffers 16 16k;
        proxy_buffer_size 32k;
        proxy_request_buffering on;
        proxy_buffering on;
        proxy_busy_buffers_size 64k;
        proxy_temp_file_write_size 64k;
    }

    location /static/ {
        alias /opt/hide-me/backend/static/;
        expires 30d;
    }

    location = /status {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    location = /health {
        access_log off;
        return 200 'OK';
    }
}
EOF

# Create a new Nginx configuration for the Go backend
GO_NGINX_CONF="/etc/nginx/sites-available/gobackend"

sudo tee $GO_NGINX_CONF > /dev/null << EOF
server {
    listen 80;
    server_name ${go_domain}; # Set dynamically

    large_client_header_buffers 4 16k;

    location / {
        proxy_pass http://127.0.0.1:${go_port}; # Set dynamically
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_cookie_path / "/";
        proxy_cookie_domain localhost ${go_domain};
        proxy_pass_header Set-Cookie;

        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        proxy_buffers 8 16k;
        proxy_buffer_size 32k;
    }

    location = /status {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    location = /health {
        access_log off;
        return 200 'OK';
    }
}
EOF

# Create a default configuration for handling unknown domains
DEFAULT_NGINX_CONF="/etc/nginx/sites-available/default"

sudo tee $DEFAULT_NGINX_CONF > /dev/null << EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location = /status {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    location = /health {
        access_log off;
        return 200 'OK';
    }

    location / {
        return 444;
    }
}
EOF

# Enable the configurations
sudo ln -sf $MAIN_NGINX_CONF /etc/nginx/sites-enabled/
sudo ln -sf $GO_NGINX_CONF /etc/nginx/sites-enabled/
sudo ln -sf $DEFAULT_NGINX_CONF /etc/nginx/sites-enabled/

# Test and start Nginx
echo "Testing Nginx configuration..."
sudo nginx -t
sudo systemctl start nginx

#############################################
# PHASE 5: Firewall Configuration
#############################################

echo "Phase 5: Firewall configuration"

# Configure UFW firewall
echo "Configuring firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment 'Allow SSH'
sudo ufw allow 80/tcp comment 'Allow HTTP'
sudo ufw allow 443/tcp comment 'Allow HTTPS'
sudo ufw allow ${port}/tcp comment 'Allow main application port'
sudo ufw allow ${go_port}/tcp comment 'Allow Go application port'
sudo ufw --force enable

#############################################
# PHASE 6: Final Verification
#############################################

echo "Phase 6: Final verification"

# Create a health check script
echo "Creating health check script..."
cat > /opt/hide-me/health-check.sh << EOF
#!/bin/bash
# Health check script

# Check if Docker is running
if ! systemctl is-active --quiet docker; then
  echo "Docker is not running"
  exit 1
fi

# Check if Nginx is running
if ! systemctl is-active --quiet nginx; then
  echo "Nginx is not running"
  exit 1
fi

# Check if the main backend container is running
if ! sudo docker ps --filter "name=backend_app" --filter "status=running" --format '{{.Names}}' | grep -q "backend_app"; then
  echo "Main backend container is not running"
  exit 1
fi

# Check if the Go backend container is running
if ! sudo docker ps --filter "name=gobackend_app" --filter "status=running" --format '{{.Names}}' | grep -q "gobackend_app"; then
  echo "Go backend container is not running"
  exit 1
fi

# Check main backend status endpoint
if ! curl -s --fail http://127.0.0.1:${port}/status > /dev/null; then
  echo "Main backend status endpoint failed"
  exit 1
fi

# Check Go backend status endpoint
if ! curl -s --fail http://127.0.0.1:${go_port}/status > /dev/null; then
  echo "Go backend status endpoint failed"
  exit 1
fi

echo "All checks passed. System is healthy."
exit 0
EOF

chmod +x /opt/hide-me/health-check.sh

echo "Setup complete."

```


**How This Script is Used:**

1.  **Templating:** The Terraform `compute` module uses the `templatefile()` function to inject variables (like ports, database details, API keys, repository info) into this script content when creating the instance template (`google_compute_instance_template.app_template`).
2.  **Instance Metadata:** The resulting script content is passed as `startup-script` metadata to each Compute Engine instance created from the template.
3.  **Execution:** When a new instance boots up, GCP automatically executes this startup script as the `root` user.

**Key Script Phases:**

*   **Phase 1: System Prep:** Updates packages, installs dependencies (Docker, Docker Compose, Nginx, Git, gcloud SDK, Go), tunes system limits (`sysctl`), and configures Docker daemon settings.
*   **Phase 2: GitHub Auth & Clone:** Attempts to clone the application repositories (`/opt/hide-me`) using multiple methods (GitHub Token from Secret Manager, SSH Key from Secret Manager, public HTTPS) for robustness. Creates a fallback structure if cloning fails.
*   **Phase 3: Application Config:** Creates `.env` files for the main backend and Go backend using variables passed via metadata. Creates a default `config.yaml` for the Go app. Builds and starts the application containers using `docker-compose`.
*   **Phase 4: Nginx Config:** Configures Nginx as a reverse proxy, listening on port 80 and forwarding requests to the appropriate backend container based on the requested domain (`api.<domain>` or `goapi.<domain>`). Includes settings for large payloads and long timeouts.
*   **Phase 5: Firewall Config:** Configures the `ufw` firewall on the instance to allow necessary ports (SSH, HTTP, HTTPS, application ports).
*   **Phase 6: Verification:** Creates a basic health check script (`/opt/hide-me/health-check.sh`) to verify service status.

