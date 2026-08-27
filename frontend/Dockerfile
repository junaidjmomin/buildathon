FROM node:24-alpine AS dependencies
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_APP_MODE=production
ARG NEXT_PUBLIC_AUTH_MODE=oidc
ARG NEXT_PUBLIC_OIDC_AUTHORITY
ARG NEXT_PUBLIC_OIDC_CLIENT_ID
ARG NEXT_PUBLIC_OIDC_AUDIENCE
ARG NEXT_PUBLIC_OIDC_SCOPE="openid profile email"
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_APP_MODE=$NEXT_PUBLIC_APP_MODE
ENV NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE
ENV NEXT_PUBLIC_OIDC_AUTHORITY=$NEXT_PUBLIC_OIDC_AUTHORITY
ENV NEXT_PUBLIC_OIDC_CLIENT_ID=$NEXT_PUBLIC_OIDC_CLIENT_ID
ENV NEXT_PUBLIC_OIDC_AUDIENCE=$NEXT_PUBLIC_OIDC_AUDIENCE
ENV NEXT_PUBLIC_OIDC_SCOPE=$NEXT_PUBLIC_OIDC_SCOPE
RUN test -n "$NEXT_PUBLIC_API_BASE_URL" \
    && if [ "$NEXT_PUBLIC_APP_MODE" = "production" ]; then \
         test "$NEXT_PUBLIC_AUTH_MODE" = "oidc" \
         && test -n "$NEXT_PUBLIC_OIDC_AUTHORITY" \
         && test -n "$NEXT_PUBLIC_OIDC_CLIENT_ID" \
         && test -n "$NEXT_PUBLIC_OIDC_AUDIENCE"; \
       fi \
    && pnpm build

FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=build --chown=nextjs:nodejs /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
