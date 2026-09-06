# 08. Hands-on — build it and play

Prerequisites: the account setup from [chapter 01](01-aws-account.md) (working CLI, and
the `Project` cost allocation tag activated). Budget about an hour.

## 0. Get the repository, check your tools

```sh
git clone https://github.com/dokkiitech/minecraft-aws-intro.git
cd minecraft-aws-intro

terraform version   # >= 1.13
aws sts get-caller-identity
python3 --version
```

## 1. Put secrets in SSM Parameter Store

**Cloudflare API token**: Cloudflare dashboard → My Profile → API Tokens → Create
Token. Scope it to **Zone → DNS → Edit for the target zone only** (never the Global API
Key — scoping limits the blast radius of a leak).

**Discord webhook**: in the channel that should receive notifications → Settings →
Integrations → create a Webhook and copy its URL.

```sh
aws ssm put-parameter --type SecureString \
  --name /minecraft/cloudflare-token --value 'xxxxxxxx'
aws ssm put-parameter --type SecureString \
  --name /minecraft/discord-webhook \
  --value 'https://discord.com/api/webhooks/xxx/yyy'
# for presence (bot online indicator); read by EC2 only, never passed to Lambda
aws ssm put-parameter --type SecureString \
  --name /minecraft/discord-bot-token --value 'xxxxxxxx'
```

(You can register `discord-bot-token` after creating the bot in the next step.)

## 2. Create the Discord application

[Discord Developer Portal](https://discord.com/developers/applications) → New Application.

1. Note the **Application ID** and **Public Key** on **General Information**
2. On the **Bot** tab, create a Bot Token and note it (used for command registration
   and the presence indicator)
3. In **OAuth2 → URL Generator**, select scopes `bot` + `applications.commands` and
   invite the bot to your Discord server via the generated URL

## 3. Fill in the variables

```sh
cp minecraft.auto.tfvars.example minecraft.auto.tfvars
```

Edit `minecraft.auto.tfvars` (gitignored):

- `discord_application_id` / `discord_public_key` — from step 2
- `record_name` — the server's FQDN (e.g. `mc.example.com`)
- `cf_zone_id` — Cloudflare dashboard → your domain → Overview, bottom right
- Optional: `server_name` (shown in the client), `allowlist` (gamertags, for invite-only)

## 4. Build the bot zip and apply

```sh
./bot/build.sh          # builds function.zip with arm64 PyNaCl wheels
terraform init
terraform plan          # read what will be created (just under 30 resources)
terraform apply
```

After apply, the instance boots for the first time and user_data sets up the Minecraft
server (a few minutes).

## 5. Wire up Discord

1. Put the URL from `terraform output interactions_endpoint_url` into
   **General Information → Interactions Endpoint URL** in the Developer Portal and save.
   Discord validates by sending a PING **and a request with a deliberately broken
   signature** (see chapter 06; if it fails, check that apply finished and the URL was
   copied exactly)
2. Register the slash commands (the only places the Bot Token is used are here and
   presence; see `bot/.env.example`):

```sh
APPLICATION_ID=... GUILD_ID=... BOT_TOKEN=... python3 bot/register_commands.py
```

`GUILD_ID` is your Discord server's ID (enable Developer Mode, right-click the server
name → Copy ID).

## 6. Play

In Discord:

```
/mc start    → after 60–90 s: "🟢 up — mc.example.com:19132"
/mc status   → check state
/mc stop     → save and stop (refused while someone is playing)
/mc allow add <gamertag>   → manage the invite list (live-reloads in ~30 s)
```

An empty allowlist disables enforcement and lets anyone join, matching the
`allowlist = []` default. Adding the first name enables enforcement again.

In Minecraft (Bedrock), add a server under the Servers tab with your `record_name` and
port `19132`.

Fifteen minutes after the last player leaves, you get a "🔴 stopping" notification, the
world is backed up to S3, and the instance stops itself. **You can walk away and go to
bed** — that is the whole point.

> Switch / PS clients cannot add custom servers, so if those players join you, a DNS
> workaround like BedrockConnect is additionally required.

## 7. Look around inside (recommended)

- Console → Resource Groups → `Minecraft` lists the tag-supported resources
- Instead of SSH: `aws ssm start-session --target $(terraform output -raw instance_id)`
  - `journalctl -u bedrock -f` tails the server log; `journalctl -u mc-watchdog -f`
    shows the watchdog at work
- Watch tar.gz files accumulate under `backups/` in the S3 bucket at every stop

## Troubleshooting

| Symptom | Where to look |
| --- | --- |
| Saving the Interactions Endpoint fails | apply finished? URL exact? CloudWatch Logs `/aws/lambda/minecraft-bot` |
| `/mc start` succeeds but can't connect | is the record **DNS only (grey cloud)**? (proxy blocks UDP) / `journalctl -u mc-dns` |
| No Discord notifications | webhook URL value in SSM / `journalctl -u mc-watchdog` |
| Budget alert forever at $0 | cost allocation tag `Project` activated? (up to 24 h) |

## Operations notes

- Updating the server (BDS): while running,
  `sudo systemctl stop bedrock && sudo /usr/local/bin/install-bds.sh && sudo systemctl start bedrock`
  (world and server.properties are preserved)
- The instance is protected from replacement by `lifecycle.ignore_changes`
  ([chapter 02](02-terraform.md)). To replace it deliberately, **check the S3 backups
  first**, then `terraform taint aws_instance.bedrock` (the world will be wiped)
- Calling `StopInstances` directly can cut a save short. Always stop via `/mc stop` or
  the watchdog

## Complete teardown

When you are done learning, or won't play for a while:

```sh
terraform destroy
```

Destroy fails if objects remain in the S3 bucket; empty the bucket and re-run
(download the world first if you want to keep it). The SSM parameters are outside
Terraform — delete them separately with `aws ssm delete-parameter`.

**Only then does billing fully stop.** Build it, use it, remove it cleanly — completing
that full cycle is what finishes the introduction.

---

Previous: [07. Monitoring and cost control](07-monitoring.md) / [Back to README](../README.md)
