"""error_severity モジュールの単体テスト。

R2 緩和策に従い、fatal/recoverable の境界ケースを網羅する。
"""

from __future__ import annotations

import asyncio
import errno
import unittest

from hve.error_severity import classify_error, is_fatal


class TestClassifyErrorFatal(unittest.TestCase):
    """fatal 判定されるべきケース。"""

    def test_keyboard_interrupt_is_fatal(self) -> None:
        self.assertEqual(classify_error(KeyboardInterrupt()), "fatal")

    def test_system_exit_is_fatal(self) -> None:
        self.assertEqual(classify_error(SystemExit(1)), "fatal")

    def test_file_not_found_is_fatal(self) -> None:
        self.assertEqual(classify_error(FileNotFoundError("x")), "fatal")

    def test_permission_error_is_fatal(self) -> None:
        self.assertEqual(classify_error(PermissionError("denied")), "fatal")

    def test_oserror_enospc_is_fatal(self) -> None:
        exc = OSError(errno.ENOSPC, "No space left on device")
        self.assertEqual(classify_error(exc), "fatal")

    def test_oserror_eio_is_fatal(self) -> None:
        exc = OSError(errno.EIO, "I/O error")
        self.assertEqual(classify_error(exc), "fatal")

    def test_oserror_erofs_is_fatal(self) -> None:
        exc = OSError(errno.EROFS, "Read-only file system")
        self.assertEqual(classify_error(exc), "fatal")

    def test_oserror_enomem_is_fatal(self) -> None:
        exc = OSError(errno.ENOMEM, "Out of memory")
        self.assertEqual(classify_error(exc), "fatal")


class TestClassifyErrorRecoverable(unittest.TestCase):
    """recoverable 判定されるべきケース。"""

    def test_runtime_error_is_recoverable(self) -> None:
        self.assertEqual(classify_error(RuntimeError("boom")), "recoverable")

    def test_value_error_is_recoverable(self) -> None:
        self.assertEqual(classify_error(ValueError("bad")), "recoverable")

    def test_type_error_is_recoverable(self) -> None:
        self.assertEqual(classify_error(TypeError("bad type")), "recoverable")

    def test_connection_error_is_recoverable(self) -> None:
        self.assertEqual(classify_error(ConnectionError("net")), "recoverable")

    def test_asyncio_timeout_is_recoverable(self) -> None:
        self.assertEqual(classify_error(asyncio.TimeoutError()), "recoverable")

    def test_builtin_timeout_is_recoverable(self) -> None:
        self.assertEqual(classify_error(TimeoutError()), "recoverable")

    def test_oserror_eagain_is_recoverable(self) -> None:
        # ENOSPC/EIO/EROFS/ENOMEM 以外の OSError は recoverable
        exc = OSError(errno.EAGAIN, "Resource temporarily unavailable")
        self.assertEqual(classify_error(exc), "recoverable")

    def test_oserror_without_errno_is_recoverable(self) -> None:
        exc = OSError("generic")
        self.assertEqual(classify_error(exc), "recoverable")


class TestIsFatal(unittest.TestCase):
    """is_fatal ショートカット関数。"""

    def test_is_fatal_true(self) -> None:
        self.assertTrue(is_fatal(KeyboardInterrupt()))

    def test_is_fatal_false(self) -> None:
        self.assertFalse(is_fatal(RuntimeError()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
