output "load_balancer_ip" {
  description = "The public IP address of the compute instance"
  value       = module.load_balancer.load_balancer_ip
}

output "network_name" {
  description = "The name of the created VPC network"
  value       = module.network.network_name
}

output "instance_ip" {
  description = "The public IP address of the compute instance"
  value       = module.compute.instance_ip
}