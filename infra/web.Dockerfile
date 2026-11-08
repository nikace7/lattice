FROM node:22.22.0-bookworm-slim
RUN npm install --global pnpm@10.33.4
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
RUN chown node:node /app
USER node
COPY --chown=node:node package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY --chown=node:node apps/web/package.json ./apps/web/
COPY --chown=node:node patches ./patches
RUN pnpm install --frozen-lockfile
COPY --chown=node:node apps/web ./apps/web
EXPOSE 3000
CMD ["pnpm", "--filter", "@lattice/web", "dev"]
