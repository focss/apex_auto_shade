# -*- coding: utf-8 -*-
"""操作符: 导入cast / 自动着色 / 视图导出 / STL导出"""
import math
import os
import re

try:
    import bpy
    from mathutils import Vector, Quaternion, Matrix
except Exception:
    bpy = None

from .core import (parse_cast, find_texture_dir_for_cast, _view_setup,
                    _mesh_to_tris, _write_stl_binary)
from .shadergraph import auto_shade_objects


def _opts(context):
    p = context.scene.apex_autoshade
    return {
        'albedo_boost': p.albedo_boost,
        'albedo_sat': p.albedo_sat,
        'albedo_auto': p.albedo_auto,
        'albedo_target': p.albedo_target,
        'albedo_gamma': p.albedo_gamma,
        'emission_strength': p.emission_strength,
        'ao_strength': p.ao_strength,
        'specular_scale': p.specular_scale,
        'spec_mode': p.spec_mode,
        'spec_curve': p.spec_curve,
        'spec_base': p.spec_base,
        'normal_strength': p.normal_strength,
        'flip_normal_g': p.flip_normal_g,
        'alpha_mode': p.alpha_mode,
        'alpha_clip': p.alpha_clip,
        'alpha_threshold': p.alpha_threshold,
        'alpha_glow': p.alpha_glow,
    }


