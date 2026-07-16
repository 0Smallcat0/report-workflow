"""Allow ``python -m report_workflow`` as a PATH-independent CLI entry point.

On Windows machines with several Python installs, a stale ``report-workflow.exe``
shim from another interpreter can shadow the working install and fail without
printing anything. ``python -m report_workflow`` always runs against the
interpreter you invoke it with, so it is the reliable escape hatch.
"""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
