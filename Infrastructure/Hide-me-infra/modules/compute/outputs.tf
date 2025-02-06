output "instance_self_link" {
  description = "The self link of the compute instance"
  value       = google_compute_instance.vm_instance.self_link
}

output "instance_ip" {
  description = "The public IP address of the compute instance"
  value       = google_compute_address.static_ip.address
}
