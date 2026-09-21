# The build context is the `frontend/` directory (compose.dev.yaml and the CI image job both use it),
# so package.json and package-lock.json are the client's own manifests.
#
# Node is pinned by version and multi-platform index digest. The version must satisfy the `engines`
# range in frontend/package.json (decision D12); update both together.
ARG NODE_IMAGE=node:26.9.0-alpine@sha256:dbaa92e5758cbbcf85d65d5403fdb530fe3442cbe8c6dbfb7ef23365450d5070

FROM ${NODE_IMAGE} AS dependencies
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts --no-audit --no-fund

# Vite development server with hot reload. Bind-mount `frontend/` over /app for live edits, or run
# `npm run dev` on the host against http://localhost:8000; the dev server proxies /api/v1.
FROM dependencies AS development
COPY . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

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
