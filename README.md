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
```


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

