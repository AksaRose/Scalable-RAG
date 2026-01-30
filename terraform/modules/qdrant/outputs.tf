# Qdrant Module Outputs

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.qdrant.id
}

output "private_ip" {
  description = "Private IP address"
  value       = aws_instance.qdrant.private_ip
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.qdrant.id
}
