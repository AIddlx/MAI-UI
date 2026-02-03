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
Full Example: MAI-UI Desktop Agent with Action Execution

This example shows a complete workflow:
1. Capture screenshot
2. Send to MAI-UI agent (via LM Studio)
3. Get predicted action
4. Execute the action on Windows

Requirements:
    pip install pyautogui pillow mss

Prerequisites:
1. LM Studio running with "mai-ui" model at http://localhost:1234
2. Screen resolution should be consistent
"""

import sys
import time
from pathlib import Path

# Fix Windows console encoding issue
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pyautogui
import mss
import numpy as np
from PIL import Image

from mai_desktop_navigation_agent import MAIDesktopNavigationAgent

# Configure pyautogui
pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = True  # Move mouse to corner to abort


class DesktopController:
    """Executes GUI actions on Windows desktop."""

    def __init__(self, screen_width, screen_height):
        """
        Initialize controller with screen dimensions.

        Args:
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
        """
        self.width = screen_width
        self.height = screen_height

    def execute_action(self, action: dict) -> str:
        """
        Execute an action on the desktop.

        Args:
            action: Action dictionary from MAI-UI agent

        Returns:
            Result message
        """
        action_type = action.get("action")

        try:
            # Mouse actions
            if action_type == "click":
                return self._click(action)
            elif action_type == "double_click":
                return self._double_click(action)
            elif action_type == "drag":
                return self._drag(action)
            elif action_type == "scroll":
                return self._scroll(action)

            # Keyboard actions (safe only - text input)
            elif action_type == "type":
                return self._type(action)

            # Application launch
            elif action_type == "launch":
                return self._launch(action)

            # System control
            elif action_type == "wait":
                return self._wait(action)
            elif action_type == "terminate":
                return f"Task {action.get('status')}"
            elif action_type == "answer":
                return f"{action.get('text', '')}"

            else:
                return f"Unknown or blocked action: {action_type}"

        except Exception as e:
            return f"Error executing {action_type}: {e}"

    def _normalize_to_screen(self, coord):
        """Convert normalized [0,1] coordinate to screen pixels."""
        if len(coord) == 2:
            x, y = coord
            return int(x * self.width), int(y * self.height)
        return coord

    def _click(self, action):
        x, y = self._normalize_to_screen(action["coordinate"])
        button = action.get("button", "left")
        pyautogui.click(x, y, button=button)
        return f"Clicked ({x}, {y}) with {button} button"

    def _double_click(self, action):
        x, y = self._normalize_to_screen(action["coordinate"])
        button = action.get("button", "left")
        pyautogui.doubleClick(x, y, button=button)
        return f"Double-clicked ({x}, {y}) with {button} button"

    def _triple_click(self, action):
        x, y = self._normalize_to_screen(action["coordinate"])
        for _ in range(3):
            pyautogui.click(x, y)
        return f"Triple-clicked ({x}, {y})"

    def _drag(self, action):
        start = self._normalize_to_screen(action["start_coordinate"])
        end = self._normalize_to_screen(action["end_coordinate"])
        x_offset = end[0] - start[0]
        y_offset = end[1] - start[1]
        pyautogui.drag(x_offset, y_offset, duration=0.5)
        return f"Dragged from {start} to {end}"

    def _hover(self, action):
        x, y = self._normalize_to_screen(action["coordinate"])
        pyautogui.moveTo(x, y)
        return f"Hovered at ({x}, {y})"

    def _mouse_move(self, action):
        """Move mouse cursor to specified position without clicking."""
        x, y = self._normalize_to_screen(action["coordinate"])
        pyautogui.moveTo(x, y)
        return f"Moved mouse to ({x}, {y})"

    def _scroll(self, action):
        x, y = self._normalize_to_screen(action["coordinate"])
        direction = action.get("direction", "up")
        amount = action.get("amount", 1)
        clicks = amount if direction in ["up", "left"] else -amount
        if direction in ["up", "down"]:
            pyautogui.scroll(clicks, x, y)
        else:
            pyautogui.hscroll(clicks, x, y)
        return f"Scrolled {direction} by {amount} at ({x}, {y})"

    def _type(self, action):
        text = action["text"]

        # 方法1: 使用pyperclip + Ctrl+V (更可靠)
        try:
            import pyperclip
            import time

            # 保存剪贴板内容
            original_clipboard = pyperclip.paste()

            # 复制新文本到剪贴板
            pyperclip.copy(text)

            # 使用Ctrl+V粘贴（更可靠）
            time.sleep(0.1)  # 短暂等待
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.2)  # 等待粘贴完成

            # 恢复剪贴板
            pyperclip.copy(original_clipboard)

            return f'Typed: "{text[:50]}{"..." if len(text) > 50 else text}" (via clipboard)'

        except Exception as e:
            # 方法2: 回退到pyautogui.write()
            try:
                pyautogui.write(text, interval=0.01)
                return f'Typed: "{text[:50]}{"..." if len(text) > 50 else text}" (via keyboard)'
            except Exception as e2:
                return f'Error typing text: {e2}'

    def _launch(self, action):
        # 获取并清理应用名（移除引号和多余空格）
        app_name = action.get("text", "").strip().strip('"').strip("'").lower()
        if not app_name:
            return "Error: launch action missing 'text' parameter"

        # 应用名映射
        app_commands = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "explorer": "explorer.exe",
            "chrome": "chrome.exe",
            "firefox": "firefox.exe",
            "edge": "msedge.exe",
            "microsoft edge": "msedge.exe",
            "word": "winword.exe",
            "excel": "excel.exe",
            "powerpoint": "powerpnt.exe",
            "wechat": r"C:\Program Files\Tencent\Weixin\Weixin.exe",
            "微信": r"C:\Program Files\Tencent\Weixin\Weixin.exe",
            "weixin": r"C:\Program Files\Tencent\Weixin\Weixin.exe",
        }

        # 先尝试已知映射
        if app_name in app_commands:
            import subprocess
            subprocess.Popen(app_commands[app_name], shell=True)
            return f"Launched: {app_name}"

        # 尝试常见变体
        for key, cmd in app_commands.items():
            if key in app_name or app_name in key:
                import subprocess
                subprocess.Popen(cmd, shell=True)
                return f"Launched: {app_name} (matched to {key})"

        # 最后尝试直接运行
        import subprocess
        try:
            subprocess.Popen(app_name, shell=True)
            return f"Launched: {app_name}"
        except Exception as e:
            return f"Failed to launch '{app_name}': {str(e)[:100]}"

    def _wait(self, action):
        duration = action.get("duration", 1)
        time.sleep(duration)
        return f"Waited {duration} seconds"


def capture_screenshot():
    """Capture screenshot using mss (faster than PIL)."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        screenshot = sct.grab(monitor)
        # Convert to PIL Image
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        return img


