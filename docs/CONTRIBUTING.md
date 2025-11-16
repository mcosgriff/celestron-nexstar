# Contributing Guide

## Commit Message Format

This project uses [Conventional Commits](https://www.conventionalcommits.org/) for automatic semantic versioning. Please format your commit messages as follows:

### Format

```text
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: A new feature (bumps MINOR version)
- `fix`: A bug fix (bumps PATCH version)
- `docs`: Documentation only changes
- `style`: Code style changes (formatting, missing semi colons, etc.)
- `refactor`: Code refactoring without feature changes or bug fixes
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks, dependency updates, etc.
- `ci`: CI/CD changes
- `build`: Build system changes

### Breaking Changes

To indicate a breaking change (bumps MAJOR version), add `BREAKING CHANGE:` in the footer:

```text
feat(api): add new authentication system

BREAKING CHANGE: The authentication API has been completely rewritten.
Old authentication tokens are no longer valid.
```

Or use `!` after the type/scope:

```text
feat(api)!: add new authentication system
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

# Documentation
git commit -m "docs: update installation instructions"

# Multiple changes
git commit -m "feat(telescope): add diagonal movement support

- Add up-left, up-right, down-left, down-right directions
- Update Direction enum with diagonal options
- Add tests for diagonal movement"
```

### Scope (Optional)

The scope should be the area of the codebase affected:

- `telescope`: Telescope control functionality
- `protocol`: Low-level protocol implementation
- `api`: High-level API
- `cli`: Command-line interface
- `database`: Database operations
- `docs`: Documentation
- `ci`: CI/CD configuration

### Automatic Versioning

When you push to the `main` branch, semantic-release will:

1. Analyze commit messages since the last release
2. Determine the next version number (major.minor.patch)
3. Update version in `pyproject.toml` and `__init__.py` files
4. Generate/update `CHANGELOG.md`
5. Create a git tag
6. Create a GitHub release

### Version Bump Rules

- **PATCH** (0.1.0 → 0.1.1): Bug fixes (`fix:`)
- **MINOR** (0.1.0 → 0.2.0): New features (`feat:`)
- **MAJOR** (1.0.0 → 2.0.0): Breaking changes (`BREAKING CHANGE:` or `!`)

### Testing Locally

You can test semantic-release locally:

```bash
# Dry run to see what would happen
uv run semantic-release version --dry-run

# Actually create a release (only if commits warrant it)
uv run semantic-release version
uv run semantic-release publish
```
