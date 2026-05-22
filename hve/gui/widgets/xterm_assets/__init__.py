"""Data-only package for xterm.js assets bundled with hve.gui.widgets.

This package contains no Python code; it exists so that setuptools picks up
`xterm.js`, `xterm.css`, addon JS, `index.html`, and `bridge.js` as
``package_data`` during wheel build. See ``[tool.setuptools.package-data]``
in ``pyproject.toml``.
"""
