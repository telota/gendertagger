# Set up a gendertagger instance

This guide installs a local instance or a shared server using Docker Compose. The backend is
implemented; the browser interface is still being built. See [project status](PLAN.md) for scope.

## 1. Prepare the host

Install Git, curl, and Docker Engine with Docker Compose 2.24.4 or newer. Docker builds both applications,
so Python and Node.js are not required on the host. The initial build downloads dependencies,
including the machine-learning libraries, and needs several gigabytes of free disk space.

Clone this repository, then run all commands below from its root directory. These instructions
assume a Linux host, a Bash shell, and a fresh installation.

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env`: replace `POSTGRES_PASSWORD` with a long, unique password. Use letters and digits to
avoid URL-encoding issues in the database connection string. Keep `REGISTRY_PREFIX=gendertagger-`
and `TAG=local` to build the images on this host.

Record the checked-out revision and dependency lockfile in the instance configuration:

```bash
printf '\nGENDERTAGGER_CODE_GIT_COMMIT=%s\n' "$(git rev-parse HEAD)" >> .env
printf 'GENDERTAGGER_DEPENDENCY_LOCK_SHA256=%s\n' \
  "$(sha256sum backend/uv.lock | cut -d ' ' -f 1)" >> .env
```

## 2. Choose local or server mode

For **local development** (the default contributor workflow), set:

```bash
export COMPOSE_FILE=compose.yaml:compose.dev.yaml
```

For a **shared server**, set:

```bash
export COMPOSE_FILE=compose.yaml:compose.prod.yaml
```

Keep this choice set in the shell for the remaining commands, and set it again in a new shell.
Local mode runs Vite with frontend hot reload, enables API source reload, and exposes diagnostic
ports on loopback. Server mode serves the compiled frontend through Nginx, applies resource limits,
and exposes only the gateway on `127.0.0.1:8080`. Server access through HTTPS is configured in step 5.
Never expose the development server as a shared production installation.

When reusing an existing stack, keep its Compose project name as well as its `.env` and mode.
Check the name with `docker compose ls`; if it is not the default `gendertagger`, set
`COMPOSE_PROJECT_NAME` to that existing name in your shell or `.env`. A different project name
selects different containers and named volumes; it does not move the existing instance data.

Both modes persist the database, Redis state, and uploaded/generated artifacts in Docker volumes.
On a server, you can instead set `POSTGRES_DATA_PATH`, `REDIS_DATA_PATH`, and `ARTIFACTS_PATH` in
`.env` to absolute host directories before the first start. The artifacts directory must be
writable by the backend container's `app` user. Back up the database and artifacts together; see
[deployment and operations](docs/12-deployment-and-operations.md).

## 3. Build and initialize

Build the two application images using the mode selected above, then start the database and
run migrations:

```bash
docker compose build api frontend
docker compose up -d db redis
docker compose --profile ops run --rm migrate
```

The base Compose file defines the builds. Local mode selects the frontend's development target
and a separate `frontend-dev` image tag; server mode selects its production target and `frontend`
tag. Do not include `compose.dev.yaml` when building images for a server.

Create the first administrator:

```bash
docker compose run --rm api \
  gendertagger users create --username admin --display-name "Admin" --role admin
```

The command prints a generated password once in its JSON output. Save it for the first login.
There is no public account registration.

## 4. Start and check the instance

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=50 api worker-cpu dispatch-coordinator
curl --fail http://localhost:8080/health
curl --fail http://localhost:8080/ready
```

Both HTTP checks should return `OK`. Wait for services with health checks to report `healthy`.
The dispatch coordinator reports `Up` without a health check; its log should include
`dispatch coordinator started`. It must run alongside the CPU worker for imports and other
queued work to execute. API readiness checks the database and artifact storage; it does not
check worker or broker availability.

## 5. Open the instance and sign in

### Local instance

