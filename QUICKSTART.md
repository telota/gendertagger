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

For a **local instance**, set:

```bash
export COMPOSE_FILE=compose.yaml:compose.dev.yaml
```

For a **shared server**, set:

```bash
export COMPOSE_FILE=compose.yaml:compose.prod.yaml
```

Keep this choice set in the shell for the remaining commands, and set it again in a new shell.
The local configuration enables backend source reload and exposes diagnostic ports on loopback.
The server configuration applies resource limits and exposes only the gateway on
`127.0.0.1:8080`. Server access through HTTPS is configured in step 5.

Both modes persist the database, Redis state, and uploaded/generated artifacts in Docker volumes.
On a server, you can instead set `POSTGRES_DATA_PATH`, `REDIS_DATA_PATH`, and `ARTIFACTS_PATH` in
`.env` to absolute host directories before the first start. The artifacts directory must be
writable by the backend container's `app` user. Back up the database and artifacts together; see
[deployment and operations](docs/12-deployment-and-operations.md).

## 3. Build and initialize

The development Compose file supplies the build definitions for both modes. Build the two
application images, then use your selected mode to start the database and run migrations:

```bash
docker compose -f compose.yaml -f compose.dev.yaml build api frontend
docker compose up -d db redis
docker compose --profile ops run --rm migrate
```

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
browser application; the standalone frontend port does not proxy API requests.

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
release registry. With the locally built images used here, rebuild from the new checkout instead,
update the commit and lockfile hash in `.env`, and apply migrations before recreating services.

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

## Stop and restart

```bash
docker compose down
docker compose up -d
```

`down` preserves the persistent volumes. Adding `--volumes` deletes them and the instance data
they contain. Keep the same `.env` and Compose mode when restarting; changing the PostgreSQL
password in `.env` does not change the password in an already initialized database.
