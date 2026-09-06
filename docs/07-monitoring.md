# 07. Monitoring and cost control — design for failure

Files: `monitoring.tf` / `budget.tf` / `lambda.tf` (EventBridge) / `server/idle-watchdog.py` / `server/alert.sh`

The scariest failure here is "auto-stop breaks and the server runs with nobody playing"
— about $20/month at 24/7. So shutdown is guarded by an almost excessive
**three detection layers plus two safety nets**, where any single failure is caught by
another layer. Read it as a miniature of distributed-systems design.

## The three detection layers

| Layer | Catches | Mechanism |
| --- | --- | --- |
| ① watchdog (in-instance) | normal idleness | 0 players for 15 min → notify → backup → stop itself |
| ② systemd OnFailure | crashes of the server or the watchdog itself | `mc-alert@.service` notifies Discord with the journal tail |
| ③ EventBridge + Lambda | OS death, OOM, manual stop, terminate | catches state-change events **from outside the instance** |

Layer ③ is the point. Layers ① and ② run inside the instance, so if the instance dies,
they die with it. EventBridge is AWS's event bus: it delivers "this EC2 went
stopped/terminated" outside the instance, and the notifier Lambda relays it to Discord.

```hcl
event_pattern = jsonencode({
  source      = ["aws.ec2"]
  detail-type = ["EC2 Instance State-change Notification"]
  detail      = { state = ["stopped", "terminated"], ... }
})
```

**Monitoring must not share the fate of the thing it monitors** — a fundamental of
monitoring design, on display here.

### Telling normal stops from abnormal ones — tags as flags

Built naively, layer ③ would also fire on layer ①'s perfectly normal auto-stop. So just
before stopping, the watchdog puts an `mc:StopReason=idle` tag on the instance. When
the notifier receives a stopped event, it checks that tag first: present → normal stop,
stay quiet, delete the tag. **Stopped with no tag = abnormal.**

Using EC2 tags as inter-process flags is a neat trick: `/mc stop` (a stop request) and
allowlist reload requests ride the same mechanism. Notice the whole system coordinates
its components without a single database.

## Safety net ①: force-stop via CloudWatch alarm

Insurance for the worst case — the watchdog itself dies and no notification comes:

```hcl
metric_name         = "NetworkOut"
threshold           = 50000   # bytes per 5 min
evaluation_periods  = 6       # fires after 30 minutes
alarm_actions       = ["arn:aws:automate:${local.region}:ec2:stop"]
```

"NetworkOut near zero for 30 minutes = running with nobody connected" is detected from
CloudWatch metrics, and the **alarm action stops the instance directly** (no Lambda
involved). The 50 KB / 5 min threshold sits above the constant noise of the SSM agent
and far below in-game traffic. `treat_missing_data = "notBreaching"` keeps the alarm
quiet while the instance is stopped (no metrics arriving). Cost: $0.10/month for one alarm.

## Safety net ②: AWS Budgets — the bill itself, watched

Even if every mechanism above fails, **the bill doesn't lie**. `budget.tf` sets a $5
monthly budget on costs tagged `Project=Minecraft`, with two notifications:

- **Actual cost reaches 80%** ($4) → early "using a bit much this month?" signal
- **Forecast exceeds 100%** → near-certain detection of a stuck instance
  (at 24/7 burn, the forecast spikes even early in the month)

Alerts flow SNS topic → notifier Lambda → Discord. The SNS topic policy allowing
publish only from `budgets.amazonaws.com` is another standard service-to-service
integration pattern worth noting.

> Prerequisite: activate the `Project` cost allocation tag in the Billing console
> (chapter 01). Skip it and the tag filter reads $0 forever — the budget never fires.

## Summary: protect your wallet with design, not vigilance

| Mechanism | Protects against |
| --- | --- |
| auto-stop (watchdog) | everyday forgetting |
| NetworkOut alarm | watchdog failure |
| Budgets $5 | everything unforeseen above |
| account-wide budget (ch. 01) | leftovers outside this project |

Not "be careful" but "make it impossible to fail silently". Once this attitude sticks,
even a personal learning account becomes a safe place to experiment.

---

Previous: [06. Lambda and the Discord bot](06-lambda-discord.md) / Next: [08. Hands-on](08-hands-on.md)
