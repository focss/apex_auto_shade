# -*- coding: utf-8 -*-
"""Blender 材质节点搭建(Principled BSDF 链路)"""
import os

try:
    import bpy
except Exception:
    bpy = None

from .core import _want_alpha, find_texture_set


def _img_node(material, name, path, non_color=True):
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        try:
            img.colorspace_settings.name = 'Non-Color'
        except Exception:
            try:
                img.colorspace_settings.name = 'Linear'
            except Exception:
                pass
    node = material.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = img
    node.label = name
    node.name = 'apex_' + name
    return node


def _math(material, op, v1, v2=None):
    n = material.node_tree.nodes.new('ShaderNodeMath')
    n.operation = op
    n.inputs[0].default_value = v1
    if v2 is not None and len(n.inputs) > 1:
        n.inputs[1].default_value = v2
    return n


def _mix_mul(mat, a, b=None, const=None):
    """颜色按通道相乘(保留彩色): a * b 或 a * const(RGB元组)。
    注意 Blender Math 节点是单通道, 颜色进 Math 会变灰度(luminance),
    这是彩色丢失的根因; 用 Mix/MixRGB 的 Multiply 按通道相乘。"""
    node = None
    try:
        node = mat.node_tree.nodes.new('ShaderNodeMix')
    except Exception:
        node = None
    if node is not None:
        try:
            try:
                node.data_type = 'RGBA'
            except Exception:
                pass
            node.blend_type = 'MULTIPLY'
            try:
                node.inputs['Factor'].default_value = 1.0
            except Exception:
                pass
            mat.node_tree.links.new(a, node.inputs['A'])
            if const is not None:
                node.inputs['B'].default_value = (const[0], const[1], const[2], 1.0)
            else:
                mat.node_tree.links.new(b, node.inputs['B'])
            return node.outputs['Result']
        except Exception:
            pass
    try:
        node = mat.node_tree.nodes.new('ShaderNodeMixRGB')
        node.blend_type = 'MULTIPLY'
        try:
            node.inputs['Fac'].default_value = 1.0
        except Exception:
            pass
        mat.node_tree.links.new(a, node.inputs['Color1'])
        if const is not None:
            node.inputs['Color2'].default_value = (const[0], const[1], const[2], 1.0)
        else:
            mat.node_tree.links.new(b, node.inputs['Color2'])
        return node.outputs['Color']
    except Exception:
        return None


def _sock(inputs, *names):
    """返回第一个存在的输入口, 兼容 Blender 3.x/4.x/5.x 的 BSDF 接口改名"""
    for n in names:
        try:
            return inputs[n]
        except (KeyError, TypeError):
            continue
    return None


def _gamma(mat, sock, g):
    """Gamma 节点抬暗部: 深色乘提亮后仍显黑时, 用它恢复色彩(藏蓝等)"""
    if abs(g - 1.0) < 1e-4:
        return sock
    try:
        node = mat.node_tree.nodes.new('ShaderNodeGamma')
        try:
            node.inputs['Gamma'].default_value = g
        except Exception:
            node.inputs[0].default_value = g
        mat.node_tree.links.new(sock, node.inputs['Color'])
        return node.outputs['Color']
    except Exception:
        return sock


def _saturate(mat, sock, factor):
    """对颜色 socket 施加饱和度倍率(用 Hue/Saturation 节点, 兼容旧版则跳过)"""
    if abs(factor - 1.0) < 1e-4:
        return sock
    try:
        node = mat.node_tree.nodes.new('ShaderNodeHueSaturation')
        try:
            node.inputs['Saturation'].default_value = factor
        except Exception:
            node.inputs[1].default_value = factor
        mat.node_tree.links.new(sock, node.inputs['Color'])
        return node.outputs['Color']
    except Exception:
        return sock


def _sep_rgb(material):
    try:
        return material.node_tree.nodes.new('ShaderNodeSeparateColor')
    except Exception:
        return material.node_tree.nodes.new('ShaderNodeSeparateRGB')


def _comb_rgb(material):
    try:
        return material.node_tree.nodes.new('ShaderNodeCombineColor')
    except Exception:
        return material.node_tree.nodes.new('ShaderNodeCombineRGB')


