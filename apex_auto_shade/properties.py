# -*- coding: utf-8 -*-
"""插件属性组(CN/EN 双语标签)"""

try:
    import bpy
except Exception:
    bpy = None

if bpy is not None:

    class ApexProperties(bpy.types.PropertyGroup):
        lang: bpy.props.EnumProperty(name='语言 / Language', items=[
            ('BOTH', '中英双语 / Bilingual', ''),
            ('CN', '中文', ''),
            ('EN', 'English', ''),
        ], default='BOTH')

        # ---- 导入 / 自动着色 ----
        tex_dir: bpy.props.StringProperty(name='贴图文件夹 / Texture folder', subtype='DIR_PATH',
            description='存放 _col/_nml/... 贴图的文件夹(导入时自动检测) / Folder with _col/_nml/... maps (auto-detected on import)')
        albedo_boost: bpy.props.FloatProperty(name='Albedo 亮度 / Brightness', default=1.0, min=0.1, max=5.0,
            description='Base Color 提亮倍数(Apex 贴图偏暗时可 >1) / Base Color multiplier (Apex maps are dark, use >1)')
        albedo_sat: bpy.props.FloatProperty(name='Albedo 饱和度 / Saturation', default=1.0, min=0.1, max=4.0,
            description='仅放大贴图中已带颜色的像素(灰色不受影响) / Boosts only already-colored pixels (gray stays gray)')
        albedo_auto: bpy.props.BoolProperty(name='自动提亮 / Auto-brighten', default=True,
            description='建材质时读取col均值, 自动算出提亮倍率 / Auto-compute boost from the col mean per skin')
        albedo_target: bpy.props.FloatProperty(name='目标亮度 / Target (sRGB)', default=0.5, min=0.2, max=1.0,
            description='自动提亮的目标均值; 越接近1越亮 / Target mean brightness; closer to 1 = brighter')
        albedo_gamma: bpy.props.FloatProperty(name='暗部抬升 / Shadow lift (Gamma)', default=1.3, min=1.0, max=2.5,
            description='用Gamma节点抬暗部(藏蓝/深色不易发黑); 1.0=关闭 / Lift darks with a Gamma node; 1.0 = off')
        emission_strength: bpy.props.FloatProperty(name='ILM 发光强度 / Emission', default=2.0, min=0.0, max=20.0)
        ao_strength: bpy.props.FloatProperty(name='AO 强度 / AO', default=1.0, min=0.0, max=3.0)
        specular_scale: bpy.props.FloatProperty(name='Spec 强度 / Specular', default=1.0, min=0.0, max=3.0)
        spec_mode: bpy.props.EnumProperty(name='高光颜色 / Spec color', items=[
            ('gloss', 'spc彩色高光 / spc-colored gloss', ''),
            ('legacy', 'spc仅强度 / intensity only', ''),
        ], default='gloss',
            description='gloss: 用spc颜色叠一层Glossy高光(金色等) / glossy layer tinted by spc (gold etc.); legacy: scalar strength only')
        spec_curve: bpy.props.FloatProperty(name='高光收敛(幂) / Gloss pow', default=2.0, min=0.5, max=8.0,
            description='混合因子=spc亮度^幂; 越大高光越集中在亮部, 暗部不泛灰 / Fac = spc^pow; higher = highlights stay on bright gold areas')
        spec_base: bpy.props.FloatProperty(name='主高光压暗 / Base specular', default=0.15, min=0.0, max=1.0,
            description='gloss模式下主BSDF的Specular值: 调低防黑色部位发灰 / Base BSDF specular in gloss mode; lower = blacks stay black')
        normal_strength: bpy.props.FloatProperty(name='法线强度 / Normal', default=1.0, min=0.0, max=3.0)
        flip_normal_g: bpy.props.BoolProperty(name='翻转法线G通道 / Flip normal G', default=False,
            description='法线显示凹凸颠倒时勾选 / Tick if bumps look inverted')
        create_armature: bpy.props.BoolProperty(name='创建骨骼骨架 / Create armature', default=True)
        flip_x: bpy.props.BoolProperty(name='镜像X轴 / Mirror X', default=False,
            description='Source(左手系)转 Blender 可选 / Optional Source-to-Blender handedness fix')
        alpha_mode: bpy.props.EnumProperty(name='Alpha半透明 / Alpha', items=[
            ('auto', '自动(仅acc/玻璃类) / auto (acc/glass only)', ''),
            ('all', '全部材质 / all materials', ''),
            ('off', '关闭 / off', ''),
        ], default='auto',
            description='按材质名启用col的alpha半透明 / Enable col alpha per material name; body materials stay opaque')
        alpha_clip: bpy.props.BoolProperty(name='硬边裁剪(阈值) / Hard clip', default=False,
            description='低于阈值的alpha全透明, 高于全不透明 / Binary alpha: below threshold transparent, above opaque')
        alpha_threshold: bpy.props.FloatProperty(name='Alpha阈值 / Threshold', default=0.5, min=0.0, max=1.0)
        alpha_glow: bpy.props.FloatProperty(name='渐变发光强度 / Gradient glow', default=2.0, min=0.0, max=10.0,
            description='让半透明蓝紫渐变区域发光可见(模拟游戏内能量覆层); 0=关闭 / Make translucent gradients glow like in-game energy overlays; 0=off')

        # ---- 参考视图导出 ----
        view_outdir: bpy.props.StringProperty(name='视图输出目录 / View output', default='//export_views', subtype='DIR_PATH')
        view_res: bpy.props.EnumProperty(name='分辨率 / Resolution', items=[
            ('2048', '2048', '标准 / standard'),
            ('4096', '4096', '高分辨率 / hi-res'),
        ], default='2048')
        view_bg: bpy.props.EnumProperty(name='背景 / Background', items=[
            ('transparent', '透明 / Transparent', ''),
            ('white', '白底 / White', ''),
            ('black', '黑底 / Black', ''),
        ], default='transparent')
        view_align: bpy.props.BoolProperty(name='自动摆正 / Auto-align', default=True,
            description='相机按"枪口+Z→水平+Y"摆放; 已手动转好请取消 / Align cameras as if muzzle +Z -> horizontal +Y; untick if already aligned')
        obl_elevation: bpy.props.FloatProperty(name='斜视俯角° / Oblique elev.', default=35.0, min=0.0, max=90.0)
        obl_azimuth: bpy.props.FloatProperty(name='斜视水平角° / Oblique azimuth', default=45.0, min=5.0, max=85.0)
        view_lighting: bpy.props.EnumProperty(name='渲染灯光 / Lighting', items=[
            ('studio', '临时环境光 / Studio light', ''),
            ('none', '场景原灯光 / Scene lights', ''),
        ], default='studio',
            description='用临时白色环境光避免导出图偏黑 / Temp white environment light to avoid dark exports')
        view_light_strength: bpy.props.FloatProperty(name='环境光强度 / Light intensity', default=1.5, min=0.1, max=10.0)
        view_vt: bpy.props.EnumProperty(name='视图变换 / View trans.', items=[
            ('current', '跟随场景 / Scene', ''),
            ('standard', 'Standard(贴图直出) / Standard', ''),
        ], default='standard',
            description='Standard 颜色接近贴图本身(rsx预览观感) / Standard shows texture-like colors')

        # ---- 3D 打印 STL ----
        stl_dir: bpy.props.StringProperty(name='STL输出目录 / STL output', default='//export_stl', subtype='DIR_PATH')
        stl_scale: bpy.props.FloatProperty(name='导出倍率 / Scale (m→mm)', default=1000.0, min=1.0, max=1000000.0,
            description='STL 无单位; 默认1000 = Blender 1m -> 打印软件 1mm / STL is unitless; 1000 = Blender 1m -> slicer 1mm')
        stl_merge: bpy.props.BoolProperty(name='合并为单件STL / Merge into one STL', default=True)
        stl_decimate: bpy.props.BoolProperty(name='合并时减面 / Decimate', default=False)
        stl_decimate_ratio: bpy.props.FloatProperty(name='减面比例 / Ratio', default=0.5, min=0.05, max=1.0)
