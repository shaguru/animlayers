# Layer logic for Anim Layers. No UI code here.
#
# Model: every NLA track on the object is a layer (index 0 = bottom). Each layer track holds
# one strip whose action stores that layer's keys. The bottom "Base" layer replaces, layers
# above it combine on top. The layer being edited is entered in NLA tweak mode, so keys you
# insert land in that layer (Blender works out the offsets for you).
# Layer colour and "show keys" are stored as custom properties on the layer's action.

import bpy

PAD = 1000            # frames of padding around the scene range when a layer strip is created
PALETTE = [
    (0.36, 0.62, 1.00), (0.99, 0.62, 0.25), (0.45, 0.85, 0.45), (0.92, 0.45, 0.78),
    (0.96, 0.85, 0.30), (0.50, 0.90, 0.92), (0.72, 0.58, 1.00), (1.00, 0.46, 0.46),
]
BLEND_CYCLE = ["COMBINE", "ADD", "REPLACE"]
BLEND_SHORT = {"COMBINE": "COMB", "ADD": "ADD", "REPLACE": "REPL", "SUBTRACT": "SUB", "MULTIPLY": "MUL"}


# ---------------------------------------------------------------- queries

def anim_data(ob):
    return ob.animation_data if ob is not None else None


def tracks(ob):
    ad = anim_data(ob)
    return list(ad.nla_tracks) if ad else []


def has_layers(ob):
    return bool(tracks(ob))


def layer_strip(track):
    return track.strips[0] if track is not None and len(track.strips) else None


def layer_action(track):
    s = layer_strip(track)
    return s.action if s else None


def active_track(ob):
    """The layer being edited (tweak mode), or None."""
    ad = anim_data(ob)
    if not ad or not ad.use_tweak_mode:
        return None
    t = ad.nla_tracks.active
    if t is not None:
        return t
    for t in ad.nla_tracks:
        for s in t.strips:
            if s.action is not None and s.action == ad.action:
                return t
    return None


def track_index(ob, track):
    for i, t in enumerate(tracks(ob)):
        if t == track:
            return i
    return -1


def color(track, index=0):
    act = layer_action(track)
    if act is not None and "al_color" in act:
        try:
            return tuple(act["al_color"])[:3]
        except Exception:
            pass
    return PALETTE[index % len(PALETTE)]


def show_keys(track):
    act = layer_action(track)
    return bool(act is not None and act.get("al_keys", False))


def set_meta(track, key, value):
    act = layer_action(track)
    if act is not None:
        act[key] = value


def influence_info(track):
    """(value, editable) - editable is False when the user has animated the influence."""
    s = layer_strip(track)
    if s is None:
        return 1.0, False
    if not s.use_animated_influence:
        return 1.0, True
    fc = s.fcurves.find("influence")
    if fc is None or len(fc.keyframe_points) == 0:
        return s.influence, True
    if len(fc.keyframe_points) == 1:
        return fc.keyframe_points[0].co[1], True
    return s.influence, False


def channelbag(action, slot):
    try:
        from bpy_extras import anim_utils
        return anim_utils.action_get_channelbag_for_slot(action, slot)
    except Exception:
        return None


def layer_fcurves(track):
    s = layer_strip(track)
    if s is None or s.action is None:
        return []
    cb = channelbag(s.action, s.action_slot)
    if cb is not None:
        return list(cb.fcurves)
    return list(getattr(s.action, "fcurves", []))


def key_range(action, slot):
    cb = channelbag(action, slot)
    fcs = list(cb.fcurves) if cb is not None else list(getattr(action, "fcurves", []))
    lo = hi = None
    for fc in fcs:
        if len(fc.keyframe_points):
            a, b = fc.range()
            lo = a if lo is None else min(lo, a)
            hi = b if hi is None else max(hi, b)
    return (lo, hi) if lo is not None else None


def strip_to_scene(strip, t):
    """Action time -> scene frame for a layer strip."""
    return strip.frame_start + (t - strip.action_frame_start) * strip.scale