Open <http://localhost:8080/login>, sign in as `admin` with the generated password, and complete
the required password change. Use `localhost` consistently and a browser that accepts secure
cookies on local HTTP, such as Chrome or Firefox. Safari requires HTTPS for these cookies; see
the [browser cookie guidance](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies#block_access_to_your_cookies).
The gateway serves the frontend and `/api/v1` together at this address.

The local API documentation is at <http://localhost:8000/docs>. Use the gateway address for the
browser application and hot reload. The standalone Vite address, <http://localhost:5173>, also
proxies `/api/v1` to the API, but choose one browser address consistently when working with sessions.

### Shared server

Configure an HTTPS reverse proxy on the host with your instance's domain and TLS certificate.
Forward requests for that domain to `http://127.0.0.1:8080`, preserving the request path and
`Host` header. Forward both `/` and `/api/v1` through this same origin. Match the proxy's upload
limit to the gateway's default of 500 MiB, and disable buffering for API event streams.

The included gateway serves HTTP internally; publishing port 443 alone does not configure TLS.
Keep port 8080 on loopback and expose the HTTPS proxy to users. Session cookies require HTTPS
when accessing the instance by a server hostname.

Open `https://YOUR_DOMAIN/login`, sign in as `admin` with the generated password, and complete
the required password change. Verify `https://YOUR_DOMAIN/health` and
`https://YOUR_DOMAIN/ready` through the proxy as well.

For institutional branding and contact details, configure the API's
[`GENDERTAGGER_BRANDING__*` settings](docs/decisions/ADR-0036-institution-branding-configuration.md).
For backups, migration rehearsal, and subsequent release updates, use the
[production runbook](docs/21-production-promotion.md). Its image-pull steps assume a configured
GitLab container registry and use the full commit-SHA image tags published by a successful
default-branch pipeline, not the moving `main` tag. With the locally built images used here,
rebuild from the new checkout instead, update the commit and lockfile hash in `.env`, and apply
migrations before recreating services.

## 6. Add accounts and method data as needed

Create additional accounts with the CLI. After creating a project in the application, grant
access using its slug:

```bash
docker compose run --rm api \
  gendertagger users create --username reviewer --display-name "Reviewer"
docker compose run --rm api \
  gendertagger projects add-member --project my-edition --username reviewer --role reviewer
```

Project roles are `viewer`, `reviewer`, and `operator`; the administrator can access every project.
Each new account must change its initial password at first login.

The instance can start without method datasets. Before using methods that require lookup tables
or model files, follow [method-data provisioning](README.md#method-data). Provision assets inside
the API container so it and the workers share the same persistent storage. Optional GPU and LLM
workers and their model configuration are described in
[deployment and operations](docs/12-deployment-and-operations.md) and the
[method reference](docs/20-method-adapters-reference.md).

## Development workflow

With local mode selected, `docker compose up -d` starts the development stack. Open
<http://localhost:8080>, edit files in `frontend/`, and save: Vite updates the browser without an
image rebuild. Docker supplies Node and keeps container dependencies in a separate volume, so
host `node_modules` are not used inside the container. API edits under `backend/src/` reload too.

For an existing local stack created before this hot-reload setup, keep its project name and
persistent volumes, then replace just the frontend and gateway:

```bash
docker compose up -d --build --no-deps --force-recreate frontend gateway
```

Not every change is a hot-reload change:

| Change | Required action |
|---|---|
| Vue, TypeScript, or CSS source | Save; Vite updates the browser automatically |
| API code under `backend/src/` | Save; Uvicorn reloads the API |
| Code used by a worker | Restart the affected worker, for example `docker compose restart worker-cpu` |
| Frontend dependencies or lockfile | Rebuild/recreate the frontend and refresh its dependency volume, as below |
| Backend dependencies, coordinator code, or migration files | Rebuild `api`, apply migrations when needed, and recreate the affected backend services; these files are baked into the image |
| Compose configuration or environment | Recreate affected services; a process restart alone does not apply changed container environment |

After changing `frontend/package.json` or its lockfile, replace only the frontend's anonymous
dependency volume and restart the gateway so it resolves the recreated frontend:

```bash
docker compose up -d --build --no-deps --renew-anon-volumes frontend
docker compose restart gateway
```

This does not delete database or artifact volumes. Do not use `docker compose down --volumes`
to refresh dependencies. For optional host-side Vite development and its separate port, see
the [frontend guide](frontend/README.md#local-development).

To verify hot reload manually, open the gateway URL, make a small visible text or CSS change,
and confirm it appears without rebuilding. Confirm the browser's Vite WebSocket connects,
then check login, an `/api/v1` request, and a direct refresh of a nested application URL.
Revert the temporary source edit afterwards. Worker reload and database migrations remain
explicit operations; frontend hot reload does not apply either of them.

## Stop and restart

```bash
docker compose down
docker compose up -d
```

`down` preserves the persistent volumes. Adding `--volumes` deletes them and the instance data
they contain. Keep the same `.env`, Compose mode, and project name when restarting; changing the
PostgreSQL password in `.env` does not change the password in an already initialized database.
