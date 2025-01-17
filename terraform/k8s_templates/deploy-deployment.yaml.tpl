apiVersion: apps/v1
kind: Deployment
metadata:
  name: lexitrail-ui-deployment
  annotations:
    terraform.io/change-cause: "${ui_files_hash}"
    cloud.google.com/gke-preemptible: "true"  # Enable preemptible workloads for cost savings
spec:
  replicas: 1  # Adjust based on workload; increase if traffic rises
  selector:
    matchLabels:
      app: lexitrail-ui
  template:
    metadata:
      labels:
        app: lexitrail-ui
      annotations:
        redeploy-hash: "${ui_files_hash}"
    spec:
      containers:
      - name: lexitrail-ui
        image: ${region}-docker.pkg.dev/${project_id}/${repo_name}/${container_name}:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 3000
        resources:  # Optimize resource requests and limits
          requests:
            memory: "128Mi"  # Lightweight UI typically doesn't need much memory
            cpu: "50m"       # Low CPU for minimal processing
          limits:
            memory: "256Mi"
            cpu: "100m"
