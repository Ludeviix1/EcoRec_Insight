"""渠道与设备分析（开发文档第 28 节）。

- channel.py：渠道质量对比（organic/search/ads/campaign/recommendation）；
- device.py：设备活跃/转化/GMV/客单价/使用时间。
"""

from .channel import ChannelConfig, channel_analysis
from .device import DeviceConfig, device_analysis

__all__ = ["ChannelConfig", "channel_analysis", "DeviceConfig", "device_analysis"]