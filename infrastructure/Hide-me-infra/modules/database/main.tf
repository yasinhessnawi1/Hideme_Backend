/**
 * # Database Module
 *
 * This module creates database resources for the Hide Me application,
 * including a PostgreSQL Cloud SQL instance with proper security and configuration.
 */

# Create a private IP address for the database
resource "google_compute_global_address" "private_ip_address" {
  name          = "hide-me-db-private-ip-${var.environment}"
  project       = var.project
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = var.network_id

}

# Create a service networking connection for private IP
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = var.network_id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]
}

# Create a PostgreSQL database instance
resource "google_sql_database_instance" "postgres" {
  name                = "${var.db_instance_name}-${random_id.db_name_suffix.hex}"
  project             = var.project
  region              = var.region
  database_version    = var.db_version
  deletion_protection = var.db_deletion_protection

  depends_on = [google_service_networking_connection.private_vpc_connection]

  settings {
    tier              = var.db_tier
    availability_type = var.environment == "prod" ? "REGIONAL" : "REGIONAL" #todo: change to Zonal if needed
    disk_size         = var.db_disk_size
    disk_type         = "PD_SSD"
    disk_autoresize   = true
    # Backup configuration
    backup_configuration {
      enabled                        = true
      binary_log_enabled             = false
      start_time                     = "02:00"
      location                       = var.region
      point_in_time_recovery_enabled = true
    }

    # Maintenance window
    maintenance_window {
      day          = 7 # Sunday
      hour         = 3 # 3 AM
      update_track = "stable"
    }

    # IP configuration
    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network_id
      require_ssl     = true

      # Do not explicitly add the private subnet CIDR as it's automatically included
      # authorized_networks {
      #   name  = "private-subnet"
      #   value = var.private_subnet_cidr
      # }
    }

    # Database flags
    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }

    database_flags {
      name  = "log_connections"
      value = "on"
    }

    database_flags {
      name  = "log_disconnections"
      value = "on"
    }

    database_flags {
      name  = "log_lock_waits"
      value = "on"
    }

    database_flags {
      name  = "log_min_error_statement"
      value = "error"
    }

    database_flags {
      name  = "log_min_messages"
      value = "warning"
    }

    database_flags {
      name  = "log_temp_files"
      value = "0"
    }

    # User labels
    user_labels = {
      environment = var.environment
      application = "hide-me"
      managed-by  = "terraform"
    }
  }

  # Fixed lifecycle block with static value
  lifecycle {
    prevent_destroy = false
  }
}

# Create a random suffix for the database instance name
resource "random_id" "db_name_suffix" {
  byte_length = 4
}

# Create a database
resource "google_sql_database" "database" {
  name      = var.db_name
  project   = var.project
  instance  = google_sql_database_instance.postgres.name
  charset   = "UTF8"
  collation = "en_US.UTF8"
}

# Create a database user
resource "google_sql_user" "user" {
  name     = var.db_user
  project  = var.project
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}

/*

# Create a read replica for production environment
resource "google_sql_database_instance" "read_replica" {
  count                = var.environment == "prod" ? 1 : 0
  name                 = "${var.db_instance_name}-replica-${random_id.db_name_suffix.hex}"
  project              = var.project
  region               = var.region
  database_version     = var.db_version
  master_instance_name = google_sql_database_instance.postgres.name
  deletion_protection  = var.db_deletion_protection

  replica_configuration {
    failover_target = false
  }

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"

    # IP configuration
    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network_id
      require_ssl     = true
    }

    # User labels
    user_labels = {
      environment = var.environment
      application = "hide-me"
      managed-by  = "terraform"
      role        = "read-replica"
    }
  }

  depends_on = [google_sql_database_instance.postgres]

  # Fixed lifecycle block with static value
  lifecycle {
    prevent_destroy = true
  }
}

 */
