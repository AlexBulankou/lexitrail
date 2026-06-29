# AC1 (#7): durable in-cluster guard that re-applies the cadvisor metric-drop
# filter to the addon-owned OperatorConfig, so a managed-prometheus addon
# upgrade/reset can't silently drop the cost trim (issue #5 ask #1).
#
# Additive by design: this does NOT adopt/own the OperatorConfig (the GMP addon
# does). It only issues an idempotent merge-patch — re-applying when already
# correct is a no-op, and merge preserves the sibling externalLabels block.
apiVersion: batch/v1
kind: CronJob
metadata:
  name: gmp-filter-guard
  namespace: ${namespace}
  labels:
    app: gmp-filter-guard
    managed-by: terraform
spec:
  schedule: "${schedule}"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      ttlSecondsAfterFinished: 3600
      template:
        metadata:
          labels:
            app: gmp-filter-guard
        spec:
          serviceAccountName: ${sa_name}
          restartPolicy: OnFailure
          containers:
            - name: kubectl
              image: ${image}
              # registry.k8s.io/kubectl is DISTROLESS — no /bin/sh, so a
              # `["/bin/sh","-c"]` wrapper fails ("/bin/sh: no such file or
              # directory"). The image entrypoint is kubectl itself, so invoke it
              # directly via args: a single idempotent --type=merge patch. The
              # job's success/failure status is the signal; AC2 verify_gmp_filter.sh
              # provides external verification (the shell form's echo logging isn't
              # available without a shell, and isn't needed).
              args:
                - patch
                - operatorconfig
                - config
                - -n
                - ${namespace}
                - --type
                - merge
                - -p
                - '${filter_patch}'
              resources:
                requests:
                  cpu: "250m"
                  memory: "512Mi"
                limits:
                  memory: "512Mi"
