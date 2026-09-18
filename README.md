# mitespotter-api

Mitespotter's user, image & annotation database API and file server.

## Getting Started

You will need a running postgresql database. You will need to set the environment variable `MITESPOTTER_DATABASE_URL`.

```shell
uv sync
cp .env.example .env
sed -i 's#REPLACE_URL#<your-url-here>#' .env
uv run --env-file .env main
```

To avoid setting the env file flag each time, you can set it in your shell: 
```
export UV_ENV_FILE=.env
uv run main # or `uv run mitespotter-api`
```

See [planning.md](./planning.md) for specification.
