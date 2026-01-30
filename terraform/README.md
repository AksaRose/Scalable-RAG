# Terraform Infrastructure for Scalable RAG

This directory contains Terraform scripts to deploy the Scalable RAG Ingestion Pipeline on AWS.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                    AWS                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                              VPC                                     │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │   │
│  │  │  Public Subnet  │  │  Public Subnet  │  │  Public Subnet  │     │   │
│  │  │     (AZ-a)      │  │     (AZ-b)      │  │     (AZ-c)      │     │   │
│  │  │   ┌─────────┐   │  │   ┌─────────┐   │  │                 │     │   │
│  │  │   │   ALB   │   │  │   │   NAT   │   │  │                 │     │   │
│  │  │   └─────────┘   │  │   └─────────┘   │  │                 │     │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘     │   │
│  │                                                                     │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │   │
│  │  │ Private Subnet  │  │ Private Subnet  │  │ Private Subnet  │     │   │
│  │  │     (AZ-a)      │  │     (AZ-b)      │  │     (AZ-c)      │     │   │
│  │  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │     │   │
│  │  │ │  ECS API    │ │  │ │ ECS Workers │ │  │ │   Qdrant    │ │     │   │
│  │  │ │  (Fargate)  │ │  │ │  (Fargate)  │ │  │ │   (EC2)     │ │     │   │
│  │  │ └─────────────┘ │  │ └─────────────┘ │  │ └─────────────┘ │     │   │
│  │  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │                 │     │   │
│  │  │ │    RDS      │ │  │ │ ElastiCache │ │  │                 │     │   │
│  │  │ │ PostgreSQL  │ │  │ │   Redis     │ │  │                 │     │   │
│  │  │ └─────────────┘ │  │ └─────────────┘ │  │                 │     │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘     │   │
│  │                                                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                         S3 Bucket                            │   │   │
│  │  │                    (Document Storage)                        │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │      ECR        │  │   CloudWatch    │  │  Secrets Mgr    │            │
│  │  (Container     │  │   (Logs &       │  │  (API Keys &    │            │
│  │   Registry)     │  │    Metrics)     │  │   Credentials)  │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **Terraform** >= 1.0.0
3. **Docker** for building and pushing images

## Quick Start

### 1. Initialize Terraform

```bash
cd terraform
terraform init
```

### 2. Configure Variables

Copy the example variables file and customize:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:
- `project_name`: Your project name
- `environment`: dev/staging/prod
- `aws_region`: AWS region
- `db_password`: RDS password

### 3. Plan and Apply

```bash
# Review changes
terraform plan

# Apply infrastructure
terraform apply
```

### 4. Build and Push Docker Images

After infrastructure is created:

```bash
# Get ECR login
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com

# Build and push API image
docker build -t scalable-rag-api -f api/Dockerfile .
docker tag scalable-rag-api:latest <account>.dkr.ecr.<region>.amazonaws.com/scalable-rag-api:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/scalable-rag-api:latest

# Build and push worker image
docker build -t scalable-rag-worker -f workers/Dockerfile .
docker tag scalable-rag-worker:latest <account>.dkr.ecr.<region>.amazonaws.com/scalable-rag-worker:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/scalable-rag-worker:latest
```

### 5. Access the Service

After deployment, Terraform outputs will show:
- ALB DNS name for API access
- RDS endpoint
- Redis endpoint
- S3 bucket name

## Estimated Costs

| Service | Instance Type | Monthly Cost (est.) |
|---------|--------------|---------------------|
| ECS Fargate (API) | 0.5 vCPU, 1GB | ~$15 |
| ECS Fargate (Workers x3) | 1 vCPU, 2GB | ~$90 |
| RDS PostgreSQL | db.t3.micro | ~$15 |
| ElastiCache Redis | cache.t3.micro | ~$12 |
| EC2 (Qdrant) | t3.medium | ~$30 |
| ALB | - | ~$20 |
| S3 | - | ~$5 |
| **Total** | | **~$187/month** |

*Costs are estimates for development/small workloads. Production will be higher.*

## Scaling

To scale workers, modify `terraform.tfvars`:

```hcl
# Increase worker count
text_worker_count  = 3
chunk_worker_count = 2
embed_worker_count = 5
```

Then apply:

```bash
terraform apply
```

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

⚠️ **Warning**: This will delete all data including the database and S3 bucket contents.

## Files Structure

```
terraform/
├── main.tf              # Main configuration
├── variables.tf         # Input variables
├── outputs.tf           # Output values
├── terraform.tfvars.example  # Example variables
├── modules/
│   ├── vpc/            # VPC, subnets, security groups
│   ├── ecs/            # ECS cluster, services, tasks
│   ├── rds/            # PostgreSQL database
│   ├── elasticache/    # Redis cache
│   ├── s3/             # S3 bucket
│   ├── qdrant/         # Qdrant vector database
│   └── alb/            # Application Load Balancer
└── README.md           # This file
```
