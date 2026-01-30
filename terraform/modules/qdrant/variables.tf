# Qdrant Module Variables

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID for Qdrant instance"
  type        = string
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to access Qdrant"
  type        = list(string)
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
}

variable "volume_size" {
  description = "EBS volume size in GB"
  type        = number
}

variable "tags" {
  description = "Tags"
  type        = map(string)
  default     = {}
}
