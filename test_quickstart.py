import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Save original sys.path before quickstart pollutes it
_original_sys_path = sys.path.copy()
import quickstart
sys.path[:] = _original_sys_path

class TestInitKernel(unittest.TestCase):

    @patch('quickstart.step')
    @patch('quickstart.subprocess.run')
    @patch('quickstart._manual_init')
    def test_init_kernel_bootstrap_success(self, mock_manual_init, mock_subprocess_run, mock_step):
        mock_kernel_bootstrap = MagicMock()
        mock_bootstrap_func = MagicMock()
        mock_kernel_bootstrap.bootstrap = mock_bootstrap_func

        with patch.dict('sys.modules', {'kernel.bootstrap': mock_kernel_bootstrap}):
            quickstart.init_kernel()

            mock_bootstrap_func.assert_called_once()
            mock_subprocess_run.assert_not_called()
            mock_manual_init.assert_not_called()

    @patch('builtins.print')
    @patch('quickstart.step')
    @patch('quickstart.subprocess.run')
    @patch('quickstart._manual_init')
    def test_init_kernel_fallback_success(self, mock_manual_init, mock_subprocess_run, mock_step, mock_print):
        mock_kernel_bootstrap = MagicMock()
        mock_bootstrap_func = MagicMock(side_effect=Exception("Simulated bootstrap error"))
        mock_kernel_bootstrap.bootstrap = mock_bootstrap_func

        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0
        mock_subprocess_result.stdout = "Fallback bootstrap success"
        mock_subprocess_run.return_value = mock_subprocess_result

        with patch.dict('sys.modules', {'kernel.bootstrap': mock_kernel_bootstrap}):
            quickstart.init_kernel()

            mock_bootstrap_func.assert_called_once()
            mock_subprocess_run.assert_called_once_with(
                [sys.executable, os.path.join(quickstart.KERNEL_DIR, 'bootstrap.py')],
                capture_output=True, text=True, cwd=quickstart.ROOT
            )
            mock_print.assert_called_with("Fallback bootstrap success")
            mock_manual_init.assert_not_called()

    @patch('builtins.print')
    @patch('quickstart.step')
    @patch('quickstart.subprocess.run')
    @patch('quickstart._manual_init')
    def test_init_kernel_fallback_failure(self, mock_manual_init, mock_subprocess_run, mock_step, mock_print):
        mock_kernel_bootstrap = MagicMock()
        mock_bootstrap_func = MagicMock(side_effect=Exception("Simulated bootstrap error"))
        mock_kernel_bootstrap.bootstrap = mock_bootstrap_func

        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 1
        mock_subprocess_result.stderr = "Fallback bootstrap failed"
        mock_subprocess_run.return_value = mock_subprocess_result

        with patch.dict('sys.modules', {'kernel.bootstrap': mock_kernel_bootstrap}):
            quickstart.init_kernel()

            mock_bootstrap_func.assert_called_once()
            mock_subprocess_run.assert_called_once_with(
                [sys.executable, os.path.join(quickstart.KERNEL_DIR, 'bootstrap.py')],
                capture_output=True, text=True, cwd=quickstart.ROOT
            )
            mock_print.assert_any_call("  Bootstrap error: Fallback bootstrap failed")
            mock_print.assert_any_call("  Attempting manual initialization...")
            mock_manual_init.assert_called_once()

if __name__ == '__main__':
    unittest.main()
