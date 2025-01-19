apiVersion: networking.gke.io/v1
kind: ManagedCertificate
metadata:
  name: backend-certificate
  namespace: ${backend_namespace}
spec:
  domains:
    - ${domain_name}