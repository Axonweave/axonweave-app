FROM node:22-alpine AS base

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* values are inlined into the client bundle at build time, so this must be a
# build argument; a runtime environment variable would have no effect.
ARG NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL

RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=base /app/public ./public
COPY --from=base --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=base --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
