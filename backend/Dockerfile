# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 80 for Flask in production
EXPOSE 80

# Set environment variables
ENV FLASK_APP=run.py
ENV FLASK_ENV=production

# issue-273 step 1: bake the git sha these bytes were built from, so /version can
# report it and a detector can say "main is ahead of production".
#
# 🔴 Declared HERE, after COPY/pip, and not near the top. An `ARG` that a later
# layer references invalidates the docker cache for every layer below it, so
# putting this above `COPY . /app` would rebuild the pip install on every commit
# -- turning a cache-warm build into a cold one and spending build minutes to
# report a string. Nothing below this line is expensive.
#
# Unset is a legitimate state (a local `docker build` with no --build-arg) and is
# handled at the route, not here: /version returns sha=null, known=false.
ARG BUILD_SHA=""
ENV BUILD_SHA=$BUILD_SHA

# Run the Flask app on port 80
CMD ["flask", "run", "--host=0.0.0.0", "--port=80"]
