# Phase 4 cutover: build the React shell (web/dist) and serve it via nginx.
# Multi-stage — no Node required on the host; `docker compose --build` builds both stages.
# The React app is the served origin; the legacy app stays recoverable under /legacy/
# (mounted repo root aliased in nginx) until all views reach parity.

FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_ENABLE_REACT=1
ENV VITE_ENABLE_REACT=${VITE_ENABLE_REACT}
# Cache node_modules across builds first.
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80