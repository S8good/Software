# main.py

import argparse
import io
import sys
import os
import time
import traceback

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from nanosense.gui.main_window import AppWindow
from nanosense.gui.splash_screen import SplashScreen
from nanosense.gui.welcome_widget import WelcomeWidget
from nanosense.utils.config_manager import load_settings
from nanosense.utils.plot_theme import configure_pyqtgraph_theme
from nanosense.utils.logging_config import (
    configure_logging,
    get_logger,
    logging_context,
    new_session_id,
)


logger = get_logger(__name__)


def _install_global_excepthook():
    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.exception(
            "uncaught_exception event=uncaught_exception",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


# 全局变量，用于持有对窗口的引用，防止被垃圾回收
# 我们现在需要分别管理欢迎页和主程序窗口
welcome_screen = None
main_app_window = None

def _resolve_welcome_hardware_selection(use_real_hardware=None, hardware_vendor=None, settings=None):
    """
    Resolve launcher hardware selection from explicit restart arguments and saved settings.
    Explicit arguments win; omitted values fall back to config.
    """
    if settings is None:
        try:
            settings = load_settings()
        except Exception:
            settings = {}

    if use_real_hardware is None:
        use_real_hardware = bool(settings.get('use_real_hardware', True))

    if hardware_vendor is None:
        hardware_vendor = settings.get('hardware_vendor')

    if not use_real_hardware:
        return False, 'mock'

    vendor = (hardware_vendor or 'ideaoptics').lower()
    if vendor not in {'ideaoptics', 'ocean'}:
        vendor = 'ideaoptics'
    return True, vendor


def show_welcome_screen(use_real_hardware=None, hardware_vendor=None):
    """
    创建并显示欢迎/启动器窗口。
    这是程序启动和重启的入口点。
    """
    global welcome_screen
    use_real_hardware, hardware_vendor = _resolve_welcome_hardware_selection(
        use_real_hardware,
        hardware_vendor,
    )

    welcome_screen = WelcomeWidget()
    if use_real_hardware:
        welcome_screen.set_hardware_vendor(hardware_vendor)
    else:
        welcome_screen.set_hardware_vendor('mock')

    # 连接信号：当用户在欢迎页选择模式后，启动主程序
    welcome_screen.mode_selected.connect(launch_main_app)
    welcome_screen.show()

def launch_main_app(mode_name, use_real_hardware, hardware_vendor='ideaoptics'):
    """
    【已升级】这个函数现在会在硬件连接失败时返回欢迎页，而不是退出
    """
    global main_app_window, welcome_screen

    # 在尝试连接时，先隐藏欢迎页，避免界面卡顿
    if welcome_screen:
        welcome_screen.hide()

    logger.info(
        "launcher_selection event=launcher_selection mode=%s real_hardware=%s vendor=%s",
        mode_name,
        use_real_hardware,
        hardware_vendor,
    )

    main_app_window = AppWindow(use_real_hardware=use_real_hardware, hardware_vendor=hardware_vendor)

    # --- 【核心修改】检查硬件连接是否失败 ---
    if main_app_window.controller is None:
        # AppWindow 内部已经弹出了错误提示框，并且会自动关闭
        logger.warning("main_window_start_failed event=main_window_start_failed")

        # 重新显示欢迎页
        if welcome_screen:
            welcome_screen.show()
        return  # 终止这次失败的启动尝试

    # --- 如果硬件连接成功，则执行以下代码 ---
    logger.info("main_window_started event=main_window_started")
    main_app_window.restart_requested.connect(show_welcome_screen)

    main_app_window.switch_to_initial_view(mode_name)
    main_app_window.show()

    # 成功启动主窗口后，可以彻底关闭欢迎页了
    if welcome_screen:
        welcome_screen.close()
        # 清理引用是个好习惯
        welcome_screen = None

def _build_argument_parser():
    return argparse.ArgumentParser(
        prog="nanosense",
        description="NanoSense spectroscopy acquisition and analysis software",
    )


def main(argv=None):
    configure_logging()
    _install_global_excepthook()
    with logging_context(session_id=new_session_id()):
        return _run_application(argv)


def _run_application(argv=None):
    parser = _build_argument_parser()
    parsed_argv = sys.argv[1:] if argv is None else list(argv)
    if any(option in {"-h", "--help"} for option in parsed_argv):
        help_stream = sys.stdout or sys.stderr or io.StringIO()
        parser.print_help(file=help_stream)
        return 0
    parser.parse_args(parsed_argv)
    configure_pyqtgraph_theme(load_settings().get("theme", "dark"))

    qt_argv = sys.argv if argv is None else [sys.argv[0], *argv]
    app = QApplication(qt_argv)

    icon_path = os.path.join(
        os.path.dirname(__file__), "nanosense", "gui", "assets", "app_icon.ico"
    )
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        logger.warning("missing_app_icon event=missing_app_icon")

    splash = None
    splash_image_path = os.path.join(
        os.path.dirname(__file__),
        "nanosense", "gui", "assets", "splash.png"
    )
    if os.path.exists(splash_image_path):
        splash = SplashScreen(splash_image_path)
        splash.show()
        for progress in range(1, 101):
            splash.update_progress(progress)
            time.sleep(0.01)
            app.processEvents()

    show_welcome_screen()
    if splash is not None and welcome_screen:
        splash.finish(welcome_screen)

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
