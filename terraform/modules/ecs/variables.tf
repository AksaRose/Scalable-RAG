# ECS Module Variables

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for ECS tasks"
  type        = list(string)
}

variable "alb_target_group_arn" {
  description = "ALB target group ARN"
  type        = string
}

variable "alb_security_group_id" {
  description = "ALB security group ID"
  type        = string
}

variable "api_cpu" {
  description = "CPU units for API task"
  type        = number
}

variable "api_memory" {
  description = "Memory for API task"
  type        = number
}

variable "api_desired_count" {
  description = "Desired number of API tasks"
  type        = number
}

variable "worker_cpu" {
  description = "CPU units for worker tasks"
  type        = number
}

variable "worker_memory" {
  description = "Memory for worker tasks"
  type        = number
}

variable "text_worker_count" {
  description = "Number of text workers"
  type        = number
}

variable "chunk_worker_count" {
  description = "Number of chunk workers"
  type        = number
}

variable "embed_worker_count" {
  description = "Number of embed workers"
  type        = number
}

variable "database_url" {
  description = "Database connection URL"
  type        = string
  sensitive   = true
}

variable "redis_url" {
  description = "Redis connection URL"
  type        = string
}

variable "qdrant_url" {
  description = "Qdrant connection URL"
  type        = string
}

variable "s3_bucket" {
  description = "S3 bucket name"
  type        = string
}

variable "embedding_model" {
  description = "Embedding model name"
  type        = string
}

variable "internal_service_token" {
  description = "Internal service token"
  type        = string
  sensitive   = true
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
