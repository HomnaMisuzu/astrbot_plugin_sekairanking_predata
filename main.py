from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from playwright.async_api import async_playwright
import os
import asyncio
from pathlib import Path

# 允许的t后缀数字列表
ALLOWED_T_VALUES = {50, 100, 200, 300, 400, 500, 1000, 2000, 3000, 4000, 5000, 10000}


# 注册插件（对应Star框架的@register装饰器）
@register(
    plugin_name="astrbot_plugin_sekairanking_predata",
    author="StreamOfAutumn",
    description="PJSK国服榜线预测：接收cnskp指令获取sekairanking截图",
    version="v1.3.0"
)
class SekaiRankingScreenshotPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.logger = context.logger  # 获取插件日志对象
        self.temp_dir = None  # 临时截图目录（在initialize中初始化）

    async def initialize(self):
        """插件初始化方法（Star框架实例化后自动调用）"""
        # 创建临时截图目录（插件目录下的temp文件夹）
        self.temp_dir = Path(__file__).parent / "temp"
        self.temp_dir.mkdir(exist_ok=True)
        self.logger.info("SekaiRanking截图插件初始化完成")

    # 注册cnskp指令处理器（对应Star框架的@filter.command装饰器）
    @filter.command("cnskp")
    async def cnskp_handler(self, event: AstrMessageEvent):
        """处理cnskp指令的核心方法"""
        # 获取用户发送的指令内容
        command_content = event.message_str.strip().lower()
        self.logger.info(f"收到cnskp指令：{command_content}")
        args = command_content.split()
        base_url = "https://sekairanking.exmeaning.com"
        target_url = None
        target_element_id = None

        # 1. 解析指令参数
        if len(args) == 1:
            # 指令：cnskp → 基础页
            target_url = f"{base_url}/simple"
        elif len(args) >= 2 and args[1].startswith("event"):
            # 指令：cnskp event[数字] / cnskp event[数字] PGAI
            event_num = args[1].replace("event", "")
            if not event_num.isdigit():
                yield event.plain_result("❌ 格式错误：event后需跟数字（如event150）")
                return
            # 拼接活动页URL
            target_url = f"{base_url}/index/event/{event_num}" if (len(args) == 3 and args[2] == "pgai") else f"{base_url}/event/{event_num}"
        elif len(args) >= 2 and args[1].startswith("t"):
            # 指令：cnskp t[数字] → 指定模块
            t_num = args[1].replace("t", "")
            if not t_num.isdigit() or int(t_num) not in ALLOWED_T_VALUES:
                yield event.plain_result(f"❌ 格式错误：t后仅支持数字{','.join(map(str, ALLOWED_T_VALUES))}")
                return
            t_num = int(t_num)
            target_url = base_url
            target_element_id = f"chart-{t_num}"
        else:
            yield event.plain_result("❌ 指令格式错误！支持：\n1. cnskp\n2. cnskp event[数字]\n3. cnskp event[数字] PGAI\n4. cnskp t[数字]")
            return

        # 2. 网页截图逻辑
        screenshot_path = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()
                
                # 访问目标页（超时60秒）
                await page.goto(target_url, wait_until="networkidle", timeout=60000)

                # 生成截图文件名
                if target_element_id:
                    screenshot_name = f"sekai_t{t_num}_{event.message_id}.png"
                elif "event" in command_content:
                    screenshot_name = f"sekai_event{event_num}_{event.message_id}.png"
                else:
                    screenshot_name = f"sekai_simple_{event.message_id}.png"
                screenshot_path = self.temp_dir / screenshot_name

                # 执行截图
                if target_element_id:
                    await page.wait_for_selector(f"#{target_element_id}", timeout=15000)
                    target_element = page.locator(f"#{target_element_id}")
                    await target_element.scroll_into_view_if_needed()
                    await target_element.screenshot(path=str(screenshot_path))
                else:
                    await page.set_viewport_size({"width": 1280, "height": 720})
                    await page.screenshot(path=str(screenshot_path), full_page=True)

                await browser.close()
                self.logger.info(f"截图成功：{screenshot_path}")
        except Exception as e:
            self.logger.error(f"截图失败：{str(e)}")
            err_msg = f"❌ 截图失败：{str(e)}"
            if "selector" in str(e) and target_element_id:
                err_msg = f"❌ 未找到模块{target_element_id}，请确认页面是否存在该内容"
            yield event.plain_result(err_msg)
            return

        # 3. 发送截图到群聊
        if screenshot_path and screenshot_path.exists():
            yield event.image_result(str(screenshot_path))  # Star框架发送图片的方式
            # 延迟清理临时截图
            asyncio.create_task(self.clean_temp_file(screenshot_path))
        else:
            yield event.plain_result("❌ 截图文件不存在，发送失败")

    async def clean_temp_file(self, file_path: Path):
        """清理临时截图文件"""
        await asyncio.sleep(30)
        if file_path.exists():
            os.remove(file_path)
            self.logger.info(f"临时截图已清理：{file_path}")

    async def terminate(self):
        """插件销毁方法（Star框架卸载时自动调用）"""
        self.logger.info("SekaiRanking截图插件已停止")