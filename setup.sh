#!/bin/bash

# Authenticate with Google Cloud
gcloud auth login
gcloud auth application-default login

# Get the project ID
PROJECT_ID=$(gcloud config get-value project)

# Replace PROJECT_ID placeholder in cloudbuild YAML files
# For macOS, we use `sed -i ''` to disable backup.
# For Linux, we use `sed -i` without a backup extension.
sed -i.bak "s/\$PROJECT_ID/$PROJECT_ID/g" ui/cloudbuild.yaml && rm ui/cloudbuild.yaml.bak
sed -i.bak "s/\${PROJECT_ID}/$PROJECT_ID/g" deploy.yaml && rm deploy.yaml.bak

# Set the bucket name, project ID, and region
FE_BUCKET_NAME="lexitrail-ui"
REGION="us-central1"  # Replace this with your preferred region

# Check if the bucket exists
if gsutil ls -b gs://$FE_BUCKET_NAME >/dev/null 2>&1; then
  echo "Bucket $FE_BUCKET_NAME already exists."
else
  echo "Creating bucket $FE_BUCKET_NAME..."
  gsutil mb -p $PROJECT_ID -l $REGION gs://$FE_BUCKET_NAME/
  echo "Bucket $FE_BUCKET_NAME created."
fi


# Get the project number
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")

# Cloud Build service account
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Granting Cloud Build service account full permissions to the bucket..."
roles=(
    "roles/storage.admin"
    "roles/logging.logWriter"
    "roles/artifactregistry.admin"
    "roles/viewer"
    "roles/storage.objectCreator"
    "roles/serviceusage.serviceUsageConsumer"
    "roles/cloudbuild.builds.editor"
)

for role in "${roles[@]}"; do
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${CLOUDBUILD_SA}" \
        --role="$role" \
        --condition=None

    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${COMPUTE_SA}" \
        --role="$role" \
        --condition=None
done





# Navigate to the frontend directory and submit the build using the custom Cloud Build YAML
cd ui/
gcloud builds submit --config=cloudbuild.yaml .

# Create a GKE Autopilot cluster
gcloud container clusters create-auto lexitrail-cluster --region=us-central1

# Set the cluster as current
gclioud container clusters get-credentials lexitrail-cluster --region=us-central1

# Deploy the application to the GKE cluster
kubectl apply -f ../deploy.yaml
