#!/usr/bin/env python3
"""
GitHub Release Preparation Script
This script helps prepare and create releases for the YouTube Downloader project.
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime

def get_current_version():
    """Get current version from git tags"""
    try:
        result = subprocess.run(['git', 'describe', '--tags', '--abbrev=0'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return "v0.0.0"
    except Exception:
        return "v0.0.0"

def increment_version(version, increment_type='patch'):
    """Increment version number"""
    # Remove 'v' prefix if present
    if version.startswith('v'):
        version = version[1:]
    
    parts = version.split('.')
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    
    if increment_type == 'major':
        major += 1
        minor = 0
        patch = 0
    elif increment_type == 'minor':
        minor += 1
        patch = 0
    elif increment_type == 'patch':
        patch += 1
    
    return f"v{major}.{minor}.{patch}"

def create_changelog():
    """Create changelog from git commits"""
    try:
        # Get commits since last tag
        result = subprocess.run(['git', 'log', '--oneline', '--since="1 week ago"'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            commits = result.stdout.strip().split('\n')
            if commits and commits[0]:
                changelog = []
                for commit in commits[:10]:  # Last 10 commits
                    if commit.strip():
                        changelog.append(f"- {commit}")
                return '\n'.join(changelog)
        return "- Bug fixes and improvements"
    except Exception:
        return "- Bug fixes and improvements"

def check_git_status():
    """Check if git working directory is clean"""
    try:
        result = subprocess.run(['git', 'status', '--porcelain'], 
                              capture_output=True, text=True)
        return result.stdout.strip() == ""
    except Exception:
        return False

def create_git_tag(version):
    """Create git tag for version"""
    try:
        # Create annotated tag
        subprocess.run(['git', 'tag', '-a', version, '-m', f'Release {version}'], 
                      check=True)
        print(f"✅ Created git tag: {version}")
        return True
    except subprocess.CalledProcessError:
        print(f"❌ Failed to create git tag: {version}")
        return False

def push_tag(version):
    """Push tag to remote repository"""
    try:
        subprocess.run(['git', 'push', 'origin', version], check=True)
        print(f"✅ Pushed tag to remote: {version}")
        return True
    except subprocess.CalledProcessError:
        print(f"❌ Failed to push tag: {version}")
        return False

def build_local_executable():
    """Build local executable for testing"""
    print("🔨 Building local executable for testing...")
    try:
        if os.name == 'nt':  # Windows
            subprocess.run(['build_exe.bat'], check=True, shell=True)
        else:  # Linux/macOS
            if sys.platform == 'darwin':
                subprocess.run(['chmod', '+x', 'build_macos.sh'], check=True)
                subprocess.run(['./build_macos.sh'], check=True)
            else:
                subprocess.run(['chmod', '+x', 'build_linux.sh'], check=True)
                subprocess.run(['./build_linux.sh'], check=True)
        print("✅ Local build completed successfully")
        return True
    except subprocess.CalledProcessError:
        print("❌ Local build failed")
        return False

def main():
    parser = argparse.ArgumentParser(description='Prepare GitHub release')
    parser.add_argument('--version', choices=['major', 'minor', 'patch'], 
                       default='patch', help='Version increment type')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be done without actually doing it')
    parser.add_argument('--skip-build', action='store_true', 
                       help='Skip local build test')
    parser.add_argument('--force', action='store_true', 
                       help='Force release even with uncommitted changes')
    
    args = parser.parse_args()
    
    print("🚀 YouTube Downloader Release Preparation")
    print("=" * 50)
    
    # Check git status
    if not args.force and not check_git_status():
        print("❌ Git working directory is not clean. Commit or stash changes first.")
        print("   Use --force to override this check.")
        return 1
    
    # Get current version and calculate new version
    current_version = get_current_version()
    new_version = increment_version(current_version, args.version)
    
    print(f"📋 Current version: {current_version}")
    print(f"📋 New version: {new_version}")
    print(f"📋 Increment type: {args.version}")
    
    # Generate changelog
    changelog = create_changelog()
    print(f"\n📝 Changelog:")
    print(changelog)
    
    if args.dry_run:
        print("\n🔍 DRY RUN - No changes will be made")
        print(f"Would create tag: {new_version}")
        print("Would push tag to trigger GitHub Actions build")
        return 0
    
    # Confirm with user
    print(f"\n❓ Create release {new_version}? (y/N): ", end="")
    if input().lower() != 'y':
        print("❌ Release cancelled")
        return 1
    
    # Build local executable for testing (optional)
    if not args.skip_build:
        if not build_local_executable():
            print("❌ Local build failed. Fix issues before releasing.")
            return 1
    
    # Create and push git tag
    if not create_git_tag(new_version):
        return 1
    
    if not push_tag(new_version):
        return 1
    
    print(f"\n🎉 Release {new_version} preparation completed!")
    print("📡 GitHub Actions will now build executables for all platforms")
    print("🔗 Check the Actions tab on GitHub for build progress")
    print("📦 Release will be created automatically when builds complete")
    
    return 0

if __name__ == '__main__':
    sys.exit(main()) 