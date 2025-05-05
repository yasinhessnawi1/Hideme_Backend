/**
 * # Monitoring Module
 * 
 * This module creates monitoring resources for the Hide Me application,
 * including dashboards, alerts, and logging configurations.
 */

# Create a monitoring notification channel for email alerts
resource "google_monitoring_notification_channel" "email_channel" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "Hide Me Alerts - ${var.environment}"
  project      = var.project
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  user_labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create a CPU utilization alert policy
resource "google_monitoring_alert_policy" "cpu_utilization_alert" {
  display_name = "Hide Me - High CPU Utilization - ${var.environment}"
  project      = var.project
  combiner     = "OR"

  conditions {
    display_name = "High CPU utilization"

    condition_threshold {
      filter          = "resource.type = \"gce_instance\" AND metric.type = \"compute.googleapis.com/instance/cpu/utilization\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_channel[0].id] : []

  documentation {
    content   = "CPU utilization has exceeded 80% for more than 1 minute. This may indicate performance issues with the application."
    mime_type = "text/markdown"
  }

  # Add labels for resource management
  user_labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create a memory utilization alert policy
resource "google_monitoring_alert_policy" "memory_utilization_alert" {
  display_name = "Hide Me - High Memory Utilization - ${var.environment}"
  project      = var.project
  combiner     = "OR"

  conditions {
    display_name = "High memory utilization"

    condition_threshold {
      filter          = "resource.type = \"gce_instance\" AND metric.type = \"agent.googleapis.com/memory/percent_used\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 85

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_channel[0].id] : []

  documentation {
    content   = "Memory utilization has exceeded 85% for more than 5 minutes. This may indicate a memory leak or insufficient resources."
    mime_type = "text/markdown"
  }

  # Add labels for resource management
  user_labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create a disk utilization alert policy
resource "google_monitoring_alert_policy" "disk_utilization_alert" {
  display_name = "Hide Me - High Disk Utilization - ${var.environment}"
  project      = var.project
  combiner     = "OR"

  conditions {
    display_name = "High disk utilization"

    condition_threshold {
      filter          = "resource.type = \"gce_instance\" AND metric.type = \"agent.googleapis.com/disk/percent_used\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 90

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_channel[0].id] : []

  documentation {
    content   = "Disk utilization has exceeded 90% for more than 5 minutes. This may cause the application to stop functioning properly if the disk becomes full."
    mime_type = "text/markdown"
  }

  # Add labels for resource management
  user_labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create a database CPU utilization alert policy
resource "google_monitoring_alert_policy" "db_cpu_utilization_alert" {
  display_name = "Hide Me - Database High CPU Utilization - ${var.environment}"
  project      = var.project
  combiner     = "OR"

  conditions {
    display_name = "Database high CPU utilization"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND resource.labels.database_id = \"${var.db_instance}\" AND metric.type = \"cloudsql.googleapis.com/database/cpu/utilization\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_channel[0].id] : []

  documentation {
    content   = "Database CPU utilization has exceeded 80% for more than 5 minutes. This may indicate performance issues with database queries."
    mime_type = "text/markdown"
  }

  # Add labels for resource management
  user_labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create a database memory utilization alert policy
resource "google_monitoring_alert_policy" "db_memory_utilization_alert" {
  display_name = "Hide Me - Database High Memory Utilization - ${var.environment}"
  project      = var.project
  combiner     = "OR"

  conditions {
    display_name = "Database high memory utilization"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND resource.labels.database_id = \"${var.db_instance}\" AND metric.type = \"cloudsql.googleapis.com/database/memory/utilization\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.85

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_channel[0].id] : []

  documentation {
    content   = "Database memory utilization has exceeded 85% for more than 5 minutes. This may indicate insufficient memory resources for the database."
    mime_type = "text/markdown"
  }

  # Add labels for resource management
  user_labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create a database disk utilization alert policy
resource "google_monitoring_alert_policy" "db_disk_utilization_alert" {
  display_name = "Hide Me - Database High Disk Utilization - ${var.environment}"
  project      = var.project
  combiner     = "OR"

  conditions {
    display_name = "Database high disk utilization"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND resource.labels.database_id = \"${var.db_instance}\" AND metric.type = \"cloudsql.googleapis.com/database/disk/utilization\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.9

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_channel[0].id] : []

  documentation {
    content   = "Database disk utilization has exceeded 90% for more than 5 minutes. This may cause the database to stop functioning properly if the disk becomes full."
    mime_type = "text/markdown"
  }

  # Add labels for resource management
  user_labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create a load balancer latency alert policy
resource "google_monitoring_alert_policy" "lb_latency_alert" {
  display_name = "Hide Me - Load Balancer High Latency - ${var.environment}"
  project      = var.project
  combiner     = "OR"

  conditions {
    display_name = "Load balancer high latency"

    condition_threshold {
      filter          = "resource.type = \"https_lb_rule\" AND resource.labels.url_map_name = \"${var.lb_name}\" AND metric.type = \"loadbalancing.googleapis.com/https/backend_latencies\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 1000 # 1000 ms = 1 second

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_99"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_channel[0].id] : []

  documentation {
    content   = "Load balancer backend latency has exceeded 1 second (99th percentile) for more than 5 minutes. This indicates performance issues with the application."
    mime_type = "text/markdown"
  }

  # Add labels for resource management
  user_labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create a load balancer error rate alert policy
resource "google_monitoring_alert_policy" "lb_error_rate_alert" {
  display_name = "Hide Me - Load Balancer High Error Rate - ${var.environment}"
  project      = var.project
  combiner     = "OR"

  conditions {
    display_name = "Load balancer high error rate"

    condition_threshold {
      filter          = "resource.type = \"https_lb_rule\" AND resource.labels.url_map_name = \"${var.lb_name}\" AND metric.type = \"loadbalancing.googleapis.com/https/request_count\" AND metric.labels.response_code_class = \"500\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 10 # More than 10 errors in 5 minutes

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_channel[0].id] : []

  documentation {
    content   = "Load balancer is experiencing a high rate of 5xx errors for more than 5 minutes. This indicates server-side issues with the application."
    mime_type = "text/markdown"
  }

  # Add labels for resource management
  user_labels = {
    environment = var.environment
    application = "hide-me"
    managed-by  = "terraform"
  }
}

# Create an application dashboard
# Create an application dashboard
resource "google_monitoring_dashboard" "app_dashboard" {
  dashboard_json = <<-EOT
{
  "displayName": "Hide Me Application Dashboard - ${var.environment}",
  "gridLayout": {
    "widgets": [
      {
        "title": "CPU Utilization",
        "xyChart": {
          "dataSets": [
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"gce_instance\" AND metric.type = \"compute.googleapis.com/instance/cpu/utilization\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_MEAN",
                    "crossSeriesReducer": "REDUCE_MEAN",
                    "groupByFields": ["resource.label.instance_id"]
                  }
                }
              },
              "plotType": "LINE"
            }
          ],
          "yAxis": {
            "label": "CPU utilization",
            "scale": "LINEAR"
          }
        }
      },
      {
        "title": "Memory Utilization",
        "xyChart": {
          "dataSets": [
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"gce_instance\" AND metric.type = \"agent.googleapis.com/memory/percent_used\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_MEAN",
                    "crossSeriesReducer": "REDUCE_MEAN",
                    "groupByFields": ["resource.label.instance_id"]
                  }
                }
              },
              "plotType": "LINE"
            }
          ],
          "yAxis": {
            "label": "Memory utilization",
            "scale": "LINEAR"
          }
        }
      },
      {
        "title": "Disk Utilization",
        "xyChart": {
          "dataSets": [
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"gce_instance\" AND metric.type = \"agent.googleapis.com/disk/percent_used\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_MEAN",
                    "crossSeriesReducer": "REDUCE_MEAN",
                    "groupByFields": ["resource.label.instance_id", "metric.label.device"]
                  }
                }
              },
              "plotType": "LINE"
            }
          ],
          "yAxis": {
            "label": "Disk utilization",
            "scale": "LINEAR"
          }
        }
      },
      {
        "title": "Network Traffic",
        "xyChart": {
          "dataSets": [
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"gce_instance\" AND metric.type = \"compute.googleapis.com/instance/network/received_bytes_count\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_RATE",
                    "crossSeriesReducer": "REDUCE_SUM",
                    "groupByFields": ["resource.label.instance_id"]
                  }
                }
              },
              "plotType": "LINE",
              "legendTemplate": "Received bytes"
            },
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"gce_instance\" AND metric.type = \"compute.googleapis.com/instance/network/sent_bytes_count\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_RATE",
                    "crossSeriesReducer": "REDUCE_SUM",
                    "groupByFields": ["resource.label.instance_id"]
                  }
                }
              },
              "plotType": "LINE",
              "legendTemplate": "Sent bytes"
            }
          ],
          "yAxis": {
            "label": "Bytes/s",
            "scale": "LINEAR"
          }
        }
      },
      {
        "title": "Database CPU Utilization",
        "xyChart": {
          "dataSets": [
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"cloudsql_database\" AND resource.labels.database_id = \"${var.db_instance}\" AND metric.type = \"cloudsql.googleapis.com/database/cpu/utilization\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_MEAN"
                  }
                }
              },
              "plotType": "LINE"
            }
          ],
          "yAxis": {
            "label": "CPU utilization",
            "scale": "LINEAR"
          }
        }
      },
      {
        "title": "Database Memory Utilization",
        "xyChart": {
          "dataSets": [
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"cloudsql_database\" AND resource.labels.database_id = \"${var.db_instance}\" AND metric.type = \"cloudsql.googleapis.com/database/memory/utilization\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_MEAN"
                  }
                }
              },
              "plotType": "LINE"
            }
          ],
          "yAxis": {
            "label": "Memory utilization",
            "scale": "LINEAR"
          }
        }
      },
      {
        "title": "Database Disk Utilization",
        "xyChart": {
          "dataSets": [
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"cloudsql_database\" AND resource.labels.database_id = \"${var.db_instance}\" AND metric.type = \"cloudsql.googleapis.com/database/disk/utilization\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_MEAN"
                  }
                }
              },
              "plotType": "LINE"
            }
          ],
          "yAxis": {
            "label": "Disk utilization",
            "scale": "LINEAR"
          }
        }
      },
      {
        "title": "Load Balancer Latency",
        "xyChart": {
          "dataSets": [
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"https_lb_rule\" AND resource.labels.url_map_name = \"${var.lb_name}\" AND metric.type = \"loadbalancing.googleapis.com/https/backend_latencies\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_PERCENTILE_99"
                  }
                }
              },
              "plotType": "LINE"
            }
          ],
          "yAxis": {
            "label": "Latency (ms)",
            "scale": "LINEAR"
          }
        }
      },
      {
        "title": "Load Balancer Error Rate",
        "xyChart": {
          "dataSets": [
            {
              "timeSeriesQuery": {
                "timeSeriesFilter": {
                  "filter": "resource.type = \"https_lb_rule\" AND resource.labels.url_map_name = \"${var.lb_name}\" AND metric.type = \"loadbalancing.googleapis.com/https/request_count\" AND metric.labels.response_code_class = \"500\"",
                  "aggregation": {
                    "alignmentPeriod": "60s",
                    "perSeriesAligner": "ALIGN_RATE",
                    "crossSeriesReducer": "REDUCE_SUM"
                  }
                }
              },
              "plotType": "LINE"
            }
          ],
          "yAxis": {
            "label": "Error count",
            "scale": "LINEAR"
          }
        }
      }
    ]
  }
}
EOT
}