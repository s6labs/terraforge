variable "project_id" {
  description = "GCP project ID where the coordinator will be deployed"
  type        = string
}

variable "domain" {
  description = <<-EOT
    Fully-qualified domain name for the coordinator.
    Headscale requires a real domain for Let's Encrypt TLS.
    Options (PRD Q1):
      - Buy a domain and add an A record after Terraform creates the IP
      - Free: yourname.duckdns.org (update after Terraform creates the static IP)
      - Self-signed: set run_health_check=false and skip TLS
  EOT
  type        = string
}

variable "admin_token" {
  description = "Admin token for TerraForge Server API and dashboard auth. Generate: openssl rand -hex 32"
  type        = string
  sensitive   = true
}

variable "acme_email" {
  description = "Email address for Let's Encrypt certificate issuance and expiry notifications"
  type        = string
}

variable "name" {
  description = "Resource name prefix applied to VM, firewall rules, and static IP"
  type        = string
  default     = "terraforge-coordinator"
}

variable "region" {
  description = "GCP region. MUST be us-central1, us-west1, or us-east1 for Free Tier."
  type        = string
  default     = "us-central1"

  validation {
    condition     = contains(["us-central1", "us-west1", "us-east1"], var.region)
    error_message = "Region must be us-central1, us-west1, or us-east1 for GCP Free Tier compliance."
  }
}

variable "zone" {
  description = "GCP zone within the selected region"
  type        = string
  default     = "us-central1-a"
}

variable "headscale_version" {
  description = "Headscale Docker image tag to deploy"
  type        = string
  default     = "0.23.0"
}

variable "tf_server_version" {
  description = "TerraForge Server Docker image tag"
  type        = string
  default     = "latest"
}

variable "dns_zone_name" {
  description = "Cloud DNS managed zone name. Leave empty to skip DNS record creation."
  type        = string
  default     = ""
}

variable "allow_ssh" {
  description = "Create a firewall rule allowing SSH. Disable after initial provisioning."
  type        = bool
  default     = true
}

variable "ssh_source_ranges" {
  description = "CIDR ranges allowed to SSH. Restrict to your IP in production."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "run_health_check" {
  description = "Poll https://DOMAIN/health after apply until it returns 200"
  type        = bool
  default     = true
}
