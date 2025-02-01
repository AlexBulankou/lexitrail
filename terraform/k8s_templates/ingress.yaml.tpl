apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: lexitrail-ingress
  annotations:
    kubernetes.io/ingress.class: "gce"
    kubernetes.io/ingress.global-static-ip-name: "lexitrail-ip"
    networking.gke.io/managed-certificates: "lexitrail-certificate"
    networking.gke.io/v1beta1.FrontendConfig: "lexitrail-frontend-frontend-config"
    kubernetes.io/ingress.allow-http: "true"
spec:
  rules:
  - http:
      paths:
      - path: /*
        pathType: ImplementationSpecific
        backend:
          service:
            name: lexitrail-ui
            port:
              number: 80