terraform {
  required_version = ">= 1.8.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# ── Static External IP ─────────────────────────────────────────────
# Free while attached to a running instance in a free-tier region.
resource "google_compute_address" "coordinator" {
  name   = "${var.name}-ip"
  region = var.region
}

# ── Firewall: Web (80 + 443) ───────────────────────────────────────
# Port 80:  ACME HTTP-01 challenge for Let's Encrypt
# Port 443: Headscale gRPC/HTTPS + TerraForge Server
resource "google_compute_firewall" "allow_web" {
  name    = "${var.name}-allow-web"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
  allow {
    protocol = "udp"
    ports    = ["443"] # HTTP/3 QUIC
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = [var.name]
  description   = "TerraForge coordinator: ACME + Headscale/HTTPS ingress only"
}

# ── Firewall: STUN/DERP relay ──────────────────────────────────────
resource "google_compute_firewall" "allow_stun" {
  name    = "${var.name}-allow-stun"
  network = "default"

  allow {
    protocol = "udp"
    ports    = ["3478"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = [var.name]
  description   = "TerraForge coordinator: STUN/DERP relay for WireGuard NAT traversal"
}

# ── Firewall: SSH (restricted, disable after first deploy) ─────────
resource "google_compute_firewall" "allow_ssh" {
  count   = var.allow_ssh ? 1 : 0
  name    = "${var.name}-allow-ssh"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.ssh_source_ranges
  target_tags   = [var.name]
  description   = "TerraForge coordinator: SSH access — restrict to your IP in production"
}

# ── Coordinator VM ─────────────────────────────────────────────────
# FREE TIER COMPLIANCE RULES (never change without understanding cost implications):
#   machine_type = "e2-micro"    ONLY type eligible for free tier
#   disk type    = "pd-standard" pd-balanced and pd-ssd are NOT free
#   disk size    = 30 GB maximum
#   region       = us-central1 / us-west1 / us-east1 only
resource "google_compute_instance" "coordinator" {
  name         = var.name
  machine_type = "e2-micro"
  zone         = var.zone
  tags         = [var.name]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 30            # Maximum allowed for free tier
      type  = "pd-standard" # MUST be pd-standard — pd-balanced is NOT free
    }
  }

  network_interface {
    network = "default"
    access_config {
      nat_ip = google_compute_address.coordinator.address
    }
  }

  # Minimal scopes — no broad IAM permissions per free tier compliance rules
  service_account {
    scopes = ["logging-write", "monitoring-write"]
  }

  metadata = {
    startup-script       = file("${path.module}/cloud_init.sh")
    tf-domain            = var.domain
    tf-admin-token       = var.admin_token
    tf-acme-email        = var.acme_email
    tf-headscale-version = var.headscale_version
    tf-server-version    = var.tf_server_version
  }
}

# ── Optional: Cloud DNS A record ───────────────────────────────────
resource "google_dns_record_set" "coordinator" {
  count        = var.dns_zone_name != "" ? 1 : 0
  name         = "${var.domain}."
  type         = "A"
  ttl          = 300
  managed_zone = var.dns_zone_name
  rrdatas      = [google_compute_address.coordinator.address]
}

# ── Post-deploy health check ───────────────────────────────────────
resource "null_resource" "health_check" {
  count      = var.run_health_check ? 1 : 0
  depends_on = [google_compute_instance.coordinator]

  triggers = {
    instance_id = google_compute_instance.coordinator.id
  }

  provisioner "local-exec" {
    command     = <<-EOT
      echo "Waiting for coordinator to become healthy at https://${var.domain}/health"
      for i in $(seq 1 40); do
        STATUS=$(curl -sk -o /dev/null -w "%{http_code}" https://${var.domain}/health 2>/dev/null || echo "000")
        if [ "$STATUS" = "200" ]; then
          echo "✓ Coordinator healthy (attempt $i)"
          exit 0
        fi
        echo "  Attempt $i/40 — HTTP $STATUS — waiting 15s..."
        sleep 15
      done
      echo "✗ Timed out. SSH in and check: tail -f /var/log/terraforge-startup.log"
      exit 1
    EOT
    interpreter = ["bash", "-c"]
  }
}
