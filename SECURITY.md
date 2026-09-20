# Security Policy

## Supported Versions

Only the latest `main` branch is actively maintained.

## Reporting a Vulnerability

Please do **not** open a public issue for a security vulnerability. Contact the repository owner privately through GitHub or use GitHub's private vulnerability reporting if enabled.

Include:

- A clear description of the vulnerability
- Reproduction steps or a proof of concept
- Affected versions or commits
- Any suggested mitigation

Please do not include real credentials, tokens, or private customer data in reports.

## Security Design Notes

- Webhook requests are authenticated with HMAC-SHA256.
- Linters run in Docker containers and should receive only file content, not repository credentials.
- Auto-fix is disabled by default and only permits whitespace-only rules (`W291`, `W292`, `W293`).
- Secrets belong in environment variables or a secret manager, never in the repository or container image.
