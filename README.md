# VaaniKit

Open-source Indian-language-first starter kit for building tool-using voice agents.

## Quick Start

```bash
# Install dependencies
make install

# Copy environment file
cp .env.example .env
# Edit .env with your Gnani API key and database URL

# Start the development server
make dev

# Check health endpoint
curl http://localhost:8000/health
```

## Configuration

Edit `agent.yaml` to configure:
- Agent language and persona
- Model settings (Gnani Prisma for STT, Timbre for TTS)
- Available tools
- Database connection

## Documentation

- [Execution Plan](docs/VaaniKit_Execution_Plan_Nov1-6.md)
- [Integration Notes](docs/integration-notes.md)

## License

Apache-2.0
