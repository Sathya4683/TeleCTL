"""WACTL worker — long-polls SQS and dispatches async commands on EC2.

This package is the runtime container for :mod:`worker.main`, which is
launched by the systemd unit at ``/etc/systemd/system/wactl-worker.service``.
"""

from __future__ import annotations
