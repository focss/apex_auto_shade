# -*- coding: utf-8 -*-
"""
Apex Legends RSX .cast 导入 + 自动着色插件
===========================================
功能:
  1. 导入 rsx_2.2.1 导出的 .cast 模型(网格/UV/法线/材质/骨骼/权重) — 格式依据
     https://github.com/r-ex/rsx 2.2.1 源码 src/core/mdl/cast.h / cast.cpp 实现
  2. 自动从同目录的同名贴图文件夹(如 repeater3030_lgnd_v25_clockwild_w)按材质名前缀匹配
     _col / _nml / _gls / _spc / _ao / _cav / _ilm 贴图并搭建 Principled BSDF 节点:
       col  -> Base Color            (Color/sRGB)
       nml  -> 重建B通道(双通道法线) -> Normal Map -> Normal   (Non-Color)
       gls  -> Invert                -> Roughness             (Non-Color)
       spc  -> Specular                                         (Non-Color)
       ao x cav -> 乘入 Base Color(环境遮蔽+缝隙)              (Non-Color)
       ilm  -> Emission                                        (Non-Color)
  3. 对已导入的对象(任意导入方式)可单独执行"自动着色"。

用法:
  Blender -> 编辑 -> 偏好设置 -> 插件 -> 安装 -> 选择本文件 -> 勾选启用
  或: 文件 -> 导入 -> Apex RSX Cast (.cast) 选择 LOD0 文件
  面板: 3D 视图 按 N -> "Apex Auto-Shade" 侧边栏
"""

bl_info = {
    "name": "Apex RSX Cast Import + Auto-Shade",
    "author": "focss",
    "version": (1, 6, 3),
    "blender": (3, 3, 0),
    "location": "File > Import > Apex RSX Cast (.cast) / 3D View > N > Apex Auto-Shade",
    "description": "Import rsx .cast weapon models and auto-build Principled BSDF materials from Apex col/nml/gls/spc/ao/cav/ilm textures",
    "category": "Import-Export",
}

import math
import os
import re
import struct

try:
    import bpy
    from mathutils import Vector, Quaternion, Matrix
except Exception:  # 允许在无 Blender 环境中仅做语法/解析测试
    bpy = None

# ----------------------------------------------------------------------------
# 1) cast 二进制解析(纯 Python, 可脱离 Blender 运行)
#    依据 rsx-2.2.1 源码 cast.h / cast.cpp
# ----------------------------------------------------------------------------

_PROP_SIZE = {
    'b': 1, 'h': 2, 'i': 4, 'l': 8, 'f': 4, 'd': 8,
    'v2': 8, 'v3': 12, 'v4': 16,
}
_CAST_ID = {
    0x746F6F72: 'Root', 0x6C646F6D: 'Model', 0x6873656D: 'Mesh', 0x68736C62: 'BlendShape',
    0x6C656B73: 'Skeleton', 0x656E6F62: 'Bone', 0x64686B69: 'IKHandle', 0x74736E63: 'Constraint',
    0x6D696E61: 'Animation', 0x76727563: 'Curve', 0x6669746E: 'NotificationTrack',
    0x6C74616D: 'Material', 0x656C6966: 'File', 0x74736E69: 'Instance',
}


class _Prop(object):
    __slots__ = ('tid', 'name', 'arr', 'data')
    def __init__(self, tid, name, arr, data):
        self.tid, self.name, self.arr, self.data = tid, name, arr, data


class _Node(object):
    __slots__ = ('cid', 'hsh', 'props', 'children')
    def __init__(self, cid, hsh, props, children):
        self.cid, self.hsh, self.props, self.children = cid, hsh, props, children

    def find(self, cid=None):
        out = [] if cid is None or self.cid != cid else [self]
        for c in self.children:
            out.extend(c.find(cid))
        return out

    def get(self, name):
        for p in self.props:
            if p.name == name:
                return p
        return None


