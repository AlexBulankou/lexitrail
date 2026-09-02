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

# issue-273 step 1: write the git sha these bytes were built from into the served
# bundle, so "is production current?" is answerable without credentials.
#
# 🔴 Placed AFTER `npm run build`, not before. CRA wipes `build/` at the start of
# a build, so a version.json written earlier would be deleted by the very step
# that produces the artifact -- and silently: the image would build green and the
# file would simply not be there.
#
# 🔴 UNSET IS ITS OWN STATE. A local `docker build` with no --build-arg must not
# produce a file that reads like a match. `sha` is JSON null and `known` is false
# in that case, mirroring the backend's /version, so one consumer handles both.
#
# ARG is declared here rather than at the top so it does not invalidate the cache
# for `npm install` -- an ARG busts every layer below its declaration.
ARG BUILD_SHA=""
RUN if [ -n "$BUILD_SHA" ]; then \
      printf '{"sha":"%s","known":true}\n' "$BUILD_SHA" > build/version.json; \
    else \
      printf '{"sha":null,"known":false}\n' > build/version.json; \
    fi

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
