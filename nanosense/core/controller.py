import sys
import os
import logging
from pathlib import Path

from nanosense.utils.logging_config import get_logger


logger = get_logger(__name__)


class FX2000Controller:
    """
    光谱仪高级控制器（单例模式）。
    这个类负责与光谱仪硬件（或模拟API）进行交互，并确保在整个程序中只有一个控制器实例。
    """
    _instance = None

    def __init__(self, wrapper_instance, use_real_hardware, device_index=0, hardware_vendor=None):
        """
        私有构造函数，不应直接调用。请使用 connect() 方法。
        """
        if FX2000Controller._instance is not None:
            raise Exception("这是一个单例类，请使用 connect() 方法获取实例。")

        self.api_wrapper = wrapper_instance
        self.device_index = device_index
        self.is_real_hardware = use_real_hardware
        # 'ideaoptics' | 'ocean' | 'mock'
        self.hardware_vendor = hardware_vendor or ('ideaoptics' if use_real_hardware else 'mock')
        self.integration_time_ms = None
        self.scans_to_average = None

        self.in_endpoint = None

        # 根据硬件模式获取设备属性
        if self.is_real_hardware:
            self._name = self.api_wrapper.getName(self.device_index)
            self._serial_number = self.api_wrapper.getSerialNumber(self.device_index)
            self._wavelengths = list(self.api_wrapper.getWavelengths(self.device_index))

            # for endpoint in self.api_wrapper.EndPoints:
            #     if endpoint.Address > 0x80 and "Bulk" in str(endpoint.GetType()):
            #         self.in_endpoint = endpoint
            #         print(f"已找到数据输入端点，地址: {hex(self.in_endpoint.Address)}")
            #         break
        else:  # 模拟API的属性是直接访问的
            self._name = self.api_wrapper.getName(self.device_index)
            self._serial_number = self.api_wrapper.getSerialNumber(self.device_index)
            self._wavelengths = self.api_wrapper.wavelengths

        FX2000Controller._instance = self

    #一个中止数据传输的公共方法
    def abort_endpoint_pipe(self):
        """
        强制中止输入端点的数据传输管道。
        这是从不稳定状态中恢复的关键。
        """
        if self.is_real_hardware and self.in_endpoint:
            try:
                logger.info("abort_endpoint event=abort_endpoint address=%s", hex(self.in_endpoint.Address))
                self.in_endpoint.Abort()
                logger.info("abort_endpoint_complete event=abort_endpoint_complete")
            except Exception:
                logger.exception("abort_endpoint_failed event=abort_endpoint_failed")
        else:
            logger.debug("abort_endpoint_skipped event=abort_endpoint_skipped")

    @classmethod
    def connect(cls, use_real_hardware=True, device_index=0, hardware_vendor=None):
        """
        连接到光谱仪的工厂方法。
        如果实例已存在，则直接返回；否则，创建新实例。
        :param use_real_hardware: 布尔值，True表示连接真实硬件，False表示使用模拟API。
        :param device_index: 要连接的设备索引。
        :param hardware_vendor: 'ideaoptics' (默认) 或 'ocean'，仅在真实硬件模式下生效。
        :return: 控制器实例或None（如果连接失败）。
        """
        if cls._instance is None:
            vendor = (hardware_vendor or ('ideaoptics' if use_real_hardware else 'mock')).lower()
            logger.info(
                "controller_connect_started event=controller_connect_started mode=%s vendor=%s",
                "real" if use_real_hardware else "mock",
                vendor,
            )

            Wrapper = None
            if use_real_hardware:
                if vendor == 'ocean':
                    try:
                        # 把项目根目录加入 sys.path 以便导入 ocean_direct_api
                        project_root = Path(__file__).resolve().parents[2]
                        if str(project_root) not in sys.path:
                            sys.path.insert(0, str(project_root))
                        from ocean_direct_api import Wrapper
                        logger.info("driver_loaded event=driver_loaded vendor=ocean")
                    except Exception:
                        logger.warning(
                            "driver_load_failed event=driver_load_failed vendor=ocean fallback=mock",
                            exc_info=True,
                        )
                        from mock_spectrometer_api import Wrapper
                        use_real_hardware = False
                        vendor = 'mock'
                else:
                    try:
                        import clr
                        # 计算并添加驱动路径
                        driver_path = Path(__file__).resolve().parents[2] / 'drivers'
                        if str(driver_path) not in sys.path:
                            sys.path.append(str(driver_path))
                        os.environ['PATH'] = f"{str(driver_path)};{os.environ.get('PATH', '')}"

                        clr.AddReference(str(driver_path / "IdeaOptics"))
                        from IdeaOptics import Wrapper
                        logger.info("driver_loaded event=driver_loaded vendor=ideaoptics")
                    except Exception:
                        logger.warning(
                            "driver_load_failed event=driver_load_failed vendor=ideaoptics fallback=mock",
                            exc_info=True,
                        )
                        from mock_spectrometer_api import Wrapper
                        use_real_hardware = False  # 强制切换模式
                        vendor = 'mock'
            else:
                from mock_spectrometer_api import Wrapper
                logger.info("mock_driver_selected event=mock_driver_selected")
                vendor = 'mock'

            try:
                api_wrapper = Wrapper()
                device_count = api_wrapper.OpenAllSpectrometers()

                if device_count == 0 and use_real_hardware:
                    logger.error("device_not_found event=device_not_found")
                    return None

                cls(api_wrapper, use_real_hardware, device_index, hardware_vendor=vendor)
                logger.info(
                    "controller_connected event=controller_connected device=%s",
                    cls._instance.name,
                )

            except Exception:
                logger.exception("controller_connect_failed event=controller_connect_failed")
                cls._instance = None

        return cls._instance

    @classmethod
    def disconnect(cls):
        """
        【已优化】类方法，用于断开连接并重置单例实例。
        这对于重启或切换硬件模式至关重要。
        """
        if cls._instance is not None:
            try:
                if cls._instance.is_real_hardware and hasattr(cls._instance.api_wrapper, 'closeAllSpectrometers'):
                    # 尝试调用底层的关闭方法（仅对真实硬件）
                    cls._instance.api_wrapper.closeAllSpectrometers()
            except Exception:
                logger.exception("controller_disconnect_failed event=controller_disconnect_failed")
            finally:
                # 【核心】清空已缓存的实例，确保下次connect()可以重新创建
                cls._instance = None
                logger.info("controller_disconnected event=controller_disconnected")

    @property
    def name(self):
        return self._name

    @property
    def serial_number(self):
        return self._serial_number

    @property
    def wavelengths(self):
        return self._wavelengths

    def set_integration_time(self, time_ms: int):
        """设置光谱仪的积分时间。"""
        self.integration_time_ms = int(time_ms)
        self.api_wrapper.setIntegrationTime(self.device_index, time_ms)

    def set_scans_to_average(self, num_scans: int):
        """【新增】设置平均扫描次数。"""
        self.scans_to_average = int(num_scans)
        if hasattr(self.api_wrapper, 'setScansToAverage'):
            self.api_wrapper.setScansToAverage(self.device_index, num_scans)
        else:
            logger.warning("scans_average_unsupported event=scans_average_unsupported")

    def set_excitation_wavelength(self, wavelength: float):
        """【预留】设置激发波长。"""
        if hasattr(self.api_wrapper, 'setExcitationWavelength'):
            self.api_wrapper.setExcitationWavelength(self.device_index, wavelength)
            logger.info("excitation_wavelength_set event=excitation_wavelength_set")
        else:
            logger.warning("excitation_wavelength_unsupported event=excitation_wavelength_unsupported")

    def set_laser_power(self, power_percent: float):
        """【预留】设置激光功率。"""
        if hasattr(self.api_wrapper, 'setLaserPower'):
            self.api_wrapper.setLaserPower(self.device_index, power_percent)
            logger.info("laser_power_set event=laser_power_set")
        else:
            logger.warning("laser_power_unsupported event=laser_power_unsupported")

    def set_laser_state(self, enabled: bool):
        """【预留】设置激光开关状态。"""
        if hasattr(self.api_wrapper, 'setLaserState'):
            self.api_wrapper.setLaserState(self.device_index, enabled)
            logger.info("laser_state_set event=laser_state_set enabled=%s", enabled)
        else:
            logger.warning("laser_state_unsupported event=laser_state_unsupported")

    def get_spectrum(self):
        """【已修正】获取一条光谱数据，确保返回值为Numpy数组。"""
        import numpy as np  # Ensure numpy is imported
        spectrum_data = self.api_wrapper.getSpectrum(self.device_index)
        # Ensure both wavelengths and spectrum data are consistently NumPy arrays
        return np.array(self.wavelengths), np.array(list(spectrum_data))
