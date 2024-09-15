apiVersion: v1
kind: Service
metadata:
  name: lexitrail-backend-service
  namespace: ${backend_namespace}
spec:
  selector:
    app: lexitrail-backend
  ports:
    - protocol: TCP
      port: 5000
      targetPort: 5000
  type: ClusterIP  # Internal service type
