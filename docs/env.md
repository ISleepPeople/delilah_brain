# Environment Variables & Secrets Policy

## Rules
- Real secrets are never committed to Git.
- `.env` and `.env.*` are ignored.
- `.env.example` is committed as a template only.

## Usage
1. Copy `.env.example` to `.env`
2. Fill in real values on the server only
3. Restart services as needed
