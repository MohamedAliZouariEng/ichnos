# syntax=docker/dockerfile:1
# Build context: repository root (pnpm needs the whole workspace).

# ---- Build: install the workspace and build the static UI ----
FROM node:22-slim AS build
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY packages/contracts/package.json packages/contracts/
COPY packages/api-client/package.json packages/api-client/
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile --filter "@ichnos/web..."
COPY packages ./packages
COPY apps/web ./apps/web
RUN pnpm --filter @ichnos/web build

# ---- Runtime: nginx serves the UI and proxies the API ----
FROM nginx:stable-alpine AS runtime
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
