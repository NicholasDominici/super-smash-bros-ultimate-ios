"""Compile/run the synthetic Mii boundary tests without proprietary fixtures."""
import pathlib
import platform
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(platform.system() == "Darwin", "native Apple ABI test")
class MiiServiceTests(unittest.TestCase):
    def test_local_database_contract(self):
        with tempfile.TemporaryDirectory(prefix="smash-mii-test-") as temporary:
            directory = pathlib.Path(temporary)
            binary = directory / "t_mii"
            subprocess.run([
                sys.executable, str(ROOT / "dm/games/game.py"), "header", "01006A800016E000",
                str(directory / "game_profile.h"),
            ], check=True, capture_output=True, text=True)
            subprocess.run([
                "xcrun", "clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-I", str(directory),
                "-I", str(ROOT / "dm/host"),
                str(ROOT / "dm/host/tests/t_mii.c"), "-o", str(binary),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn("empty user database", result.stdout)
            self.assertIn("failure atomicity", result.stdout)


if __name__ == "__main__":
    unittest.main()
