apiVersion: v1
kind: ServiceAccount
metadata:
  name: ${sa_name}
  namespace: ${namespace}
  labels:
    app: gmp-filter-guard
    managed-by: terraform
