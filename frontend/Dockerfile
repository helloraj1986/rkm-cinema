# Build the React shell (frontend/dist) and serve it via nginx.
# Multi-stage — no Node required on the host; `docker compose --build` builds both stages.
# nginx serves the React shell (baked into the image) as the origin. No legacy app anymore.

FROM node:20-alpine AS build
WORKDIR /app
# Cache node_modules across builds first.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80