# ---------------------------------------------------------------- tweak mode

def _nla_op(context, enter):
    """Run the NLA tweak operator through a borrowed area so we get full-stack evaluation."""
    win = context.window
    screen = win.screen if win else None
    if screen is None:
        return False
    area = next((a for a in screen.areas if a.type == "NLA_EDITOR"), None)
    restore = None
    if area is None:
        cands = [a for a in screen.areas if a.type != "VIEW_3D"] or list(screen.areas)
        if not cands:
            return False
        area = min(cands, key=lambda a: a.width * a.height)
        restore = area.ui_type
        area.ui_type = "NLA_EDITOR"
    try:
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        with context.temp_override(window=win, screen=screen, area=area, region=region):
            if enter:
                if not bpy.ops.nla.tweakmode_enter.poll():
                    return False
                bpy.ops.nla.tweakmode_enter(use_upper_stack_evaluation=True)
            else:
                if not bpy.ops.nla.tweakmode_exit.poll():
                    return False
                bpy.ops.nla.tweakmode_exit()
        return True
    except Exception as e:
        print("Anim Layers: NLA operator failed:", e)
        return False
    finally:
        if restore is not None:
            area.ui_type = restore


def _isolate_selection(context, ob):
    """Only `ob` selected while the NLA operator runs (it acts on every selected object)."""
    others = [o for o in context.selected_objects if o != ob]
    for o in others:
        o.select_set(False)
    was = ob.select_get()
    ob.select_set(True)
    return others, was


def _restore_selection(ob, others, was):
    for o in others:
        try:
            o.select_set(True)
        except Exception:
            pass
    try:
        ob.select_set(was)
    except Exception:
        pass


def exit_tweak(context, ob):
    ad = anim_data(ob)
    if ad is None:
        return
    if context.window is not None and ad.use_tweak_mode:
        others, was = _isolate_selection(context, ob)
        try:
            _nla_op(context, enter=False)
        finally:
            _restore_selection(ob, others, was)
    if ad.use_tweak_mode:
        ad.use_tweak_mode = False


def enter_tweak(context, ob, track):
    ad = anim_data(ob)
    if ad is None or track is None:
        return False
    strip = layer_strip(track)
    if strip is None:
        return False
    exit_tweak(context, ob)
    for t in ad.nla_tracks:
        t.select = t == track
        for s in t.strips:
            s.select = False
    ad.nla_tracks.active = track
    strip.select = True
    ok = False
    if context.window is not None:
        others, was = _isolate_selection(context, ob)
        try:
            ok = _nla_op(context, enter=True)
            if not ok:          # another object left the scene in tweak mode: clear and retry
                _nla_op(context, enter=False)
                ok = _nla_op(context, enter=True)
        finally:
            _restore_selection(ob, others, was)
    if not ad.use_tweak_mode:
        ad.use_tweak_mode = True   # fallback: lower-stack tweak through RNA
    return ad.use_tweak_mode


# ---------------------------------------------------------------- building layers

def _ensure_slot(action, ob, slot=None):
    if slot is not None:
        return slot
    for s in action.slots:
        if s.target_id_type in ("OBJECT", "UNSPECIFIED"):
            return s
    return action.slots.new(id_type="OBJECT", name=ob.name)


def _make_strip(context, ob, track, action, slot, base):
    sc = context.scene
    slot = _ensure_slot(action, ob, slot)
    kr = key_range(action, slot)
    lo = min(sc.frame_start, kr[0] if kr else sc.frame_start) - PAD
    hi = max(sc.frame_end, kr[1] if kr else sc.frame_end) + PAD
    strip = track.strips.new(track.name, int(lo), action)
    if strip.action_slot != slot:
        strip.action_slot = slot
    strip.use_sync_length = False
    strip.action_frame_end = hi
    strip.action_frame_start = lo
    strip.scale = 1.0
    strip.repeat = 1.0
    strip.frame_start_ui = lo        # keep action time == scene time
    strip.use_auto_blend = False
    strip.blend_in = strip.blend_out = 0.0
    strip.blend_type = "REPLACE" if base else "COMBINE"
    strip.extrapolation = "HOLD" if base else "HOLD_FORWARD"
    strip.name = track.name
    return strip