def build_apex_material(mat, texset, opts):
    """按 texset 贴图集搭建 Principled BSDF 节点"""
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.name = 'apex_bsdf'
    nt.links.new(bsdf.outputs[0], out.inputs[0])

    base = texset.get('col')
    if base:
        col = _img_node(mat, 'col', base, non_color=False)
        boost = opts.get('albedo_boost', 1.0)
        if opts.get('albedo_auto', True):
            try:
                img = col.image
                w, h = img.size
                pix = img.pixels
                span = w * h * 4
                n = 0
                s = 0.0
                for i in range(7 * 4, span - 4, 7 * 4 * 193):
                    s += pix[i] + pix[i + 1] + pix[i + 2]
                    n += 3
                if n > 0:
                    mean = s / n
                    auto = (opts.get('albedo_target', 0.5)) / max(mean, 0.01)
                    auto = min(6.0, max(1.0, auto))
                    boost = max(boost, auto)
                    print('[ApexAutoShade] {m}: col均值={v:.3f} 自动提亮 x{f:.2f}'.format(m=mat.name, v=mean, f=auto))
            except Exception:
                pass
        if boost != 1.0:
            _m = _mix_mul(mat, col.outputs['Color'], None, (boost, boost, boost))
            target = _m if _m is not None else col.outputs['Color']
        else:
            target = col.outputs['Color']
        target = _gamma(mat, target, opts.get('albedo_gamma', 1.3))
        target = _saturate(mat, target, opts.get('albedo_sat', 1.0))
        ao = texset.get('ao')
        cav = texset.get('cav')
        if ao or cav:
            acc = None
            if ao:
                acc = _img_node(mat, 'ao', ao).outputs['Color']
            if cav:
                cavn = _img_node(mat, 'cav', cav).outputs['Color']
                if acc is None:
                    acc = cavn
                else:
                    _m = _mix_mul(mat, acc, cavn)
                    if _m is not None:
                        acc = _m
            ao_fac = opts.get('ao_strength', 1.0)
            if ao_fac != 1.0:
                _m = _mix_mul(mat, acc, None, (ao_fac, ao_fac, ao_fac))
                if _m is not None:
                    acc = _m
            _m = _mix_mul(mat, target, acc)
            if _m is not None:
                target = _m
        base_sock = _sock(bsdf.inputs, 'Base Color')
        if base_sock is not None:
            nt.links.new(target, base_sock)
        if _want_alpha(mat.name or '', opts.get('alpha_mode', 'auto')):
            alpha_sock = _sock(bsdf.inputs, 'Alpha')
            if alpha_sock is not None:
                try:
                    if opts.get('alpha_clip', False):
                        th = _math(mat, 'GREATER_THAN', 1.0)
                        th.inputs[1].default_value = max(0.0, min(1.0, opts.get('alpha_threshold', 0.5)))
                        nt.links.new(col.outputs['Alpha'], th.inputs[0])
                        nt.links.new(th.outputs[0], alpha_sock)
                        mat.blend_method = 'CLIP'
                    else:
                        nt.links.new(col.outputs['Alpha'], alpha_sock)
                        mat.blend_method = 'BLEND'
                except Exception:
                    pass
            glow_v = opts.get('alpha_glow', 0.0)
            if glow_v > 0.0:
                try:
                    gmul = _math(mat, 'MULTIPLY', glow_v)
                    nt.links.new(col.outputs['Alpha'], gmul.inputs[0])
                    est = _sock(bsdf.inputs, 'Emission Strength')
                    ecol = _sock(bsdf.inputs, 'Emission Color')
                    if est is not None:
                        nt.links.new(gmul.outputs[0], est)
                    if ecol is not None:
                        nt.links.new(col.outputs['Color'], ecol)
                except Exception:
                    pass

    nml = texset.get('nml')
    if nml:
        nnode = _img_node(mat, 'nml', nml)
        sep = _sep_rgb(mat)
        nt.links.new(nnode.outputs['Color'], sep.inputs[0])
        r = sep.outputs[0]
        g = sep.outputs[1]
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nr_in = nm.inputs[1]  # Color(3.x) / Vector(4.x/5.x)
        comb = _comb_rgb(mat)
        nt.links.new(r, comb.inputs[0])
        gv = g
        if opts.get('flip_normal_g', False):
            inv = _math(mat, 'SUBTRACT', 1.0)
            nt.links.new(g, inv.inputs[1])
            gv = inv.outputs[0]
        nt.links.new(gv, comb.inputs[1])

        def nx_chain(src):
            a = _math(mat, 'SUBTRACT', 0.5)
            nt.links.new(src, a.inputs[1])
            b = _math(mat, 'MULTIPLY', 2.0)
            nt.links.new(a.outputs[0], b.inputs[0])
            c = _math(mat, 'MULTIPLY', 1.0)
            nt.links.new(b.outputs[0], c.inputs[0])
            nt.links.new(b.outputs[0], c.inputs[1])
            return c

        rx = nx_chain(r)
        gy = nx_chain(gv)
        add = _math(mat, 'ADD', 1.0)
        nt.links.new(rx.outputs[0], add.inputs[0])
        nt.links.new(gy.outputs[0], add.inputs[1])
        inv2 = _math(mat, 'SUBTRACT', 1.0)
        nt.links.new(add.outputs[0], inv2.inputs[1])
        sq = _math(mat, 'SQRT', 1.0)
        nt.links.new(inv2.outputs[0], sq.inputs[0])
        h1 = _math(mat, 'MULTIPLY', 0.5)
        nt.links.new(sq.outputs[0], h1.inputs[0])
        h2 = _math(mat, 'ADD', 0.5)
        nt.links.new(h1.outputs[0], h2.inputs[0])
        nt.links.new(h2.outputs[0], comb.inputs[2])
        nt.links.new(comb.outputs[0], nr_in)
        nm.inputs['Strength'].default_value = opts.get('normal_strength', 1.0)
        nrm = _sock(bsdf.inputs, 'Normal')
        if nrm is not None:
            nt.links.new(nm.outputs['Normal'], nrm)

    _rough_gloss = None
    gls = texset.get('gls')
    if gls:
        gn = _img_node(mat, 'gls', gls)
        inv = _math(mat, 'SUBTRACT', 1.0)
        nt.links.new(gn.outputs['Color'], inv.inputs[1])
        rgh = _sock(bsdf.inputs, 'Roughness')
        if rgh is not None:
            nt.links.new(inv.outputs[0], rgh)
        _rough_gloss = inv.outputs[0]

    spc = texset.get('spc')
    if spc:
        sn = _img_node(mat, 'spc', spc)
        sc = opts.get('specular_scale', 1.0)
        if opts.get('spec_mode', 'gloss') == 'gloss' and _rough_gloss is not None:
            try:
                glossy = nt.nodes.new('ShaderNodeBsdfGlossy')
                try:
                    glossy.inputs['Roughness'].default_value = 0.2
                except Exception:
                    pass
                nt.links.new(sn.outputs['Color'], glossy.inputs['Color'])
                gr_sock = _sock(glossy.inputs, 'Roughness')
                if gr_sock is not None:
                    nt.links.new(_rough_gloss, gr_sock)
                _sb = _sock(bsdf.inputs, 'Specular', 'Specular IOR Level')
                if _sb is not None:
                    _sb.default_value = max(0.0, min(1.0, opts.get('spec_base', 0.15)))
                mix_node = nt.nodes.new('ShaderNodeMixShader')
                curve = max(0.5, opts.get('spec_curve', 2.0))
                pw = _math(mat, 'POWER', curve)
                nt.links.new(sn.outputs['Color'], pw.inputs[0])
                pw.inputs[1].default_value = curve
                if sc != 1.0:
                    fac = _math(mat, 'MULTIPLY', sc)
                    nt.links.new(pw.outputs[0], fac.inputs[0])
                    nt.links.new(fac.outputs[0], mix_node.inputs['Fac'])
                else:
                    nt.links.new(pw.outputs[0], mix_node.inputs['Fac'])
                nt.links.new(bsdf.outputs[0], mix_node.inputs[1])
                nt.links.new(glossy.outputs[0], mix_node.inputs[2])
                nt.links.new(mix_node.outputs[0], out.inputs[0])
            except Exception as e:
                print('[ApexAutoShade] spc 高光层失败, 回退旧方式: %s' % e)
                spc_sock = _sock(bsdf.inputs, 'Specular', 'Specular IOR Level')
                if spc_sock is not None:
                    nt.links.new(sn.outputs['Color'], spc_sock)
        else:
            spc_sock = _sock(bsdf.inputs, 'Specular', 'Specular IOR Level')
            if spc_sock is None:
                print('[ApexAutoShade] 提示: 当前 Blender 版本没有 Specular 输入, 已跳过 spc 连线')
            elif sc != 1.0:
                mul = _math(mat, 'MULTIPLY', sc)
                nt.links.new(sn.outputs['Color'], mul.inputs[0])
                nt.links.new(mul.outputs[0], spc_sock)
            else:
                nt.links.new(sn.outputs['Color'], spc_sock)

    _glow_on = opts.get('alpha_glow', 0.0) > 0.0 and _want_alpha(mat.name or '', opts.get('alpha_mode', 'auto'))
    ilm = texset.get('ilm')
    if ilm and not _glow_on:
        en = _img_node(mat, 'ilm', ilm)
        st = _math(mat, 'MULTIPLY', opts.get('emission_strength', 2.0))
        nt.links.new(en.outputs['Color'], st.inputs[0])
        est = _sock(bsdf.inputs, 'Emission Strength')
        ecol = _sock(bsdf.inputs, 'Emission Color')
        if est is not None:
            nt.links.new(st.outputs[0], est)
        if ecol is not None:
            nt.links.new(en.outputs['Color'], ecol)
    return mat


def auto_shade_objects(objects, folder, opts):
    """对一组网格对象: 依据其材质名自动配色(找不到文件夹则跳过并报告)"""
    report = []
    mats_done = {}
    for obj in objects:
        if obj is None or getattr(obj, 'type', '') != 'MESH':
            continue
        for slot in obj.data.materials:
            if slot is None:
                continue
            key = slot.name
            if key in mats_done:
                continue
            texset = find_texture_set(folder, key)
            if not texset.get('col'):
                report.append('{k}: 未在 {f} 中找到 _col 贴图'.format(k=key, f=folder))
                continue
            build_apex_material(slot, texset, opts)
            mats_done[key] = texset
            report.append('{k}: {s}'.format(
                k=key, s=', '.join('{r}={b}'.format(r=r, b=os.path.basename(p)) for r, p in sorted(texset.items()))))
    return report
