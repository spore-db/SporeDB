# Deploy SporeDB on AWS (ECS/Fargate)

Deploy SporeDB on AWS using ECS/Fargate with RDS PostgreSQL and S3.
This guide walks through the AWS Console and CLI step by step -- estimated
time: 20 minutes.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| AWS account | With admin or IAM permissions to create ECS, RDS, S3, Secrets Manager, and CloudWatch resources |
| AWS CLI v2 | Installed and configured (`aws configure`) |
| Docker | Installed locally (to verify the image, optional) |

## Quick Start

This guide creates the following AWS resources:

- **ECS Cluster** with a Fargate service running SporeDB
- **RDS PostgreSQL 16** instance for metadata storage
- **S3 Bucket** for Parquet data files
- **Secrets Manager** entries for database URL, S3 keys, and Ed25519 signing keys
- **CloudWatch Log Group** for container logs

Follow the step-by-step sections below to provision each resource.

## Step-by-Step Setup

### 1. Create an S3 Bucket

```bash
aws s3 mb s3://sporedb-data --region us-east-1
```

This bucket stores Parquet files for batch time-series data.

### 2. Create an RDS PostgreSQL Instance

**Via CLI:**

```bash
aws rds create-db-instance \
  --db-instance-identifier sporedb-db \
  --db-instance-class db.t4g.micro \
  --engine postgres \
  --engine-version 16 \
  --master-username sporedb \
  --master-user-password YOUR_PASSWORD_HERE \
  --allocated-storage 20 \
  --no-publicly-accessible \
  --region us-east-1
```

> **Security Warning:** For production deployments handling audit trail data
> (FDA 21 CFR Part 11), do **NOT** use `--publicly-accessible`. The command
> above uses `--no-publicly-accessible` (the recommended default), which keeps
> the RDS instance accessible only from within the VPC. Allow inbound access on
> port 5432 only from the ECS task security group.

**Via Console:** Go to **RDS > Create database > PostgreSQL 16 > db.t4g.micro**.
Set the master username to `sporedb`, choose a strong password, and note the
endpoint after creation (e.g., `sporedb-db.xxxx.us-east-1.rds.amazonaws.com`).

Wait for the instance to become available:

```bash
aws rds wait db-instance-available --db-instance-identifier sporedb-db
```

### 3. Generate Ed25519 Signing Keys

SporeDB uses Ed25519 key pairs for JWT authentication and audit trail signing.
Generate them locally:

```bash
openssl genpkey -algorithm ed25519 -out private.pem
openssl pkey -in private.pem -pubout -out public.pem
```

Base64-encode the keys for storage in Secrets Manager:

```bash
# Use openssl base64 -A to produce single-line output (portable across macOS/Linux):
PRIVATE_KEY_B64=$(openssl base64 -A -in private.pem)
PUBLIC_KEY_B64=$(openssl base64 -A -in public.pem)
```

### 4. Store Secrets in AWS Secrets Manager

> **WARNING:** Use the `postgresql+asyncpg://` connection string prefix.
> Do NOT use `postgres://` or `postgresql://`. SporeDB passes the URL
> directly to SQLAlchemy's `create_async_engine` with no prefix normalization.

```bash
# Database connection string
aws secretsmanager create-secret \
  --name sporedb/database-url \
  --secret-string "postgresql+asyncpg://sporedb:YOUR_PASSWORD_HERE@sporedb-db.xxxx.us-east-1.rds.amazonaws.com:5432/sporedb" \
  --region us-east-1

# S3 access credentials
aws secretsmanager create-secret \
  --name sporedb/s3-access-key \
  --secret-string "YOUR_AWS_ACCESS_KEY" \
  --region us-east-1

aws secretsmanager create-secret \
  --name sporedb/s3-secret-key \
  --secret-string "YOUR_AWS_SECRET_KEY" \
  --region us-east-1

# Ed25519 signing keys (base64-encoded)
aws secretsmanager create-secret \
  --name sporedb/ed25519-private-key-b64 \
  --secret-string "$PRIVATE_KEY_B64" \
  --region us-east-1

aws secretsmanager create-secret \
  --name sporedb/ed25519-public-key-b64 \
  --secret-string "$PUBLIC_KEY_B64" \
  --region us-east-1
```

### 5. Create an IAM Execution Role

The ECS task needs an execution role with permission to pull secrets:

