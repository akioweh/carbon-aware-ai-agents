# Docker stuffs

## 1. Dev Container

If you are unable to install a C++23 toolchain, we have a Vis\*\*l St\*\*\*o
C\*\*e _Dev Container_.

You'll need

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [VS Code](https://code.visualstudio.com/)
- [Dev Containers Extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

and then look up how to use dev containers :).  
Finally, work as usual, following the guidance from the general READMEs.

---

## 2. Compose Locally

You can build and run the Scheduler, UI, and Stats locally using Docker Compose.

### Basic Stack (Default)

Starts the UI, Scheduler, and PostgreSQL database. The Scheduler and UI will
connect to the **external** Stats API by default.

```bash
docker compose up --build
```

- **UI**: <http://localhost:8080>
- **Scheduler**: <http://localhost:6970> (Internal: 6969)
- **DB**: localhost:5433 (Internal: 5432)

### Full Stack (Local Stats API)

Starts all components, including a local instance of the Stats API. This is
useful when not working on `main` since `main`'s Stats is on CD and you could do
the basic stack instead.

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

---

## 3. Using Release Images

Ready-to-use images are available on the GitHub Container Registry. You don't
need to clone code or build anything.

1. download [`docker-compose.release.yml`](./../docker-compose.release.yml).
2. profit:

```bash
docker compose -f docker-compose.release.yml up
```

---

## Configuration Reference

The important environmental variables:

| name                | what it does             | default value                |
| ------------------- | ------------------------ | ---------------------------- |
| `UI_HOST_PORT`      | Port to access the UI    | `8080`                       |
| `STATS_API_URL`     | URL of the Stats API     | `http://140.238.79.139:5000` |
| `SCHEDULER_API_URL` | URL of the Scheduler API | `http://scheduler:6969`      |
| `PGHOST`            | Scheduler DB Host        | `db`                         |
| `DB_HOST_PORT`      | Scheduler DB Port        | `5433`                       |
