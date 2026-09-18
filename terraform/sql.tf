resource "kubectl_manifest" "mysql_namespace" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-namespace.yaml.tpl", {
    sql_namespace = var.sql_namespace,
    gsa_email     = google_service_account.lexitrail_sa.email
  })
  depends_on = [
    google_container_cluster.autopilot_cluster
  ]
}

resource "kubectl_manifest" "default_sa_annotation" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-default-service-account.yaml.tpl", {
    sql_namespace = var.sql_namespace,
    gsa_email     = google_service_account.lexitrail_sa.email
  })
  depends_on = [
    google_container_cluster.autopilot_cluster
  ]
}

resource "kubectl_manifest" "mysql_pvc" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-pvc.yaml.tpl", {
    sql_namespace = var.sql_namespace
  })
  depends_on = [google_container_cluster.autopilot_cluster, kubectl_manifest.mysql_namespace]
}

resource "kubectl_manifest" "mysql_service" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-service.yaml.tpl", {
    sql_namespace = var.sql_namespace
  })
  depends_on = [google_container_cluster.autopilot_cluster, kubectl_manifest.mysql_namespace]
}

resource "kubectl_manifest" "mysql_deployment" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-deployment.yaml.tpl", {
    sql_namespace    = var.sql_namespace,
    db_root_password = local.db_root_password,
    terraform_time   = timestamp()
  })
  depends_on = [google_container_cluster.autopilot_cluster, kubectl_manifest.mysql_pvc, kubectl_manifest.mysql_service]
}

resource "kubectl_manifest" "mysql_schema_and_data_job" {
  yaml_body = templatefile("${path.module}/k8s_templates/mysql-schema-and-data-job.yaml.tpl", {
    sql_namespace      = var.sql_namespace,
    db_root_password   = local.db_root_password,
    mysql_files_bucket = google_storage_bucket.mysql_files_bucket.name,
    db_name            = var.db_name,
    files_hash = sha1(join("", [
      filesha1("${path.module}/schema-tables.sql"),
      filesha1("${path.module}/schema-data.sql"),
      sha1(join("", [
        # issue-513 STEP 3. This list is EXACTLY the files the seed Job loads
        # (`storage.tf` uploads these two and no others; `schema-data.sql` has
        # two matching LOAD DATA statements). It used to be
        # `fileset(".../csv", "**/*")`, which is wrong in two directions:
        #
        #   __pycache__/*.pyc  gitignored + machine-local, and `fileset` reads
        #                      the FILESYSTEM, not git -- so two engineers at the
        #                      same commit computed DIFFERENT hashes, and running
        #                      the generator locally re-fired the Job.
        #   generate_words_*.py  a build-time input. Editing it re-fired the Job
        #   HSK[1-6].csv         even though neither file is ever loaded.
        #
        # Verified empirically, not assumed: `terraform console` on this
        # directory expands the old glob to 10 entries including the .pyc.
        #
        # 🔴 Keep this an EXPLICIT LIST, not a glob. A glob silently re-widens
        # when a file is added to csv/; this list reds `test_seed_hash_inputs_513.py`
        # instead, which is the outcome you want -- that test derives the
        # expected set from storage.tf, so adding a THIRD loaded CSV correctly
        # demands a change here.
        filesha1("${path.module}/csv/wordsets.csv"),
        filesha1("${path.module}/csv/words.csv"),
      ]))
    ]))
  })

  depends_on = [
    google_container_cluster.autopilot_cluster,
    kubectl_manifest.mysql_deployment,
    google_storage_bucket_object.schema_tables_sql,
    google_storage_bucket_object.schema_data_sql,
    google_storage_bucket_object.wordsets_csv,
    google_storage_bucket_object.words_csv,
    google_service_account_iam_member.lexitrail_workload_identity_binding_mysql,
    google_project_iam_member.bucket_access,
    null_resource.schema_tables_sql_trigger,
    null_resource.schema_data_sql_trigger,
    null_resource.csv_files_trigger
  ]
}

resource "kubectl_manifest" "adminer_deployment" {
  yaml_body = templatefile("${path.module}/k8s_templates/adminer-deployment.yaml.tpl", {
    sql_namespace = var.sql_namespace
  })
  depends_on = [google_container_cluster.autopilot_cluster, kubectl_manifest.mysql_namespace]
}

resource "kubectl_manifest" "adminer_service" {
  yaml_body = templatefile("${path.module}/k8s_templates/adminer-service.yaml.tpl", {
    sql_namespace = var.sql_namespace
  })
  depends_on = [google_container_cluster.autopilot_cluster, kubectl_manifest.mysql_namespace]
}