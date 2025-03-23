# Hide Me Infrastructure - Terraform Configuration

This Terraform project defines the infrastructure for the Hide Me application, focusing on security, modularity, scalability, and cost efficiency.

## Project Structure

```
terraform_project/
├── main.tf                 # Main configuration file
├── variables.tf            # Input variables
├── outputs.tf              # Output values
├── terraform.tfvars        # Variable values
├── modules/
│   ├── vpc/                # Network infrastructure
│   ├── security/           # Security configurations
│   ├── database/           # PostgreSQL database
│   ├── compute/            # Compute resources
│   ├── load_balancer/      # Load balancing with static IP
│   └── monitoring/         # Monitoring and alerting
```

## Features

- **Security**
  - Least privilege service accounts
  - Network segmentation with public/private subnets
  - Cloud Armor WAF protection
  - Secret Manager for sensitive data
  - Shielded VMs with secure boot
  - Comprehensive firewall rules
  - SSL policy for HTTPS connections

- **Availability & Scalability**
  - Regional managed instance groups
  - Autoscaling based on load
  - Cloud SQL with high availability configuration
  - Global load balancer with health checks
  - Multi-zone deployment

- **Cost**
  - Autoscaling to match demand
  - Storage lifecycle management
  - Preemptible VMs for non-production
  - Monitoring and alerting for resource utilization
  - Right-sized database instances

- **Modularity & Maintainability**
  - Modular architecture
  - Consistent naming conventions
  - Comprehensive documentation
  - Resource tagging and labeling

## Prerequisites

- Google Cloud Platform account
- Terraform 1.0.0 or newer
- Google Cloud SDK
- Service account with appropriate permissions

## Usage

1. Initialize Terraform:
   ```
   terraform init
   ```

2. Review the execution plan:
   ```
   terraform plan
   ```

3. Apply the configuration:
   ```
   terraform apply
   ```

4. Connect your domain to the static IP (see outputs for instructions)

## Notes

- The static IP address for the load balancer is configured to be permanent
- Database credentials are stored securely in Secret Manager
- Monitoring alerts can be configured by setting the alert_email variable
