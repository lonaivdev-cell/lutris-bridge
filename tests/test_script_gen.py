"""Tests for launch script generation."""

import stat
from pathlib import Path

import pytest

from lutris_bridge.lutris_config import GameConfig
from lutris_bridge.lutris_db import LutrisGame
from lutris_bridge.script_gen import (
    generate_fallback_script,
    generate_launch_script,
    generate_linux_script,
    generate_wine_script,
)


@pytest.fixture
def wine_game():
    return LutrisGame(
        id=1,
        slug="valheim",
        name="Valheim",
        runner="wine",
        platform="Linux",
        directory="/games/valheim",
        configpath="valheim-12345",
    )


@pytest.fixture
def wine_config():
    return GameConfig(
        exe="C:/Games/Valheim/valheim.exe",
        prefix="/home/user/.wine/prefixes/valheim",
        args="-console",
        working_dir="/home/user/.wine/prefixes/valheim/drive_c/Games/Valheim",
        wine_version="lutris-GE-Proton8-14-x86_64",
        env={"MANGOHUD": "1", "ENABLE_VKBASALT": "1"},
        gamemode=True,
        dxvk=True,
        dll_overrides="d3d11=n;dxgi=n",
    )


@pytest.fixture
def linux_game():
    return LutrisGame(
        id=2,
        slug="celeste",
        name="Celeste",
        runner="linux",
        platform="Linux",
        directory="/games/celeste",
        configpath="celeste-67890",
    )


@pytest.fixture
def linux_config():
    return GameConfig(
        exe="/games/celeste/Celeste.x86_64",
        working_dir="/games/celeste",
        env={"SDL_GAMECONTROLLERCONFIG": "some_config"},
        gamemode=True,
    )


@pytest.fixture
def dosbox_game():
    return LutrisGame(
        id=5,
        slug="dos-game",
        name="DOS Game",
        runner="dosbox",
        platform="DOS",
        directory="/games/dos",
        configpath="dos-33333",
    )


