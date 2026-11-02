# PMI api (Fastify) — production image, built from the monorepo root context.
FROM node:24-slim
RUN npm install -g pnpm@10.17.0
WORKDIR /repo

COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages/contracts/package.json packages/contracts/package.json
COPY apps/api/package.json apps/api/package.json
RUN pnpm install --frozen-lockfile --filter @pmi/api...

COPY packages/contracts packages/contracts
COPY apps/api apps/api
RUN pnpm --filter @pmi/api build

EXPOSE 8000
USER node
CMD ["node", "apps/api/dist/server.js"]
