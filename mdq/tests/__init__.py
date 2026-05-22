"""Repository-independent unit tests for the mdq package.

Each test creates an isolated tmp directory containing its own Markdown
fixtures, so the suite can be run in any workspace by simply:

    python -m pytest mdq/tests -q
"""
