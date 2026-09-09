# -*- coding: utf-8 -*-
"""Apex RSX .cast 解析 + 贴图匹配 + 视图/STL 几何辅助(纯 Python, 不依赖 Blender)。
格式依据 rsx-2.2.1 源码 https://github.com/r-ex/rsx src/core/mdl/cast.h / cast.cpp
"""
import math
import os
import re
import struct

# ----------------------------------------------------------------------------
# 1) cast 二进制解析
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
# 2) 贴图匹配
# ----------------------------------------------------------------------------

_ROLES = [
    ('col', '_col'), ('nml', '_nml'), ('gls', '_gls'),
    ('spc', '_spc'), ('ao', '_ao'), ('cav', '_cav'), ('ilm', '_ilm'),
]


def find_texture_dir_for_cast(path):
    """cast 文件名 e.g. xxx_w_LOD0.cast -> 同名贴图文件夹 xxx_w"""
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


# ----------------------------------------------------------------------------
# 3) 参考视图几何(纯 Python, 可单测)
# ----------------------------------------------------------------------------

def _view_setup(el_deg=35.0, az_deg=45.0):
    """8 个参考视图: (名称, 相机朝向单位向量, 画面上方向量)
    坐标约定为"摆正后"的模型空间: 枪口=+Y, 枪身顶=+Z, 枪身右=+X
    前后/左右已按用户要求互换: front=枪尾方向"""
    el = math.radians(el_deg)
    az = math.radians(az_deg)
    ce, se = math.cos(el), math.sin(el)
    up = (0.0, 0.0, 1.0)
    up_flat = (1.0, 0.0, 0.0)
    return [
        ('front', (0.0, -1.0, 0.0), up),
        ('back', (0.0, 1.0, 0.0), up),
        ('right', (-1.0, 0.0, 0.0), up),
        ('left', (1.0, 0.0, 0.0), up),
        ('top', (0.0, 0.0, 1.0), up_flat),
        ('bottom', (0.0, 0.0, -1.0), up_flat),
        ('oblique_l', (-math.sin(az) * ce, math.cos(az) * ce, se), up),
        ('oblique_r', (math.sin(az) * ce, math.cos(az) * ce, se), up),
    ]


# ----------------------------------------------------------------------------
# 4) STL 导出(纯 Python, 不依赖内置 STL 插件)
# ----------------------------------------------------------------------------

def _write_stl_binary(path, tris, scale):
    """将三角面列表写入二进制STL。tris: [( (x,y,z),(x,y,z),(x,y,z) )...] 米制;
    scale=1000 -> 打印软件(如Bambu Studio) 1mm"""
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
    """把(已求值/带修改器的)网格三角化并转到世界坐标, 返回STL用的三角列表(需在Blender内调用)"""
    me.calc_loop_triangles()
    tris = []
    for lt in me.loop_triangles:
        ps = [mw @ me.vertices[lt.vertices[i]].co for i in range(3)]
        tris.append(((ps[0][0], ps[0][1], ps[0][2]),
                     (ps[1][0], ps[1][1], ps[1][2]),
                     (ps[2][0], ps[2][1], ps[2][2])))
    return tris
