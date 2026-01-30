# =============================================================================
# Terraform Variables for Scalable RAG Infrastructure
# =============================================================================

variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
  default     = "scalable-rag"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

# -----------------------------------------------------------------------------
# VPC Configuration
# -----------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

# -----------------------------------------------------------------------------
# Database Configuration
# -----------------------------------------------------------------------------

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "rag_db"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "rag_user"
}

variable "db_password" {
  description = "Database master password"
  type        = string
  sensitive   = true
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS (GB)"
  type        = number
  default     = 20
}

# -----------------------------------------------------------------------------
# Redis Configuration
# -----------------------------------------------------------------------------

variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_cache_nodes" {
  description = "Number of Redis cache nodes"
  type        = number
  default     = 1
}

# -----------------------------------------------------------------------------
# Qdrant Configuration
# -----------------------------------------------------------------------------

variable "qdrant_instance_type" {
  description = "EC2 instance type for Qdrant"
  type        = string
  default     = "t3.medium"
}

variable "qdrant_volume_size" {
  description = "EBS volume size for Qdrant (GB)"
  type        = number
  default     = 50
}

# -----------------------------------------------------------------------------
# ECS Configuration
# -----------------------------------------------------------------------------

variable "api_cpu" {
  description = "CPU units for API task (1024 = 1 vCPU)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Memory for API task (MiB)"
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "Desired number of API tasks"
  type        = number
  default     = 2
}

variable "worker_cpu" {
  description = "CPU units for worker tasks"
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Memory for worker tasks (MiB)"
  type        = number
  default     = 2048
}

variable "text_worker_count" {
  description = "Number of text extraction workers"
  type        = number
  default     = 1
}

variable "chunk_worker_count" {
  description = "Number of chunking workers"
  type        = number
  default     = 1
}

variable "embed_worker_count" {
  description = "Number of embedding workers"
  type        = number
  default     = 2
}

# -----------------------------------------------------------------------------
# Application Configuration
# -----------------------------------------------------------------------------

variable "embedding_model" {
  description = "Embedding model to use"
  type        = string
  default     = "BAAI/bge-small-en-v1.5"
}

variable "internal_service_token" {
  description = "Token for internal service authentication"
  type        = string
  sensitive   = true
  default     = ""
}

# -----------------------------------------------------------------------------
# Tags
# -----------------------------------------------------------------------------

variable "tags" {
  description = "Additional tags for all resources"
  type        = map(string)
  default     = {}
}
