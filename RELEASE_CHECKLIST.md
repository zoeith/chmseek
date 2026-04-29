# Release Checklist

## 0.1.0

- [ ] Confirm `README.md` examples match the released package name.
- [ ] Create and activate the Conda environment:
  `conda env create -f environment.yml && conda activate chmseek-dev`
- [ ] Install editable package: `python -m pip install -e .`
- [ ] Run tests: `pytest`
- [ ] Run diagnostics: `chmseek diagnose`
- [ ] Run audit: `chmseek audit`
- [ ] Build package from the Conda env: `python -m build --no-isolation`
- [ ] Inspect wheel/sdist contents.
- [ ] Create GitHub repository.
- [ ] Push `main`.
- [ ] Tag release: `git tag v0.1.0 && git push origin v0.1.0`
- [ ] Publish GitHub Release using `CHANGELOG.md` notes.
- [ ] Optionally publish to PyPI after a final maintainer review.
