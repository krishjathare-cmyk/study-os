# Study OS

Study OS is a FastAPI and React study assistant with PDF-generated learning
maps, practice, lecture transcription, Google authentication, email
verification, usage limits, and Stripe subscriptions.

## Local development

Copy `backend/.env.example` to `backend/.env`, fill the development service
keys, then run:

```bash
docker compose up --build
```

The API is available on `http://localhost:8001` and the frontend on
`http://localhost:5173`. Compose applies Alembic migrations and starts a
separate durable PDF worker.

`OUTLINE_LLM_ENABLED=false` keeps deterministic heading extraction.
`SUBTOPIC_CONSOLIDATION_ENABLED=false` also prevents the optional one-call
consolidation of PDFs with more than eight detected topics.

## Production

- Generic single-host production: `docker-compose.prod.yml`
- AWS EC2 + RDS deployment: [`deploy/aws/README.md`](deploy/aws/README.md)

Both production configurations require real HTTPS domain, SMTP, Google,
Stripe, PostgreSQL, model, and vector-store credentials. The backend refuses
to start in production when any required safety configuration is absent.
