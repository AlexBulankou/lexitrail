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
      port: 5001
      targetPort: 5001
  type: LoadBalancer  # Expose service externally
