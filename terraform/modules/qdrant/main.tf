# =============================================================================
# Qdrant Module - Vector Database on EC2
# =============================================================================

# -----------------------------------------------------------------------------
# Security Group
# -----------------------------------------------------------------------------

resource "aws_security_group" "qdrant" {
  name        = "${var.name_prefix}-qdrant-sg"
  description = "Security group for Qdrant"
  vpc_id      = var.vpc_id

  # Qdrant HTTP API
  ingress {
    from_port   = 6333
    to_port     = 6333
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # Qdrant gRPC
  ingress {
    from_port   = 6334
    to_port     = 6334
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  # SSH (optional, for debugging)
  ingress {
    from_port   = 22
    to_port     = 22
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
    Name = "${var.name_prefix}-qdrant-sg"
  })
}

# -----------------------------------------------------------------------------
# IAM Role for EC2
# -----------------------------------------------------------------------------

resource "aws_iam_role" "qdrant" {
  name = "${var.name_prefix}-qdrant-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "qdrant_ssm" {
  role       = aws_iam_role.qdrant.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "qdrant" {
  name = "${var.name_prefix}-qdrant-profile"
  role = aws_iam_role.qdrant.name
}

# -----------------------------------------------------------------------------
# EC2 Instance
# -----------------------------------------------------------------------------

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "qdrant" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [aws_security_group.qdrant.id]
  iam_instance_profile   = aws_iam_instance_profile.qdrant.name

  root_block_device {
    volume_size = var.volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = <<-EOF
    #!/bin/bash
    set -e

    # Install Docker
    yum update -y
    yum install -y docker
    systemctl start docker
    systemctl enable docker

    # Create data directory
    mkdir -p /var/lib/qdrant/storage

    # Run Qdrant
    docker run -d \
      --name qdrant \
      --restart always \
      -p 6333:6333 \
      -p 6334:6334 \
      -v /var/lib/qdrant/storage:/qdrant/storage \
      qdrant/qdrant:v1.7.0

    # Install CloudWatch agent for monitoring
    yum install -y amazon-cloudwatch-agent
  EOF

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-qdrant"
  })
}