def _unique_track_name(ob, name):
    names = {t.name for t in tracks(ob)}
    if name not in names:
        return name
    i = 2
    while f"{name} {i}" in names:
        i += 1
    return f"{name} {i}"


def start_layers(context, ob):
    """Turn the object's current animation into a Base layer."""
    ad = ob.animation_data or ob.animation_data_create()
    if len(ad.nla_tracks):
        return active_track(ob) or ad.nla_tracks[0]
    act, slot = ad.action, ad.action_slot
    if act is None:
        act = bpy.data.actions.new(f"{ob.name}_Base")
        slot = None
    ad.action = None
    track = ad.nla_tracks.new()
    track.name = "Base"
    _make_strip(context, ob, track, act, slot, base=True)
    act["al_color"] = PALETTE[0]
    act["al_keys"] = False
    ad.use_nla = True
    enter_tweak(context, ob, track)
    return track


def add_layer(context, ob, name="Layer"):
    if not has_layers(ob):
        start_layers(context, ob)
    ad = ob.animation_data
    above = active_track(ob) or ad.nla_tracks[-1]
    above_name = above.name
    exit_tweak(context, ob)
    above = ad.nla_tracks[above_name]
    name = _unique_track_name(ob, name)
    act = bpy.data.actions.new(f"{ob.name}_{name}")
    slot = act.slots.new(id_type="OBJECT", name=ob.name)
    track = ad.nla_tracks.new(prev=above)
    track.name = name
    _make_strip(context, ob, track, act, slot, base=False)
    act["al_color"] = PALETTE[(len(ad.nla_tracks) - 1) % len(PALETTE)]
    act["al_keys"] = False
    enter_tweak(context, ob, track)
    return track


def duplicate_layer(context, ob, track):
    ad = ob.animation_data
    src = layer_strip(track)
    if src is None:
        return None
    name = _unique_track_name(ob, track.name + " copy")
    src_name = track.name
    exit_tweak(context, ob)
    track = ad.nla_tracks[src_name]
    src = layer_strip(track)
    act = src.action.copy()
    act.name = f"{ob.name}_{name}"
    new = ad.nla_tracks.new(prev=track)
    new.name = name
    slot = None
    if src.action_slot is not None:
        slot = next((s for s in act.slots if s.identifier == src.action_slot.identifier), None)
    strip = _make_strip(context, ob, new, act, slot, base=False)
    strip.blend_type = src.blend_type
    val, _ = influence_info(track)
    if val < 0.999:
        set_influence(context, new, val)
    act["al_color"] = PALETTE[(len(ad.nla_tracks) - 1) % len(PALETTE)]
    enter_tweak(context, ob, new)
    return new


def delete_layer(context, ob, track):
    ad = ob.animation_data
    idx = track_index(ob, track)
    name = track.name
    exit_tweak(context, ob)
    track = ad.nla_tracks[name]
    act = layer_action(track)
    ad.nla_tracks.remove(track)
    if act is not None and act.users == 0:
        bpy.data.actions.remove(act)
    rest = tracks(ob)
    if rest:
        enter_tweak(context, ob, rest[max(0, min(idx - 1, len(rest) - 1))])


# ---------------------------------------------------------------- per-layer settings

def set_influence(context, track, value):
    s = layer_strip(track)
    if s is None:
        return False
    value = max(0.0, min(1.0, value))
    if not s.use_animated_influence:
        s.use_animated_influence = True
    fc = s.fcurves.find("influence")
    if fc is not None:
        n = len(fc.keyframe_points)
        if n > 1:
            return False        # animated by the user: leave it alone
        if n == 0:
            fc.keyframe_points.insert(context.scene.frame_current, value)
        kp = fc.keyframe_points[0]
        kp.co[1] = value
        kp.handle_left[1] = value
        kp.handle_right[1] = value
        fc.update()
    s.influence = value
    return True


