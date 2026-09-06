# 02. Terraform basics

## What is IaC (Infrastructure as Code)?

Infrastructure built by clicking around the AWS console has problems:

- No record of what you configured (not reproducible)
- Easy to miss leftovers and misconfigurations
- Building the same environment again means repeating the same manual work

Terraform lets you describe the **desired state** of your infrastructure as code and
**converges** the real AWS environment to match. Every resource in this project (EC2,
Lambda, IAM, S3, alarms, budgets…) lives in `.tf` files: `terraform apply` builds it
all, `terraform destroy` removes it all.

## The three basic commands

```sh
terraform init    # first time only: fetch plugins (the AWS provider, etc.)
terraform plan    # dry run: show what would be created / changed / destroyed
terraform apply   # execute: apply the plan to AWS
```

Get in the habit of **reading the plan before applying**. `+` means create, `~` means
change in place, and `-/+` means **replace (destroy then create)**. Watch out for `-/+`
in particular — in this project, replacing the EC2 instance deletes your world data
(mitigation below).

## How resources are written

The basic unit in a `.tf` file is the `resource` block. From `s3.tf`:

```hcl
resource "aws_s3_bucket" "minecraft" {
  bucket = "minecraft-bedrock-${local.account_id}"
}
```

- `aws_s3_bucket` is the resource type, `minecraft` is its name within the code
- Other resources can reference it as `aws_s3_bucket.minecraft.bucket`.
  **These references form the dependency graph Terraform uses to order operations**
- `data` blocks only *read* existing things. This project uses them to look up the
  default VPC and the latest Ubuntu AMI (`ec2.tf`)

## variables / outputs / tfvars

- `variables.tf` — values that differ per user (domain name, instance type, idle
  minutes before auto-stop, …). Anything without a `default` is required input
- `minecraft.auto.tfvars` — your actual values. `*.auto.tfvars` files are read
  automatically at apply time. This file holds personal values, so it is
  **gitignored** (copy the `.example` file)
- `outputs.tf` — values printed after apply; here, e.g. the URL you paste into Discord

```sh
terraform output interactions_endpoint_url
```

## State

Terraform records "what I created and its real IDs" in `terraform.tfstate`. It is the
**mapping between your code and reality** — lose it, and Terraform no longer knows what
it owns.

- This project keeps state local (fine for one person)
- `terraform.tfstate` is gitignored. **It contains resource IDs — never push it to a
  public repository**
- To share across a team or machines, use an S3 backend (example commented in `main.tf`)

## Terraform techniques this project shows off

**`default_tags`: tag every resource** (`main.tf`)

```hcl
provider "aws" {
  region = "ap-northeast-1"
  default_tags {
    tags = { Project = "Minecraft" }
  }
}
```

Set on the provider, this puts `Project=Minecraft` on every resource. That one tag
powers three things — a single Resource Group view in the console, IAM permissions
scoped to this project, and a budget scoped to this project. It is the backbone of the
whole design.

**`lifecycle.ignore_changes`: prevent accidental replacement** (`ec2.tf`)

AMIs are updated constantly, so naive code would propose "new AMI available → replace
the instance" on every apply — **deleting your world**. `ignore_changes = [ami,
user_data, ...]` declares "after initial creation, ignore drift on these attributes"
and prevents that accident.

**`templatefile`: inject values into scripts** (`ec2.tf` → `user_data.sh.tftpl`)

The instance's first-boot script (user_data) is a template that receives Terraform
values (S3 bucket name, domain name, …). Infrastructure values and in-server
configuration stay managed in one place.

## Growing an IaC repository

This repository keeps all `.tf` files **flat at the root**. With a single stack (one
unit that applies together), that is the simplest correct layout for a tutorial.

What about real operations with multiple projects? The answer is a **monorepo with one
directory per stack**. The repository this project came from looks like:

```
infra/
├── aws/
│   ├── minecraft/     ← the original of this repo; terraform apply runs here
│   ├── portfolio/     ← another project with its own independent state
│   └── ...
├── cloudflare/
│   └── dns/           ← also split by provider (cloud)
└── docs/              ← architecture diagrams etc.
```

Three principles to remember:

1. **Stack = state = blast radius.** With independent state per directory, an apply
   mistake in `minecraft/` can never break `portfolio/`. One giant all-in-one state
   means slow plans and maximum blast radius
2. **Split by "created together, destroyed together".** This project's EC2, Lambda,
   IAM, and budget share a fate — one stack is correct. A DNS zone or shared VPC
   referenced by many projects belongs in its own stack
3. **Once you have multiple stacks, move state to a remote backend (S3).** Local state
   tops out at one stack and one operator (see the comment in `main.tf`)

So the flat layout here is not a shortcut — it **is one directory of a monorepo, cut
out**. When your own infrastructure grows after forking, graduate it into an
`aws/minecraft/`-style hierarchy.

---

Previous: [01. Setting up your AWS account](01-aws-account.md) / Next: [03. EC2](03-ec2.md)