def _parse_cast_node(data, off):
    cid = _CAST_ID.get(struct.unpack_from('<I', data, off)[0], '?')
    hsh = struct.unpack_from('<Q', data, off + 8)[0]
    pcount, ccount = struct.unpack_from('<II', data, off + 16)
    o = off + 24
    props = []
    for _ in range(pcount):
        t16 = struct.unpack_from('<H', data, o)[0]
        b1, b2 = (t16 >> 8) & 0xff, t16 & 0xff
        if b1 == ord('v') and b2 == ord('3'):
            tid = 'v3'
        elif b1 == ord('v') and b2 == ord('2'):
            tid = 'v2'
        elif b1 == ord('v') and b2 == ord('4'):
            tid = 'v4'
        elif b1 == 0:
            tid = chr(b2)
        else:
            tid = chr(b1) + chr(b2)
        nsz = struct.unpack_from('<H', data, o + 2)[0]
        arr = struct.unpack_from('<I', data, o + 4)[0]
        name = bytes(data[o + 8:o + 8 + nsz]).decode('latin1')
        o += 8 + nsz
        if tid == 's':
            end = data.index(0, o)
            props.append(_Prop('s', name, arr, data[o:end].decode('utf-8', 'replace')))
            o = end + 1
        else:
            vs = _PROP_SIZE[tid]
            n = vs * arr
            props.append(_Prop(tid, name, arr, data[o:o + n]))
            o += n
    children = []
    for _ in range(ccount):
        child, o = _parse_cast_node(data, o)
        children.append(child)
    return _Node(cid, hsh, props, children), o


