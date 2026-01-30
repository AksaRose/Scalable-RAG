# =============================================================================
# ECS Module - Container Services (API and Workers)
# =============================================================================

# -----------------------------------------------------------------------------
# ECR Repositories
# -----------------------------------------------------------------------------

resource "aws_ecr_repository" "api" {
  name                 = "${var.name_prefix}-api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_repository" "worker" {
  name                 = "${var.name_prefix}-worker"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# ECS Cluster
# -----------------------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = var.tags
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# -----------------------------------------------------------------------------
# IAM Roles
# -----------------------------------------------------------------------------

# ECS Task Execution Role
resource "aws_iam_role" "ecs_execution" {
  name = "${var.name_prefix}-ecs-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ECS Task Role (for S3 access, etc.)
resource "aws_iam_role" "ecs_task" {
  name = "${var.name_prefix}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "ecs_task_s3" {
  name = "${var.name_prefix}-ecs-task-s3"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket}",
          "arn:aws:s3:::${var.s3_bucket}/*"
        ]
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Security Group for ECS Tasks
# -----------------------------------------------------------------------------

resource "aws_security_group" "ecs" {
  name        = "${var.name_prefix}-ecs-sg"
  description = "Security group for ECS tasks"
  vpc_id      = var.vpc_id

  # Allow inbound from ALB
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [var.alb_security_group_id]
  }

  # Allow all outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-ecs-sg"
  })
}

# -----------------------------------------------------------------------------
# API Task Definition
# -----------------------------------------------------------------------------

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name_prefix}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "api"
      image = "${aws_ecr_repository.api.repository_url}:latest"
      
      portMappings = [{
        containerPort = 8000
        protocol      = "tcp"
      }]
      
      environment = [
        { name = "DATABASE_URL", value = var.database_url },
        { name = "REDIS_URL", value = var.redis_url },
        { name = "QDRANT_URL", value = var.qdrant_url },
        { name = "S3_BUCKET", value = var.s3_bucket },
        { name = "AWS_DEFAULT_REGION", value = data.aws_region.current.name },
        { name = "EMBEDDING_MODEL", value = var.embedding_model },
        { name = "INTERNAL_SERVICE_TOKEN", value = var.internal_service_token },
        { name = "USE_S3", value = "true" }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.name_prefix}/api"
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "api"
        }
      }
      
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = var.tags
}

# -----------------------------------------------------------------------------
# API Service
# -----------------------------------------------------------------------------

resource "aws_ecs_service" "api" {
  name            = "${var.name_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group_arn
    container_name   = "api"
    container_port   = 8000
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Worker Task Definitions
# -----------------------------------------------------------------------------

# Text Extraction Worker
resource "aws_ecs_task_definition" "text_worker" {
  family                   = "${var.name_prefix}-text-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "text-worker"
      image = "${aws_ecr_repository.worker.repository_url}:latest"
      
      command = ["python", "-m", "workers.text_extractor.worker"]
      
      environment = [
        { name = "DATABASE_URL", value = var.database_url },
        { name = "REDIS_URL", value = var.redis_url },
        { name = "S3_BUCKET", value = var.s3_bucket },
        { name = "AWS_DEFAULT_REGION", value = data.aws_region.current.name },
        { name = "USE_S3", value = "true" }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.name_prefix}/workers"
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "text-worker"
        }
      }
    }
  ])

  tags = var.tags
}

# Chunk Worker
resource "aws_ecs_task_definition" "chunk_worker" {
  family                   = "${var.name_prefix}-chunk-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "chunk-worker"
      image = "${aws_ecr_repository.worker.repository_url}:latest"
      
      command = ["python", "-m", "workers.chunker.worker"]
      
      environment = [
        { name = "DATABASE_URL", value = var.database_url },
        { name = "REDIS_URL", value = var.redis_url },
        { name = "S3_BUCKET", value = var.s3_bucket },
        { name = "AWS_DEFAULT_REGION", value = data.aws_region.current.name },
        { name = "USE_S3", value = "true" }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.name_prefix}/workers"
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "chunk-worker"
        }
      }
    }
  ])

  tags = var.tags
}

# Embed Worker
resource "aws_ecs_task_definition" "embed_worker" {
  family                   = "${var.name_prefix}-embed-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "embed-worker"
      image = "${aws_ecr_repository.worker.repository_url}:latest"
      
      command = ["python", "-m", "workers.embedder.worker"]
      
      environment = [
        { name = "DATABASE_URL", value = var.database_url },
        { name = "REDIS_URL", value = var.redis_url },
        { name = "QDRANT_URL", value = var.qdrant_url },
        { name = "S3_BUCKET", value = var.s3_bucket },
        { name = "AWS_DEFAULT_REGION", value = data.aws_region.current.name },
        { name = "EMBEDDING_MODEL", value = var.embedding_model },
        { name = "USE_S3", value = "true" }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.name_prefix}/workers"
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "embed-worker"
        }
      }
    }
  ])

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Worker Services
# -----------------------------------------------------------------------------

resource "aws_ecs_service" "text_worker" {
  name            = "${var.name_prefix}-text-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.text_worker.arn
  desired_count   = var.text_worker_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = var.tags
}

resource "aws_ecs_service" "chunk_worker" {
  name            = "${var.name_prefix}-chunk-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.chunk_worker.arn
  desired_count   = var.chunk_worker_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = var.tags
}

resource "aws_ecs_service" "embed_worker" {
  name            = "${var.name_prefix}-embed-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.embed_worker.arn
  desired_count   = var.embed_worker_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "aws_region" "current" {}
