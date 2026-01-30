# =============================================================================
# Terraform Configuration for Scalable RAG Infrastructure on AWS
# =============================================================================

terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Uncomment and configure for remote state
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "scalable-rag/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-locks"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(var.tags, {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    })
  }
}

# -----------------------------------------------------------------------------
# Local Variables
# -----------------------------------------------------------------------------

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# -----------------------------------------------------------------------------
# Generate Random Strings for Secrets
# -----------------------------------------------------------------------------

resource "random_password" "internal_token" {
  count   = var.internal_service_token == "" ? 1 : 0
  length  = 32
  special = false
}

locals {
  internal_service_token = var.internal_service_token != "" ? var.internal_service_token : random_password.internal_token[0].result
}

# -----------------------------------------------------------------------------
# VPC Module
# -----------------------------------------------------------------------------

module "vpc" {
  source = "./modules/vpc"

  name_prefix        = local.name_prefix
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  tags               = local.common_tags
}

# -----------------------------------------------------------------------------
# S3 Module (Document Storage)
# -----------------------------------------------------------------------------

module "s3" {
  source = "./modules/s3"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

# -----------------------------------------------------------------------------
# RDS Module (PostgreSQL)
# -----------------------------------------------------------------------------

module "rds" {
  source = "./modules/rds"

  name_prefix         = local.name_prefix
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  allowed_cidr_blocks = [var.vpc_cidr]
  
  db_name             = var.db_name
  db_username         = var.db_username
  db_password         = var.db_password
  db_instance_class   = var.db_instance_class
  allocated_storage   = var.db_allocated_storage
  
  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# ElastiCache Module (Redis)
# -----------------------------------------------------------------------------

module "elasticache" {
  source = "./modules/elasticache"

  name_prefix         = local.name_prefix
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  allowed_cidr_blocks = [var.vpc_cidr]
  
  node_type           = var.redis_node_type
  num_cache_nodes     = var.redis_num_cache_nodes
  
  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# Qdrant Module (Vector Database)
# -----------------------------------------------------------------------------

module "qdrant" {
  source = "./modules/qdrant"

  name_prefix         = local.name_prefix
  vpc_id              = module.vpc.vpc_id
  subnet_id           = module.vpc.private_subnet_ids[0]
  allowed_cidr_blocks = [var.vpc_cidr]
  
  instance_type       = var.qdrant_instance_type
  volume_size         = var.qdrant_volume_size
  
  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# ALB Module (Application Load Balancer)
# -----------------------------------------------------------------------------

module "alb" {
  source = "./modules/alb"

  name_prefix = local.name_prefix
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.public_subnet_ids
  
  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# ECS Module (API and Workers)
# -----------------------------------------------------------------------------

module "ecs" {
  source = "./modules/ecs"

  name_prefix = local.name_prefix
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids
  
  # ALB configuration
  alb_target_group_arn = module.alb.target_group_arn
  alb_security_group_id = module.alb.security_group_id
  
  # API configuration
  api_cpu           = var.api_cpu
  api_memory        = var.api_memory
  api_desired_count = var.api_desired_count
  
  # Worker configuration
  worker_cpu          = var.worker_cpu
  worker_memory       = var.worker_memory
  text_worker_count   = var.text_worker_count
  chunk_worker_count  = var.chunk_worker_count
  embed_worker_count  = var.embed_worker_count
  
  # Environment variables
  database_url           = "postgresql://${var.db_username}:${var.db_password}@${module.rds.endpoint}/${var.db_name}"
  redis_url              = "redis://${module.elasticache.endpoint}:6379/0"
  qdrant_url             = "http://${module.qdrant.private_ip}:6333"
  s3_bucket              = module.s3.bucket_name
  embedding_model        = var.embedding_model
  internal_service_token = local.internal_service_token
  
  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# CloudWatch Log Groups
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name_prefix}/api"
  retention_in_days = 30
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "workers" {
  name              = "/ecs/${local.name_prefix}/workers"
  retention_in_days = 30
  tags              = local.common_tags
}

# -----------------------------------------------------------------------------
# Secrets Manager (for API keys and credentials)
# -----------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "api_credentials" {
  name        = "${local.name_prefix}/api-credentials"
  description = "API credentials for Scalable RAG service"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "api_credentials" {
  secret_id = aws_secretsmanager_secret.api_credentials.id
  secret_string = jsonencode({
    internal_service_token = local.internal_service_token
    db_password            = var.db_password
  })
}
