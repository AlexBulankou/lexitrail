apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: ${role_name}
  namespace: ${namespace}
  labels:
    app: gmp-filter-guard
    managed-by: terraform
subjects:
  - kind: ServiceAccount
    name: ${sa_name}
    namespace: ${namespace}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: ${role_name}
