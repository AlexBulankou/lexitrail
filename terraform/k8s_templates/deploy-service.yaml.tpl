apiVersion: v1
kind: Service
metadata:
  name: lexitrail-ui
  %{ if enable_https }
  annotations:
    cloud.google.com/neg: '{"ingress": true}'
    cloud.google.com/backend-config: '{"default": "lexitrail-frontend-config"}'
  %{ endif }
spec:
  type: ${enable_https ? "ClusterIP" : "LoadBalancer"}
  ports:
    - port: 80
      targetPort: 3000
      protocol: TCP
  selector:
    app: lexitrail-ui