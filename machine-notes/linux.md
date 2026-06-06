# Linux Machine Notes

## 2026-05-02 - Ubuntu/WSL - pending

Goal:

Prove the Ubuntu setup and run path from a GitHub checkout.

Suggested first commands:

```bash
git clone https://github.com/bandsight/vic.git
cd vic
bash scripts/setup-ubuntu.sh
bash scripts/run-ubuntu.sh
```

If the target cannot reach or trust PyPI:

```bash
OFFLINE=1 bash scripts/setup-ubuntu.sh
```

That offline command requires `vendor/python-wheels` to be present in the checkout or copied in from a dependency-bundled package.

Result:

Not run yet.

Blockers:

The current Windows host has `wsl.exe`, but no WSL distro is installed, so Ubuntu validation could not be run here.

Next suggested action:

On the Linux machine, clone the repo, run setup, capture the first failure if any, and add the result below this section.
