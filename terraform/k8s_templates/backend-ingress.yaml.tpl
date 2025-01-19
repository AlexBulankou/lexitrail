apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: lexitrail-backend-ingress
  namespace: ${backend_namespace}
  annotations:
    kubernetes.io/ingress.class: "gce"
    kubernetes.io/ingress.allow-http: "false"
spec:
  tls:
  - secretName: backend-tls-secret
  defaultBackend:
    service:
      name: lexitrail-backend-service
      port:
        number: 443