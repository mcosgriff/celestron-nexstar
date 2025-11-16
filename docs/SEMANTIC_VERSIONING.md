# Semantic Versioning Setup

This project uses [python-semantic-release](https://python-semantic-release.readthedocs.io/) to automatically manage version numbers based on commit messages.

## How It Works

When you push commits to the `main` branch, the GitHub Actions workflow analyzes your commit messages and:

1. **Determines the next version** based on conventional commits:
   - `feat:` → Minor version bump (0.1.0 → 0.2.0)
   - `fix:` → Patch version bump (0.1.0 → 0.1.1)
   - `BREAKING CHANGE:` or `!` → Major version bump (0.1.0 → 1.0.0)

2. **Updates version numbers** in:
   - `pyproject.toml`
   - `src/celestron_nexstar/__init__.py`
   - `src/celestron_nexstar/cli/__init__.py`

3. **Generates/updates** `CHANGELOG.md`

4. **Creates a git tag** (e.g., `v0.2.0`)

5. **Creates a GitHub release** with release notes

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```html
<type>(<scope>): <subject>

<body>

<footer>
```

### Examples

```bash
# Feature (minor version bump)
git commit -m "feat(telescope): add step movement function"

# Bug fix (patch version bump)
git commit -m "fix(protocol): handle connection timeout errors"

# Breaking change (major version bump)
git commit -m "feat(api)!: refactor coordinate system

BREAKING CHANGE: Coordinate system now uses radians instead of degrees"

# Multiple changes
git commit -m "feat(telescope): add diagonal movement support

- Add up-left, up-right, down-left, down-right directions
- Update Direction enum with diagonal options
- Add tests for diagonal movement"
```

## Testing Locally

You can test semantic-release locally before pushing:

```bash
# Install dependencies
uv sync --all-extras --dev

# Dry run to see what would happen (won't make changes)
uv run python -m semantic_release --noop version

# Actually create a release (only if commits warrant it)
uv run python -m semantic_release version
uv run python -m semantic_release publish
```

## Configuration

Configuration is in `pyproject.toml` under `[tool.semantic_release]`:

- `version_variable`: Files where version is stored
- `changelog_file`: Path to changelog
- `upload_to_pypi`: Set to `true` when ready to auto-publish to PyPI
- `major_on_zero`: Treat 0.x versions as pre-release (set to `false`)

## Workflow

The `.github/workflows/release.yml` workflow runs on every push to `main`:

1. Checks out the repository
2. Installs dependencies
3. Runs `semantic-release version` to determine and update version
4. Runs `semantic-release publish` to create tag and GitHub release

## Version Bump Rules

- **PATCH** (0.1.0 → 0.1.1): Bug fixes (`fix:`)
- **MINOR** (0.1.0 → 0.2.0): New features (`feat:`)
- **MAJOR** (1.0.0 → 2.0.0): Breaking changes (`BREAKING CHANGE:` or `!`)

## Skipping Releases

If you want to skip a release for a commit, use:

```bash
git commit -m "docs: update README [skip release]"
```

Or use `[skip ci]` to skip the entire workflow.

## Manual Release

If you need to manually trigger a release:

```bash
# Bump version manually
uv run semantic-release version --noop  # Dry run first
uv run semantic-release version

# Publish
uv run semantic-release publish
```

## Troubleshooting

### Version not updating

- Check that commit messages follow conventional commit format
- Ensure commits are on the `main` branch
- Check GitHub Actions logs for errors

### Multiple version files out of sync

The tool automatically updates all files listed in `version_variable`. If they get out of sync, run:

```bash
uv run python -m semantic_release version --noop
```

This will show what would be updated without making changes.
