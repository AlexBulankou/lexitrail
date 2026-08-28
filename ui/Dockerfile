# Use an official Node.js runtime as a parent image
FROM node:16-alpine

# Install curl using the Alpine package manager
RUN apk add --no-cache curl

# Set the working directory to /app
WORKDIR /app

# Copy the package.json and install dependencies
COPY package.json ./
RUN npm install

# Copy the current directory contents into the container at /app
COPY . .

# Build the app for production
RUN npm run build

# Install serve to serve the build folder
RUN npm install -g serve

# Set the environment variable to production
ENV NODE_ENV=production

# Expose port 3000 to the outside world
EXPOSE 3000

# Serve the built app.
#
# 🔴 NO `-s` (lexitrail#204), and that is load-bearing rather than tidying. `--single` injects its
# own `{"source":"**","destination":"/index.html"}`, which returns the SPA shell with HTTP 200 for
# EVERY path — so every typo'd or stale inbound link was an indexable soft-404, and no amount of
# rewrite configuration in serve.json could change it (measured: with `-s`, an enumerated rewrite
# list plus a 404.html still returned 200 on unknown paths).
#
# The SPA routes are enumerated in `public/serve.json` instead, derived from `src/App.js` and
# pinned by `src/utils/serveRoutes.test.js` so a route added to one and not the other cannot 404
# silently. Unknown paths now fall through to `public/404.html`, which serve returns with a real
# 404 status.
CMD ["serve", "build"]