def cycle_blend(track):
    s = layer_strip(track)
    if s is None:
        return None
    cur = s.blend_type
    nxt = BLEND_CYCLE[(BLEND_CYCLE.index(cur) + 1) % len(BLEND_CYCLE)] if cur in BLEND_CYCLE else "COMBINE"
    s.blend_type = nxt
    return nxt


def rename_layer(ob, track, name):
    name = name.strip() or track.name
    if name == track.name:
        return
    name = _unique_track_name(ob, name)
    track.name = name
    s = layer_strip(track)
    if s is not None:
        s.name = name
        if s.action is not None and (s.action.users <= 2 or s.action.name.startswith(ob.name + "_")):
            s.action.name = f"{ob.name}_{name}"


# ---------------------------------------------------------------- reordering

_STRIP_FIELDS = ("action_frame_start", "action_frame_end", "scale", "repeat", "blend_type", "extrapolation",
                 "blend_in", "blend_out", "use_auto_blend", "mute", "use_reverse", "use_sync_length",
                 "use_animated_time", "use_animated_time_cyclic")


def _snapshot(track):
    out = []
    for s in track.strips:
        d = {f: getattr(s, f) for f in _STRIP_FIELDS}
        d.update(name=s.name, action=s.action, slot=s.action_slot, frame_start=s.frame_start,
                 influence=s.influence, animated_influence=s.use_animated_influence, inf_keys=[])
        fc = s.fcurves.find("influence") if s.use_animated_influence else None
        if fc is not None:
            d["inf_keys"] = [(tuple(k.co), k.interpolation) for k in fc.keyframe_points]
        out.append(d)
    return dict(name=track.name, mute=track.mute, lock=track.lock, solo=track.is_solo, strips=out)


def _restore(track, snap):
    for s in list(track.strips):
        track.strips.remove(s)
    for d in snap["strips"]:
        if d["action"] is None:
            continue
        s = track.strips.new(d["name"] + "~", int(d["frame_start"]), d["action"])
        if d["slot"] is not None:
            s.action_slot = d["slot"]
        s.action_frame_end = d["action_frame_end"]
        s.action_frame_start = d["action_frame_start"]
        for f in _STRIP_FIELDS[2:]:
            try:
                setattr(s, f, d[f])
            except Exception:
                pass
        s.frame_start_ui = d["frame_start"]
        if d["animated_influence"]:
            s.use_animated_influence = True
            fc = s.fcurves.find("influence")
            if fc is not None:
                while len(fc.keyframe_points):
                    fc.keyframe_points.remove(fc.keyframe_points[0])
                for co, interp in d["inf_keys"]:
                    kp = fc.keyframe_points.insert(co[0], co[1])
                    kp.interpolation = interp
            s.influence = d["influence"]
        s.name = d["name"]
    track.mute = snap["mute"]
    track.lock = snap["lock"]


def move_layer(context, ob, track, direction):
    """direction +1 = up, -1 = down. Swaps contents with the neighbouring track."""
    ts = tracks(ob)
    i = track_index(ob, track)
    j = i + direction
    if i < 0 or not (0 <= j < len(ts)):
        return False
    a_name, b_name = ts[i].name, ts[j].name
    exit_tweak(context, ob)
    ad = ob.animation_data
    A, B = ad.nla_tracks[a_name], ad.nla_tracks[b_name]
    sa, sb = _snapshot(A), _snapshot(B)
    A.name, B.name = "__al_tmp_a", "__al_tmp_b"
    _restore(A, sb)
    _restore(B, sa)
    A.name, B.name = sb["name"], sa["name"]
    for t, snap in ((A, sb), (B, sa)):
        if snap["solo"]:
            t.is_solo = True
    enter_tweak(context, ob, B)     # B now holds the moved layer
    return True


def toggle_solo(track):
    track.is_solo = not track.is_solo


def toggle_mute(track):
    track.mute = not track.mute
