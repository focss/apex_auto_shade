# Apex RSX Cast Import + Auto-Shade

Apex Legends (Respawn Source Engine) 武器 **.cast** 模型导入、自动着色、参考视图导出与 3D 打印 STL 工具。
Import rsx **.cast** weapon models, auto-shade with Apex texture sets, export 6+2 reference views and print-ready STL (mm). CN/EN 双语界面 / Bilingual UI.

---

## 功能特性 / Features

| 功能 / Feature | 说明 / Description |
|---|---|
| 导入 .cast / Import .cast | 解析 rsx_2.2.1 导出的二进制 .cast（网格/UV/法线/材质/骨骼/权重）。格式依据 r-ex/rsx 2.2.1 源码 src/core/mdl/cast.h 实现 |
| 自动着色 / Auto-Shade | 按材质名自动匹配同目录贴图集 _col/_nml/_gls/_spc/_ao/_cav/_ilm，搭建 Principled BSDF |
| 彩色还原 / Color fidelity | 自动提亮、Gamma 抬暗部、饱和度增强、spc 彩色金色高光层、alpha 半透明与渐变发光 |
| 参考视图 / Reference views | 六面视图 + 两张 3/4 斜视，正交相机、自动摆正（枪口水平）、临时 Studio 环境光、Standard 视图变换 |
| 3D 打印 / 3D Print | 自带二进制 STL 写入器（不依赖内置 STL 插件），倍率 1000：Blender 1m -> Bambu Studio 1mm |
| 双语 UI / Bilingual UI | 面板顶部可切换 中文 / English / 双语 |

## 安装 / Installation

