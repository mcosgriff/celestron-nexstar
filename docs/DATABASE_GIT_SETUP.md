# Database File Git Setup

## Problem

The `catalogs.db` file can grow large (100+ MB) when light pollution data is imported, exceeding GitHub's 100 MB file size limit.

## Solution

The database file is now excluded from Git version control. Users should generate their own database by importing catalogs.

## Setup Instructions

### For New Clones

1. Clone the repository (database file won't be included)
2. Import catalogs to generate the database:
   ```bash
   nexstar data import openngc
   ```

### For Existing Repositories

**IMMEDIATE FIX** (if you can't push due to large file in history):

```bash
# Step 1: Remove from Git tracking (already done, but verify)
git rm --cached src/celestron_nexstar/cli/data/catalogs.db*

# Step 2: Commit the removal
git commit -m "Remove database files from version control"

# Step 3: Remove from Git history (choose one method below)
```

**Option 1: Using git-filter-repo (Recommended - Fastest)**

```bash
# Install git-filter-repo
pip install git-filter-repo

# Remove database files from all history
git filter-repo --path src/celestron_nexstar/cli/data/catalogs.db --invert-paths --force
git filter-repo --path src/celestron_nexstar/cli/data/catalogs.db-shm --invert-paths --force
git filter-repo --path src/celestron_nexstar/cli/data/catalogs.db-wal --invert-paths --force
git filter-repo --path src/celestron_nexstar/cli/data/catalogs.db.backup --invert-paths --force

# Force push (WARNING: rewrites history)
git push origin --force --all
```

**Option 2: Using BFG Repo-Cleaner (Fast)**

```bash
# Download BFG from https://rtyley.github.io/bfg-repo-cleaner/
# Or install: brew install bfg (macOS) or download JAR

# Remove database files
bfg --delete-files catalogs.db
bfg --delete-files catalogs.db-shm
bfg --delete-files catalogs.db-wal
bfg --delete-files catalogs.db.backup

# Clean up
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# Force push (WARNING: rewrites history)
git push origin --force --all
```

**Option 3: Using git filter-branch (Slow but works without extra tools)**

```bash
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch src/celestron_nexstar/cli/data/catalogs.db*" \
  --prune-empty --tag-name-filter cat -- --all

# Force push (WARNING: rewrites history)
git push origin --force --all
```

## Why Database Files Shouldn't Be in Git

1. **Size**: Database files can grow very large (100+ MB)
2. **Generated**: The database is created from catalog imports
3. **User-specific**: Different users may have different data
4. **GitHub limits**: GitHub has a 100 MB file size limit

## Alternative: Git LFS (Not Recommended)

If you really need to track the database file, you could use Git LFS:

```bash
# Install Git LFS
git lfs install

# Track database files with LFS
git lfs track "*.db"

# Add .gitattributes
git add .gitattributes
```

However, this is **not recommended** because:
- Git LFS has bandwidth limits
- Database files change frequently
- Users should generate their own databases

## Recommended Approach

**Don't track database files in Git.** Instead:
- Include catalog source files (YAML, etc.)
- Provide import commands to generate the database
- Document the setup process

This keeps the repository small and allows users to customize their database.

