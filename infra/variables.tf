variable "env" {
  description = "Deployment environment: dev, staging, prod. Used as a name suffix."
  type        = string
  default     = "dev"
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

# ─── Telegram bot secrets ────────────────────────────────────────────
# The bot stores these on the Lambda / EC2 instance as plain env vars
# rather than SSM Parameter Store (simpler + free-tier friendly).
# Pass them at apply time:
#   terraform apply \
#     -var "telegram_bot_token=123456:ABC..." \
#     -var "gemini_api_key=AIza..." \
#     -var "telegram_webhook_secret_token=$(openssl rand -hex 32)"
variable "telegram_bot_token" {
  description = "Telegram bot token from @BotFather. Empty = webhook Lambda will fail at startup."
  type        = string
  sensitive   = true
  default     = ""
}

variable "telegram_webhook_secret_token" {
  description = "Optional shared secret verified against X-Telegram-Bot-Api-Secret-Token header. Empty = no verification."
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Gemini API key for /pdf-audio TTS. Empty = the command will reject requests."
  type        = string
  sensitive   = true
  default     = ""
}
