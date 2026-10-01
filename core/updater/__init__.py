"""
core/updater

Checks GitHub Releases for a newer build, downloads it, verifies it, and hands
the actual replacement over to the standalone updater process. The GUI only
talks to this package, never to the GitHub API directly.
"""
