# 🚀 Quick Start Guide

## Installation (2 minutes)

```bash
# 1. Clone repository
git clone https://github.com/hermasorca13-stack/Orca-Agent-.git
cd Orca-Agent-

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment
cp .env.example .env
# Edit .env with your API keys

# 5. Run the agent
python main.py
```

## API Endpoints

### Health Check
```bash
curl http://localhost:8000/api/health
```

### GitHub Webhook
```bash
POST http://localhost:8000/api/github/webhook
Content-Type: application/json
```

### Manus Sync
```bash
POST http://localhost:8000/api/manus/sync
```

## Configuration

Edit `.env` with:
- `CLAUDE_API_KEY` - Your Claude API key
- `GITHUB_TOKEN` - GitHub personal access token
- `MANUS_API_KEY` - Your Manus API key

## Next Steps

- Read [Architecture Guide](./ARCHITECTURE.md)
- Check [API Reference](./API.md)
- Explore [Examples](../examples/)
