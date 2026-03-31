output "coordinator_ip" {
  description = "Public static IP address of the coordinator VM"
  value       = google_compute_address.coordinator.address
}

output "coordinator_url" {
  description = "HTTPS base URL of the coordinator"
  value       = "https://${var.domain}"
}

output "health_url" {
  description = "Health check endpoint — returns HTTP 200 when coordinator is ready"
  value       = "https://${var.domain}/health"
}

output "headscale_url" {
  description = "Headscale control server URL used by Tailscale clients"
  value       = "https://${var.domain}"
}

output "api_url" {
  description = "TerraForge Server REST API base URL"
  value       = "https://${var.domain}/api/v1"
}

output "join_url" {
  description = "One-liner node join URL (implemented in Phase 2)"
  value       = "https://${var.domain}/join"
}

output "ssh_command" {
  description = "SSH command to access the coordinator for debugging"
  value       = "ssh ubuntu@${google_compute_address.coordinator.address}"
}

output "startup_log" {
  description = "Command to tail the startup log on the coordinator VM"
  value       = "ssh ubuntu@${google_compute_address.coordinator.address} tail -f /var/log/terraforge-startup.log"
}

output "docker_logs" {
  description = "Command to view all service logs on the coordinator"
  value       = "ssh ubuntu@${google_compute_address.coordinator.address} 'docker compose -f /opt/terraforge/docker-compose.yml logs -f'"
}

output "free_tier_compliance" {
  description = "Free tier compliance summary"
  value = {
    machine_type = "e2-micro (free)"
    disk_type    = "pd-standard (free)"
    disk_size_gb = "30 (maximum free)"
    region       = var.region
    monthly_cost = "$0.00 (within free tier)"
  }
}
