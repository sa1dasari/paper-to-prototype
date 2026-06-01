"""Allow `python -m src <pdf>` invocation.

On Windows the default Proactor event loop does not implement the "add_reader"
family required by Tornado/zmq; that causes a noisy RuntimeWarning at runtime.
Set the selector event loop policy early when available to avoid the warning.
"""
import sys
try:
	# Only available on Windows/Python 3.8+; harmless to call elsewhere.
	if sys.platform.startswith("win"):
		import asyncio

		try:
			asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
		except AttributeError:
			# Older Python where WindowsSelectorEventLoopPolicy may not exist.
			pass
except Exception:
	# Best-effort; don't fail startup if the policy can't be set.
	pass

from .agent import main

raise SystemExit(main())