def main():
    # Get screen size
    screen_width, screen_height = pyautogui.size()

    # Initialize agent
    print("🚀 Initializing MAI-UI Desktop Agent...")
    agent = MAIDesktopNavigationAgent(
        llm_base_url="http://localhost:1234/v1",
        model_name="mai-ui",
        runtime_conf={
            "history_n": 3,
            "temperature": 0.0,
            "max_tokens": 8192,  # Increased significantly - model needs room for thinking + JSON
        },
    )
    print(f"✓ Agent ready (logs: {agent.log_file})")

    # Initialize controller
    controller = DesktopController(screen_width, screen_height)

    # Example task loop
    instruction = input("\n💬 Enter your instruction (or 'quit' to exit): ")

    while instruction.lower() != "quit":
        try:
            max_steps = 20  # 防止无限循环
            step_count = 0

            print(f"\n{'='*60}")
            print(f"🎯 Task: {instruction}")
            print(f"{'='*60}\n")

            # 自动循环执行，直到任务完成
            last_execution_result = ""  # 存储上一步的执行结果
            while step_count < max_steps:
                # Capture screenshot
                screenshot = capture_screenshot()

                # Get action from agent (pass previous execution result as feedback)
                prediction, action = agent.predict(
                    instruction=instruction,
                    obs={
                        "screenshot": screenshot,
                        "accessibility_tree": None,
                        "execution_result": last_execution_result,  # 反馈上一步结果
                    }
                )

                step_count += 1

                # Extract and display thinking from prediction
                import re
                thinking_match = re.search(r'<thinking>(.*?)</thinking>', prediction, re.DOTALL)
                if thinking_match:
                    thinking = thinking_match.group(1).strip()
                    if thinking:
                        print(f"\n  🧠 Thinking: {thinking[:200]}{'...' if len(thinking) > 200 else ''}")
                    else:
                        print(f"\n  🧠 Thinking: (empty - model not reasoning)")
                else:
                    print(f"\n  🧠 Thinking: (not found in output)")

                # Check if action is None (parsing failed)
                if action is None or action.get("action") is None:
                    print(f"\n  ⚠️  Failed to get valid action from model")
                    print(f"  Check the log file for details: {agent.log_file}")
                    break

                # 检查是否任务完成
                if action.get("action") in ["terminate", "answer"]:
                    print(f"\n  {'─'*58}")
                    print(f"  📋 Task Result: {action.get('text', 'Task finished')}")
                    print(f"  {'─'*58}")
                    break

                # Execute action
                result = controller.execute_action(action)

                # Check for invalid action and break to prevent infinite loop
                if result.startswith("Unknown or blocked action"):
                    print(f"\n  ⚠️  {result}")
                    print(f"  ⚠️  Model used invalid action type!")
                    print(f"  ⚠️  Feedback: {result} (will be sent to model)")
                    last_execution_result = result
                    continue  # 继续循环，让模型知道错误并尝试其他方法

                # Display execution result with [EXECUTED] prefix
                action_type = action.get("action", "").upper()
                print(f"\n  [EXECUTED] {action_type} → {result}")

                # Store execution result for next iteration (feedback to model)
                last_execution_result = result

                # Wait for action to complete (给应用时间响应)
                # 启动应用需要更长的等待时间
                if action.get("action") == "launch":
                    time.sleep(3)  # 应用启动需要等待
                elif action.get("action") == "click":
                    time.sleep(1.5)  # 点击后等待界面更新
                elif action.get("action") == "type":
                    time.sleep(0.5)  # 输入后短暂等待
                else:
                    time.sleep(0.8)  # 其他操作默认等待

                # 如果是 wait 动作，等待更长时间
                if action.get("action") == "wait":
                    time.sleep(action.get("duration", 1))

            if step_count >= max_steps:
                print(f"\n{'='*60}")
                print(f"⚠️  Reached maximum steps ({max_steps}), task may not be complete")
                print(f"{'='*60}")

        except Exception as e:
            print(f"\n{'='*60}")
            print(f"✗ Error: {e}")
            print(f"{'='*60}")
            import traceback
            traceback.print_exc()

        # Next instruction
        instruction = input("\n💬 Next instruction (or 'quit' to exit): ")

    print("\n👋 Goodbye!")


if __name__ == "__main__":
    main()
