# Security Policy

## Supported Versions

`chmseek` is currently pre-1.0. Security fixes are applied to the latest released version.

## Reporting A Vulnerability

Please open a private security advisory on GitHub, or contact the repository owner before filing a
public issue. Include:

- the affected version or commit
- the operating system
- a minimal reproduction, if safe to share
- whether the issue involves a malicious CHM file or model-loading behavior

## Threat Model

`chmseek` treats CHM files as untrusted input. The tool must not execute, render, launch, or fetch
content from CHM-derived files. Model download and remote model code are also explicit trust
boundaries.

Before release, run:

```bash
chmseek audit
pytest
```
