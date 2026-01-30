# =============================================================================
# RDS Module - PostgreSQL Database
# =============================================================================

# -----------------------------------------------------------------------------
# Security Group
# -----------------------------------------------------------------------------

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds-sg"
  description = "Security group for RDS PostgreSQL"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-rds-sg"
  })
}

# -----------------------------------------------------------------------------
# Subnet Group
# -----------------------------------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-rds-subnet-group"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-rds-subnet-group"
  })
}

# -----------------------------------------------------------------------------
# Parameter Group
# -----------------------------------------------------------------------------

resource "aws_db_parameter_group" "main" {
  name   = "${var.name_prefix}-rds-pg"
  family = "postgres15"

  parameter {
    name  = "log_connections"
    value = "1"
  }

  parameter {
    name  = "log_disconnections"
    value = "1"
  }

  tags = var.tags
}

# -----------------------------------------------------------------------------
# RDS Instance
# -----------------------------------------------------------------------------

resource "aws_db_instance" "main" {
  identifier = "${var.name_prefix}-postgres"

  engine               = "postgres"
  engine_version       = "15"
  instance_class       = var.db_instance_class
  allocated_storage    = var.allocated_storage
  storage_type         = "gp3"
  storage_encrypted    = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.main.name

  multi_az               = false  # Set to true for production
  publicly_accessible    = false
  skip_final_snapshot    = true   # Set to false for production
  deletion_protection    = false  # Set to true for production

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  performance_insights_enabled = true
  monitoring_interval          = 60
  monitoring_role_arn          = aws_iam_role.rds_monitoring.arn

  tags = var.tags
}

# -----------------------------------------------------------------------------
# IAM Role for Enhanced Monitoring
# -----------------------------------------------------------------------------

resource "aws_iam_role" "rds_monitoring" {
  name = "${var.name_prefix}-rds-monitoring"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "monitoring.rds.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