```bash
# Create the role (if it does not already exist)
aws iam create-role \
  --role-name ecsTaskExecutionRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach the managed ECS execution policy
aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Grant Secrets Manager read access
# NOTE: Replace the wildcard (*) in the account ID position below with your
# actual AWS account ID (e.g., 123456789012) to follow least-privilege.
# The wildcard is used here as a placeholder for simplicity.
aws iam put-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-name SporeDBSecretsAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:sporedb/*"
    }]
  }'
```

### 6. Create an ECS Cluster

```bash
aws ecs create-cluster --cluster-name sporedb --region us-east-1
```

### 7. Create a CloudWatch Log Group

```bash
aws logs create-log-group --log-group-name /ecs/sporedb --region us-east-1
```

### 8. Register the Task Definition

The included [`task-definition.json`](aws/task-definition.json) configures a
Fargate task with:

- SporeDB container image from GHCR
- Secrets Manager references for database URL, S3 keys, and Ed25519 keys
- A startup command that decodes base64-encoded Ed25519 keys to files before
  launching uvicorn
- Health check on port 8000
- CloudWatch logging

Before registering, update the placeholders in `task-definition.json`:

- Replace `ACCOUNT_ID` with your AWS account ID
- Replace `REGION` with your AWS region (e.g., `us-east-1`)

```bash
aws ecs register-task-definition \
  --cli-input-json file://docs/deploy/aws/task-definition.json \
  --region us-east-1
```

### 9. Create the ECS Service

Replace `subnet-xxx` and `sg-xxx` with your VPC subnet and security group IDs.
The security group must allow inbound traffic on port 8000 and outbound to RDS
(port 5432) and S3.

```bash
aws ecs create-service \
  --cluster sporedb \
  --service-name sporedb \
  --task-definition sporedb \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --region us-east-1
```

### 10. Verify the Deployment

Check that the service is running:

```bash
aws ecs describe-services \
  --cluster sporedb \
  --services sporedb \
  --region us-east-1 \
  --query 'services[0].{status:status,running:runningCount,desired:desiredCount}'
```

Get the public IP of the running task:

```bash
TASK_ARN=$(aws ecs list-tasks --cluster sporedb --service-name sporedb --query 'taskArns[0]' --output text --region us-east-1)
ENI_ID=$(aws ecs describe-tasks --cluster sporedb --tasks $TASK_ARN --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text --region us-east-1)
PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --query 'NetworkInterfaces[0].Association.PublicIp' --output text --region us-east-1)
echo "SporeDB is running at http://$PUBLIC_IP:8000"
```

Test the health endpoint:

```bash
curl -f http://$PUBLIC_IP:8000/health
```

## What Gets Provisioned

| Resource | Specification |
|----------|--------------|
| ECS Fargate task | 0.5 vCPU, 1 GB RAM |
| RDS PostgreSQL 16 | db.t4g.micro, 20 GB storage |
| S3 bucket | Standard storage class |
| Secrets Manager | 5 secrets (DB URL, S3 keys, Ed25519 keys) |
| CloudWatch log group | `/ecs/sporedb` |

## Configuration

| Variable | Source | Description |
|----------|--------|-------------|
| `SPOREDB_MODE` | Environment | `selfhosted` |
| `SPOREDB_SERVER_PORT` | Environment | `8000` |
| `SPOREDB_S3_BUCKET` | Environment | `sporedb` |
| `SPOREDB_JWT_SECRET_KEY_PATH` | Environment | `/home/sporedb/app/keys/cloud_private.pem` |
| `SPOREDB_JWT_PUBLIC_KEY_PATH` | Environment | `/home/sporedb/app/keys/cloud_public.pem` |
| `SPOREDB_DATABASE_URL` | Secrets Manager | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `SPOREDB_S3_ACCESS_KEY` | Secrets Manager | S3 access key |
| `SPOREDB_S3_SECRET_KEY` | Secrets Manager | S3 secret key |
| `SPOREDB_ED25519_PRIVATE_KEY_B64` | Secrets Manager | Base64-encoded Ed25519 private key |
| `SPOREDB_ED25519_PUBLIC_KEY_B64` | Secrets Manager | Base64-encoded Ed25519 public key |

### Connection String Format

> **WARNING:** SporeDB requires `postgresql+asyncpg://` as the connection string
> prefix. Do NOT use `postgres://` or `postgresql://`. The URL is passed directly
> to SQLAlchemy's `create_async_engine` with no automatic prefix normalization.
>
> **Correct:** `postgresql+asyncpg://sporedb:pass@host:5432/sporedb`
> **Wrong:** `postgres://sporedb:pass@host:5432/sporedb`

