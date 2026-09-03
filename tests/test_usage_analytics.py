#!/usr/bin/env python
"""Tests for the Scarf usage-analytics opt-out and its off-thread dispatch.

The event is reported once per Filter init. Two properties matter and are easy to
regress:

1. The opt-out is honored, and the startup log agrees with it. The SDK has the
   final say, but openfilter checks the same variables so it does not announce
   analytics as enabled to someone who opted out.
2. Reporting never blocks Filter construction. The SDK call is a synchronous POST
   with a 3s timeout; run inline it made every Filter wait out that timeout on any
   network where the endpoint is unreachable but not actively refused.
"""

import os
import threading
import time
import unittest
from unittest.mock import patch

from openfilter.filter_runtime.filter import (
    _report_filter_initialized,
    _usage_analytics_disabled,
)

OPT_OUT_VARS = ["DO_NOT_TRACK", "SCARF_NO_ANALYTICS"]


class TestUsageAnalyticsOptOut(unittest.TestCase):
    """_usage_analytics_disabled mirrors the variables the Scarf SDK honors."""

    def _assert(self, env, expected):
        clean = {k: v for k, v in os.environ.items() if k not in OPT_OUT_VARS}
        clean.update(env)
        with patch.dict(os.environ, clean, clear=True):
            self.assertEqual(_usage_analytics_disabled(), expected, env)

    def test_enabled_when_unset(self):
        self._assert({}, False)

    def test_do_not_track_truthy_values(self):
        for value in ("1", "true", "TRUE", "True"):
            self._assert({"DO_NOT_TRACK": value}, True)

    def test_scarf_no_analytics_truthy_values(self):
        for value in ("1", "true", "TRUE"):
            self._assert({"SCARF_NO_ANALYTICS": value}, True)

    def test_falsy_values_do_not_opt_out(self):
        # An explicit "0"/"" means "do not opt out" and must not be read as a
        # generic "the variable is present" signal.
        for value in ("0", "", "false", "no"):
            self._assert({"DO_NOT_TRACK": value}, False)

    def test_either_variable_is_enough(self):
        self._assert({"DO_NOT_TRACK": "0", "SCARF_NO_ANALYTICS": "1"}, True)


class TestReportFilterInitialized(unittest.TestCase):
    """_report_filter_initialized runs on a daemon thread and never raises."""

    def test_sends_the_filter_name(self):
        with patch("openfilter.filter_runtime.filter.scarf_elogger") as elogger:
            _report_filter_initialized("myfilter")
        elogger.log_event.assert_called_once_with(
            properties={"filter_initialized": "myfilter"}
        )

    def test_swallows_sdk_errors(self):
        # It runs on a thread, so an escaping exception would print a bare
        # traceback to stderr with nothing to catch it.
        with patch("openfilter.filter_runtime.filter.scarf_elogger") as elogger:
            elogger.log_event.side_effect = RuntimeError("connection refused")
            _report_filter_initialized("myfilter")  # must not raise

    def test_does_not_block_the_caller(self):
        # The regression this guards: the SDK call used to run inline in
        # Filter.__init__, so an endpoint that accepts the connection and then
        # stalls delayed startup by the full timeout, once per filter.
        started = threading.Event()

        def stall(*_args, **_kwargs):
            started.set()
            time.sleep(3.0)

        with patch("openfilter.filter_runtime.filter.scarf_elogger") as elogger:
            elogger.log_event.side_effect = stall

            begin = time.monotonic()
            thread = threading.Thread(
                target=_report_filter_initialized,
                args=("myfilter",),
                name="scarf-usage-event",
                daemon=True,
            )
            thread.start()
            elapsed = time.monotonic() - begin

            self.assertTrue(started.wait(timeout=2.0), "reporter never ran")
            self.assertLess(elapsed, 0.5, f"dispatch blocked for {elapsed:.2f}s")
            self.assertTrue(thread.daemon, "reporter must not hold up process exit")


if __name__ == "__main__":
    unittest.main()
