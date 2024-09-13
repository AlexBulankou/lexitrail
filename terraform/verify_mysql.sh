#!/bin/bash

# Exit script on any error
set -e

# Parameters
CLUSTER_NAME=lexitrail-cluster
REGION=us-central1
NAMESPACE=mysql
DBNAME=lexitraildb


# Load environment variables from the parent directory's .env file
if [ -f ../.env ]; then
    echo "Loading environment variables from ../.env file..."
    export $(grep -v '^#' ../.env | xargs)
else
    echo "Error: .env file not found in the parent directory!"
    exit 1
fi

# Check if db_root_password is set
if [ -z "$DB_ROOT_PASSWORD" ]; then
    echo "Error: db_root_password not set in the .env file!"
    exit 1
fi

# Authenticate with the GKE cluster
echo "Authenticating with the GKE cluster..."
gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION"

# Get the MySQL pod name
MYSQL_POD=$(kubectl get pods -n "$NAMESPACE" -l app=mysql -o jsonpath='{.items[0].metadata.name}')

echo "Found MySQL pod: $MYSQL_POD"

# Verify that the database exists
echo "Checking for databases..."
kubectl exec -n "$NAMESPACE" "$MYSQL_POD" -- mysql -u root -p"$DB_ROOT_PASSWORD" -e "SHOW DATABASES;"

# Verify tables in the database
echo "Checking for tables in $DBNAME..."
kubectl exec -n "$NAMESPACE" "$MYSQL_POD" -- mysql -u root -p"$DB_ROOT_PASSWORD" -e "USE $DBNAME; SHOW TABLES;"

# Verify that data exists in the wordsets table
echo "Checking data in wordsets table in $DBNAME..."
kubectl exec -n "$NAMESPACE" "$MYSQL_POD" -- mysql -u root -p"$DB_ROOT_PASSWORD" -e "USE $DBNAME; SELECT * FROM words LIMIT 55;"

echo "Verification completed!"