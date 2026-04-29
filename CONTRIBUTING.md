# Contributing

Thanks for helping make old documentation easier and safer to search.

## Development

```bash
conda env create -f environment.yml
conda activate chmseek-dev
python -m pip install -e .
pytest
```

Keep changes small and testable. The test suite must remain runnable without proprietary CHM
files or network access.

## Security Expectations

- Do not execute CHM-derived content.
- Do not add `shell`-based subprocess calls.
- Do not add unsafe archive extraction.
- Keep model download and remote code execution behind explicit user flags.
- Prefer clear JSON errors with actionable hints.

## Before Opening A PR

```bash
pytest
chmseek audit
```
