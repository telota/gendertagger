# The build context is the `frontend/` directory (compose.yaml and the CI image job both use it),
# so package.json and package-lock.json are the client's own manifests.
#
# Node is pinned by version and multi-platform index digest. The version must satisfy the `engines`
# range in frontend/package.json (decision D12); update both together.
ARG NODE_IMAGE=node:26.9.0-alpine@sha256:dbaa92e5758cbbcf85d65d5403fdb530fe3442cbe8c6dbfb7ef23365450d5070

FROM ${NODE_IMAGE} AS dependencies
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts --no-audit --no-fund

# Vite uses the same internal port as the static image so the gateway and published ports stay
# unchanged. compose.dev.yaml mounts source and isolates node_modules in a container volume.
FROM dependencies AS development
COPY . .
EXPOSE 80
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "80", "--strictPort"]

FROM dependencies AS builder
COPY . .
RUN npm run build

# Static assets behind the same-origin gateway. nginx/default.conf adds the history-mode fallback
# (decision D13) so a deep link resolves to the application instead of a 404.
FROM nginx:1.25-alpine AS production
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
