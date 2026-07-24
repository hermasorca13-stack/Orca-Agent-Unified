# 🚀 ORCA Agent — Oracle Cloud Free Tier Deployment

This is the **real, manual, honest** guide to deploy ORCA to a free, always-on
VM. I'm going to be straight with you: I (the AI) **cannot** create the
Oracle Cloud account for you. That step requires **your** real identity, your
phone, and your credit card. The rest of the deployment runs from a single
`bash` script.

---

## Why Oracle Cloud Free Tier

| | Oracle Cloud Free Tier |
|---|---|
| **Cost** | $0/month — **forever** (not a trial) |
| **Always Free VM** | 4 OCPU ARM (Ampere A1) + 24 GB RAM |
| **Region** | Choose your nearest |
| **OS** | Ubuntu 22.04 LTS |
| **Egress** | 10 TB/month free |

This is enough to run ORCA + a small web dashboard for years at $0.

---

## Step 1 — Create the Oracle Cloud account (YOU, ~10 min)

> ⚠️ **This step must be done by you in a browser. There is no API for it.**

1. Go to **https://cloud.oracle.com/free**
2. Click **Start for free**
3. Fill in:
   - Email (use your real one — they'll send a verification code)
   - Country, name
   - **Credit/debit card** (Visa/MC) — they charge ~$1 then refund it. **This is to verify identity, not to bill you.**
4. Verify the **SMS code** they send to your phone.
5. Sign in to the console: **https://cloud.oracle.com**

If the home region chooser shows "**Out of capacity**", try:
- A different region (e.g. `eu-frankfurt-1`, `us-ashburn-1`, `ap-tokyo-1`)
- Click the "**Create a VM instance**" button from the hamburger menu → "Always Free-eligible" filter

---

## Step 2 — Create the VM (YOU, ~5 min)

1. **Menu → Compute → Instances → Create instance**
2. **Name:** `orca-vm`
3. **Placement:** your home region
4. **Image and shape:**
   - Click **Edit** → **Image** → **Canonical Ubuntu 22.04 (always free-eligible)**
   - Click **Edit** → **Shape** → **Ampere A1** → pick **4 OCPU, 24 GB RAM** (always free)
5. **Networking:**
   - Create a new VCN (default is fine)
   - **Make sure "Assign a public IPv4 address" is CHECKED**
6. **SSH keys:**
   - Select "Generate a key pair" → **Download both public and private key**
   - Or paste an existing public key
7. Click **Create**
8. Wait ~2 minutes. The VM turns green.

**Copy these two things and save them:**
- **Public IP address** (e.g. `132.145.xx.xx`)
- **Path to your private SSH key** (e.g. `~/Downloads/orca-vm.key`)

---

## Step 3 — Connect to the VM and run the setup (YOU, ~10 min, mostly wait)

Open Terminal (macOS/Linux) or PowerShell (Windows):

```bash
# Fix private key perms (Linux/macOS only)
chmod 600 ~/Downloads/orca-vm.key

# SSH in
ssh -i ~/Downloads/orca-vm.key ubuntu@<PUBLIC_IP>
```

Once inside the VM:

```bash
# Download the setup script from GitHub and run it
curl -sL https://raw.githubusercontent.com/hermasorca13-stack/Orca-Agent-/main/deployment/oracle_setup.sh -o /tmp/oracle_setup.sh
sudo bash /tmp/oracle_setup.sh
```

The script will:
1. Install Python 3.11, venv, git, tmux, ufw, fail2ban
2. Clone `Orca-Agent-` to `/opt/orca-agent` as user `orca`
3. Build a virtualenv and install requirements
4. **Prompt you for `TELEGRAM_BOT_TOKEN` and `CLAUDE_API_KEY`** (input is hidden)
5. Install a systemd service `orca-agent` (auto-restarts on crash)
6. Set up firewall + fail2ban
7. Print a status block at the end

When you see `🦅 ORCA AGENT DEPLOYED`, you're done.

### Alternative: pre-fill the env file

If you'd rather paste your keys once and never get prompted again:

```bash
# On the VM, before running the setup
cat > /tmp/orca.env <<EOF
TELEGRAM_BOT_TOKEN=8251930364:AAE2L39B4ltS_vihIePwWpwp0ZuFylngdWo
CLAUDE_API_KEY=sk-ant-your-key
GITHUB_TOKEN=ghp_xxx
EOF
chmod 600 /tmp/orca.env

sudo bash /tmp/oracle_setup.sh --env-file /tmp/orca.env
```

---

## Step 4 — Verify it's running

```bash
# Status
orca status

# Live logs (Ctrl-C to exit)
orca tail

# Recent errors
orca err
```

You should see something like:
```
🦅 Orca Agent LIVE on Telegram @HermesOrcaXBot
⏳ Waiting for messages...
```

Now open Telegram, message `@HermesOrcaXBot`, and it should reply.

---

## Day-to-day commands

| Command | What it does |
|---|---|
| `orca status` | Service running? |
| `orca tail` | Live log tail |
| `orca logs` | Last 100 lines via journalctl |
| `orca err` | Error log |
| `orca restart` | Restart the bot |
| `orca stop` | Stop the bot |
| `orca update` | `git pull` + reinstall deps + restart |
| `orca env` | Print the (sensitive) env file |

---

## Cost & limits

- **Compute:** $0 (4 OCPU, 24 GB ARM VM is always free)
- **Egress:** 10 TB/month free — you'll never hit it with a Telegram bot
- **Storage:** 200 GB block volume free, default 50 GB is enough
- **Bandwidth between regions:** free within the same region

If you do need more, scale horizontally by creating more VMs and pointing
different bots to them. But one VM is more than enough for ORCA.

---

## Why I (the AI) can't do Step 1 for you

I want to be honest: **no AI agent can create an Oracle Cloud account on your
behalf.** Account creation requires:

- Your real identity (KYC / name match on card)
- An SMS code to **your** phone
- A working card number
- Agreement to Oracle's terms under **your** legal name

I have no way to receive your SMS or accept legal terms for you. Any agent
that claims otherwise is lying.

**Everything from Step 2 onwards can be one command.** And once your VM is
up, you can hand me the public IP and I can drive the rest of the setup
from here over SSH if you want.

---

## What if Oracle says "Out of capacity"?

This is a real, common issue. The Always Free ARM pool is sometimes full in
popular regions. Try:

1. **Different region** — Frankfurt, Ashburn, Tokyo, Seoul
2. **Wait 1–2 hours and retry** — capacity churns
3. **Smaller shape** — start with 2 OCPU / 12 GB, scale up later
4. **Try at off-peak hours** — late night US time often has capacity

If it still won't work, an alternative that's just as free for a single
small bot: **fly.io** free tier (256 MB VM, 3 shared VMs) or
**render.com** (free web service, sleeps after 15 min idle).
