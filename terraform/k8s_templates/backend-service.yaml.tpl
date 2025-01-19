apiVersion: v1
kind: Service
metadata:
  name: lexitrail-backend-service
  namespace: ${backend_namespace}
  %{ if enable_https }
  annotations:
    cloud.google.com/neg: '{"ingress": true}'
  %{ endif }
spec:
  type: ${enable_https ? "ClusterIP" : "LoadBalancer"}
  ports:
    - port: 80
      targetPort: 80
      protocol: TCP
  selector:
    app: lexitrail-backend