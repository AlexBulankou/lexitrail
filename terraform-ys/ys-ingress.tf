# WS2 (my-hermes#905) — Gateway API frontends for the Lexitrail UI + backend on
# ys-autopilot, REPLACING the incr-4b GKE Ingresses (converted 2026-07-01 at cutover).
#
# WHY Gateway API (not GKE Ingress): TLS comes from the Certificate Manager cert-map
# (ys-tls.tf). GKE's gce-class Ingress SILENTLY IGNORES the `networking.gke.io/certmap`
# annotation — it builds only a :80 HTTP frontend, never a :443 HTTPS target-proxy
# (certmap is Gateway-API-only). The Ingress form served HTTP (301 redirect) but HTTPS
# TLS-reset ("unexpected eof") on both ingresses — no target-https-proxy / :443
# forwarding rule ever got created. Converting to Gateway API + certmap: the certmap
# attaches to the Gateway's HTTPS listener, so HTTPS serves immediately from the
# pre-validated (DNS-auth) certs — no cutover HTTPS-down window (the whole point of
# certmap-before-cutover; HC2 #905 catch 2). Sister: ADM's ys-orch TLS uses the same
# pattern. Verified live: UI https 200, API https 200, HTTP→HTTPS 301.
#
# KEY certmap-on-Gateway rule: the HTTPS listener has NO `tls:` block — the
# `networking.gke.io/certmap` annotation handles termination. Including
# `tls: {mode: Terminate}` makes the CRD reject it ("certificateRefs or options must be
# specified when mode is Terminate"); certmap is mutually exclusive with
# tls.certificateRefs (per cloud.google.com/kubernetes-engine/docs/how-to/secure-gateway).
#
# Two Gateways (one per reserved static IP) preserve the pre-staged cutover A-records
# (UI 34.149.198.93 / backend 8.233.184.38). Each binds its reserved GLOBAL static IP
# via `spec.addresses: {type: NamedAddress, value: <ip-resource-name>}`. HTTP→HTTPS
# redirect is a per-Gateway HTTPRoute with a RequestRedirect filter on the :80 listener
# (replaces the old GKE FrontendConfig, which is Ingress-only).
#
# Health checks: derived from each Service's pod readiness probe (backend HTTP /health:80;
# UI TCP :3000 — workloads.tf, HC2 #16). The allow-lb-healthcheck NetworkPolicy
# (35.191.0.0/16 + 130.211.0.0/22) lets the GFE LB probes reach the pods.
#
# NOTE (state reconciliation): the live Gateways/HTTPRoutes were created out-of-band via
# kubectl at the #905 cutover. A `terraform apply` from this config will `kubectl apply`
# the same objects (server-side apply adopts them); the old Ingress + FrontendConfig
# resources are removed from this file, so apply also destroys their (already kubectl-
# deleted) state entries as no-ops. If kubectl_manifest errors on an already-existing
# object, `terraform import` the six objects first (2 Gateways + 4 HTTPRoutes).

# ===== UI Gateway (lexitrail.com → reserved IP google_compute_global_address.ui) =====
resource "kubectl_manifest" "ui_gateway" {
  yaml_body = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: Gateway
    metadata:
      name: lexitrail-ys-ui-gw
      namespace: ${var.namespace}
      annotations:
        networking.gke.io/certmap: ${google_certificate_manager_certificate_map.lexitrail.name}
    spec:
      gatewayClassName: gke-l7-global-external-managed
      addresses:
      - type: NamedAddress
        value: ${google_compute_global_address.ui.name}
      listeners:
      - name: https
        protocol: HTTPS
        port: 443
        hostname: lexitrail.com
        allowedRoutes: {namespaces: {from: Same}}
      - name: http
        protocol: HTTP
        port: 80
        hostname: lexitrail.com
        allowedRoutes: {namespaces: {from: Same}}
  YAML
}

resource "kubectl_manifest" "ui_route" {
  depends_on = [kubectl_manifest.ui_gateway]
  yaml_body  = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: HTTPRoute
    metadata:
      name: lexitrail-ys-ui-route
      namespace: ${var.namespace}
    spec:
      parentRefs:
      - name: lexitrail-ys-ui-gw
        sectionName: https
      hostnames: [lexitrail.com]
      rules:
      - backendRefs:
        - name: lexitrail-ui
          port: 80
  YAML
}

resource "kubectl_manifest" "ui_redirect" {
  depends_on = [kubectl_manifest.ui_gateway]
  yaml_body  = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: HTTPRoute
    metadata:
      name: lexitrail-ys-ui-redirect
      namespace: ${var.namespace}
    spec:
      parentRefs:
      - name: lexitrail-ys-ui-gw
        sectionName: http
      hostnames: [lexitrail.com]
      rules:
      - filters:
        - type: RequestRedirect
          requestRedirect: {scheme: https, statusCode: 301}
  YAML
}

# ===== Backend Gateway (api.lexitrail.com → reserved IP ...backend) =====
resource "kubectl_manifest" "backend_gateway" {
  yaml_body = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: Gateway
    metadata:
      name: lexitrail-ys-backend-gw
      namespace: ${var.namespace}
      annotations:
        networking.gke.io/certmap: ${google_certificate_manager_certificate_map.lexitrail.name}
    spec:
      gatewayClassName: gke-l7-global-external-managed
      addresses:
      - type: NamedAddress
        value: ${google_compute_global_address.backend.name}
      listeners:
      - name: https
        protocol: HTTPS
        port: 443
        hostname: api.lexitrail.com
        allowedRoutes: {namespaces: {from: Same}}
      - name: http
        protocol: HTTP
        port: 80
        hostname: api.lexitrail.com
        allowedRoutes: {namespaces: {from: Same}}
  YAML
}

resource "kubectl_manifest" "backend_route" {
  depends_on = [kubectl_manifest.backend_gateway]
  yaml_body  = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: HTTPRoute
    metadata:
      name: lexitrail-ys-backend-route
      namespace: ${var.namespace}
    spec:
      parentRefs:
      - name: lexitrail-ys-backend-gw
        sectionName: https
      hostnames: [api.lexitrail.com]
      rules:
      - backendRefs:
        - name: lexitrail-backend-service
          port: 80
  YAML
}

resource "kubectl_manifest" "backend_redirect" {
  depends_on = [kubectl_manifest.backend_gateway]
  yaml_body  = <<-YAML
    apiVersion: gateway.networking.k8s.io/v1
    kind: HTTPRoute
    metadata:
      name: lexitrail-ys-backend-redirect
      namespace: ${var.namespace}
    spec:
      parentRefs:
      - name: lexitrail-ys-backend-gw
        sectionName: http
      hostnames: [api.lexitrail.com]
      rules:
      - filters:
        - type: RequestRedirect
          requestRedirect: {scheme: https, statusCode: 301}
  YAML
}
