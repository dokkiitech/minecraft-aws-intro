# 06. Lambda and the Discord bot

Files: `lambda.tf` / `bot/lambda_function.py` / `bot/register_commands.py` / `bot/build.sh`

## Choosing serverless

Discord bots are normally built as processes holding a persistent Gateway (WebSocket)
connection. But a resident process needs somewhere to live, and even a small Fargate
task or EC2 instance runs $8–10/month — **the bot would cost more than the game server**.

Instead we use Discord's **Interactions Endpoint** model: when a slash command is typed,
Discord sends an HTTP POST to a URL you specify. Point that URL at **Lambda**, and code
runs only in the moment a command arrives. At this usage level it stays within the free
tier — $0/month.

"Borrow compute only when an event happens" is the serverless mindset. Recognizing that
a process invoked a few dozen times a month does not deserve an always-on server is a
big step up in cloud cost design.

## Function URLs — an HTTP endpoint without API Gateway

```hcl
resource "aws_lambda_function_url" "bot" {
  function_name      = aws_lambda_function.bot.function_name
  authorization_type = "NONE"
}
```

Lambda can expose a dedicated HTTPS endpoint directly (simpler and cheaper than putting
API Gateway in front). `NONE` means anyone can hit the URL — but it is not
unauthenticated: **authentication happens at the application layer via Ed25519
signature verification** (next section).

With `authorization_type = "NONE"`, the AWS provider creates both public invocation
permissions required by current Lambda Function URL behavior.

## Signature verification — rejecting forged requests

Discord signs every request (`X-Signature-Ed25519`). The bot verifies it with the
public key from the Developer Portal and returns 401 on failure (top of
`bot/lambda_function.py`).

The fun part is Discord's own check: the moment you save an Interactions Endpoint URL,
Discord sends a PING **and a request with a deliberately broken signature**, and only
registers the endpoint if you correctly return 401. A bot that skips signature
verification cannot even be registered.

## The 3-second rule and async self-invocation

Discord requires a response to a command **within 3 seconds** — but a full EC2 boot
takes 60–90 seconds. So:

1. Synchronous side: verify the signature → immediately return a "deferred" ACK (type 5)
2. Just before that, **invoke itself asynchronously** (`InvocationType='Event'`)
3. Async side: `ec2:StartInstances` → wait until a RakNet ping succeeds → edit the
   original message via the follow-up API to "🟢 up — `mc.example.com:19132`"

"ACK fast, do the heavy work in the background" is a standard pattern for webhook
integrations everywhere. The interaction token lives 15 minutes, so the wait cap
(`BOOT_TIMEOUT=150s`) and the Lambda timeout (180s) both sit comfortably inside it.

## Deployment packages and arm64

The bot verifies signatures with PyNaCl (a native extension), so the zip must contain
wheels built for the Lambda runtime (arm64 / Python 3.12). That is `bot/build.sh`:

```sh
pip3 install --target package \
  --platform manylinux2014_aarch64 --python-version 3.12 --only-binary=:all: \
  "PyNaCl>=1.5,<2" "mcstatus>=11,<15"
```

Bundling binaries built for your own laptop and getting ImportError on Lambda is the
single most common Lambda pitfall. Note the Lambdas themselves run on arm64 (Graviton):
cheaper than x86, and Python code runs unchanged — only the Bedrock server binary
demands x86_64.

## Create log groups in Terraform, not implicitly

```hcl
resource "aws_cloudwatch_log_group" "bot" {
  name              = "/aws/lambda/minecraft-bot"
  retention_in_days = 30
}
```

If you let Lambda auto-create its log group, retention is **never expire** and junk
accumulates forever. Creating the group in Terraform with a retention period is the
standard move.

## The second Lambda — notifier

`notifier_lambda.py` is a notification-only function that relays abnormal EC2 stops
(chapter 07) and budget alerts to Discord. It has zero dependencies (boto3 + urllib),
so Terraform zips it directly with the `archive_file` data source — a nice contrast in
deployment methods depending on whether dependencies exist.

---

Previous: [05. S3 and SSM Parameter Store](05-s3-ssm.md) / Next: [07. Monitoring and cost control](07-monitoring.md)
