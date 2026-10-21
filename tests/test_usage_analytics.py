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

import atexit
import os
import subprocess
import sys
import textwrap
import threading
import time
import unittest
from unittest.mock import patch

import openfilter.filter_runtime.filter as filter_mod
from openfilter.filter_runtime.filter import (
    _report_filter_initialized,
    _stop_usage_logging,
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


class TestUsageLoggingShutdown(unittest.TestCase):
    """The reporter must not be inside a stderr write when the interpreter ends.

    A daemon thread holding the stderr lock at finalization is a *fatal* error,
    not a catchable one: CPython aborts with ``_enter_buffered_busy`` and the
    process exits non-zero with its work already done. The reporter's only write
    is its failure warning, so the guard is on that write.
    """

    def setUp(self):
        # Module-level flag; restore it so ordering between tests cannot matter.
        self._saved = filter_mod._usage_logging_stopped
        filter_mod._usage_logging_stopped = False

    def tearDown(self):
        filter_mod._usage_logging_stopped = self._saved

    def test_logs_the_failure_before_shutdown(self):
        with patch("openfilter.filter_runtime.filter.scarf_elogger") as elogger, \
             patch("openfilter.filter_runtime.filter.logger") as log:
            elogger.log_event.side_effect = RuntimeError("connection refused")
            _report_filter_initialized("myfilter")
        log.warning.assert_called_once()

    def test_silent_once_shutdown_has_started(self):
        _stop_usage_logging()
        with patch("openfilter.filter_runtime.filter.scarf_elogger") as elogger, \
             patch("openfilter.filter_runtime.filter.logger") as log:
            elogger.log_event.side_effect = RuntimeError("connection refused")
            _report_filter_initialized("myfilter")  # must not raise
        log.warning.assert_not_called()

    def test_shutdown_waits_for_an_in_flight_write(self):
        """The half that actually closes the race.

        Setting the flag is not enough on its own: a thread already inside the
        write would still be there when finalization began. The hook takes the
        same lock the write holds, so it cannot return — and finalization cannot
        start — until that write is finished.
        """
        writing = threading.Event()
        release = threading.Event()

        def blocking_warning(*_args, **_kwargs):
            writing.set()
            release.wait(timeout=5.0)

        with patch("openfilter.filter_runtime.filter.scarf_elogger") as elogger, \
             patch("openfilter.filter_runtime.filter.logger") as log:
            elogger.log_event.side_effect = RuntimeError("connection refused")
            log.warning.side_effect = blocking_warning

            reporter = threading.Thread(
                target=_report_filter_initialized, args=("myfilter",), daemon=True
            )
            reporter.start()
            self.assertTrue(writing.wait(timeout=5.0), "write never started")

            hook_returned = threading.Event()
            threading.Thread(
                target=lambda: (_stop_usage_logging(), hook_returned.set()),
                daemon=True,
            ).start()

            # The write is in flight, so the hook must still be blocked.
            self.assertFalse(
                hook_returned.wait(timeout=0.5),
                "shutdown hook returned while a stderr write was in flight",
            )

            release.set()
            self.assertTrue(hook_returned.wait(timeout=5.0), "hook never returned")
            reporter.join(timeout=5.0)

        self.assertTrue(filter_mod._usage_logging_stopped)

    def test_hook_is_registered_with_atexit(self):
        """Registration is what makes the guard run at all.

        A refactor that defines the hook but drops the ``atexit.register`` call
        leaves every other assertion here passing and the bug back, so this
        checks it directly. atexit exposes no way to list handlers, so the probe
        runs them -- in a subprocess, where doing that is harmless.
        """
        script = textwrap.dedent(
            """
            import atexit
            import openfilter.filter_runtime.filter as f

            assert f._usage_logging_stopped is False, "flag set too early"
            atexit._run_exitfuncs()
            assert f._usage_logging_stopped is True, "hook is not registered"
            print("registered")
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        self.assertIn("registered", proc.stdout)


class TestInterpreterExitIsClean(unittest.TestCase):
    """End to end: many reporters failing fast, then an immediate exit."""

    SCRIPT = textwrap.dedent(
        """
        import threading
        import openfilter.filter_runtime.filter as f

        # Refused immediately, so every reporter reaches its warning, which is
        # the write that used to straddle finalization.
        f.scarf_elogger.endpoint_url = "http://127.0.0.1:1/openfilter"

        for _ in range(60):
            threading.Thread(
                target=f._report_filter_initialized, args=("x",), daemon=True
            ).start()
        """
    )

    def test_exits_zero_without_a_fatal_error(self):
        # This cannot force the race -- it is timing-dependent, which is why it
        # surfaced in CI and not locally. What it does guard is the shutdown path
        # end to end: a hook that raises, deadlocks, or is never registered fails
        # here, and so does a reporter that writes after the flag is set.
        proc = subprocess.run(
            [sys.executable, "-c", self.SCRIPT],
            capture_output=True, text=True, timeout=60,
        )
        self.assertNotIn("Fatal Python error", proc.stderr)
        self.assertNotIn("_enter_buffered_busy", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
