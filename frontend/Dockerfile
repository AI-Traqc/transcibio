# syntax=docker/dockerfile:1

# --- Stage 1: build the Vite/React static bundle --------------------------------
FROM node:20-slim AS build
WORKDIR /app

# Install deps with the lockfile for reproducibility. Skip lifecycle scripts here
# (postinstall runs setup:vad, which needs scripts/ + public/ that aren't copied
# yet) and run the VAD asset copy explicitly after the full source is in place.
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run setup:vad && npm run build

# --- Stage 2: serve via nginx ---------------------------------------------------
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
