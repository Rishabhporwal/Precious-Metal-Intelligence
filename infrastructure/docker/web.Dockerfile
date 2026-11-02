# PMI web (Next.js) — production image, built from the monorepo root context.
FROM node:24-slim
RUN npm install -g pnpm@10.17.0
WORKDIR /repo

# Copy workspace manifests first for layer-cached dependency install.
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY packages/contracts/package.json packages/contracts/package.json
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @pmi/web...

# Copy sources and build.
COPY packages/contracts packages/contracts
COPY apps/web apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @pmi/web build

EXPOSE 3000
CMD ["pnpm", "--filter", "@pmi/web", "start"]
