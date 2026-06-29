# Namespaced Role: the minimum to re-apply the cadvisor metric-drop filter.
# get/patch on the single OperatorConfig named "config" in gmp-public — no
# create/delete, no other resources. Scoped to gmp-public where the addon-owned
# OperatorConfig lives.
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ${role_name}
  namespace: ${namespace}
  labels:
    app: gmp-filter-guard
    managed-by: terraform
rules:
  - apiGroups: ["monitoring.googleapis.com"]
    resources: ["operatorconfigs"]
    resourceNames: ["config"]
    verbs: ["get", "patch"]
