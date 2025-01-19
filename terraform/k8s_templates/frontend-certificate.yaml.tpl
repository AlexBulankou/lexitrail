apiVersion: networking.gke.io/v1
kind: ManagedCertificate
metadata:
  name: lexitrail-certificate
spec:
  domains:
    - ${domain_name}