class TestWineScript:
    def test_has_shebang(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert script.startswith("#!/bin/bash\n")

    def test_has_wineprefix(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert 'export WINEPREFIX="/home/user/.wine/prefixes/valheim"' in script

    def test_has_dll_overrides(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert 'export WINEDLLOVERRIDES="d3d11=n;dxgi=n"' in script

    def test_has_dxvk_vars(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert "DXVK_LOG_LEVEL=none" in script
        assert "DXVK_HUD=0" in script

    def test_has_env_vars(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert 'export MANGOHUD="1"' in script
        assert 'export ENABLE_VKBASALT="1"' in script

    def test_has_gamemoderun(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert "gamemoderun " in script

    def test_no_gamescope(self, wine_game, wine_config):
        """CRITICAL: Scripts must never invoke gamescope."""
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert "gamescope" not in script.lower()

    def test_has_working_dir(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert 'cd "' in script

    def test_has_exe_and_args(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert "valheim.exe" in script
        assert "-console" in script

    def test_umu_launcher(self, wine_game, wine_config):
        wine_config.use_umu = True
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert "umu-run" in script

    def test_header_comment(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert "Valheim" in script
        assert "valheim" in script
        assert "DO NOT EDIT" in script


    def test_has_set_e(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert "set -eo pipefail" in script

    def test_has_err_trap(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert "trap " in script
        assert "ERR" in script
        assert "launch-errors.log" in script

    def test_validates_empty_exe(self, wine_game, wine_config):
        wine_config.exe = None
        with pytest.raises(ValueError, match="no exe configured"):
            generate_wine_script(wine_game, wine_config, Path("/runners"))

    def test_validates_empty_exe_str(self, wine_game, wine_config):
        wine_config.exe = ""
        with pytest.raises(ValueError, match="no exe configured"):
            generate_wine_script(wine_game, wine_config, Path("/runners"))

    def test_wine_command_check(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert 'command -v "wine"' in script

    def test_umu_command_check(self, wine_game, wine_config):
        wine_config.use_umu = True
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert 'command -v "umu-run"' in script

    def test_gamemoderun_check(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert 'command -v "gamemoderun"' in script

    def test_no_gamemoderun_check_when_disabled(self, wine_game, wine_config):
        wine_config.gamemode = False
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert "gamemoderun" not in script

    def test_working_dir_validation(self, wine_game, wine_config):
        script = generate_wine_script(wine_game, wine_config, Path("/runners"))
        assert '[ ! -d "' in script


class TestLinuxScript:
    def test_has_shebang(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert script.startswith("#!/bin/bash\n")

    def test_has_exe(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert "Celeste.x86_64" in script

    def test_has_working_dir(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert 'cd "/games/celeste"' in script

    def test_has_env_vars(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert "SDL_GAMECONTROLLERCONFIG" in script

    def test_has_gamemoderun(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert "gamemoderun" in script

    def test_no_gamescope(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert "gamescope" not in script.lower()

    def test_no_wine_vars(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert "WINEPREFIX" not in script
        assert "DXVK" not in script

    def test_has_set_e(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert "set -eo pipefail" in script

    def test_has_err_trap(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert "trap " in script
        assert "ERR" in script

    def test_validates_empty_exe(self, linux_game, linux_config):
        linux_config.exe = None
        with pytest.raises(ValueError, match="no exe configured"):
            generate_linux_script(linux_game, linux_config)

    def test_exe_executable_check(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert '[ ! -x "' in script

    def test_working_dir_validation(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert '[ ! -d "' in script

    def test_gamemoderun_check(self, linux_game, linux_config):
        script = generate_linux_script(linux_game, linux_config)
        assert 'command -v "gamemoderun"' in script


class TestFallbackScript:
    def test_uses_lutris_client(self, dosbox_game):
        script = generate_fallback_script(dosbox_game)
        assert f'lutris "lutris:rungameid/{dosbox_game.id}"' in script

    def test_mentions_runner(self, dosbox_game):
        script = generate_fallback_script(dosbox_game)
        assert "dosbox" in script

    def test_has_set_e(self, dosbox_game):
        script = generate_fallback_script(dosbox_game)
        assert "set -eo pipefail" in script

    def test_has_err_trap(self, dosbox_game):
        script = generate_fallback_script(dosbox_game)
        assert "trap " in script
        assert "ERR" in script

    def test_lutris_command_check(self, dosbox_game):
        script = generate_fallback_script(dosbox_game)
        assert 'command -v "lutris"' in script


class TestGenerateLaunchScript:
    def test_writes_file(self, tmp_path, wine_game, wine_config):
        runners_dir = tmp_path / "runners"
        runners_dir.mkdir()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        path = generate_launch_script(wine_game, wine_config, scripts_dir, runners_dir)
        assert path.exists()
        assert path.name == "valheim.sh"

    def test_file_is_executable(self, tmp_path, wine_game, wine_config):
        runners_dir = tmp_path / "runners"
        runners_dir.mkdir()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        path = generate_launch_script(wine_game, wine_config, scripts_dir, runners_dir)
        assert path.stat().st_mode & stat.S_IEXEC

    def test_linux_runner(self, tmp_path, linux_game, linux_config):
        runners_dir = tmp_path / "runners"
        runners_dir.mkdir()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        path = generate_launch_script(linux_game, linux_config, scripts_dir, runners_dir)
        content = path.read_text()
        assert "WINEPREFIX" not in content
        assert "Celeste" in content

    def test_fallback_runner(self, tmp_path, dosbox_game):
        runners_dir = tmp_path / "runners"
        runners_dir.mkdir()
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        path = generate_launch_script(dosbox_game, GameConfig(), scripts_dir, runners_dir)
        content = path.read_text()
        assert "lutris" in content
