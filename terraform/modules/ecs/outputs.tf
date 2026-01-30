# ECS Module Outputs

output "cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "ecr_api_repository_url" {
  description = "ECR API repository URL"
  value       = aws_ecr_repository.api.repository_url
}

output "ecr_worker_repository_url" {
  description = "ECR worker repository URL"
  value       = aws_ecr_repository.worker.repository_url
}

output "api_service_name" {
  description = "API service name"
  value       = aws_ecs_service.api.name
}

output "security_group_id" {
  description = "ECS security group ID"
  value       = aws_security_group.ecs.id
}
