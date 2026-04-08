#!/usr/bin/env python3
"""
GitHub Release Preparation Script
This script helps prepare and create releases for the YouTube Downloader project.
Automates version management, changelog generation, and release preparation.
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime
from typing import List, Optional, Tuple

# Constants
DEFAULT_VERSION = "v0.0.0"
MAX_CHANGELOG_COMMITS = 10
COMMIT_LOOKBACK_DAYS = 7

class ReleaseManager:
    """Manages the release preparation process"""
    
    def __init__(self, dry_run: bool = False, force: bool = False):
        self.dry_run = dry_run
        self.force = force
    
    def get_current_version(self) -> str:
        """
        Get current version from git tags
        
        Returns:
            Current version string or default if none exists
        """
        try:
            result = subprocess.run(
                ['git', 'describe', '--tags', '--abbrev=0'], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.stdout.strip() if result.returncode == 0 else DEFAULT_VERSION
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return DEFAULT_VERSION

    def increment_version(self, version: str, increment_type: str = 'patch') -> str:
        """
        Increment version number based on semantic versioning
        
        Args:
            version: Current version string
            increment_type: Type of increment (major, minor, patch)
            
        Returns:
            New version string
        """
        # Remove 'v' prefix if present
        clean_version = version[1:] if version.startswith('v') else version
        
        try:
            parts = clean_version.split('.')
            if len(parts) != 3:
                raise ValueError("Invalid version format")
            
            major, minor, patch = map(int, parts)
            
            if increment_type == 'major':
                major += 1
                minor = 0
                patch = 0
            elif increment_type == 'minor':
                minor += 1
                patch = 0
            elif increment_type == 'patch':
                patch += 1
            else:
                raise ValueError(f"Invalid increment type: {increment_type}")
            
            return f"v{major}.{minor}.{patch}"
        except (ValueError, IndexError) as e:
            print(f"❌ Error parsing version '{version}': {e}")
            return DEFAULT_VERSION

    def create_changelog(self) -> str:
        """
        Create changelog from recent git commits
        
        Returns:
            Formatted changelog string
        """
        try:
            # Get commits from the last week
            result = subprocess.run(
                ['git', 'log', '--oneline', f'--since="{COMMIT_LOOKBACK_DAYS} days ago"'], 
                capture_output=True, 
                text=True,
                timeout=15
            )
            
            if result.returncode != 0:
                return self._get_default_changelog()
            
            commits = result.stdout.strip().split('\n')
            
            if not commits or not commits[0]:
                return self._get_default_changelog()
            
            # Format changelog with recent commits
            changelog = []
            for commit in commits[:MAX_CHANGELOG_COMMITS]:
                if commit.strip():
                    # Clean up commit message
                    commit_msg = commit.split(' ', 1)[1] if ' ' in commit else commit
                    changelog.append(f"- {commit_msg}")
            
            return '\n'.join(changelog) if changelog else self._get_default_changelog()
            
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return self._get_default_changelog()

    def _get_default_changelog(self) -> str:
        """Get default changelog when git commits are not available"""
        return "- Bug fixes and improvements\n- Performance optimizations\n- UI enhancements"

    def check_git_status(self) -> bool:
        """
        Check if git working directory is clean
        
        Returns:
            True if working directory is clean
        """
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'], 
                capture_output=True, 
                text=True,
                timeout=10
            )
            return result.returncode == 0 and result.stdout.strip() == ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def create_git_tag(self, version: str) -> bool:
        """
        Create annotated git tag for version
        
        Args:
            version: Version string to tag
            
        Returns:
            True if tag was created successfully
        """
        if self.dry_run:
            print(f"🔍 DRY RUN: Would create git tag: {version}")
            return True
        
        try:
            subprocess.run(
                ['git', 'tag', '-a', version, '-m', f'Release {version}'], 
                check=True,
                timeout=10
            )
            print(f"✅ Created git tag: {version}")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print(f"❌ Failed to create git tag: {version}")
            return False

    def push_tag(self, version: str) -> bool:
        """
        Push tag to remote repository
        
        Args:
            version: Version tag to push
            
        Returns:
            True if push was successful
        """
        if self.dry_run:
            print(f"🔍 DRY RUN: Would push tag: {version}")
            return True
        
        try:
            subprocess.run(
                ['git', 'push', 'origin', version], 
                check=True,
                timeout=30
            )
            print(f"✅ Pushed tag to remote: {version}")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print(f"❌ Failed to push tag: {version}")
            return False

    def build_local_executable(self) -> bool:
        """
        Build local executable for testing
        
        Returns:
            True if build was successful
        """
        if self.dry_run:
            print("🔍 DRY RUN: Would build local executable")
            return True
        
        print("🔨 Building local executable for testing...")
        
        try:
            if os.name == 'nt':  # Windows
                result = subprocess.run(
                    ['build_exe.bat'], 
                    check=True, 
                    shell=True,
                    timeout=300
                )
            else:  # Linux/macOS
                if sys.platform == 'darwin':
                    # macOS
                    subprocess.run(['chmod', '+x', 'build_macos.sh'], check=True)
                    result = subprocess.run(['./build_macos.sh'], check=True, timeout=300)
                else:
                    # Linux
                    subprocess.run(['chmod', '+x', 'build_linux.sh'], check=True)
                    result = subprocess.run(['./build_linux.sh'], check=True, timeout=300)
            
            print("✅ Local build completed successfully")
            return True
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"❌ Local build failed: {e}")
            return False
        except FileNotFoundError:
            print("❌ Build script not found")
            return False

    def prepare_release(self, version_increment: str) -> int:
        """
        Main release preparation workflow
        
        Args:
            version_increment: Type of version increment
            
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        print("🚀 YouTube Downloader Release Preparation")
        print("=" * 50)
        
        # Check git status
        if not self.force and not self.check_git_status():
            print("❌ Git working directory is not clean. Commit or stash changes first.")
            print("   Use --force to override this check.")
            return 1
        
        # Get version information
        current_version = self.get_current_version()
        new_version = self.increment_version(current_version, version_increment)
        
        print(f"📋 Current version: {current_version}")
        print(f"📋 New version: {new_version}")
        print(f"📋 Increment type: {version_increment}")
        
        # Generate changelog
        changelog = self.create_changelog()
        print(f"\n📝 Changelog:")
        print(changelog)
        
        if self.dry_run:
            print("\n🔍 DRY RUN - No changes will be made")
            print(f"Would create tag: {new_version}")
            print("Would push tag to trigger GitHub Actions build")
            return 0
        
        # Confirm with user
        print(f"\n❓ Create release {new_version}? (y/N): ", end="")
        if input().lower() != 'y':
            print("❌ Release cancelled")
            return 1
        
        return self._execute_release(new_version)

    def _execute_release(self, version: str) -> int:
        """
        Execute the release process
        
        Args:
            version: Version to release
            
        Returns:
            Exit code
        """
        # Build local executable for testing (optional)
        if not self.build_local_executable():
            print("❌ Local build failed. Fix issues before releasing.")
            return 1
        
        # Create and push git tag
        if not self.create_git_tag(version):
            return 1
        
        if not self.push_tag(version):
            return 1
        
        # Success message
        print(f"\n🎉 Release {version} preparation completed!")
        print("📡 GitHub Actions will now build executables for all platforms")
        print("🔗 Check the Actions tab on GitHub for build progress")
        print("📦 Release will be created automatically when builds complete")
        
        return 0

def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Prepare GitHub release for YouTube Downloader',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --version patch          # Increment patch version (default)
  %(prog)s --version minor          # Increment minor version
  %(prog)s --version major          # Increment major version
  %(prog)s --dry-run                # Show what would be done
  %(prog)s --force                  # Force release with uncommitted changes
  %(prog)s --skip-build             # Skip local build test
        """
    )
    
    parser.add_argument(
        '--version', 
        choices=['major', 'minor', 'patch'], 
        default='patch',
        help='Version increment type (default: patch)'
    )
    parser.add_argument(
        '--dry-run', 
        action='store_true',
        help='Show what would be done without actually doing it'
    )
    parser.add_argument(
        '--skip-build', 
        action='store_true',
        help='Skip local build test'
    )
    parser.add_argument(
        '--force', 
        action='store_true',
        help='Force release even with uncommitted changes'
    )
    
    args = parser.parse_args()
    
    # Initialize release manager
    release_manager = ReleaseManager(
        dry_run=args.dry_run,
        force=args.force
    )
    
    # Prepare release
    return release_manager.prepare_release(args.version)

if __name__ == '__main__':
    sys.exit(main()) 