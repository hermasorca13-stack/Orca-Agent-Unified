import asyncio
import os
from loguru import logger
from typing import Optional

class TermuxAutomationSkills:
    def __init__(self):
        logger.info("Initializing Termux Automation Skills")

    async def execute_termux_command(self, command: str, description: Optional[str] = None) -> str:
        """Executes a shell command within Termux environment (simulated here)."""
        logger.info(f"Executing Termux command: {command}")
        # In a real Termux environment, this would execute directly.
        # Here, we simulate it as a shell command.
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_message = f"Termux command failed with error: {stderr.decode().strip()}"
            logger.error(error_message)
            return error_message
        
        return stdout.decode().strip()

    async def adb_tap(self, x: int, y: int) -> str:
        """Simulates a tap on the Android screen using ADB."""
        command = f"adb shell input tap {x} {y}"
        return await self.execute_termux_command(command, "Tapping screen")

    async def adb_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> str:
        """Simulates a swipe on the Android screen using ADB."""
        command = f"adb shell input swipe {x1} {y1} {x2} {y2} {duration}"
        return await self.execute_termux_command(command, "Swiping screen")

    async def adb_text(self, text: str) -> str:
        """Types text into an active input field using ADB."""
        # ADB requires spaces to be %s
        formatted_text = text.replace(" ", "%s")
        command = f"adb shell input text \"{formatted_text}\""
        return await self.execute_termux_command(command, "Typing text")

    async def adb_keyevent(self, keycode: int) -> str:
        """Sends a key event (e.g., back button) using ADB."""
        command = f"adb shell input keyevent {keycode}"
        return await self.execute_termux_command(command, "Sending key event")

    async def adb_screenshot(self, output_path: str = "/sdcard/screenshot.png") -> str:
        """Takes a screenshot and saves it to the specified path on the Android device."""
        command = f"adb shell screencap -p {output_path}"
        result = await self.execute_termux_command(command, "Taking screenshot")
        if "error" in result.lower():
            return result
        return f"Screenshot saved to {output_path} on device."

    async def adb_pull_file(self, remote_path: str, local_path: str) -> str:
        """Pulls a file from the Android device to the Termux environment."""
        command = f"adb pull {remote_path} {local_path}"
        return await self.execute_termux_command(command, "Pulling file from device")

    async def adb_start_activity(self, action: str, data: Optional[str] = None, component: Optional[str] = None) -> str:
        """Starts an Android activity using ADB."""
        cmd = ["adb", "shell", "am", "start", "-a", action]
        if data: cmd.extend(["-d", data])
        if component: cmd.extend(["-n", component])
        command = " ".join(cmd)
        return await self.execute_termux_command(command, "Starting Android activity")

    async def termux_api_call(self, api_command: str, *args) -> str:
        """Executes a Termux:API command."""
        full_command = f"termux-{api_command}"
        if args:
            full_command += " " + " ".join(args)
        return await self.execute_termux_command(full_command, f"Calling Termux API: {api_command}")

