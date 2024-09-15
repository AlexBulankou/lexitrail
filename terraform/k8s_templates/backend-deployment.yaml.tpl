apiVersion: apps/v1
kind: Deployment
metadata:
  name: lexitrail-backend
  namespace: ${backend_namespace}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: lexitrail-backend
  template:
    metadata:
      labels:
        app: lexitrail-backend
    spec:
      containers:
      - name: lexitrail-backend
        image: ${region}-docker.pkg.dev/${project_id}/${repo_name}/${container_name}:latest
        ports:
        - containerPort: 5000
        env:
        - name: MYSQL_FILES_BUCKET
          valueFrom:
            configMapKeyRef:
              name: backend-config
              key: MYSQL_FILES_BUCKET
        - name: SQL_NAMESPACE
          valueFrom:
            configMapKeyRef:
              name: backend-config
              key: SQL_NAMESPACE
        - name: DATABASE_NAME
          valueFrom:
            configMapKeyRef:
              name: backend-config
              key: DATABASE_NAME
        - name: DB_ROOT_PASSWORD
          valueFrom:
            secretKeyRef:
              name: backend-secret
              key: DB_ROOT_PASSWORD
