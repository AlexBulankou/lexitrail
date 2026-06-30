# WS2 increment 4 (my-hermes#905) — TLS foundation for the Lexitrail ingresses on
# ys-autopilot. The GKE Ingresses (incr-4b, ys-ingress.tf) create a Google Cloud
# Load Balancer in yojowa-claw, so the static IPs + SSL certs live in claw too.
#
# WHY Certificate Manager + DNS-authorization (not GKE ManagedCertificate, which
# the live cluster uses): a GKE ManagedCertificate only begins provisioning AFTER
# the domain's A-record points at the new LB — i.e. it can't go Active until the
# cutover A-flip, leaving an HTTPS-down window of 15-60min on a LIVE service
# (HC2 #905 catch 2). Certificate Manager with DNS-authorization validates domain
# ownership via a TXT record at the DNS provider (TopDNS), INDEPENDENT of where the
# A-record points — so the cert can be ACTIVE before cutover and HTTPS works the
# instant traffic flips. The one cost: a one-time TopDNS TXT record per domain
# (operator/Alex action — TopDNS is the registrar, not Cloud DNS; see the
# `dns_auth_*` outputs + my-hermes#905).

# Declared for cutover-reproducibility (enabled live already; disable_on_destroy
# false so a future destroy of this stack doesn't yank the API from other users).
resource "google_project_service" "certmanager" {
  project            = var.ys_project_id
  service            = "certificatemanager.googleapis.com"
  disable_on_destroy = false
}

# ---------- Global static IPs (claw) — one per ingress ----------
resource "google_compute_global_address" "ui" {
  project = var.ys_project_id
  name    = "lexitrail-ys-ui-ip"
}

resource "google_compute_global_address" "backend" {
  project = var.ys_project_id
  name    = "lexitrail-ys-backend-ip"
}

# ---------- DNS authorizations — produce the TopDNS TXT records ----------
# Each emits a CNAME-style TXT (`dns_resource_record`) the operator adds at TopDNS;
# once live, the cert below provisions without touching A-records.
resource "google_certificate_manager_dns_authorization" "ui" {
  project = var.ys_project_id
  name    = "lexitrail-ys-ui-dnsauth"
  domain  = "lexitrail.com"
}

resource "google_certificate_manager_dns_authorization" "backend" {
  project = var.ys_project_id
  name    = "lexitrail-ys-backend-dnsauth"
  domain  = "api.lexitrail.com"
}

# ---------- DNS-authorized managed certificates ----------
resource "google_certificate_manager_certificate" "ui" {
  project = var.ys_project_id
  name    = "lexitrail-ys-ui-cert"
  managed {
    domains            = ["lexitrail.com"]
    dns_authorizations = [google_certificate_manager_dns_authorization.ui.id]
  }
}

resource "google_certificate_manager_certificate" "backend" {
  project = var.ys_project_id
  name    = "lexitrail-ys-backend-cert"
  managed {
    domains            = ["api.lexitrail.com"]
    dns_authorizations = [google_certificate_manager_dns_authorization.backend.id]
  }
}

# ---------- Certificate map (referenced by the GKE Ingresses via the
#            networking.gke.io/certmap annotation in incr-4b) ----------
resource "google_certificate_manager_certificate_map" "lexitrail" {
  project = var.ys_project_id
  name    = "lexitrail-ys-certmap"
}

resource "google_certificate_manager_certificate_map_entry" "ui" {
  project      = var.ys_project_id
  name         = "lexitrail-ys-ui-entry"
  map          = google_certificate_manager_certificate_map.lexitrail.name
  certificates = [google_certificate_manager_certificate.ui.id]
  hostname     = "lexitrail.com"
}

resource "google_certificate_manager_certificate_map_entry" "backend" {
  project      = var.ys_project_id
  name         = "lexitrail-ys-backend-entry"
  map          = google_certificate_manager_certificate_map.lexitrail.name
  certificates = [google_certificate_manager_certificate.backend.id]
  hostname     = "api.lexitrail.com"
}

# ---------- Outputs: the exact TXT records for the operator to add at TopDNS ----------
# `terraform output -json dns_auth_records` after apply → hand these to Alex.
output "dns_auth_records" {
  description = "TXT records to add at TopDNS so the Cert Manager certs provision BEFORE cutover."
  value = {
    "lexitrail.com"     = google_certificate_manager_dns_authorization.ui.dns_resource_record
    "api.lexitrail.com" = google_certificate_manager_dns_authorization.backend.dns_resource_record
  }
}

output "ingress_static_ips" {
  description = "Static IPs the cutover A-records will point at (handed to Alex at the incr-6 cutover, not now)."
  value = {
    "lexitrail.com"     = google_compute_global_address.ui.address
    "api.lexitrail.com" = google_compute_global_address.backend.address
  }
}
