# 00. Introduction

## About this text

There are plenty of AWS beginner books out there, but most stop at "launch an EC2
instance, serve a web page, done." This text takes the opposite approach: you learn AWS
by **building one complete, practical system end to end**.

The subject is a Minecraft Bedrock server for you and your friends — but built the way
you would build it for real operation:

- **On-demand startup**: boot it with `/mc start` in Discord. While nobody is playing,
  it stays stopped and you pay only for the EBS volume
- **Auto-stop**: after 15 minutes with zero players, it saves, backs up the world, and stops itself
- **Failure detection**: three layers of watchers, designed for the case where auto-stop
  itself breaks, plus a budget alarm
- **Everything as code**: one `terraform apply` builds it; one `terraform destroy` removes it all

"Run things only when needed to minimize pay-as-you-go costs", "design for failure with
layered defenses", "manage infrastructure as code" — these are exactly the ideas you use
in professional cloud work.

## Who this is for

- People new to AWS, or people who have touched it but never quite got how the services
  fit together
- Anyone comfortable with basic terminal usage (`cd`, `ls`, running commands)
- Programming experience is not required (though if you can read Python, the bot
  internals are a bonus)

## What it costs

**About $2/month if you never play, about $4.30 for 40 hours of play** (Tokyo region).

| Item | Approx. |
| --- | --- |
| t3a.medium on-demand, 40 h | ~$2.20 |
| EBS gp3 20 GB (billed even while stopped) | ~$1.90 |
| CloudWatch alarm ×1 | $0.10 |
| Lambda / SSM / S3 / DNS | ~$0 (free tier) |
| **Total** | **~$4.30 / month** |

AWS bills for what you use, which makes "forgot to turn it off" the scariest failure
mode. This setup ships with three safety nets — auto-stop, force-stop, and budget
alerts (details in [chapter 07](07-monitoring.md)). If you are still nervous, chapter 01
also sets up an account-wide billing alert.

## The big picture

```
Discord (/mc start)
      │ Interactions Endpoint (HTTP)
      ▼
Lambda Function URL (minecraft-bot)
      │ verify signature → ACK → async self-invoke
      │ ec2:StartInstances
      ▼
   EC2 (t3a.medium)
      │ ① mc-dns: writes its own public IP back to a Cloudflare A record
      │ ② bedrock: the Minecraft server (fetches the latest build at boot)
      │ ③ mc-watchdog: monitors player count
      │    - boot complete → "🟢 server is up" in Discord
      │    - 0 players for 15 min → backup to S3 → stops itself
      ▼
   mc.example.com:19132  ← clients always connect to the same address
```

Two key points:

1. **No Elastic IP.** An EIP is billed while the instance is stopped, so instead the
   instance writes its (changing) public IP back to DNS at every boot — a stable
   address without the standing cost.
2. **The bot is not a daemon.** A Discord bot usually means a 24/7 process; with the
   Interactions Endpoint model, Lambda runs only when a command is typed — $0/month.

## What to prepare

| Item | Notes |
| --- | --- |
| AWS account | We create one in [chapter 01](01-aws-account.md) |
| A domain | DNS managed on Cloudflare (domain cost only; Cloudflare free plan is fine). Route 53 works too — the code here targets Cloudflare; see [chapter 03](03-ec2.md) for why, and how to port |
| Discord account & server | Somewhere to put the bot. Creating a fresh server is fine |
| A work machine | macOS / Linux / WSL, with Terraform >= 1.13, AWS CLI v2, Python 3 |

> **No domain yet?** Registrars like Cloudflare Registrar sell `.dev` / `.com` domains
> for around $10/year. You can technically play by raw IP, but the IP changes on every
> boot in this design, so DNS is effectively required.

## How to work through it

- **Thorough**: read chapters 01 onward in order, then build in chapter 08
- **Hands-on first**: jump straight to [08 Hands-on](08-hands-on.md), get it running,
  then read chapters 02–07 with a live system to poke at

The text is written so that both paths work.

---

Next: [01. Setting up your AWS account](01-aws-account.md)
