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
Example: MAI-UI Desktop One-Shot Agent

Simple single-action automation - predict and execute in one call.
"""

import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import mss
from PIL import Image

from mai_desktop_oneshot_agent import MAIDesktopOneShotAgent


def main():
    # Initialize agent
    print("🚀 Initializing MAI-UI Desktop One-Shot Agent...")
    agent = MAIDesktopOneShotAgent(
        llm_base_url="http://localhost:1234/v1",
        model_name="mai-ui",
    )
    print(f"✓ Model: {agent.model_name}")
    print(f"✓ Screen: {agent.screen_width}x{agent.screen_height}")
    print("\n" + "="*60)
    print("MAI-UI One-Shot Agent - 单指令单动作")
    print("="*60)
    print("\n每次调用只执行一个动作，无历史记录\n")

    while True:
        instruction = input("💬 输入指令 (或 'quit' 退出): ").strip()

        if instruction.lower() == 'quit':
            print("\n👋 Goodbye!")
            break

        if not instruction:
            continue

        try:
            # Capture screenshot
            print("  📸 截图中...")
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

            # Run prediction + execution
            print("  🤖 预测并执行...\n")
            result = agent.run(instruction, img, execute=True)

            # Display results
            if result.get("thinking"):
                print(f"  🧠 思考过程:")
                thinking = result["thinking"]
                if len(thinking) > 150:
                    thinking = thinking[:150] + "..."
                print(f"     {thinking}")

            action = result.get("action")
            if action:
                print(f"\n  🎯 执行动作: {action.get('action', '').upper()}")
                print(f"  📋 动作详情: {action}")

            if result.get("executed"):
                print(f"\n  ✅ 执行结果: {result['result']}")

            # Check if task is complete
            if action and action.get("action") in ["answer", "terminate"]:
                print(f"\n  {'='*50}")
                print(f"  📋 任务完成: {action.get('text', '')}")
                print(f"  {'='*50}\n")

        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n  ✗ 错误: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