if bpy is not None:

    class IMPORT_OT_apex_cast(bpy.types.Operator):
        bl_idname = 'import_scene.apex_cast'
        bl_label = '导入 Apex RSX Cast / Import Apex RSX Cast (.cast)'
        bl_options = {'REGISTER', 'UNDO'}

        filepath: bpy.props.StringProperty(subtype='FILE_PATH')
        filter_glob: bpy.props.StringProperty(default='*.cast', options={'HIDDEN'})

        def execute(self, context):
            p = context.scene.apex_autoshade
            cast_result = parse_cast(self.filepath)
            folder = p.tex_dir or ''
            if not folder or not os.path.isdir(folder):
                folder = find_texture_dir_for_cast(self.filepath)
                if folder:
                    p.tex_dir = folder
            if not folder:
                self.report({'ERROR'}, '找不到贴图文件夹, 请在侧边栏手动指定 / Texture folder not found, set it in the panel')
                return {'CANCELLED'}

            model = os.path.splitext(os.path.basename(self.filepath))[0]
            model = re.sub(r'_LOD\d+$', '', model)
            col = bpy.data.collections.new('apex_' + model)
            context.scene.collection.children.link(col)

            sx = -1.0 if p.flip_x else 1.0
            bone_names = [b['name'] for b in cast_result['bones']]

            mats = {}
            for msh in cast_result['meshes']:
                me = bpy.data.meshes.new(msh['name'])
                verts = [(sx * v[0], v[1], v[2]) for v in msh['positions']]
                faces = [list(f) for f in msh['faces']]
                me.from_pydata(verts, [], faces)
                me.update()
                if msh['normals']:
                    try:
                        me.use_auto_smooth = True
                        me.normals_split_custom_set_from_vertices(
                            [(sx * n[0], n[1], n[2]) for n in msh['normals']])
                    except Exception:
                        pass
                if msh['uvs']:
                    uvl = me.uv_layers.new(name='UVMap')
                    for poly in me.polygons:
                        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
                            v = me.loops[li].vertex_index
                            u, vv = msh['uvs'][v]
                            uvl.data[li].uv = (u, 1.0 - vv)
                obj = bpy.data.objects.new(msh['name'], me)
                col.objects.link(obj)
                mname = msh['material']
                if mname:
                    if mname not in mats:
                        m = bpy.data.materials.new(mname)
                        mats[mname] = m
                    obj.data.materials.append(mats[mname])
                if p.create_armature and msh['weights']:
                    for vi, (bi, w) in enumerate(msh['weights']):
                        if w <= 0.0 or bi < 0 or bi >= len(bone_names):
                            continue
                        grp = obj.vertex_groups.get(bone_names[bi]) or obj.vertex_groups.new(name=bone_names[bi])
                        try:
                            grp.add([vi], w, 'REPLACE')
                        except Exception:
                            pass

            if p.create_armature and cast_result['bones']:
                arm = bpy.data.armatures.new(model + '_arm')
                arm_obj = bpy.data.objects.new(model + '_arm', arm)
                col.objects.link(arm_obj)
                context.view_layer.objects.active = arm_obj
                bpy.ops.object.mode_set(mode='EDIT')
                ebones = []
                for i, b in enumerate(cast_result['bones']):
                    eb = arm.edit_bones.new(b['name'])
                    eb.parent = ebones[b['parent']] if 0 <= b['parent'] < len(ebones) else None
                    loc = b['pos'] or (0.0, 0.0, 0.0)
                    rot = b['quat'] or (1.0, 0.0, 0.0, 0.0)
                    q = Quaternion((rot[3], rot[0], rot[1], rot[2])) if len(rot) == 4 else Quaternion()
                    if sx < 0:
                        loc = (-loc[0], loc[1], loc[2])
                    eb.head = Vector(loc)
                    eb.tail = eb.head + Vector((0.0, 0.0, 0.08))
                    try:
                        eb.matrix = Matrix.Translation(Vector(loc)) @ q.to_matrix().to_4x4()
                    except Exception:
                        pass
                    ebones.append(eb)
                bpy.ops.object.mode_set(mode='OBJECT')

            report = auto_shade_objects(
                [o for o in col.objects if o.type == 'MESH'], folder, _opts(context))
            for line in report:
                print('[ApexAutoShade]', line)
            self.report({'INFO'}, '导入 {n} 个网格并着色 / Imported {n} meshes and shaded: {f}'.format(
                n=len(cast_result['meshes']), f=folder))
            return {'FINISHED'}

        def invoke(self, context, event):
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}

    class MAT_OT_apex_auto_shade(bpy.types.Operator):
        bl_idname = 'material.apex_auto_shade'
        bl_label = '自动着色 / Auto-Shade (Apex)'
        bl_options = {'REGISTER', 'UNDO'}

        mode: bpy.props.EnumProperty(items=[
            ('SELECTED', '选中对象 / Selected', ''),
            ('ALL', '场景全部 / All', ''),
        ], default='SELECTED')

        def execute(self, context):
            p = context.scene.apex_autoshade
            folder = p.tex_dir or ''
            if not os.path.isdir(folder):
                self.report({'ERROR'}, '请先在侧边栏指定贴图文件夹 / Set the texture folder in the panel first')
                return {'CANCELLED'}
            objs = (context.selected_objects if self.mode == 'SELECTED'
                    else list(context.scene.objects))
            report = auto_shade_objects(objs, folder, _opts(context))
            for line in report:
                print('[ApexAutoShade]', line)
            self.report({'INFO'}, '完成, 共处理 {n} 条材质 / Done, {n} materials'.format(n=len(report)))
            return {'FINISHED'}

    class VIEW_OT_apex_export_views(bpy.types.Operator):
        bl_idname = 'apex.export_views'
        bl_label = '导出六面+2斜视参考图 / Export 6 + 2 Reference Views'
        bl_options = {'REGISTER'}

        def execute(self, context):
            p = context.scene.apex_autoshade
            objs = [o for o in context.selected_objects if o.type == 'MESH']
            if not objs:
                self.report({'ERROR'}, '请先选中网格对象(枪身网格) / Select the mesh objects first')
                return {'CANCELLED'}
            outdir = bpy.path.abspath(p.view_outdir or '//export_views')
            try:
                os.makedirs(outdir, exist_ok=True)
            except OSError as e:
                self.report({'ERROR'}, '无法创建输出目录 / Cannot create output dir: {e}'.format(e=e))
                return {'CANCELLED'}

            pts = []
            for o in objs:
                mw = o.matrix_world
                for v in o.data.vertices:
                    pts.append(mw @ v.co)
            if not pts:
                self.report({'ERROR'}, '对象没有顶点 / No vertices found')
                return {'CANCELLED'}
            mn = Vector((min(v.x for v in pts), min(v.y for v in pts), min(v.z for v in pts)))
            mx = Vector((max(v.x for v in pts), max(v.y for v in pts), max(v.z for v in pts)))
            center = (mn + mx) * 0.5
            dims = mx - mn
            maxdim = max(dims.x, dims.y, dims.z)
            if maxdim <= 0.0:
                self.report({'ERROR'}, '包围盒无效 / Invalid bounds')
                return {'CANCELLED'}
            ortho = maxdim * 1.15
            dist = maxdim * 4.0

            rot = Matrix.Rotation(math.radians(-90.0), 4, 'X') if p.view_align else Matrix.Identity(4)

            rs = context.scene.render
            _res = int(p.view_res)
            rs.resolution_x = _res
            rs.resolution_y = _res
            rs.image_settings.file_format = 'PNG'
            if p.view_bg == 'transparent':
                rs.film_transparent = True
                rs.image_settings.color_mode = 'RGBA'
            else:
                rs.film_transparent = False
                rs.image_settings.color_mode = 'RGB'

            saved_world = context.scene.world
            saved_film = rs.film_transparent
            saved_exposure = context.scene.view_settings.exposure
            saved_vt = context.scene.view_settings.view_transform
            world_light = None
            if p.view_lighting == 'studio':
                world_light = bpy.data.worlds.get('apex_view_world')
                if world_light is None:
                    world_light = bpy.data.worlds.new('apex_view_world')
                world_light.use_nodes = True
                wnt = world_light.node_tree
                for wn in list(wnt.nodes):
                    wnt.nodes.remove(wn)
                bg = wnt.nodes.new('ShaderNodeBackground')
                bg.inputs['Color'].default_value = (0.85, 0.85, 0.85, 1.0)
                bg.inputs['Strength'].default_value = p.view_light_strength
                wo = wnt.nodes.new('ShaderNodeOutputWorld')
                wnt.links.new(bg.outputs[0], wo.inputs['Surface'])
                context.scene.world = world_light
                if p.view_bg == 'black':
                    rs.film_transparent = True
                    rs.image_settings.color_mode = 'RGBA'
                context.scene.view_settings.exposure += 0.5
            if p.view_vt == 'standard':
                context.scene.view_settings.view_transform = 'Standard'
            made = []
            try:
                for name, d, vup in _view_setup(p.obl_elevation, p.obl_azimuth):
                    cam = bpy.data.cameras.new('apex_view_' + name)
                    cam.type = 'ORTHO'
                    cam.ortho_scale = ortho
                    cam.clip_start = 0.001
                    cam.clip_end = maxdim * 200.0
                    cam_obj = bpy.data.objects.new('apex_viewcam_' + name, cam)
                    context.scene.collection.objects.link(cam_obj)
                    made.append(cam_obj)
                    wdir = (rot @ Vector(d)).normalized()
                    wup = (rot @ Vector(vup)).normalized()
                    pos = center + wdir * dist
                    f = (center - pos).normalized()
                    rv = f.cross(wup)
                    if rv.length_squared < 1e-10:
                        rv = f.cross(Vector((0.0, 0.0, 1.0)))
                    if rv.length_squared < 1e-10:
                        rv = f.cross(Vector((1.0, 0.0, 0.0)))
                    rv.normalize()
                    upv = rv.cross(f)
                    cam_obj.matrix_world = Matrix((
                        (rv.x, upv.x, -f.x, pos.x),
                        (rv.y, upv.y, -f.y, pos.y),
                        (rv.z, upv.z, -f.z, pos.z),
                        (0.0, 0.0, 0.0, 1.0),
                    ))
                    context.scene.camera = cam_obj
                    rs.filepath = os.path.join(outdir, name + '.png')
                    bpy.ops.render.render(write_still=True)
            finally:
                if world_light is not None:
                    context.scene.world = saved_world
                    context.scene.view_settings.exposure = saved_exposure
                    context.scene.view_settings.view_transform = saved_vt
                    rs.film_transparent = saved_film
                    try:
                        bpy.data.worlds.remove(world_light)
                    except Exception:
                        pass
                for o in made:
                    try:
                        bpy.data.objects.remove(o, do_unlink=True)
                    except Exception:
                        pass
                for c in list(bpy.data.cameras):
                    if c.name.startswith('apex_view_'):
                        try:
                            bpy.data.cameras.remove(c)
                        except Exception:
                            pass
            self.report({'INFO'}, '已导出 8 张参考视图到 / Exported 8 views to: {d}'.format(d=outdir))
            return {'FINISHED'}

    class STL_OT_apex_export(bpy.types.Operator):
        bl_idname = 'apex.export_stl'
        bl_label = '导出打印STL(mm) / Export Print STL (mm)'
        bl_options = {'REGISTER'}

        def execute(self, context):
            p = context.scene.apex_autoshade
            sel = context.selected_objects
            objs = [o for o in sel if o.type == 'MESH'] if sel else [o for o in context.scene.objects if o.type == 'MESH']
            if not objs:
                self.report({'ERROR'}, '请先选中网格对象 / Select mesh objects first')
                return {'CANCELLED'}
            outdir = bpy.path.abspath(p.stl_dir or '//export_stl')
            try:
                os.makedirs(outdir, exist_ok=True)
            except OSError as e:
                self.report({'ERROR'}, '无法创建输出目录 / Cannot create output dir: {e}'.format(e=e))
                return {'CANCELLED'}
            scale = p.stl_scale
            prev_sel = list(sel)
            prev_active = context.view_layer.objects.active
            try:
                deps = context.evaluated_depsgraph_get()
                if p.stl_merge and len(objs) > 1:
                    tmp_col = bpy.data.collections.new('__apex_stl_tmp__')
                    context.scene.collection.children.link(tmp_col)
                    temps = []
                    for o in objs:
                        ev = o.evaluated_get(deps)
                        me = bpy.data.meshes.new_from_object(ev, depsgraph=deps)
                        tmp = bpy.data.objects.new(o.name + '_tmp', me)
                        tmp.matrix_world = Matrix(o.matrix_world)
                        tmp_col.objects.link(tmp)
                        temps.append(tmp)
                    bpy.ops.object.select_all(action='DESELECT')
                    for t in temps:
                        t.select_set(True)
                    context.view_layer.objects.active = temps[0]
                    if len(temps) > 1:
                        bpy.ops.object.join()
                    merged = temps[0]
                    if p.stl_decimate:
                        md = merged.modifiers.new('apex_decimate', 'DECIMATE')
                        md.ratio = p.stl_decimate_ratio
                    outpath = os.path.join(outdir, context.scene.name + '_print.stl')
                    evm = merged.evaluated_get(deps)
                    fme = bpy.data.meshes.new_from_object(evm, depsgraph=deps)
                    tris = _mesh_to_tris(fme, merged.matrix_world, scale)
                    _write_stl_binary(outpath, tris, scale)
                    bpy.data.meshes.remove(fme, do_unlink=False)
                    bpy.data.objects.remove(merged, do_unlink=True)
                    bpy.data.collections.remove(tmp_col)
                else:
                    for o in objs:
                        ev = o.evaluated_get(deps)
                        me = bpy.data.meshes.new_from_object(ev, depsgraph=deps)
                        tris = _mesh_to_tris(me, o.matrix_world, scale)
                        outpath = os.path.join(outdir, o.name + '_print.stl')
                        _write_stl_binary(outpath, tris, scale)
                        bpy.data.meshes.remove(me, do_unlink=False)
            except Exception as e:
                self.report({'ERROR'}, 'STL 导出失败 / STL export failed: {e}'.format(e=e))
                return {'CANCELLED'}
            finally:
                bpy.ops.object.select_all(action='DESELECT')
                for o in prev_sel:
                    try:
                        o.select_set(True)
                    except Exception:
                        pass
                context.view_layer.objects.active = prev_active
            self.report({'INFO'}, 'STL 已导出(倍率 {s:.2f}, Blender m→打印 mm) / STL exported (scale {s:.2f}): {d}'.format(s=scale, d=outdir))
            return {'FINISHED'}
