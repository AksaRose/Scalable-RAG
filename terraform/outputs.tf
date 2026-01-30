# =============================================================================
# Terraform Outputs for Scalable RAG Infrastructure
# =============================================================================

# -----------------------------------------------------------------------------
# VPC Outputs
# -----------------------------------------------------------------------------

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = module.vpc.public_subnet_ids
}

# -----------------------------------------------------------------------------
# API Outputs
# -----------------------------------------------------------------------------

output "api_url" {
  description = "URL to access the API"
  value       = "http://${module.alb.dns_name}"
}

output "api_docs_url" {
  description = "URL to access API documentation"
  value       = "http://${module.alb.dns_name}/docs"
}

# -----------------------------------------------------------------------------
# Database Outputs
# -----------------------------------------------------------------------------

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.endpoint
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = module.rds.port
}

# -----------------------------------------------------------------------------
# Redis Outputs
# -----------------------------------------------------------------------------

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = module.elasticache.endpoint
}

output "redis_port" {
  description = "ElastiCache Redis port"
  value       = module.elasticache.port
}

# -----------------------------------------------------------------------------
# Qdrant Outputs
# -----------------------------------------------------------------------------

output "qdrant_private_ip" {
  description = "Private IP of Qdrant instance"
  value       = module.qdrant.private_ip
}

output "qdrant_url" {
  description = "URL to access Qdrant"
  value       = "http://${module.qdrant.private_ip}:6333"
}

# -----------------------------------------------------------------------------
# S3 Outputs
# -----------------------------------------------------------------------------

output "s3_bucket_name" {
  description = "Name of the S3 bucket for document storage"
  value       = module.s3.bucket_name
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = module.s3.bucket_arn
}

# -----------------------------------------------------------------------------
# ECS Outputs
# -----------------------------------------------------------------------------

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = module.ecs.cluster_name
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = module.ecs.cluster_arn
}

# -----------------------------------------------------------------------------
# ECR Outputs
# -----------------------------------------------------------------------------

output "ecr_api_repository_url" {
  description = "URL of the ECR repository for API image"
  value       = module.ecs.ecr_api_repository_url
}

output "ecr_worker_repository_url" {
  description = "URL of the ECR repository for worker image"
  value       = module.ecs.ecr_worker_repository_url
}

# -----------------------------------------------------------------------------
# Secrets Manager Outputs
# -----------------------------------------------------------------------------

output "secrets_manager_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.api_credentials.arn
}

# -----------------------------------------------------------------------------
# Connection Information
# -----------------------------------------------------------------------------

output "connection_info" {
  description = "Connection information for the deployed services"
  value = <<-EOT

    ╔══════════════════════════════════════════════════════════════════╗
    ║           Scalable RAG Infrastructure - Connection Info          ║
    ╠══════════════════════════════════════════════════════════════════╣
    ║                                                                  ║
    ║  API Endpoint:     http://${module.alb.dns_name}
    ║  API Docs:         http://${module.alb.dns_name}/docs
    ║                                                                  ║
    ║  PostgreSQL:       ${module.rds.endpoint}:${module.rds.port}
    ║  Redis:            ${module.elasticache.endpoint}:${module.elasticache.port}
    ║  Qdrant:           http://${module.qdrant.private_ip}:6333
    ║                                                                  ║
    ║  S3 Bucket:        ${module.s3.bucket_name}
    ║                                                                  ║
    ╚══════════════════════════════════════════════════════════════════╝

    To push Docker images:
    
    1. Authenticate to ECR:
       aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${module.ecs.ecr_api_repository_url}
    
    2. Push API image:
       docker tag scalable-rag-api:latest ${module.ecs.ecr_api_repository_url}:latest
       docker push ${module.ecs.ecr_api_repository_url}:latest
    
    3. Push Worker image:
       docker tag scalable-rag-worker:latest ${module.ecs.ecr_worker_repository_url}:latest
       docker push ${module.ecs.ecr_worker_repository_url}:latest

  EOT
}
