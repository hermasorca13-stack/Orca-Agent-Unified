# 🫍 ORCA Agent - Quick Deploy Guide

## Current Status (July 24, 2026)

### ✅ Active Components:
- **GitHub Repo:** https://github.com/hermasorca13-stack/orca-agent
- **Telegram Bot:** @HermesOrcaXBot
- **Bot Token:** Active and verified
- **Skills:** 24/24 loaded
- **Real APIs Tested:** ✅ Bitcoin, Ethereum, Yahoo Finance, CoinGecko

### 🔧 To Deploy on Oracle Cloud Free Tier:

#### Step 1: Create Oracle Account
1. Go to https://cloud.oracle.com/free
2. Sign up (use hermasorca13@gmail.com)
3. Verify email + add credit card (not charged)

#### Step 2: Create ARM VM
1. Compute → Instances → Create Instance
2. Shape: `VM.Standard.A1.Flex` (4 OCPU, 24GB RAM)
3. Image: Ubuntu 22.04
4. Save SSH keys

#### Step 3: SSH and Deploy
```bash
# From your local machine
ssh -i path/to/key.key ubuntu@<VM_IP>

# Clone ORCA
git clone https://github.com/hermasorca13-stack/orca-agent.git
cd orca-agent

# Install
pip3 install -r requirements.txt

# Configure
cp .env.example .env
nano .env  # Add: TELEGRAM_BOT_TOKEN=8251930364:...

# Run
python3 main.py
```

#### Step 4: Keep it running 24/7
```bash
sudo bash deployment/oracle_setup.sh
```

This installs as systemd service that auto-starts on boot.

## 💰 Cost: $0/month forever

Oracle Cloud Free Tier includes:
- 4 ARM cores
- 24GB RAM  
- 200GB storage
- 10TB bandwidth/month

## 📊 What You Get:
- 24 AI skills
- Persistent memory
- Multi-modal (text, voice, images)
- Multi-LLM support
- Health monitoring
- Auto-restart
- 24/7 availability
