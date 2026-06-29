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
              command: ["/bin/sh", "-c"]
              args:
                - |
                  set -eu
                  echo "[gmp-filter-guard] re-applying cadvisor metric-drop filter to operatorconfig/config in ${namespace}"
                  kubectl patch operatorconfig config -n ${namespace} --type merge -p '${filter_patch}'
                  echo "[gmp-filter-guard] patch applied (idempotent). current filter.matchOneOf:"
                  kubectl get operatorconfig config -n ${namespace} -o jsonpath='{.collection.filter.matchOneOf}'
                  echo
              resources:
                requests:
                  cpu: "250m"
                  memory: "512Mi"
                limits:
                  memory: "512Mi"
