# 1. Build and push container image
resource "null_resource" "backend_cloud_build" {
  triggers = {
    files_hash = local.backend_files_hash
  }

  provisioner "local-exec" {
    command = <<EOT
      gcloud builds submit --project ${local.project_id} \
                           --tag ${var.region}-docker.pkg.dev/${local.project_id}/${var.repository_id}/${var.backend_container_name}:latest \
                           ../backend/
    EOT
  }
  depends_on = [
    google_project_iam_member.compute_roles,
    google_project_iam_member.cloudbuild_roles,
    google_artifact_registry_repository.my_repo
  ]
}

# 2. Create namespace and configure service account
resource "kubectl_manifest" "backend_namespace" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-namespace.yaml.tpl", {
    backend_namespace = var.backend_namespace,
    gsa_email        = google_service_account.lexitrail_sa.email
  })
  depends_on = [
    google_container_cluster.autopilot_cluster
  ]
}

resource "kubectl_manifest" "backend_default_sa_annotation" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-default-service-account.yaml.tpl", {
    backend_namespace = var.backend_namespace,
    gsa_email        = google_service_account.lexitrail_sa.email
  })
  depends_on = [
    google_container_cluster.autopilot_cluster,
    kubectl_manifest.backend_namespace
  ]
}

# 3. Create ConfigMap and Secrets
resource "kubectl_manifest" "backend_configmap" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-configmap.yaml.tpl", {
    backend_namespace   = var.backend_namespace,
    mysql_files_bucket = google_storage_bucket.mysql_files_bucket.name,
    sql_namespace      = var.sql_namespace,
    database_name      = var.db_name,
    google_client_id   = local.google_client_id,
    project_id         = local.project_id,
    location           = var.region
  })
  depends_on = [
    google_container_cluster.autopilot_cluster,
    kubectl_manifest.backend_namespace,
    google_storage_bucket.mysql_files_bucket
  ]
}

resource "kubectl_manifest" "backend_secret" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-secret.yaml.tpl", {
    backend_namespace = var.backend_namespace,
    db_root_password = base64encode(local.db_root_password)
  })
  depends_on = [
    google_container_cluster.autopilot_cluster,
    kubectl_manifest.backend_namespace
  ]
}

# 4. Create static IP and certificate (only if HTTPS is enabled)
resource "google_compute_global_address" "backend_ip" {
  count = var.enable_https ? 1 : 0
  name  = "lexitrail-backend-ip"
}

resource "kubectl_manifest" "backend_certificate" {
  count = var.enable_https ? 1 : 0
  yaml_body = templatefile("${path.module}/k8s_templates/backend-certificate.yaml.tpl", {
    backend_namespace = var.backend_namespace
    domain_name      = "api.${local.domain_name}"
  })
  depends_on = [
    kubectl_manifest.backend_namespace
  ]
}

# 5. Deploy backend application
resource "kubectl_manifest" "backend_deployment" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-deployment.yaml.tpl", {
    project_id         = local.project_id,
    container_name     = var.backend_container_name,
    repo_name          = var.repository_id,
    region             = var.region,
    backend_namespace  = var.backend_namespace,
    backend_files_hash = local.backend_files_hash
  })
  depends_on = [
    google_container_cluster.autopilot_cluster,
    kubectl_manifest.backend_namespace,
    kubectl_manifest.backend_configmap,
    kubectl_manifest.backend_secret,
    null_resource.backend_cloud_build,
    google_service_account_iam_member.lexitrail_workload_identity_binding_backend
  ]
}

# 6. Create service and ingress
resource "kubectl_manifest" "backend_service" {
  yaml_body = templatefile("${path.module}/k8s_templates/backend-service.yaml.tpl", {
    backend_namespace = var.backend_namespace,
    enable_https     = var.enable_https
  })
  depends_on = [
    google_container_cluster.autopilot_cluster,
    kubectl_manifest.backend_namespace,
    kubectl_manifest.backend_deployment
  ]
}

resource "kubectl_manifest" "backend_ingress" {
  count = var.enable_https ? 1 : 0
  yaml_body = templatefile("${path.module}/k8s_templates/backend-ingress.yaml.tpl", {
    backend_namespace = var.backend_namespace,
    enable_https     = var.enable_https,
    domain_name      = "api.${local.domain_name}"
  })
  depends_on = [
    kubectl_manifest.backend_service,
    kubectl_manifest.backend_certificate[0]
  ]
}

# 7. Data sources and outputs
data "kubernetes_service" "backend_service" {
  count = var.enable_https ? 0 : 1
  metadata {
    name      = "lexitrail-backend-service"
    namespace = var.backend_namespace
  }
  depends_on = [
    kubectl_manifest.backend_service
  ]
}

data "kubernetes_ingress_v1" "backend_ingress" {
  count = var.enable_https ? 1 : 0
  metadata {
    name      = "lexitrail-backend-ingress"
    namespace = var.backend_namespace
  }
  depends_on = [
    kubectl_manifest.backend_ingress
  ]
}

output "backend_ip" {
  description = "Backend service IP address"
  value = var.enable_https ? (
    google_compute_global_address.backend_ip[0].address
  ) : (
    data.kubernetes_service.backend_service[0].status[0].load_balancer[0].ingress[0].ip
  )
}
