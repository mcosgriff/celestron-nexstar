#!/bin/bash
# Script to remove database files from Git history
# WARNING: This rewrites Git history. Make sure you have a backup!

set -e

echo "This script will remove catalogs.db* files from Git history."
echo "WARNING: This rewrites history and requires force push!"
echo ""
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

# Check if git-filter-repo is available
if command -v git-filter-repo &> /dev/null; then
    echo "Using git-filter-repo..."
    git filter-repo --path src/celestron_nexstar/cli/data/catalogs.db --invert-paths --force
    git filter-repo --path src/celestron_nexstar/cli/data/catalogs.db-shm --invert-paths --force
    git filter-repo --path src/celestron_nexstar/cli/data/catalogs.db-wal --invert-paths --force
    git filter-repo --path src/celestron_nexstar/cli/data/catalogs.db.backup --invert-paths --force
    echo "Done! Now run: git push origin --force --all"
elif command -v bfg &> /dev/null; then
    echo "Using BFG Repo-Cleaner..."
    bfg --delete-files catalogs.db
    bfg --delete-files catalogs.db-shm
    bfg --delete-files catalogs.db-wal
    bfg --delete-files catalogs.db.backup
    git reflog expire --expire=now --all
    git gc --prune=now --aggressive
    echo "Done! Now run: git push origin --force --all"
else
    echo "Neither git-filter-repo nor BFG is installed."
    echo "Installing git-filter-repo is recommended:"
    echo "  pip install git-filter-repo"
    echo ""
    echo "Or use git filter-branch (slower):"
    echo "  git filter-branch --force --index-filter \\"
    echo "    \"git rm --cached --ignore-unmatch src/celestron_nexstar/cli/data/catalogs.db*\" \\"
    echo "    --prune-empty --tag-name-filter cat -- --all"
    exit 1
fi

