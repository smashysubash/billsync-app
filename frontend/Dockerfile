# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first for better caching
COPY package*.json ./
RUN --mount=type=cache,target=/app/.npm \
    npm set cache /app/.npm && \
    npm ci

# Copy source and build
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: Production Server
FROM nginx:alpine

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Custom Nginx config for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Security: Non-root user could be added here for extra hardening
# USER nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

