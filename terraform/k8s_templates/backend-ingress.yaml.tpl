apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: lexitrail-backend-ingress
  namespace: ${backend_namespace}
  annotations:
    kubernetes.io/ingress.class: "gce"
    kubernetes.io/ingress.allow-http: "false"
    kubernetes.io/ingress.global-static-ip-name: "lexitrail-backend-ip"
    networking.gke.io/managed-certificates: "backend-certificate"
spec:
  rules:
  - host: ${domain_name}
    http:
      paths:
      - path: /*
        pathType: ImplementationSpecific
        backend:
          service:
            name: lexitrail-backend-service
            port:
              number: 80