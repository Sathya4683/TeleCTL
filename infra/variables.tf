variable "env" {
  description = "Deployment environment: dev, staging, prod. Used as a name suffix."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env must be one of dev, staging, prod."
  }
}

variable "project_name" {
  description = "Project prefix attached to every resource."
  type        = string
  default     = "wactl"
}

variable "region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-1"
}

variable "domain" {
  description = "Public domain for the webhook URL (optional). Empty = API Gateway default URL."
  type        = string
  default     = ""
}
