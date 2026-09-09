# -*- coding: utf-8 -*-
"""Apex RSX Cast Import + Auto-Shade
=====================================
Apex Legends (Respawn Source Engine) 武器 .cast 模型导入 + 自动着色 + 参考视图 + 3D打印STL。
Import rsx .cast weapon models, auto-build Principled BSDF materials from
col/nml/gls/spc/ao/cav/ilm maps, export 6+2 reference views and print-ready STL (mm).
"""

from . import core            # 纯解析/匹配/几何(可脱离 Blender 测试)
from . import shadergraph     # 材质节点搭建
from . import properties      # 属性组(双语)
from . import operators       # 操作符
from . import ui              # 面板 + 菜单 + 注册
from .ui import register, unregister

bl_info = {
    "name": "Apex RSX Cast Import + Auto-Shade",
    "author": "focss",
    "version": (2, 0, 0),
    "blender": (3, 3, 0),
    "location": "File > Import > Apex RSX Cast (.cast) / 3D View > N > Apex Auto-Shade",
    "description": "Import rsx .cast weapon models, auto-shade with Apex col/nml/gls/spc/ao/cav/ilm maps, "
                   "export 6+2 reference views and print STL in mm. CN/EN bilingual UI.",
    "category": "Import-Export",
    "support": "COMMUNITY",
    "doc_url": "https://github.com/r-ex/rsx",
}

__all__ = ['register', 'unregister', 'core', 'shadergraph', 'properties', 'operators', 'ui']
