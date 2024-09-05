apiVersion: batch/v1
kind: Job
metadata:
  name: mysql-schema-and-data-job
  namespace: ${sql_namespace}
spec:
  template:
    spec:
      containers:
      - name: mysql-schema-and-data
        image: mysql:8.0
        command: ["/bin/sh", "-c"]
        args:
          - "mysql -h mysql -u root -p${db_root_password} < /sql/schema.sql"
        volumeMounts:
        - name: sql-script
          mountPath: /sql  # Mounting SQL script
        - name: csv-files
          mountPath: /csv  # Mounting CSV directory where wordsets.csv and words.csv reside
      restartPolicy: OnFailure
      volumes:
      - name: sql-script
        hostPath:
          path: ${sql_script_path}  # Path to static SQL file (schema.sql)
      - name: csv-files
        hostPath:
          path: ${csv_files_path}  # Path to the CSV files (csv/wordsets.csv, csv/words.csv)
