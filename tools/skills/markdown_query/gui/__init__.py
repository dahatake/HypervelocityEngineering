"""tools.skills.markdown_query.gui - Standalone GUI for the markdown-query Skill.

This package contains a self-contained Qt (PySide6) settings panel and a
standalone window that can be launched independently of the HVE GUI.

When this directory is copied into another repository, the launcher scripts
(launch-gui.{cmd,ps1,sh}) prepend ``vendor/`` to ``sys.path`` so that the
vendored ``mdq`` package becomes importable.
"""
