apiVersion: batch/v1
kind: Job
metadata:
  name: mysql-schema-and-data-job
  namespace: ${sql_namespace}
spec:
  template:
    spec:
      serviceAccountName: default # Add this line! Replace 'default' if needed
      containers:
      - name: mysql-schema-and-data
        image: google/cloud-sdk:slim  # This image includes gsutil
        command: ["/bin/sh", "-c"]
        args:
          - |
            echo "Installing MariaDB client (compatible with MySQL)...";
            apt-get update && apt-get install -y mariadb-client;
            echo "Downloading SQL and CSV files from GCS...";
            gsutil cp gs://${mysql_files_bucket}/schema.sql /mnt/sql/schema.sql;
            gsutil cp gs://${mysql_files_bucket}/csv/wordsets.csv /mnt/csv/wordsets.csv;
            gsutil cp gs://${mysql_files_bucket}/csv/words.csv /mnt/csv/words.csv;
            echo "Running MySQL script...";
            mysql --local-infile=1 -h mysql -u root -p${db_root_password} < /mnt/sql/schema.sql;
        volumeMounts:
        - name: sql-volume
          mountPath: /mnt/sql
        - name: csv-volume
          mountPath: /mnt/csv
      restartPolicy: OnFailure
      volumes:
      - name: sql-volume
        emptyDir: {}  # Temporary storage for SQL file
      - name: csv-volume
        emptyDir: {}  # Temporary storage for CSV files
