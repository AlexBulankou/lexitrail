apiVersion: v1
kind: Service
metadata:
  name: lexitrail-backend-service
  namespace: ${backend_namespace}
  annotations:
    cloud.google.com/backend-config: '{"default": "lexitrail-backend-config"}'
    cloud.google.com/neg: '{"ingress": true}'  # Add NEG support
spec:
  selector:
    app: lexitrail-backend
  ports:
    - protocol: TCP
      port: 443
      targetPort: 80
      name: https  # Name the port for clarity
  type: ClusterIP