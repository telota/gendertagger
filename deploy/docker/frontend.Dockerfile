FROM node:22-alpine AS builder

WORKDIR /app
# We'll use a placeholder for now since frontend doesn't exist
# COPY package.json package-lock.json ./
# RUN npm ci
# COPY . .
# RUN npm run build
RUN mkdir -p dist && echo "<h1>GenderTagger Frontend Placeholder</h1>" > dist/index.html

FROM nginx:1.25-alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

FROM node:22-alpine AS development
WORKDIR /app
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
