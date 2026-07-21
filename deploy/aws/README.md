# AWS production deployment

The first production topology is deliberately small and operationally simple:

- one EC2 host runs the API, PDF worker, static frontend, and Caddy;
- Amazon RDS for PostgreSQL stores relational state;
- the EC2 encrypted EBS volume stores uploads and the local Whisper cache;
- Route 53 points the public domain at an Elastic IP;
- Caddy obtains and renews HTTPS certificates automatically;
- Amazon SES supplies SMTP email;
- Chroma Cloud remains the vector store.

This removes SQLite and long-running PDF work from the web process while
avoiding a premature ECS/EFS deployment. Move `/data` to EFS or S3 before
scaling the API and worker across more than one EC2 host.

## AWS resources

Create these in one region (for example `eu-central-1`):

1. A VPC with two availability zones, public subnets for EC2 and private
   subnets for RDS.
2. A PostgreSQL 17 RDS instance with storage encryption, automated backups,
   deletion protection, and no public address. Its security group should allow
   port 5432 only from the EC2 security group.
3. An EC2 instance sized for local Whisper and PDF processing (start with
   `t3.large`) using an encrypted, delete-protected EBS data volume. Allow
   inbound 80 and 443; limit SSH to an administrator address or use SSM.
4. An Elastic IP and a Route 53 `A` record for the chosen domain.
5. SES production access plus a verified sending domain/address. Create SES
   SMTP credentials in the same region.

## Host setup

Install Docker Engine, the Compose plugin, and Git on the EC2 host. Clone this
repository to `/opt/study-os`, then create the two ignored secret files:

```text
/opt/study-os/.env
/opt/study-os/backend/.env.production
```

Use `.env.production.example` and `backend/.env.production.example` as the
templates. The backend `DATABASE_URL` must use the private RDS endpoint and
must be URL-encoded if the password contains reserved URL characters.

Start the stack from the repository root:

```bash
docker compose --env-file .env -f docker-compose.aws.yml config
docker compose --env-file .env -f docker-compose.aws.yml up -d --build
docker compose --env-file .env -f docker-compose.aws.yml ps
```

The backend runs `alembic upgrade head` before starting. The worker does not
start until the API and database health check passes.

## External configuration

- Google Cloud: add `https://YOUR_DOMAIN` as an authorized JavaScript origin,
  then use the same web client ID for `GOOGLE_CLIENT_ID` and
  `VITE_GOOGLE_CLIENT_ID`.
- Stripe: create recurring Student Pro and Professional prices, place their
  price IDs in the backend environment, and register
  `https://YOUR_DOMAIN/api/billing/webhook`. Subscribe it to
  `checkout.session.completed`, `customer.subscription.created`,
  `customer.subscription.updated`, `customer.subscription.deleted`, and
  `invoice.payment_failed`.
- SES: set `EMAIL_DELIVERY_MODE=smtp`, the regional SMTP endpoint and
  credentials, and a verified `SMTP_FROM_EMAIL`.

## Release and rollback

Before each release, snapshot RDS and the EBS data volume. Deploy an immutable
Git commit, rebuild, and check `/api/health`. Application rollback is a Git
checkout of the prior commit followed by a rebuild; do not downgrade the
database migration unless the migration has been explicitly reviewed as safe.
