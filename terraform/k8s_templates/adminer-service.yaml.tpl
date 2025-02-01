apiVersion: v1
kind: Service
metadata:
  name: adminer-service
  namespace: ${sql_namespace}
spec:
  selector:
    app: adminer
  ports:
  - port: 80
    targetPort: 8080
  type: LoadBalancer