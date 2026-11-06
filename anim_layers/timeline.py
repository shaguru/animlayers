# Key lanes: for every layer with "show keys" on, draw a coloured strip of key diamonds along the
# bottom of the Timeline / Dope Sheet, so you can see keys from layers you are not editing.

import traceback

import bpy

from . import draw as D
from . import layers as L

ADDON = __package__
_CACHE = {}


def prefs():
    return bpy.context.preferences.addons[ADDON].preferences


def _selected_bones(ob):
    if ob.type != "ARMATURE" or ob.mode != "POSE":
        return None
    sel_attr = "select" in bpy.types.PoseBone.bl_rna.properties
    return {pb.name for pb in ob.pose.bones if (pb.select if sel_attr else pb.bone.select)}


def key_frames(ob, track, only_selected):
    """Scene frames that have a key in this layer (optionally only for selected bones)."""
    s = L.layer_strip(track)
    if s is None or s.action is None:
        return []
    fcs = L.layer_fcurves(track)
    bones = _selected_bones(ob) if only_selected else None
    sig = (s.as_pointer(), s.action.as_pointer(), s.frame_start, s.action_frame_start, s.scale,
           len(fcs), sum(len(fc.keyframe_points) for fc in fcs),
           None if bones is None else hash(frozenset(bones)))
    hit = _CACHE.get(track.as_pointer())
    if hit and hit[0] == sig and not _CACHE.get("__dirty"):
        return hit[1]
    frames = set()
    for fc in fcs:
        if bones is not None and fc.data_path.startswith('pose.bones["'):
            name = fc.data_path[12:fc.data_path.find('"]', 12)]
            if name not in bones:
                continue
        n = len(fc.keyframe_points)
        if not n:
            continue
        arr = [0.0] * (2 * n)
        fc.keyframe_points.foreach_get("co", arr)
        frames.update(round(L.strip_to_scene(s, f), 2) for f in arr[0::2])
    out = sorted(frames)
    _CACHE[track.as_pointer()] = (sig, out)
    return out


def mark_dirty():
    _CACHE.clear()


def draw_lanes():
    try:
        ctx = bpy.context
        region, space = ctx.region, ctx.space_data
        if region is None or region.type != "WINDOW" or space is None:
            return
        p = prefs()
        if not p.show_lanes:
            return
        ob = ctx.active_object
        if ob is None or not L.has_layers(ob):
            return
        ts = L.tracks(ob)
        lanes = [(i, t) for i, t in enumerate(ts) if L.show_keys(t)]
        if not lanes:
            return
        ui = ctx.preferences.system.ui_scale
        lh = p.lane_height * ui
        only_sel = bool(getattr(getattr(space, "dopesheet", None), "show_only_selected", False))
        v2d = region.view2d
        cv = D.Canvas()
        y0 = 14 * ui
        act = L.active_track(ob)
        frame = ctx.scene.frame_current
        for row, (i, t) in enumerate(lanes):          # bottom layer lowest, like the stack
            y = y0 + row * (lh + 2 * ui)
            col = L.color(t, i)
            muted = t.mute
            cv.fill(D.rrect(0, y, region.width, lh, 0), (col[0], col[1], col[2], 0.10 if not muted else 0.04), 0, aa=False)
            cv.line((0, y + lh), (region.width, y + lh), (col[0], col[1], col[2], 0.35), 1.0, 0)
            r = lh * 0.34
            for f in key_frames(ob, t, only_sel):
                x, _ = v2d.view_to_region(f, 0, clip=False)
                if x < -10 or x > region.width + 10:
                    continue
                dia = D.rdiamond(x, y + lh / 2, r, 0.12)
                on_frame = abs(f - frame) < 0.01
                if muted:
                    cv.outline(dia, (col[0], col[1], col[2], 0.6), 1.2, 2)
                else:
                    cv.fill(dia, (col[0], col[1], col[2], 1.0), 1)
                    cv.outline(dia, (1, 1, 1, 0.95) if on_frame else (0, 0, 0, 0.7), 1.0, 2)
            label = t.name + ("  ✎" if t == act else "") + ("  (hidden)" if muted else "")
            ts_ = 10 * ui
            tw = D.text_width(label, ts_)
            cv.fill(D.rrect(4 * ui, y + 1 * ui, tw + 10 * ui, lh - 2 * ui, 3 * ui), (0.08, 0.08, 0.09, 0.82), 3, aa=False)
            cv.fill(D.rrect(4 * ui, y + 1 * ui, 3 * ui, lh - 2 * ui, 1 * ui), (col[0], col[1], col[2], 1), 4, aa=False)
            cv.text(10 * ui, y + lh / 2 - 3.5 * ui, label, ts_, (0.95, 0.95, 0.95, 1))
        cv.flush(region.width, region.height)
    except Exception:
        traceback.print_exc()


@bpy.app.handlers.persistent
def on_depsgraph(scene, depsgraph):
    for u in depsgraph.updates:
        if isinstance(u.id, bpy.types.Action):
            mark_dirty()
            return
