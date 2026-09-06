# 05. S3 and SSM Parameter Store

Files: `s3.tf` / `main.tf` (SSM parameter names) / `server/mc-sync.sh`

## S3 — object storage

S3 (Simple Storage Service) stores files ("objects"): effectively unlimited capacity,
eleven nines of durability, and a few cents a month for a few hundred MB of world data.
This project uses one bucket for three purposes:

```
minecraft-bedrock-<account-id>/
├── backups/    ← world tar.gz files the watchdog uploads before stopping
├── bootstrap/  ← operational scripts & units the instance fetches at boot
└── config/allowlist.json  ← the invite list (edited by the bot)
```

### Bucket names and the public access block

Bucket names must be **globally unique**, hence the account-ID suffix. And the first
thing after creating a bucket: block all public access and explicitly enable SSE-S3
encryption at rest.

```hcl
resource "aws_s3_bucket_public_access_block" "minecraft" {
  block_public_acls   = true
  block_public_policy = true
  # ...
}
```

"Misconfigured S3 bucket exposed to the world" is a classic data-breach headline. Any
bucket with no reason to be public should be mechanically locked down like this.

### Lifecycle rules — automating cleanup

Backups accumulate forever if you let them. A lifecycle rule on the `backups/` prefix
**expires objects after 60 days** and aborts incomplete multipart uploads after seven
days — no human has to remember to clean up.

```hcl
rule {
  filter { prefix = "backups/" }
  expiration { days = 60 }
}
```

### The bootstrap pattern — distributing scripts via S3

Terraform uploads everything under `server/` to the bucket's `bootstrap/` prefix
(`aws_s3_object.bootstrap` with `for_each`), and the instance re-fetches it **on every
boot** via `mc-sync.service`.

Why this is great: **fixing a server-side script requires no login to the instance.**
Edit the script in the repo → `terraform apply` (S3 updated) → picked up automatically
at the next boot. The inside of the server is under Git control too.

After syncing the scripts, `mc-sync.sh` runs `install-bds.sh` to check the official API
for a newer Bedrock server build. A failed update check triggers the systemd failure
notification but does not block the already installed server from starting.

### Keeping the "single source of truth" in S3 — the allowlist

The invite list `config/allowlist.json` has an interesting design:

- Terraform writes only the initial value
- From then on, **the bot (Lambda) edits S3 directly** via Discord's `/mc allow add/remove`
- Terraform is told `ignore_changes = [content]`, so an apply never reverts the bot's edits

This is a practical case study in drawing the line between "initial state managed by
Terraform" and "runtime state that changes while operating" — a real question in every
IaC deployment.

## SSM Parameter Store — managing secrets

The Cloudflare API token and Discord webhook URL are secrets that **must not appear in
code**. This project keeps them in SSM Parameter Store as SecureStrings (KMS-encrypted):

```sh
aws ssm put-parameter --type SecureString \
  --name /minecraft/cloudflare-token --value 'xxxxxxxx'
```

- Registered **outside** Terraform (so no plaintext ends up in tfstate either)
- EC2 can read the three named parameters; the notifier Lambda can read only the
  Discord webhook parameter (chapter 04)
- No secret appears in code, the repository, or the state file

AWS also offers Secrets Manager (rotation etc., $0.40/secret/month); at this scale, the
free Parameter Store is plenty.

---

Previous: [04. IAM](04-iam.md) / Next: [06. Lambda and the Discord bot](06-lambda-discord.md)
