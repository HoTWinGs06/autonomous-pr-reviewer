# Contributing to Autonomous PR Reviewer

Thanks for your interest in improving this project.

## How to Contribute

1. **Fork the repository** and clone your fork locally.
2. **Create a branch** for your change:
   ```bash
   git checkout -b feature/my-improvement
   ```
3. **Make your changes** and add tests under `tests/`.
4. **Run the test suite**:
   ```bash
   pytest tests/ -v
   ```
5. **Run linting**:
   ```bash
   flake8 app tests --max-line-length=100
   ```
6. **Commit with a clear message**:
   ```bash
   git commit -m "feat: add my improvement"
   ```
7. **Push and open a PR** against `main`.

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/).
- Use `black .` for formatting.
- Keep functions small and focused.
- Add tests for new behavior; update tests for changed behavior.

## Reporting Issues

When opening an issue, include:
- Steps to reproduce
- Expected behavior vs actual behavior
- Logs / stack traces if applicable
- Environment details (Python version, Docker version, OS)

## Security

- Never commit secrets, tokens, or credentials.
- Report security vulnerabilities privately rather than in public issues.