## Ed25519 Key Setup

SporeDB loads Ed25519 signing keys from file paths only. On ECS/Fargate,
container filesystems are ephemeral -- key files do not persist across task
restarts. The task definition handles this with a startup command that:

1. Reads `SPOREDB_ED25519_PRIVATE_KEY_B64` and `SPOREDB_ED25519_PUBLIC_KEY_B64`
   from Secrets Manager (injected as environment variables)
2. Decodes the base64 values to files at `/home/sporedb/app/keys/`
3. Sets `SPOREDB_JWT_SECRET_KEY_PATH` and `SPOREDB_JWT_PUBLIC_KEY_PATH` to
   point to those files
4. Launches uvicorn

The `command` field in `task-definition.json` implements this pattern:

```bash
mkdir -p /home/sporedb/app/keys \
  && echo "$SPOREDB_ED25519_PRIVATE_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_private.pem \
  && echo "$SPOREDB_ED25519_PUBLIC_KEY_B64" | base64 -d > /home/sporedb/app/keys/cloud_public.pem \
  && exec uvicorn sporedb.cloud.app:create_app --factory --host 0.0.0.0 --port 8000
```

## Cost Estimate

All prices are approximate monthly costs for US East (N. Virginia) region,
running 24/7.

| Workload | Fargate | RDS Postgres | S3 | Total/month |
|----------|---------|-------------|-----|-------------|
| Small (10 batches) | ~$10/mo (0.25 vCPU, 512MB) | ~$15/mo (db.t4g.micro) | ~$1/mo | ~$26/mo |
| Medium (50 batches) | ~$19/mo (0.5 vCPU, 1GB) | ~$30/mo (db.t4g.small) | ~$2/mo | ~$51/mo |
| Large (100+ batches) | ~$37/mo (1 vCPU, 2GB) | ~$65/mo (db.t4g.medium) | ~$5/mo | ~$107/mo |

Secrets Manager adds ~$2/mo for 5 secrets. CloudWatch Logs pricing depends on
ingestion volume (typically under $1/mo for small workloads).

## Recommended Sizing

| Workload | Fargate CPU | Fargate RAM | RDS Instance | S3 Storage |
|----------|-------------|-------------|-------------|------------|
| Small (10 batches) | 0.25 vCPU | 512 MB | db.t4g.micro (20 GB) | 10 GB |
| Medium (50 batches) | 0.5 vCPU | 1 GB | db.t4g.small (50 GB) | 50 GB |
| Large (100+ batches) | 1 vCPU | 2 GB | db.t4g.medium (100 GB) | 100 GB |

To change Fargate sizing, update the `cpu` and `memory` fields in
`task-definition.json` and re-register the task definition. To change the RDS
instance class, modify it via the RDS console or CLI.

## Troubleshooting

### Task fails to start

Check CloudWatch logs:

```bash
aws logs tail /ecs/sporedb --region us-east-1 --follow
```

The most common cause is missing Secrets Manager permissions on
`ecsTaskExecutionRole`. Verify the role has `secretsmanager:GetSecretValue`
permission for `arn:aws:secretsmanager:us-east-1:*:secret:sporedb/*`.

### Health check failing

Verify the security group allows inbound traffic on port 8000. Also confirm
the task is in a public subnet with `assignPublicIp=ENABLED` (or behind an
ALB with proper target group configuration).

```bash
aws ec2 describe-security-groups --group-ids sg-xxx \
  --query 'SecurityGroups[0].IpPermissions'
```

### Database connection timeout or rfc1738 error

- Ensure `SPOREDB_DATABASE_URL` in Secrets Manager uses the
  `postgresql+asyncpg://` prefix (not `postgres://`)
- Verify the RDS security group allows inbound on port 5432 from the ECS
  task security group
- Confirm the RDS instance is in the same VPC or has appropriate VPC peering

```bash
aws rds describe-db-instances \
  --db-instance-identifier sporedb-db \
  --query 'DBInstances[0].Endpoint'
```

### FileNotFoundError for keys / 500 on auth endpoints

- Verify the Ed25519 base64 secrets exist in Secrets Manager:
  ```bash
  aws secretsmanager get-secret-value --secret-id sporedb/ed25519-private-key-b64 --region us-east-1
  ```
- Confirm the task definition `command` field includes the key decoding script
- Check that the container runs as a user with write access to
  `/home/sporedb/app/keys/` (the default `sporedb` user in the Dockerfile has
  this permission)
