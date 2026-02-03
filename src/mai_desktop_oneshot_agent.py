# Copyright (c) 2025, Alibaba Cloud and its affiliates;
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
MAI-UI Desktop One-Shot Agent - Single prediction + execution

A simplified agent that:
1. Takes instruction and screenshot
2. Predicts ONE action
3. Executes it immediately
4. Returns the result

No history, no multi-step planning - just one action at a time.
"""

import base64
import json
import subprocess
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI
from PIL import Image


# Constants - same as Navigation Agent
SCALE_FACTOR = 999


class MAIDesktopOneShotAgent:
    """
    One-shot desktop automation agent.

    Each call: instruction + screenshot → predict + execute → return result
    """

    def __init__(
        self,
        llm_base_url: str,
        model_name: str,
        screen_width: int = None,
        screen_height: int = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        save_screenshots: bool = True,
        screenshot_dir: str = "screenshots",
    ):
        """
        Initialize the one-shot agent.

        Args:
            llm_base_url: Base URL for the LLM API.
            model_name: Name of the model.
            screen_width: Screen width (auto-detected if None).
            screen_height: Screen height (auto-detected if None).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            save_screenshots: Whether to save screenshots to disk.
            screenshot_dir: Directory to save screenshots.
        """
        self.llm_base_url = llm_base_url
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.save_screenshots = save_screenshots
        self.screenshot_dir = Path(screenshot_dir)
        self.call_count = 0

        # Create screenshot directory if needed
        if self.save_screenshots:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Auto-detect screen size if not provided
        if screen_width is None or screen_height is None:
            import pyautogui
            # Disable fail-safe for smoother operation
            pyautogui.FAILSAFE = False
            self.screen_width, self.screen_height = pyautogui.size()
        else:
            self.screen_width = screen_width
            self.screen_height = screen_height

        self.llm = OpenAI(
            base_url=self.llm_base_url,
            api_key="empty",
        )

    def run(
        self,
        instruction: str,
        screenshot: Image.Image,
        execute: bool = True,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """
        Run one-shot prediction and optional execution.

        Args:
            instruction: User's instruction.
            screenshot: Current screenshot as PIL Image.
            execute: Whether to execute the action (default: True).
            confirm: Whether to ask for confirmation before executing.

        Returns:
            Dictionary with:
                - "thinking": Model's reasoning
                - "action": Predicted action
                - "executed": Whether action was executed
                - "result": Execution result (if executed)
                - "raw_output": Raw model output
                - "screenshot_path": Path to saved screenshot (if enabled)
        """
        # Save screenshot
        screenshot_path = self._save_screenshot(screenshot, instruction)

        # Predict action
        result = self._predict_action(instruction, screenshot)

        # Add screenshot path to result
        if screenshot_path:
            result["screenshot_path"] = str(screenshot_path)

        action = result.get("action")
        if not action:
            return result

        # Execute action (optional)
        if execute:
            if confirm:
                # Ask for confirmation
                print(f"\n🎯 Action: {action.get('action', '').upper()}")
                print(f"📋 Details: {json.dumps(action, ensure_ascii=False)}")
                user_input = input("\n执行? (y/n): ").strip().lower()
                if user_input != 'y':
                    result["executed"] = False
                    result["result"] = "Skipped by user"
                    return result

            # Execute the action
            exec_result = self._execute_action(action)
            result["executed"] = True
            result["result"] = exec_result
        else:
            result["executed"] = False
            result["result"] = None

        return result

    def _predict_action(self, instruction: str, screenshot: Image.Image) -> Dict[str, Any]:
        """Predict action from instruction and screenshot."""
        # Encode image
        buffered = BytesIO()
        screenshot.save(buffered, format="PNG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

        # Build messages
        messages = self._build_messages(instruction, image_base64)

        # Call LLM
        response = self.llm.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        raw_output = response.choices[0].message.content.strip()

        # Parse response
        result = self._parse_response(raw_output)
        result["raw_output"] = raw_output
        return result

    def _save_screenshot(self, screenshot: Image.Image, instruction: str) -> Optional[Path]:
        """
        Save screenshot to disk with timestamp and instruction info.

        Args:
            screenshot: PIL Image to save.
            instruction: User instruction for filename context.

        Returns:
            Path to saved screenshot, or None if saving is disabled.
        """
        if not self.save_screenshots:
            return None

        self.call_count += 1

        # Create filename: step_YYYYMMDD_HHMMSS_instruction.png
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize instruction for filename (remove/replace problematic chars)
        safe_instruction = "".join(
            c if c.isalnum() or c in ('-', '_') else '_'
            for c in instruction[:30]  # Limit to 30 chars
        )
        filename = f"step_{self.call_count:03d}_{timestamp}_{safe_instruction}.png"
        filepath = self.screenshot_dir / filename

        # Save screenshot
        screenshot.save(filepath)
        return filepath

    def _build_messages(self, instruction: str, image_base64: str) -> list:
        """Build messages for LLM."""
        # Import the same prompt used by Navigation Agent
        from prompt import MAI_DESKTOP_SYS_PROMPT_CN

        system_prompt = MAI_DESKTOP_SYS_PROMPT_CN

        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            },
        ]
        return messages

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse model output."""
        import re

        result = {"thinking": None, "action": None}

        # Extract thinking
        thinking_pattern = r"<thinking>(.*?)</thinking>"
        thinking_match = re.search(thinking_pattern, text, re.DOTALL)
        if thinking_match:
            result["thinking"] = thinking_match.group(1).strip()

        # Extract action JSON
        invoke_pattern = r"<invoke>\s*(\{.*?\})\s*</invoke>"
        invoke_match = re.search(invoke_pattern, text, re.DOTALL)
        if invoke_match:
            action_json = invoke_match.group(1).strip()
            try:
                # Handle both wrapped and direct format
                parsed = json.loads(action_json)
                if "arguments" in parsed:
                    action = parsed["arguments"]
                else:
                    action = parsed

                # Debug: print raw coordinate before normalization
                if "coordinate" in action:
                    print(f"🔍 Raw coordinate from model: {action['coordinate']}")

                # Auto-detect and normalize coordinates
                # If coordinates are > 1.5, assume they are pixel values and normalize them
                action = self._normalize_action_coordinates(action)

                # Debug: print coordinate after normalization
                if "coordinate" in action:
                    print(f"🔍 Normalized coordinate: {action['coordinate']}")
                    print(f"🔍 Screen size: {self.screen_width}x{self.screen_height}")

                result["action"] = action
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse action JSON: {e}")

        return result

    def _normalize_action_coordinates(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Auto-detect and normalize coordinates in action.

        Model outputs coordinates in [0, SCALE_FACTOR] range (0-999).
        We need to normalize them to [0, 1] range.
        """
        def should_normalize(val):
            """Check if value should be normalized."""
            if isinstance(val, (int, float)):
                return val > 1.5
            return False

        def normalize_value(val):
            """Normalize from SCALE_FACTOR range to [0, 1]."""
            if should_normalize(val):
                return val / SCALE_FACTOR
            return val

        # Check and normalize coordinate in click action
        if "coordinate" in action:
            coord = action["coordinate"]
            if isinstance(coord, list) and len(coord) >= 2:
                x, y = coord[0], coord[1]
                if should_normalize(x) or should_normalize(y):
                    action["coordinate"] = [
                        normalize_value(x),
                        normalize_value(y),
                    ]

        # Check and normalize start_coordinate and end_coordinate
        for key in ["start_coordinate", "end_coordinate"]:
            if key in action:
                coord = action[key]
                if isinstance(coord, list) and len(coord) >= 2:
                    x, y = coord[0], coord[1]
                    if should_normalize(x) or should_normalize(y):
                        action[key] = [
                            normalize_value(x),
                            normalize_value(y),
                        ]

        return action

    def _execute_action(self, action: Dict[str, Any]) -> str:
        """Execute the action on desktop."""
        import pyautogui
        import pyperclip

        action_type = action.get("action")

        try:
            if action_type == "click":
                return self._click(action)
            elif action_type == "type":
                return self._type(action)
            elif action_type == "launch":
                return self._launch(action)
            elif action_type == "scroll":
                return self._scroll(action)
            elif action_type == "wait":
                return self._wait(action)
            elif action_type == "answer":
                return f"Answer: {action.get('text', '')}"
            else:
                return f"Unknown action: {action_type}"
        except Exception as e:
            return f"Error executing {action_type}: {e}"

    def _to_screen_coords(self, coord):
        """Convert normalized [0,1] to screen pixels."""
        if len(coord) == 2:
            x, y = coord
            # Clamp to [0, 1] range to avoid invalid coordinates
            x = max(0.0, min(1.0, x))
            y = max(0.0, min(1.0, y))
            screen_x = int(x * self.screen_width)
            screen_y = int(y * self.screen_height)

            # Validate coordinates
            if not (0 <= screen_x <= self.screen_width and 0 <= screen_y <= self.screen_height):
                raise ValueError(f"Invalid coordinates: ({screen_x}, {screen_y}) outside screen ({self.screen_width}x{self.screen_height})")

            return screen_x, screen_y
        return coord

    def _click(self, action):
        import pyautogui
        # Ensure fail-safe is disabled
        pyautogui.FAILSAFE = False

        coord = action["coordinate"]
        x, y = self._to_screen_coords(coord)
        button = action.get("button", "left")

        # Add a small pause before clicking to ensure smooth execution
        pyautogui.PAUSE = 0.25

        # Move first, then click (more reliable)
        pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.click(x, y, button=button)

        return f"Clicked ({x}, {y}) with {button} button"

    def _type(self, action):
        import pyautogui
        text = action["text"]
        try:
            # Use clipboard for more reliable input
            original = pyperclip.paste()
            pyperclip.copy(text)
            time.sleep(0.1)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.2)
            pyperclip.copy(original)
            return f'Typed: "{text[:50]}..." if len(text) > 50 else text'
        except:
            pyautogui.write(text, interval=0.01)
            return f'Typed: "{text[:50]}..." if len(text) > 50 else text'

    def _launch(self, action):
        app_name = action.get("text", "").strip().strip('"').strip("'").lower()

        app_commands = {
            "notepad": "notepad.exe",
            "calc": "calc.exe",
            "calculator": "calc.exe",
            "chrome": "chrome.exe",
            "edge": "msedge.exe",
            "wechat": r"C:\Program Files\Tencent\Weixin\Weixin.exe",
            "weixin": r"C:\Program Files\Tencent\Weixin\Weixin.exe",
        }

        if app_name in app_commands:
            subprocess.Popen(app_commands[app_name], shell=True)
            return f"Launched: {app_name}"

        # Fuzzy match
        for key, cmd in app_commands.items():
            if key in app_name or app_name in key:
                subprocess.Popen(cmd, shell=True)
                return f"Launched: {app_name}"

        return f"Unknown app: {app_name}"

    def _scroll(self, action):
        import pyautogui
        x, y = self._to_screen_coords(action["coordinate"])
        direction = action.get("direction", "up")
        amount = action.get("amount", 3)
        clicks = amount if direction in ["up", "left"] else -amount
        pyautogui.scroll(clicks, x, y)
        return f"Scrolled {direction} by {amount} at ({x}, {y})"

    def _wait(self, action):
        duration = action.get("duration", 1)
        time.sleep(duration)
        return f"Waited {duration} seconds"


# Convenience function for quick usage
def execute_instruction(
    instruction: str,
    llm_base_url: str = "http://localhost:1234/v1",
    model_name: str = "mai-ui",
) -> Dict[str, Any]:
    """
    One-line function to execute an instruction.

    Args:
        instruction: Natural language instruction.
        llm_base_url: LLM API base URL.
        model_name: Model name.

    Returns:
        Result dictionary with thinking, action, and execution result.
    """
    import mss

    # Capture screenshot
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

    # Run agent
    agent = MAIDesktopOneShotAgent(llm_base_url, model_name)
    return agent.run(instruction, img, execute=True)


if __name__ == "__main__":
    import sys

    # Simple CLI usage
    if len(sys.argv) < 2:
        print("Usage: python mai_desktop_oneshot_agent.py \"your instruction\"")
        print("Example: python mai_desktop_oneshot_agent.py \"点击记事本图标\"")
        sys.exit(1)

    instruction = sys.argv[1]

    print(f"🚀 Executing: {instruction}")
    result = execute_instruction(instruction)

    print(f"\n🧠 Thinking: {result.get('thinking', 'N/A')[:200]}")
    print(f"🎯 Action: {json.dumps(result.get('action'), ensure_ascii=False)}")
    print(f"✓ Result: {result.get('result', 'N/A')}")
