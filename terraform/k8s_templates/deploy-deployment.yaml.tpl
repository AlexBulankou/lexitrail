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
        image: ${region}-docker.pkg.dev/${project_id}/${repo_name}/${container_name}:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 3000
