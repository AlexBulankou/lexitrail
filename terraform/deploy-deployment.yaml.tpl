apiVersion: apps/v1
kind: Deployment
metadata:
  name: lexitrail-ui-deployment
spec:
  replicas: 2
  selector:
    matchLabels:
      app: lexitrail-ui
  template:
    metadata:
      labels:
        app: lexitrail-ui
    spec:
      containers:
      - name: lexitrail-ui
        image: gcr.io/${project_id}/${container_name}:latest
        ports:
        - containerPort: 3000
