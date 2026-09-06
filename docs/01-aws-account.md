# 01. Setting up your AWS account

If you already have a working AWS CLI environment, just check the
[billing alert](#set-up-a-billing-alert) and [cost allocation tag](#activate-the-cost-allocation-tag-required-for-this-project)
sections and move on.

## Create the account

Sign up at [aws.amazon.com](https://aws.amazon.com/). You will need a credit card and a
phone number (SMS verification).

Do these immediately after creating the account:

1. **Enable MFA on the root user.** The root user can do anything — if it is
   compromised, so is your bill and your data. In the IAM console, register an
   authenticator app for the root user.
2. **Stop using the root user.** Day-to-day work happens with the IAM identity you
   create next.

## Create working credentials

Two kinds of principals operate on AWS: humans (console / CLI) and AWS resources
themselves (EC2, Lambda). Both are governed by IAM (Identity and Access Management).
Resource-side roles are covered in [chapter 04](04-iam.md); here we set up the human side.

**Recommended: IAM Identity Center (formerly AWS SSO)**

Even on a personal account, Identity Center gives your CLI short-lived credentials, so
no long-lived access keys sit on your machine.

1. Enable "IAM Identity Center" in the console (Tokyo `ap-northeast-1` is fine)
2. Create one user and assign the `AdministratorAccess` permission set
3. Configure the CLI locally:

```sh
aws configure sso
# enter the SSO start URL / region → authenticate in the browser
aws sso login --profile <profile-name>
export AWS_PROFILE=<profile-name>
aws sts get-caller-identity   # OK if it returns your account ID
```

**Quick and simple: IAM user + access key**

For learning, an IAM user with `AdministratorAccess` and an access key via
`aws configure` also works. Just remember an access key is a long-lived credential —
never commit it to git, and deactivate it when you no longer need it.

> This project assumes you run Terraform with admin-level permissions, while the
> **resources it creates (EC2 / Lambda) get tightly scoped permissions**. That asymmetry
> is normal in practice — chapter 04 explains it.

## Pick a default region

Costs in this text assume Tokyo, `ap-northeast-1`. For a game server, latency is felt
directly, so choose the region closest to your players.

```sh
aws configure set region ap-northeast-1
```

## Set up a billing alert

This project has its own budget watch ($5, [chapter 07](07-monitoring.md)), but that
only covers resources tagged `Project=Minecraft`. An **account-wide** budget catches
leftovers from other experiments too.

1. Console → Billing → Budgets → "Create budget"
2. Use the "Monthly cost budget" template, set e.g. $10, add your email

It takes five minutes and is something every AWS learner should do first.

## Activate the cost allocation tag (required for this project)

The project budget filters on "cost of resources tagged `Project=Minecraft`". For tags
to be usable in cost reports, you must activate them at the account level:

1. Billing console → **Cost allocation tags**
2. Select `Project` and click **Activate**

It can take up to 24 hours to propagate, so **do this the day before the hands-on**.
If you skip it, the Budgets tag filter always reads $0 and the alert never fires.

---

Previous: [00. Introduction](00-intro.md) / Next: [02. Terraform basics](02-terraform.md)
