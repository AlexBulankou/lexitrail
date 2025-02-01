apiVersion: apps/v1
kind: Deployment
metadata:
  name: adminer
  namespace: ${sql_namespace}
spec:
  selector:
    matchLabels:
      app: adminer
  template:
    metadata:
      labels:
        app: adminer
    spec:
      containers:
      - name: adminer
        image: adminer:latest
        ports:
        - containerPort: 8080
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 100m
            memory: 128Mi
        env:
        - name: ADMINER_DEFAULT_SERVER
          value: mysql 