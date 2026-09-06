# 04. IAM — least-privilege role design

Files: `iam.tf`

IAM (Identity and Access Management) decides "who may do what to what" and is the core
of AWS security. This project defines **three roles**, each restricted to exactly what
its job requires (the principle of least privilege).

## Roles — how to avoid handing out access keys

The scripts on the EC2 instance need AWS permissions to back up worlds to S3. The naive
approach — putting an access key on the server — is a leak waiting to happen.

Instead we use **IAM roles**: bundles of permissions that AWS services themselves
assume (AssumeRole). EC2 gets one via an instance profile; Lambda gets one as its
execution role. AWS issues and rotates the temporary credentials automatically —
**no key ever appears in code or config**.

```hcl
assume_role_policy = jsonencode({
  Statement = [{
    Effect    = "Allow"
    Principal = { Service = "ec2.amazonaws.com" }  # only EC2 can assume this role
    Action    = "sts:AssumeRole"
  }]
})
```

## What each of the three roles may do

| Role | Used by | Allowed to |
| --- | --- | --- |
| `minecraft-bedrock` | EC2 (watchdog) | read SSM secrets / back up to S3 / **stop itself** / manage tags |
| `minecraft-bot` | bot Lambda | **start** the instance / describe it / set request tags / edit the allowlist / async self-invoke |
| `minecraft-notifier` | notifier Lambda | read the webhook secret / read & clear the stop-reason tag |

Note that the bot Lambda can start (`ec2:StartInstances`) but **cannot stop**
(`ec2:StopInstances`). Stopping must save the world first, so the bot can only *ask*
the in-instance watchdog via a tag. The permission split itself enforces the safe
shutdown flow.

## Tag conditions — scoping to "this project's resources only"

When allowing `ec2:StartInstances`, granting it on `instance/*` (all instances) would
let the bot start unrelated instances in the account. But writing the target instance's
ARN directly creates a circular dependency (the role references the instance, the
instance references the role).

The answer is a **tag condition**:

```hcl
{
  Action    = ["ec2:StartInstances"]
  Resource  = "arn:aws:ec2:${local.region}:${local.account_id}:instance/*"
  Condition = {
    StringEquals = { "aws:ResourceTag/Project" = "Minecraft" }
  }
}
```

"May operate only on instances tagged `Project=Minecraft`". Chapter 02's
`default_tags` puts that tag on the EC2 instance, so permissions are automatically
confined to this project. A pattern well worth memorizing for real-world work.

> The `Describe*` actions use `Resource = "*"` because AWS does not support
> resource-level restrictions for them (read-only, so acceptable).

## SSM Session Manager — the SSH replacement

The EC2 role attaches the AWS managed policy `AmazonSSMManagedInstanceCore`, which
gives you a shell with **no SSH, no open port, no key management**:

```sh
aws ssm start-session --target <instance-id>
```

- Port 22 is closed, so brute-force SSH scans are irrelevant
- Who connected and when is recorded in CloudTrail (auditability)
- No key files to distribute or revoke

All troubleshooting (`journalctl -u mc-watchdog`, etc.) goes through this.

---

Previous: [03. EC2](03-ec2.md) / Next: [05. S3 and SSM Parameter Store](05-s3-ssm.md)
