resource "null_resource" "cloud_build" {
  triggers = {
    files_hash = local.ui_files_hash
  }

  provisioner "local-exec" {
    command = <<EOT
      gcloud builds submit --project ${local.project_id} \
                           --tag ${var.region}-docker.pkg.dev/${local.project_id}/${var.repository_id}/${var.container_name}:latest \
                           ../ui/
    EOT
  }
  depends_on = [
    google_project_iam_member.compute_roles,
    google_project_iam_member.cloudbuild_roles
  ]
}

resource "kubectl_manifest" "lexitrail_ui_deployment" {
  yaml_body = templatefile("${path.module}/k8s_templates/deploy-deployment.yaml.tpl", {
    project_id     = local.project_id,
    container_name = var.container_name,
    repo_name      = var.repository_id,
    region         = var.region,
    ui_files_hash  = local.ui_files_hash
  })

  depends_on = [
    google_container_cluster.autopilot_cluster,
    null_resource.cloud_build
  ]
}



resource "kubectl_manifest" "lexitrail_ui_service" {
  yaml_body = templatefile("${path.module}/k8s_templates/deploy-service.yaml.tpl", {
    enable_https = var.enable_https,
    domain_name = local.domain_name
  })

  depends_on = [
    google_container_cluster.autopilot_cluster
  ]
}

resource "kubectl_manifest" "frontend_config" {
  count = var.enable_https ? 1 : 0
  
  yaml_body = templatefile("${path.module}/k8s_templates/frontend-config.yaml.tpl", {})

  depends_on = [
    google_container_cluster.autopilot_cluster
  ]
}

resource "kubectl_manifest" "frontend_frontend_config" {
  count = var.enable_https ? 1 : 0
  
  yaml_body = templatefile("${path.module}/k8s_templates/frontend-frontend-config.yaml.tpl", {})

  depends_on = [
    google_container_cluster.autopilot_cluster
  ]
}

resource "google_compute_global_address" "default" {
  count = var.enable_https ? 1 : 0
  name = "lexitrail-ip"
}

resource "kubectl_manifest" "certificate" {
  count = var.enable_https ? 1 : 0
  
  yaml_body = templatefile("${path.module}/k8s_templates/frontend-certificate.yaml.tpl", {
    domain_name = local.domain_name
  })

  depends_on = [
    google_container_cluster.autopilot_cluster
  ]
}

resource "kubectl_manifest" "ingress" {
  count = var.enable_https ? 1 : 0
  
  yaml_body = templatefile("${path.module}/k8s_templates/ingress.yaml.tpl", {
    domain_name = local.domain_name
  })

  depends_on = [
    kubectl_manifest.lexitrail_ui_service,
    kubectl_manifest.frontend_frontend_config[0]
  ]
}