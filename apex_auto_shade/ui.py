# -*- coding: utf-8 -*-
"""侧边栏面板(CN/EN 双语) + 注册入口"""

try:
    import bpy
except Exception:
    bpy = None

from . import operators as O


def _T(p, zh, en):
    """按面板语言设置返回中文/英文/双语文本"""
    lang = getattr(p, 'lang', 'BOTH')
    if lang == 'CN':
        return zh
    if lang == 'EN':
        return en
    return zh + ' / ' + en


if bpy is not None:
    from .properties import ApexProperties

    class VIEW3D_PT_apex_autoshade(bpy.types.Panel):
        bl_label = 'Apex Auto-Shade'
        bl_idname = 'VIEW3D_PT_apex_autoshade'
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'Apex Auto-Shade'

        def draw(self, context):
            lay = self.layout
            p = context.scene.apex_autoshade
            lay.prop(p, 'lang')

            box = lay.box()
            box.label(text=_T(p, '导入模型 (.cast)', 'Import Model (.cast)'))
            box.operator('import_scene.apex_cast', text=_T(p, '选择 .cast 文件导入', 'Choose .cast file'), icon='IMPORT')

            box = lay.box()
            box.label(text=_T(p, '自动着色', 'Auto-Shade'))
            box.prop(p, 'tex_dir')
            box.operator('material.apex_auto_shade',
                         text=_T(p, '着色: 选中对象', 'Shade: Selected')).mode = 'SELECTED'
            box.operator('material.apex_auto_shade',
                         text=_T(p, '着色: 场景全部', 'Shade: All')).mode = 'ALL'

            box = lay.box()
            box.label(text=_T(p, '颜色与材质调节', 'Color & Material'))
            box.prop(p, 'albedo_auto')
            box.prop(p, 'albedo_target')
            box.prop(p, 'albedo_gamma')
            box.prop(p, 'albedo_boost')
            box.prop(p, 'albedo_sat')
            box.prop(p, 'emission_strength')
            box.prop(p, 'ao_strength')
            box.prop(p, 'specular_scale')
            box.prop(p, 'spec_mode')
            box.prop(p, 'spec_curve')
            box.prop(p, 'spec_base')
            box.prop(p, 'normal_strength')
            box.prop(p, 'flip_normal_g')
            box.prop(p, 'alpha_mode')
            box.prop(p, 'alpha_clip')
            box.prop(p, 'alpha_threshold')
            box.prop(p, 'alpha_glow')

            box = lay.box()
            box.label(text=_T(p, '导出参考视图 (六面+2斜视)', 'Reference Views (6 + 2 oblique)'), icon='CAMERA_DATA')
            box.operator('apex.export_views', text=_T(p, '渲染导出 8 张视图', 'Render 8 views'))
            box.prop(p, 'view_outdir')
            row = box.row()
            row.prop(p, 'view_res')
            row.prop(p, 'view_bg')
            box.prop(p, 'view_align')
            row = box.row()
            row.prop(p, 'obl_elevation')
            row.prop(p, 'obl_azimuth')
            box.prop(p, 'view_lighting')
            box.prop(p, 'view_light_strength')
            box.prop(p, 'view_vt')

            box = lay.box()
            box.label(text=_T(p, '3D 打印 STL (mm)', '3D Print STL (mm)'), icon='MOD_ARRAY')
            box.operator('apex.export_stl', text=_T(p, '导出 STL (选中对象)', 'Export STL (selected)'))
            box.prop(p, 'stl_dir')
            box.prop(p, 'stl_scale')
            box.prop(p, 'stl_merge')
            box.prop(p, 'stl_decimate')
            box.prop(p, 'stl_decimate_ratio')

            box = lay.box()
            box.label(text=_T(p, '导入选项', 'Import Options'))
            box.prop(p, 'create_armature')
            box.prop(p, 'flip_x')

    def _menu_func(self, context):
        self.layout.operator(O.IMPORT_OT_apex_cast.bl_idname, text='Apex RSX Cast (.cast)')

    classes = (ApexProperties, O.IMPORT_OT_apex_cast, O.MAT_OT_apex_auto_shade,
               O.VIEW_OT_apex_export_views, O.STL_OT_apex_export, VIEW3D_PT_apex_autoshade)

def register():
    if bpy is None:
        return
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.apex_autoshade = bpy.props.PointerProperty(type=ApexProperties)
    bpy.types.TOPBAR_MT_file_import.append(_menu_func)

def unregister():
    if bpy is None:
        return
    bpy.types.TOPBAR_MT_file_import.remove(_menu_func)
    del bpy.types.Scene.apex_autoshade
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
