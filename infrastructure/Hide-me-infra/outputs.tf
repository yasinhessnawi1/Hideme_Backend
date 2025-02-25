output "load_balancer_ip" {
  description = "The public IP address of the compute instance"
  value       = module.load_balancer.load_balancer_ip
}

output "instance_ip" {
  description = "The public IP address of the compute instance"
  value       = module.compute.instance_ip
}