terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  credentials = file(var.credentials_file) # Path to your service account JSON file
  project     = var.project
  region      = var.region
  zone        = var.zone
}

module "network" {
  source       = "./modules/network"
  network_name = var.network_name
  region       = var.region
  project      = var.project
}

module "compute" {
  source        = "./modules/compute"
  instance_name = var.instance_name
  zone          = var.zone
  region        = var.region
  machine_type  = var.machine_type
  subnetwork    = module.network.subnetwork_self_link
  gpu_count     = var.gpu_count
  project       = var.project
  disk_size     = var.disk_size
}

module "load_balancer" {
  source             = "./modules/load_balancer"
  project            = var.project
  region             = var.region
  instance_zone      = var.zone
  instance_self_link = module.compute.instance_self_link
  instance_name      = var.instance_name
  backend_port       = 80 # or your custom backend port
}

