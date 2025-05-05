/**
 * # Main Terraform Configuration
 *
 * This is the main entry point for the Hide Me application infrastructure.
 * It orchestrates all the modules that make up the complete infrastructure.
 */

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 4.0"
    }
  }

  # Uncomment to use a remote backend for state management
  # backend "gcs" {
  #   bucket = "hide-me-terraform-state"
  #   prefix = "terraform/state"
  # }
}

provider "google" {
  project     = var.project
  region      = var.region
  zone        = var.zone
  credentials = file(var.credentials_file)
}

provider "google-beta" {
  project     = var.project
  region      = var.region
  zone        = var.zone
  credentials = file(var.credentials_file)
}

# VPC Module
module "vpc" {
  source       = "modules/vpc"
  project      = var.project
  region       = var.region
  network_name = var.network_name
  environment  = var.environment
}

# Security Module
module "security" {
  source                = "modules/security"
  project               = var.project
  network_id            = module.vpc.network_id
  environment           = var.environment
  private_subnet_ranges = [module.vpc.private_subnet_cidr]
  health_check_port     = var.health_check_port
  backend_port          = var.backend_port
  db_user               = var.db_user
  db_password           = var.db_password
  db_name               = var.db_name
  depends_on            = [module.vpc]
  region                = var.region
}

# Database Module
module "database" {
  source                 = "modules/database"
  project                = var.project
  region                 = var.region
  environment            = var.environment
  network_id             = module.vpc.network_id
  private_subnet_cidr    = module.vpc.private_subnet_cidr
  db_instance_name       = var.db_instance_name
  db_version             = var.db_version
  db_tier                = var.db_tier
  db_name                = var.db_name
  db_user                = var.db_user
  db_password            = var.db_password
  db_deletion_protection = var.db_deletion_protection
  db_disk_size           = var.db_disk_size
  depends_on             = [module.vpc, module.security]
}

# Compute Module
module "compute" {
  source                = "modules/compute"
  project               = var.project
  region                = var.region
  environment           = var.environment
  instance_name         = var.instance_name
  machine_type          = var.machine_type
  disk_size             = var.disk_size
  disk_type             = var.disk_type
  network_id            = module.vpc.network_id
  subnet_id             = module.vpc.private_subnet_id
  service_account_email = module.security.app_service_account_email
  db_connection_name    = module.database.connection_name
  db_name               = var.db_name
  db_user               = var.db_user
  db_host               = var.db_host
  db_port               = var.db_port
  db_password           = var.db_password
  min_instances         = var.min_instances
  max_instances         = var.max_instances
  app_port              = var.backend_port
  go_port               = var.go_backend_port
  zones                 = ["${var.region}-a", "${var.region}-b", "${var.region}-c"]
  github_ssh_key        = var.github_ssh_key
  gemini_api_key        = var.gemini_api_key
  github_repo           = var.github_repo
  github_branch         = var.github_branch
  depends_on            = [module.vpc, module.security, module.database]
  github_token          = var.github_token
  repo_owner            = var.repo_owner
  repo_name             = var.repo_name
  domain                = var.domain
  ssl_email             = var.ssl_email

}

# Load Balancer Module
module "load_balancer" {
  source               = "modules/load_balancer"
  project              = var.project
  environment          = var.environment
  instance_group       = module.compute.instance_group
  health_check_port    = var.health_check_port
  static_ip_name       = var.static_ip_name
  domain_name          = var.domain_name # Using root domain variable
  /*
  security_policy_name = module.security.security_policy_name

   */
  depends_on           = [module.vpc, module.compute]
}

# DNS Module (New)
module "dns" {
  source           = "modules/dns"
  project          = var.project
  environment      = var.environment
  domain_name      = var.domain_name # Using root domain variable for DNS zone
  load_balancer_ip = module.load_balancer.lb_external_ip
  depends_on       = [module.load_balancer]
}

/*
# Monitoring Module
module "monitoring" {
  source       = "./modules/monitoring"
  project      = var.project
  region       = var.region
  environment  = var.environment
  instance_ids = [module.compute.instance_group]
  db_instance  = module.database.db_instance_name
  lb_name      = module.load_balancer.lb_name
  alert_email  = var.alert_email
  depends_on   = [module.compute, module.database, module.load_balancer]
}
*/