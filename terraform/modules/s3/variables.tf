# S3 Module Variables

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "tags" {
  description = "Tags"
  type        = map(string)
  default     = {}
}
