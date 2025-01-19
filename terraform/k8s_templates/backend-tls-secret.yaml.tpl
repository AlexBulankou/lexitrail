apiVersion: v1
kind: Secret
metadata:
  name: backend-tls-secret
  namespace: ${backend_namespace}
type: kubernetes.io/tls
data:
  tls.crt: ${tls_cert}
  tls.key: ${tls_key} 