def parse_cast(path):
    """解析 .cast, 返回 dict: materials/bones/meshes"""
    with open(path, 'rb') as f:
        data = f.read()
    magic, ver, roots, flags = struct.unpack_from('<IIII', data, 0)
    if magic != 0x74736163:
        raise ValueError('{p} 不是有效的 .cast 文件(魔数不符)'.format(p=path))
    o = 16
    nodes = []
    for _ in range(roots):
        n, o = _parse_cast_node(data, o)
        nodes.append(n)
    root = nodes[0]

    materials = {}
    for m in root.find('Material'):
        nm = m.get('n')
        if nm is not None:
            materials[m.hsh] = nm.data

    bones = []
    for b in root.find('Bone'):
        nm = b.get('n')
        parent = b.get('p')
        lp = b.get('lp')
        lr = b.get('lr')
        wp = b.get('wp')
        wr = b.get('wr')
        pos = None
        quat = None
        if lp is not None:
            pos = struct.unpack('<3f', lp.data)
        elif wp is not None:
            pos = struct.unpack('<3f', wp.data)
        if lr is not None:
            quat = struct.unpack('<4f', lr.data)
        elif wr is not None:
            quat = struct.unpack('<4f', wr.data)
        bones.append({
            'name': nm.data if nm else 'bone_{n}'.format(n=len(bones)),
            'parent': struct.unpack('<i', parent.data)[0] if parent is not None else -1,
            'pos': pos,
            'quat': quat,
        })

    meshes = []
    for msh in root.find('Mesh'):
        nm = msh.get('n')
        vp, vn, f = msh.get('vp'), msh.get('vn'), msh.get('f')
        uv0 = msh.get('u0')
        mat_ref = msh.get('m')
        wb, wv = msh.get('wb'), msh.get('wv')
        if vp is None or f is None:
            continue
        vcount = len(vp.data) // 12
        positions = [struct.unpack_from('<3f', vp.data, i * 12) for i in range(vcount)]
        normals = None
        if vn is not None:
            normals = [struct.unpack_from('<3f', vn.data, i * 12) for i in range(vcount)]
        uvs = None
        if uv0 is not None:
            uvs = [struct.unpack_from('<2f', uv0.data, i * 8) for i in range(vcount)]
        ps = _PROP_SIZE[f.tid]
        nidx = len(f.data) // ps
        if f.tid == 'b':
            raw = struct.unpack('<{n}B'.format(n=nidx), f.data)
        elif f.tid == 'h':
            raw = struct.unpack('<{n}H'.format(n=nidx), f.data)
        else:
            raw = struct.unpack('<{n}I'.format(n=nidx), f.data)
        faces = [tuple(raw[i:i + 3]) for i in range(0, nidx - 2, 3)]
        weights = []
        if wb is not None and wv is not None:
            psb = _PROP_SIZE[wb.tid]
            nb = len(wb.data) // psb
            if wb.tid == 'b':
                bi = struct.unpack('<{n}B'.format(n=nb), wb.data)
            elif wb.tid == 'h':
                bi = struct.unpack('<{n}H'.format(n=nb), wb.data)
            else:
                bi = struct.unpack('<{n}I'.format(n=nb), wb.data)
            wv = struct.unpack('<{n}f'.format(n=len(wv.data) // 4), wv.data)
            m = min(len(bi), len(wv), vcount)
            weights = [(bi[i], wv[i]) for i in range(m)]
        matname = None
        if mat_ref is not None:
            matname = materials.get(struct.unpack('<Q', mat_ref.data)[0])
        meshes.append({
            'name': nm.data if nm else 'mesh_{n}'.format(n=len(meshes)),
            'material': matname,
            'positions': positions,
            'normals': normals,
            'uvs': uvs,
            'faces': faces,
            'weights': weights,
        })
    return {'materials': materials, 'bones': bones, 'meshes': meshes}


# ----------------------------------------------------------------------------
# 2) 贴图匹配(纯 Python)
# ----------------------------------------------------------------------------

_ROLES = [
    ('col', '_col'), ('nml', '_nml'), ('gls', '_gls'),
    ('spc', '_spc'), ('ao', '_ao'), ('cav', '_cav'), ('ilm', '_ilm'),
]


def find_texture_dir_for_cast(path):
    """cast 文件名 repeater3030_..._w_LOD0.cast -> 同名贴图文件夹 repeater3030_..._w"""
    d = os.path.dirname(path)
    base = os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r'_LOD\d+$', '', base)
    cand = os.path.join(d, base)
    if os.path.isdir(cand):
        return cand
    for name in sorted(os.listdir(d)):
        full = os.path.join(d, name)
        if os.path.isdir(full) and name.startswith(base.split('_')[0]):
            return full
    return None


def find_texture_set(folder, matname):
    """按材质名在 folder 中匹配 7 类贴图, 返回 {role: 绝对路径}"""
    if not folder or not os.path.isdir(folder):
        return {}
    try:
        names = os.listdir(folder)
    except OSError:
        return {}
    lower = {n.lower(): n for n in names if n.lower().endswith(('.png', '.tga', '.dds', '.jpg', '.jpeg'))}
    out = {}
    m = matname.lower()
    for role, suf in _ROLES:
        key = (m + suf).lower()
        hit = None
        for n in names:
            if n.lower().startswith(m + suf + '.'):
                hit = n
                break
        if hit is None:
            hit = lower.get(key + '.png') or lower.get(key + '.tga') or lower.get(key + '.dds')
        if hit:
            out[role] = os.path.join(folder, hit)
    return out


# ----------------------------------------------------------------------------
# 3) Blender 节点搭建
# ----------------------------------------------------------------------------

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


_ALPHA_KEYWORDS = ('acc', 'glass', 'glow', 'transparent', 'transp', 'emi', 'lens', 'light')


def _want_alpha(matname, mode):
    """决定材质是否启用 col 的 alpha 半透明"""
    if mode == 'off':
        return False
    if mode == 'all':
        return True
    if not matname:
        return False
    n = matname.lower().replace('-', '_').replace(' ', '_')
    return any(k in n for k in _ALPHA_KEYWORDS)


def _mix_mul(mat, a, b=None, const=None):
    """颜色按通道相乘(保留彩色): a * b 或 a * const(RGB元组)。
    Blender Math节点是单通道, 颜色进Math会变灰度(luminance), 这才是彩色丢失的根因;
    这里使用 Mix/MixRGB 的 Multiply 混合按通道相乘。"""
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
            # 读 col 均值(分段采样)自动提亮, 让深色贴图里的颜色可见
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
            # 渐变发光: alpha 驱动发射, 让半透明蓝紫渐变可见(模拟游戏内能量覆层)
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

    # 法线: 双通道(BC5/DXT5nm) -> 重建 B -> Normal Map
    nml = texset.get('nml')
    if nml:
        nnode = _img_node(mat, 'nml', nml)
        sep = _sep_rgb(mat)
        nt.links.new(nnode.outputs['Color'], sep.inputs[0])
        r = sep.outputs[0]
        g = sep.outputs[1]
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nr_in = nm.inputs[1]  # Color(3.x) / Vector(4.x)
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
            # spc 彩色高光层: spc颜色(金) -> Glossy, 用spc亮度做混合因子, 叠在主BSDF上
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
                # 压低主BSDF默认高光, 黑色部位不被白色高光冲灰
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

    # 若该材质启用了渐变发光(alpha_glow), 由 glow 提供发射, 跳过几乎全黑的 ilm
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


def _view_setup(el_deg=35.0, az_deg=45.0):
    """8 个参考视图: (名称, 相机朝向单位向量, 画面上方向量)
    坐标约定为"摆正后"的模型空间: 枪口=+Y, 枪身顶=+Z, 枪身右=+X
    前/后/右/左: 画面向上=枪顶(+Z); 顶/底: 画面向上=枪右(+X), 让枪身在画面里水平摆放
    另外两张 3/4 斜视 = 左前上 / 右前上"""
    el = math.radians(el_deg)
    az = math.radians(az_deg)
    ce, se = math.cos(el), math.sin(el)
    up = (0.0, 0.0, 1.0)
    up_flat = (1.0, 0.0, 0.0)
    return [
        # 前后/左右已按用户要求互换: front=枪尾方向, right=原left方向
        ('front', (0.0, -1.0, 0.0), up),
        ('back', (0.0, 1.0, 0.0), up),
        ('right', (-1.0, 0.0, 0.0), up),
        ('left', (1.0, 0.0, 0.0), up),
        ('top', (0.0, 0.0, 1.0), up_flat),
        ('bottom', (0.0, 0.0, -1.0), up_flat),
        ('oblique_l', (-math.sin(az) * ce, math.cos(az) * ce, se), up),
        ('oblique_r', (math.sin(az) * ce, math.cos(az) * ce, se), up),
    ]


def _write_stl_binary(path, tris, scale):
    """将三角面列表写入二进制STL(不依赖内置STL插件)。
    tris: [( (x,y,z), (x,y,z), (x,y,z) )...] Blender米制坐标; scale=1000 -> 打印软件(如Bambu) 1mm"""
    header = b'ApexAutoShade STL: Blender 1m -> print 1mm (x' + str(scale).encode() + b')'
    with open(path, 'wb') as fh:
        fh.write(header[:80].ljust(80, b'\x00'))
        fh.write(struct.pack('<I', len(tris)))
        for a, b, c in tris:
            ux, uy, uz = a[0] - c[0], a[1] - c[1], a[2] - c[2]
            vx, vy, vz = b[0] - c[0], b[1] - c[1], b[2] - c[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            L = (nx * nx + ny * ny + nz * nz) ** 0.5
            if L > 1e-12:
                nx, ny, nz = nx / L, ny / L, nz / L
            else:
                nx = ny = nz = 0.0
            fh.write(struct.pack('<3f', nx, ny, nz))
            for p in (a, b, c):
                fh.write(struct.pack('<3f', p[0] * scale, p[1] * scale, p[2] * scale))
            fh.write(struct.pack('<H', 0))


def _mesh_to_tris(me, mw, scale):
    """把(已求值/带修改器的)网格三角化并转到世界坐标, 返回STL用的三角列表"""
    me.calc_loop_triangles()
    tris = []
    for lt in me.loop_triangles:
        ps = [mw @ me.vertices[lt.vertices[i]].co for i in range(3)]
        tris.append(((ps[0][0], ps[0][1], ps[0][2]),
                     (ps[1][0], ps[1][1], ps[1][2]),
                     (ps[2][0], ps[2][1], ps[2][2])))
    return tris


# ----------------------------------------------------------------------------
# 4) Blender 导入操作符
# ----------------------------------------------------------------------------

if bpy is not None:

    class ApexProperties(bpy.types.PropertyGroup):
        tex_dir: bpy.props.StringProperty(name='贴图文件夹', subtype='DIR_PATH',
            description='存放 _col/_nml/... 贴图的文件夹(导入时自动检测)')
        albedo_boost: bpy.props.FloatProperty(name='Albedo 亮度', default=1.0, min=0.1, max=5.0,
            description='Base Color 提亮倍数(Apex 贴图偏暗时可 >1)')
        albedo_sat: bpy.props.FloatProperty(name='Albedo 饱和度', default=1.0, min=0.1, max=4.0,
            description='仅放大贴图中已带颜色的像素(灰色不受影响); 让灰底皮肤上的红/黄点缀可见, 如 >1')
        albedo_auto: bpy.props.BoolProperty(name='自动提亮到目标亮度', default=True,
            description='建材质时读取col均值, 自动算出提亮倍率, 让深色贴图里的颜色可见(每把枪自动适配)')
        albedo_target: bpy.props.FloatProperty(name='目标亮度(sRGB)', default=0.5, min=0.2, max=1.0,
            description='自动提亮的目标均值; 越接近1越亮')
        albedo_gamma: bpy.props.FloatProperty(name='暗部抬升(Gamma)', default=1.3, min=1.0, max=2.5,
            description='线性乘提亮后, 用Gamma节点单独抬暗部(藏蓝/深色不易发黑, 颜色更保真); 1.0=关闭')
        emission_strength: bpy.props.FloatProperty(name='ILM 发光强度', default=2.0, min=0.0, max=20.0)
        ao_strength: bpy.props.FloatProperty(name='AO 强度', default=1.0, min=0.0, max=3.0)
        specular_scale: bpy.props.FloatProperty(name='Spec 强度', default=1.0, min=0.0, max=3.0)
        spec_mode: bpy.props.EnumProperty(name='高光颜色', items=[
            ('gloss', 'spc彩色高光(金色等,游戏观感)', ''),
            ('legacy', 'spc仅强度(旧)', ''),
        ], default='gloss',
            description='gloss: 用spc贴图的颜色叠一层Glossy高光(金色反光正确还原); legacy: 只当标量强度接Specular')
        spec_curve: bpy.props.FloatProperty(name='高光收敛(幂)', default=2.0, min=0.5, max=8.0,
            description='混合因子=spc亮度^幂; 越大金色越集中在spc最亮处, 暗部越不会泛灰')
        spec_base: bpy.props.FloatProperty(name='主高光压暗', default=0.15, min=0.0, max=1.0,
            description='gloss模式下主BSDF的Specular值: 调低让黑色部位不因白色高光变灰(金色全由高光层出)')
        normal_strength: bpy.props.FloatProperty(name='法线强度', default=1.0, min=0.0, max=3.0)
        flip_normal_g: bpy.props.BoolProperty(name='翻转法线G通道', default=False,
            description='法线显示凹凸颠倒时勾选')
        create_armature: bpy.props.BoolProperty(name='创建骨骼骨架', default=True)
        flip_x: bpy.props.BoolProperty(name='镜像X轴', default=False,
            description='Source 坐标系(左手)转 Blender 右手系时可选')
        alpha_mode: bpy.props.EnumProperty(name='Alpha半透明', items=[
            ('auto', '自动(仅acc/玻璃类材质)', ''),
            ('all', '全部材质', ''),
            ('off', '关闭', ''),
        ], default='auto',
            description='按材质名决定是否启用col的alpha; 自动模式只对acc/glass/glow等覆层材质启用, 主体(opaque)不透明')
        alpha_clip: bpy.props.BoolProperty(name='硬边裁剪(阈值)', default=False,
            description='低于阈值的alpha全透明, 高于全不透明; 消除半透明渐变导致的透底')
        alpha_threshold: bpy.props.FloatProperty(name='Alpha阈值', default=0.5, min=0.0, max=1.0)
        alpha_glow: bpy.props.FloatProperty(name='渐变发光强度', default=2.0, min=0.0, max=10.0,
            description='仅对启用alpha的材质: 让半透明蓝紫渐变区域发光可见(模拟游戏内能量覆层); 0=关闭')
        # ---- 参考视图导出 ----
        view_outdir: bpy.props.StringProperty(name='视图输出目录', default='//export_views', subtype='DIR_PATH')
        view_res: bpy.props.EnumProperty(name='分辨率', items=[
            ('2048', '2048', '标准'),
            ('4096', '4096', '高分辨率'),
        ], default='2048')
        view_bg: bpy.props.EnumProperty(name='背景', items=[
            ('transparent', '透明', ''),
            ('white', '白底', ''),
            ('black', '黑底', ''),
        ], default='transparent')
        view_align: bpy.props.BoolProperty(name='自动摆正(枪口+Z→水平+Y)', default=True,
            description='勾选: 相机按"枪口+Z→水平+Y"摆放; 若已手动转好模型请取消勾选')
        obl_elevation: bpy.props.FloatProperty(name='斜视俯角°', default=35.0, min=0.0, max=90.0)
        obl_azimuth: bpy.props.FloatProperty(name='斜视水平角°', default=45.0, min=5.0, max=85.0)
        view_lighting: bpy.props.EnumProperty(name='渲染灯光', items=[
            ('studio', '临时环境光(接近材质预览)', ''),
            ('none', '场景原灯光', ''),
        ], default='studio',
            description='材质预览用内置 Studio HDRI; 直接渲染易偏黑, 默认用临时白色环境光提亮')
        view_light_strength: bpy.props.FloatProperty(name='环境光强度', default=1.5, min=0.1, max=10.0)
        view_vt: bpy.props.EnumProperty(name='渲染视图变换', items=[
            ('current', '跟随场景', ''),
            ('standard', 'Standard(贴图直出,接近rsx预览)', ''),
        ], default='standard',
            description='Standard 不做影视化暗部压缩, 颜色更接近贴图本身(rsx低清预览的观感)')
        # ---- 3D 打印 STL ----
        stl_dir: bpy.props.StringProperty(name='STL输出目录', default='//export_stl', subtype='DIR_PATH')
        stl_scale: bpy.props.FloatProperty(name='导出倍率(Blender m→打印 mm)', default=1000.0, min=1.0, max=1000000.0,
            description='STL 无单位; 默认1000 = Blender 1m -> 打印软件(如Bambu Studio) 1mm')
        stl_merge: bpy.props.BoolProperty(name='合并为单件STL', default=True)
        stl_decimate: bpy.props.BoolProperty(name='合并时减面(Decimate)', default=False)
        stl_decimate_ratio: bpy.props.FloatProperty(name='减面比例', default=0.5, min=0.05, max=1.0)

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

    class IMPORT_OT_apex_cast(bpy.types.Operator):
        bl_idname = 'import_scene.apex_cast'
        bl_label = '导入 Apex RSX Cast (.cast)'
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
                self.report({'ERROR'}, '找不到贴图文件夹, 请在侧边栏手动指定')
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

            # 骨骼
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
            self.report({'INFO'}, '导入 {n} 个网格, 自动着色完成: {f}'.format(
                n=len(cast_result['meshes']), f=folder))
            return {'FINISHED'}

        def invoke(self, context, event):
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}

    class MAT_OT_apex_auto_shade(bpy.types.Operator):
        bl_idname = 'material.apex_auto_shade'
        bl_label = '自动着色(Apex)'
        bl_options = {'REGISTER', 'UNDO'}

        mode: bpy.props.EnumProperty(items=[
            ('SELECTED', '选中对象', ''),
            ('ALL', '场景全部', ''),
        ], default='SELECTED')

        def execute(self, context):
            p = context.scene.apex_autoshade
            folder = p.tex_dir or ''
            if not os.path.isdir(folder):
                self.report({'ERROR'}, '请先在侧边栏指定贴图文件夹')
                return {'CANCELLED'}
            objs = (context.selected_objects if self.mode == 'SELECTED'
                    else list(context.scene.objects))
            report = auto_shade_objects(objs, folder, _opts(context))
            for line in report:
                print('[ApexAutoShade]', line)
            self.report({'INFO'}, '完成, 共处理 {n} 条材质'.format(n=len(report)))
            return {'FINISHED'}

    class VIEW_OT_apex_export_views(bpy.types.Operator):
        bl_idname = 'apex.export_views'
        bl_label = '导出六面+2斜视参考图'
        bl_options = {'REGISTER'}

        def execute(self, context):
            p = context.scene.apex_autoshade
            objs = [o for o in context.selected_objects if o.type == 'MESH']
            if not objs:
                self.report({'ERROR'}, '请先选中网格对象(枪身网格)')
                return {'CANCELLED'}
            outdir = bpy.path.abspath(p.view_outdir or '//export_views')
            try:
                os.makedirs(outdir, exist_ok=True)
            except OSError as e:
                self.report({'ERROR'}, '无法创建输出目录: {e}'.format(e=e))
                return {'CANCELLED'}

            pts = []
            for o in objs:
                mw = o.matrix_world
                for v in o.data.vertices:
                    pts.append(mw @ v.co)
            if not pts:
                self.report({'ERROR'}, '对象没有顶点')
                return {'CANCELLED'}
            mn = Vector((min(v.x for v in pts), min(v.y for v in pts), min(v.z for v in pts)))
            mx = Vector((max(v.x for v in pts), max(v.y for v in pts), max(v.z for v in pts)))
            center = (mn + mx) * 0.5
            dims = mx - mn
            maxdim = max(dims.x, dims.y, dims.z)
            if maxdim <= 0.0:
                self.report({'ERROR'}, '包围盒无效')
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

            # 临时环境光: 模拟材质预览的 Studio HDRI 照明, 避免导出图偏黑
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
                if p.view_bg == 'black':  # 黑底改为透明底, 避免黑环境把模型照黑
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
                    # 方向与画面向上都施加同样的摆正旋转, 相机的俯仰/翻滚随摆正一起变化
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
            self.report({'INFO'}, '已导出 8 张参考视图到: {d}'.format(d=outdir))
            return {'FINISHED'}

    class STL_OT_apex_export(bpy.types.Operator):
        bl_idname = 'apex.export_stl'
        bl_label = '导出打印STL(mm)'
        bl_options = {'REGISTER'}

        def execute(self, context):
            p = context.scene.apex_autoshade
            sel = context.selected_objects
            objs = [o for o in sel if o.type == 'MESH'] if sel else [o for o in context.scene.objects if o.type == 'MESH']
            if not objs:
                self.report({'ERROR'}, '请先选中网格对象')
                return {'CANCELLED'}
            outdir = bpy.path.abspath(p.stl_dir or '//export_stl')
            try:
                os.makedirs(outdir, exist_ok=True)
            except OSError as e:
                self.report({'ERROR'}, '无法创建输出目录: {e}'.format(e=e))
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
                self.report({'ERROR'}, 'STL 导出失败: {e}'.format(e=e))
                return {'CANCELLED'}
            finally:
                bpy.ops.object.select_all(action='DESELECT')
                for o in prev_sel:
                    try:
                        o.select_set(True)
                    except Exception:
                        pass
                context.view_layer.objects.active = prev_active
            self.report({'INFO'}, 'STL 已导出(倍率 {s:.2f}, Blender m → 打印 mm): {d}'.format(s=scale, d=outdir))
            return {'FINISHED'}

    class VIEW3D_PT_apex_autoshade(bpy.types.Panel):
        bl_label = 'Apex Auto-Shade'
        bl_idname = 'VIEW3D_PT_apex_autoshade'
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'Apex Auto-Shade'

        def draw(self, context):
            lay = self.layout
            p = context.scene.apex_autoshade
            box = lay.box()
            box.label(text='导入模型 (.cast)')
            box.operator('import_scene.apex_cast', text='选择 .cast 文件导入', icon='IMPORT')
            box = lay.box()
            box.label(text='自动着色')
            box.prop(p, 'tex_dir')
            box.operator('material.apex_auto_shade', text='着色: 选中对象').mode = 'SELECTED'
            box.operator('material.apex_auto_shade', text='着色: 场景全部').mode = 'ALL'
            box = lay.box()
            box.label(text='调节')
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
            box.label(text='导出参考视图 (六面+2斜视)', icon='CAMERA_DATA')
            box.operator('apex.export_views', text='渲染导出 8 张视图')
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
            box.label(text='3D 打印 STL (mm)', icon='MOD_ARRAY')
            box.operator('apex.export_stl', text='导出 STL (选中对象)')
            box.prop(p, 'stl_dir')
            box.prop(p, 'stl_scale')
            box.prop(p, 'stl_merge')
            box.prop(p, 'stl_decimate')
            box.prop(p, 'stl_decimate_ratio')
            box = lay.box()
            box.label(text='导入选项')
            box.prop(p, 'create_armature')
            box.prop(p, 'flip_x')

    def _menu_func(self, context):
        self.layout.operator(IMPORT_OT_apex_cast.bl_idname, text='Apex RSX Cast (.cast)')

    classes = (ApexProperties, IMPORT_OT_apex_cast, MAT_OT_apex_auto_shade,
               VIEW_OT_apex_export_views, STL_OT_apex_export, VIEW3D_PT_apex_autoshade)

    def register():
        for c in classes:
            bpy.utils.register_class(c)
        bpy.types.Scene.apex_autoshade = bpy.props.PointerProperty(type=ApexProperties)
        bpy.types.TOPBAR_MT_file_import.append(_menu_func)

    def unregister():
        bpy.types.TOPBAR_MT_file_import.remove(_menu_func)
        del bpy.types.Scene.apex_autoshade
        for c in reversed(classes):
            bpy.utils.unregister_class(c)


if __name__ == '__main__':
    if bpy is not None:
        register()