文件夹安装（推荐）：
1. 把本仓库的 **apex_auto_shade/** 文件夹整个复制到 Blender 插件目录，例如：
   - Windows: %APPDATA%\Blender Foundation\Blender\5.2\scripts\addons\apex_auto_shade\
2. Blender -> 编辑（Edit）-> 偏好设置（Preferences）-> 插件（Add-ons）-> 搜索 "Apex" -> 勾选启用。

单文件兼容版（可选）：仓库根目录的 apex_auto_shade.py 是等效的单文件版（v1.6.x），可通过 "Install from Disk" 安装；二选一即可，不要同时启用。

## 使用步骤 / Quick Start

1. 在 rsx 中导出模型；确保同目录有同名贴图文件夹，如 repeater3030_lgnd_v25_clockwild_w/。
2. Blender -> 文件（File）-> 导入（Import）-> **Apex RSX Cast (.cast)** -> 选择 xxx_LOD0.cast。
3. 插件自动：创建网格+材质+骨骼 -> 自动匹配贴图 -> 搭好 Principled BSDF。
4. 需要时：选枪 -> 导出参考视图（8 张 PNG）；或导出 STL 拖进 Bambu Studio 打印。

控制台会打印每套材质匹配到的贴图，以及自动提亮倍率（如 col均值=0.310 自动提亮 x1.61）。

## 材质连线总览 / Material Map (Principled BSDF)

| 贴图 / Map | 用途 / Socket | 颜色空间 / Colorspace |
|---|---|---|
| _col | Base Color（自动提亮 -> Gamma抬暗部 -> 饱和度 -> ao×cav） | sRGB |
| _nml | Normal（双通道法线自动重建 B 通道） | Non-Color |
| _gls | Roughness（1-glx） | Non-Color |
| _spc | 彩色高光层 Glossy（金色等，默认）/ 或 Specular 强度 | Non-Color |
| _ao | 乘入 Base Color（环境遮蔽） | Non-Color |
| _cav | 与 ao 相乘（缝隙细节） | Non-Color |
| _ilm | Emission（烘焙光照；acc 材质启用渐变发光时改用 alpha 驱动） | Non-Color |

## 参数速查 / Parameter Reference

### 颜色与材质 / Color & Material

| 参数 / Parameter | 默认 / Default | 说明 / Note |
|---|---|---|
| 自动提亮 / Auto-brighten | 开 | 读取 col 均值自动算倍率（每把枪适配）；深色贴图不再发黑 |
| 目标亮度 / Target (sRGB) | 0.5 | 越接近 1 越亮 |
| 暗部抬升 / Shadow lift (Gamma) | 1.3 | 藏蓝等深色不易变黑；1.0 关闭 |
| Albedo 亮度 / Brightness | 1.0 | 手动倍率（与自动取较大值） |
| Albedo 饱和度 / Saturation | 1.0 | >1 只放大已有彩色（灰底皮肤的红黄点缀可见） |
| ILM 发光 / Emission | 2.0 | ilm 强度 |
| AO 强度 / AO | 1.0 | |
| Spec 强度 / Specular | 1.0 | 高光层混合强度 |
| 高光颜色 / Spec color | spc彩色高光 | 金色反光由 spc 颜色正确还原 |
| 高光收敛(幂) / Gloss pow | 2.0 | 高光集中在亮部，暗部不泛灰 |
| 主高光压暗 / Base specular | 0.15 | 黑色部位不被白色高光冲灰 |
| 法线强度 / Normal | 1.0 | |
| 翻转法线G / Flip normal G | 关 | 法线颠倒时勾选 |
| Alpha 半透明 / Alpha | 自动(仅acc/玻璃类) | 主体材质不透明，覆层材质半透明 |
| 硬边裁剪 / Hard clip | 关 | 用阈值把 alpha 变二值 |
| 渐变发光 / Gradient glow | 2.0 | 半透明蓝紫渐变发光可见；0 关闭 |

### 参考视图 / Reference Views

| 参数 / Parameter | 默认 / Default | 说明 / Note |
|---|---|---|
| 分辨率 / Resolution | 2048 / 4096 | |
| 背景 / Background | 透明 | 透明/白底/黑底(黑底自动透明) |
| 自动摆正 / Auto-align | 开 | 相机按"枪口+Z->水平+Y"摆放 |
| 斜视俯角/水平角 / Oblique elev./az | 35° / 45° | 两张 3/4 视图：左前上、右前上 |
| 渲染灯光 / Lighting | 临时环境光 | 避免导出图偏黑 |
| 环境光强度 / Light intensity | 1.5 | |
| 视图变换 / View transform | Standard | 颜色接近贴图直出（rsx 预览观感） |

### 3D 打印 STL / 3D Print

| 参数 / Parameter | 默认 / Default | 说明 / Note |
|---|---|---|
| 导出倍率 / Scale (m->mm) | 1000 | Blender 1m = Bambu Studio 1mm；真实尺寸枪（0.76m）-> 导出 760mm |
| 合并单件 / Merge | 开 | 选中多个网格时合并为一个 STL |
| 减面 / Decimate | 关 | 合并时可选 DECIMATE 简化 |

## 输出文件 / Outputs

- 参考视图：export_views/（.blend 同目录）-> front/back/right/left/top/bottom/oblique_l/oblique_r.png
- STL：export_stl/ -> <scene>_print.stl / <obj>_print.stl（二进制 STL，mm 精确）

## 常见问题 / FAQ

- **导出图偏黑**：确认"自动提亮"开启；把"环境光强度"调到 2~3；把色彩管理(视图变换)改为 Standard。
- **金色高光不出现或太灰**：高光颜色=spc彩色高光，Spec 强度 1~1.5、收敛幂 2~2.5；暗部泛灰就把主高光压暗调到 0.05~0.15。
- **半透明区域乱透/主体被挖洞**：Alpha 半透明保持"自动"或"关闭"。
- **Blender 5.x 报 "Specular not found" 等**：插件已做 3.x/4.x/5.x 接口兼容，找不到输入口会跳过不崩。
- **STL 大小不对**：确认导出倍率 1000（1m->1mm）；模型若已按真实尺寸（x0.0254）则枪长约 760mm。

## 目录结构 / Repository Layout

~~~
apex_auto_shade/            # Blender 插件包(安装整个文件夹)
|-- __init__.py             # bl_info + 注册入口
|-- core.py                 # cast 解析 / 贴图匹配 / 视图几何 / STL 写入(纯Python, 可单测)
|-- shadergraph.py          # Principled BSDF 节点搭建
|-- properties.py           # 属性组(双语标签)
|-- operators.py            # 导入 / 着色 / 视图 / STL 操作符
'-- ui.py                   # 侧边栏面板(双语) + 菜单 + 注册
apex_auto_shade.py          # 单文件兼容版(可选, v1.6.x)
README.md                   # 本说明
LICENSE.md
~~~

## 致谢 / Credits

- r-ex/rsx — Apex/TF 素材提取工具，.cast 格式源码依据
- Gl2imm/Apex-Toolbox — 社区工具箱（尺寸换算思路参考：Source 英寸 -> 米 0.0254）
- dtzxporter/cast — .cast 导入参考实现

## 许可 / License

MIT，详见 LICENSE.md。与游戏资产无关的代码部分自由使用；模型与贴图资产归 Respawn/EA 所有，请勿用于商业发行。
