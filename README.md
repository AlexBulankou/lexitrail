# Lexitrail

<img width="1633" alt="image" src="https://github.com/user-attachments/assets/2db50d59-624c-4d0f-a278-e8f629d354df">

A vocabulary learning platform with a React frontend and Flask backend.

## Prerequisites
- Python 3.x
- Node.js
- Google Cloud SDK
- Terraform

## Quick Start

### Backend
This project uses Python 3.9 to maintain consistency with our production environment.

1. Install Python 3.9:
   ```bash
   # macOS with Homebrew
   brew install python@3.9
   
   # Ubuntu/Debian
   sudo add-apt-repository ppa:deadsnakes/ppa
   sudo apt update
   sudo apt install python3.9 python3.9-venv
   ```

2. Set up and activate a virtual environment:
   ```bash
   cd backend
   python3.9 -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Configure environment variables in `.env`:
   ```
   DATABASE_URL=mysql://username:password@localhost/dbname
   SECRET_KEY=<your-secret-key>
   ```

4. Start MySQL connection and run the backend:
   ```bash
   gcloud container clusters get-credentials lexitrail-cluster --location=us-central1
   kubectl port-forward svc/mysql 3306:3306 -n mysql
   python run.py
   ```

   Alternatively, test with Docker to match production environment:
   ```bash
   docker build -t lexitrail-backend .
   docker run -p 80:80 --env-file .env lexitrail-backend
   ```

### Frontend
1. Install dependencies and start the server:
   ```bash
   cd ui/
   npm install
   npm start
   ```

## Deployment
```bash
cd terraform/
gcloud auth login
terraform apply
```

## Configuration

### Environment Variables
- `DATABASE_URL`: MySQL connection string
- `SECRET_KEY`: Flask secret key
- `PROJECT_ID`: Google Cloud project ID
- `GOOGLE_CLIENT_ID`: OAuth client ID

### OAuth Setup
1. Configure consent screen in Google Cloud Console.
2. Create OAuth client ID and update `.env`.

## API Overview
- **Users**: Create, retrieve, update, delete users.
- **Wordsets**: Manage collections of words.
- **Words**: CRUD operations for vocabulary words.

## Testing
Run tests with:
```bash
cd backend
pytest
```

## Contributing
Contributions are welcome! Please fork the repository and submit a pull request with your changes. Ensure your code follows the project's coding standards and includes appropriate tests.

# Architecture
The Lexitrail application is built using React, a popular JavaScript library for building user interfaces. The frontend is structured into components, each responsible for specific parts of the UI. The game logic is handled in React components, which manage state and user interactions.

# Running UI locally

Create .env file inside /ui/ folder. This file will not be saved to git.

```
cd ui/
npm install
npm start
```

# Deploy to cloud
```
cd terraform/
gcloud auth login
gcloud auth application-default login
terraform apply
```


## Handling Deleted Kubernetes Clusters: Pruning Resources from Terraform State

If a Kubernetes cluster is deleted outside of Terraform, its associated Kubernetes resources (e.g., `kubectl_manifest`, `helm_release`) may still remain in the `terraform.tfstate` file. These residual state entries can cause issues when attempting to redeploy the cluster.

To resolve this, you need to **prune** the orphaned resources from the state file. Follow these steps:

1. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Run the state pruning script:
   ```bash
   python state_pruner.py
   ```

The `state_pruner.py` script automatically removes entries of type `kubectl_manifest` and `helm_release` from the Terraform state file.


# Create OAuthClientID

## Configure OAuth consent screen
* Go to APs & Services => OAuth consent screen
* Follow the prompts


## Configure client-side credentials
* Go to APIs & Services => Credentials
* Create OAuth client ID
* Application Type => `Web Application`
* Name => `Lexitrail UI`
* Click `Create`
* Save the `client_id` field, update it in the .env file
    ```
    REACT_APP_CLIENT_ID=<YOUR_CLIENT_ID>
    ```

## Database Management with lexitrailcmd

A utility for synchronizing vocabulary data across local files, database, and cloud storage.

### Usage

From the backend directory with activated virtual environment:

```bash
# Check differences without making changes (dry run)
python -m scripts.lexitrailcmd dbcheck

# Synchronize data across all platforms
python -m scripts.lexitrailcmd dbupdate
```

The `dbupdate` command follows this flow:
1. Uses local CSV files as the source of truth
2. Updates the database to match local files
3. Uploads CSV files to Google Cloud Storage

CSV files are located in `backend/data/` (wordsets.csv and words.csv).