apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mysql
  namespace: ${sql_namespace}
spec:
  serviceName: mysql
  replicas: 1
  selector:
    matchLabels:
      app: mysql
  template:
    metadata:
      labels:
        app: mysql
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: cloud.google.com/gke-spot
                operator: In
                values:
                - "true"
      containers:
      - name: mysql
        image: mysql:8.0
        args:
        - "--local-infile=1"  # Enable local infile on the server
        env:
        - name: MYSQL_ROOT_PASSWORD
          value: "${db_root_password}"
        ports:
        - containerPort: 3306
          name: mysql
        volumeMounts:
        - name: mysql-persistent-storage
          mountPath: /var/lib/mysql
        readinessProbe:
          exec:
            command:
            - mysqladmin
            - ping
            - "-h"
            - "127.0.0.1"
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          exec:
            command:
            - mysqladmin
            - ping
            - "-h"
            - "127.0.0.1"
          initialDelaySeconds: 30
          periodSeconds: 10
        resources:
          requests:
            memory: "512Mi"
            cpu: "200m"
          limits:
            memory: "1024Mi"
            cpu: "400m"
  volumeClaimTemplates:
  - metadata:
      name: mysql-persistent-storage
    spec:
      accessModes:
      - ReadWriteOnce
      resources:
        requests:
          storage: 5Gi
      storageClassName: standard
