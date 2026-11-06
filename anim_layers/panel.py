# Floating layer panel drawn over the 3D View, plus the modal operator that handles its mouse input.

import time
import traceback

import bpy

from . import draw as D
from . import layers as L

ADDON = __package__

STATE = {
    "show": False, "op": None, "area_ptr": 0, "pos": None, "collapsed": False,
    "hover": None, "drag": None, "status": "", "last_click": None,
}

ICON_TEXT = (0.92, 0.92, 0.92, 1)
DIM_TEXT = (0.62, 0.62, 0.65, 1)
ACCENT = (1.0, 0.62, 0.20, 1)


# ---------------------------------------------------------------- helpers

def prefs():
    return bpy.context.preferences.addons[ADDON].preferences


def ui_scale():
    return bpy.context.preferences.system.ui_scale


def op_alive():
    op = STATE["op"]
    if op is None:
        return False
    try:
        op.bl_idname
        return True
    except ReferenceError:
        STATE["op"] = None
        return False


def target_area(screen):
    areas = [a for a in screen.areas if a.type == "VIEW_3D"] if screen else []
    for a in areas:
        if a.as_pointer() == STATE["area_ptr"]:
            return a
    if not areas:
        return None
    best = max(areas, key=lambda a: a.width * a.height)
    STATE["area_ptr"] = best.as_pointer()
    return best


def window_region(area):
    regs = [r for r in area.regions if r.type == "WINDOW"]
    return max(regs, key=lambda r: r.width * r.height) if regs else None


def redraw_all(screen=None):
    screen = screen or bpy.context.screen
    if screen:
        for a in screen.areas:
            a.tag_redraw()


def undo(msg):
    try:
        bpy.ops.ed.undo_push(message=msg)
    except Exception:
        pass


def in_rect(x, y, r):
    return r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]


# ---------------------------------------------------------------- layout

class Frame:
    pass


FOOT_BUTTONS = [("+ Layer", "add", 1.25), ("Duplicate", "dup", 1.15), ("Delete", "del", 1.0),
                ("▲", "up", 0.55), ("▼", "down", 0.55)]


def make_frame(rw, rh, ob):
    p = prefs()
    k = p.scale * ui_scale()
    F = Frame()
    F.k = k
    F.w = 350 * k
    F.head = 26 * k
    F.row = 30 * k
    F.pad = 6 * k
    n = len(L.tracks(ob)) if ob is not None else 0
    F.n = n
    body = (n * F.row if n else 64 * k) + F.pad
    foot = 28 * k + F.pad + 18 * k
    F.h = F.head + (0 if STATE["collapsed"] else body + foot)
    if STATE["pos"] is None:
        STATE["pos"] = [rw - F.w - 70 * ui_scale(), 70.0]
    px, py = STATE["pos"]
    px = min(max(px, 80 - F.w), rw - 80)
    py = min(max(py, 0), max(0, rh - F.head))
    STATE["pos"] = [px, py]
    F.x = px
    F.top = rh - py
    F.y = F.top - F.h
    F.body_top = F.top - F.head - F.pad * 0.5
    return F


def build_items(F, ob):
    k = F.k
    items = []
    bh = F.head - 8 * k
    bx = F.x + F.w - 4 * k
    for key, label in (("close", "×"), ("collapse", "+" if STATE["collapsed"] else "–")):
        bx -= 24 * k + 3 * k
        items.append(dict(type="hdr", key=key, label=label, rect=(bx, F.top - F.head + 4 * k, 24 * k, bh)))
    if STATE["collapsed"]:
        items.append(dict(type="header", rect=(F.x, F.top - F.head, F.w, F.head)))
        return items
    items.append(dict(type="grip", rect=(F.x + F.w - 16 * k, F.y, 16 * k, 16 * k)))
    ts = L.tracks(ob) if ob is not None else []
    x0 = F.x + F.pad
    xr = F.x + F.w - F.pad
    if ts:
        for row, i in enumerate(reversed(range(len(ts)))):     # top layer drawn first
            t = ts[i]
            y = F.body_top - (row + 1) * F.row
            rh = F.row - 3 * k
            cy = y + rh / 2
            solo = (xr - 20 * k, cy - 9 * k, 20 * k, 18 * k)
            keys_cx = solo[0] - 17 * k
            infl = (keys_cx - 19 * k - 70 * k, cy - 7 * k, 70 * k, 14 * k)
            blend = (infl[0] - 8 * k - 40 * k, cy - 9 * k, 40 * k, 18 * k)
            eye_c = (x0 + 20 * k, cy)
            items += [
                dict(type="solo", i=i, rect=solo),
                dict(type="keys", i=i, rect=(keys_cx - 10 * k, cy - 10 * k, 20 * k, 20 * k), cx=keys_cx, cy=cy),
                dict(type="infl", i=i, rect=infl),
                dict(type="blend", i=i, rect=blend),
                dict(type="eye", i=i, rect=(eye_c[0] - 11 * k, cy - 11 * k, 22 * k, 22 * k), cx=eye_c[0], cy=cy),
                dict(type="row", i=i, rect=(x0, y, xr - x0, rh), name_x=x0 + 38 * k, name_w=blend[0] - x0 - 44 * k),
            ]
    else:
        bw = 150 * k
        items.append(dict(type="start", rect=(F.x + (F.w - bw) / 2, F.body_top - 44 * k, bw, 28 * k)))
    fy = F.y + 18 * k + F.pad * 0.5
    total = sum(w for _, _, w in FOOT_BUTTONS)
    avail = F.w - 2 * F.pad - (len(FOOT_BUTTONS) - 1) * 4 * k
    x = x0
    for label, key, w in FOOT_BUTTONS:
        bw = avail * w / total
        items.append(dict(type="foot", key=key, label=label, rect=(x, fy, bw, 26 * k)))
        x += bw + 4 * k
    items.append(dict(type="header", rect=(F.x, F.top - F.head, F.w, F.head)))
    items.append(dict(type="panel", rect=(F.x, F.y, F.w, F.h)))
    return items


def hit(items, x, y):
    for it in items:
        if in_rect(x, y, it["rect"]):
            return it
    return None


def item_key(it):
    if it is None:
        return None
    return (it["type"], it.get("i"), it.get("key"))


# ---------------------------------------------------------------- drawing

def draw_eye(cv, cx, cy, k, on, col):
    if on:
        cv.fill(D.ellipse(cx, cy, 9 * k, 5.5 * k), (0.92, 0.92, 0.92, 1), 4)
        cv.fill(D.circle(cx, cy, 3.6 * k), D.with_alpha(col, 1), 5)
        cv.fill(D.circle(cx, cy, 1.6 * k), (0.05, 0.05, 0.05, 1), 6)
    else:
        cv.outline(D.ellipse(cx, cy, 9 * k, 5.5 * k), (0.5, 0.5, 0.52, 1), 1.4, 4)
        cv.line((cx - 9 * k, cy - 6 * k), (cx + 9 * k, cy + 6 * k), (0.6, 0.6, 0.62, 1), 1.6, 5)


def draw_panel(context, region):
    ob = context.active_object
    p = prefs()
    F = make_frame(region.width, region.height, ob)
    items = build_items(F, ob)
    k = F.k
    cv = D.Canvas()
    hover = STATE["hover"]
    bg = tuple(p.col_bg) + (p.opacity,)
    cv.fill(D.rrect(F.x, F.y, F.w, F.h, 6 * k), bg, 0)
    cv.outline(D.rrect(F.x, F.y, F.w, F.h, 6 * k), (1, 1, 1, 0.12), 1.0, 0)
    hc = D.mix(bg, (1, 1, 1, 1), 0.07)
    cv.fill(D.rrect(F.x + 1, F.top - F.head, F.w - 2, F.head - 1, 5 * k), D.with_alpha(hc, min(1, p.opacity + 0.05)), 0)
    # header: stacked-layers glyph + title
    gx, gy = F.x + 12 * k, F.top - F.head / 2
    for j, a in enumerate((0.45, 0.7, 1.0)):
        cv.fill(D.rdiamond(gx + 6 * k, gy - 4 * k + j * 4 * k, 6 * k, 0.1), (1, 0.62, 0.2, a), 1)
    title = ("Layers · " + ob.name) if ob is not None else "Layers"
    while len(title) > 6 and D.text_width(title, 12 * k) > F.w - 100 * k:
        title = title[:-2]
    cv.text(F.x + 26 * k, F.top - F.head + 8 * k, title, 12 * k, ICON_TEXT)

    ts = L.tracks(ob) if ob is not None else []
    act = L.active_track(ob) if ob is not None else None
    for it in items:
        t = it["type"]
        hv = item_key(it) == hover
        if t == "hdr":
            x, y, w, h = it["rect"]
            cv.fill(D.rrect(x, y, w, h, 4 * k), (1, 1, 1, 0.22 if hv else 0.10), 1)
            cv.text(x + w / 2, y + h / 2 - 4.5 * k, it["label"], 12 * k, ICON_TEXT, "C")
    if STATE["collapsed"]:
        cv.flush(region.width, region.height)
        return

    if ob is None:
        cv.text(F.x + F.w / 2, F.body_top - 30 * k, "Select an object to animate", 12 * k, DIM_TEXT, "C")

    row_hover = hover[1] if hover and hover[0] in ("row", "eye", "infl", "blend", "keys", "solo") else None
    for it in items:
        t = it["type"]
        hv = item_key(it) == hover
        if t == "row":
            i = it["i"]
            tr = ts[i]
            col = L.color(tr, i) + (1.0,)
            x, y, w, h = it["rect"]
            is_act = tr == act
            base = (1, 1, 1, 0.035 if row_hover != i else 0.07)
            if is_act:
                base = D.with_alpha(col, 0.22)
            cv.fill(D.rrect(x, y, w, h, 4 * k), base, 1)
            if is_act:
                cv.outline(D.rrect(x, y, w, h, 4 * k), D.with_alpha(col, 0.95), 1.6 * k, 2)
            cv.fill(D.rrect(x + 2 * k, y + 3 * k, 4 * k, h - 6 * k, 2 * k), col, 2)
            muted = tr.mute
            name = tr.name
            fs = 12 * k
            while len(name) > 2 and D.text_width(name, fs) > it["name_w"] - (18 * k if is_act else 0):
                name = name[:-2]
            tcol = DIM_TEXT if muted else ICON_TEXT
            cv.text(it["name_x"], y + h / 2 - 4.5 * k, name, fs, tcol)
            if is_act:
                cv.text(it["name_x"] + D.text_width(name, fs) + 5 * k, y + h / 2 - 4.5 * k, "✎", fs,
                        D.with_alpha(col, 1))
        elif t == "eye":
            tr = ts[it["i"]]
            draw_eye(cv, it["cx"], it["cy"], k, not tr.mute, L.color(tr, it["i"]))
        elif t == "blend":
            s = L.layer_strip(ts[it["i"]])
            x, y, w, h = it["rect"]
            label = L.BLEND_SHORT.get(s.blend_type, s.blend_type[:4]) if s else "—"
            cv.fill(D.rrect(x, y, w, h, h / 2), (1, 1, 1, 0.16 if hv else 0.08), 3)
            cv.text(x + w / 2, y + h / 2 - 4 * k, label, 9.5 * k, ICON_TEXT, "C")
        elif t == "infl":
            tr = ts[it["i"]]
            val, editable = L.influence_info(tr)
            col = L.color(tr, it["i"]) + (1.0,)
            x, y, w, h = it["rect"]
            cv.fill(D.rrect(x, y, w, h, 3 * k), (0, 0, 0, 0.35), 3)
            if val > 0.002:
                cv.fill(D.rrect(x, y, max(h * 0.5, w * val), h, 3 * k), D.with_alpha(col, 0.75 if editable else 0.35), 4)
            if hv:
                cv.outline(D.rrect(x, y, w, h, 3 * k), (1, 1, 1, 0.6), 1.2, 5)
            txt = f"{round(val * 100)}%" + ("" if editable else " ~")
            cv.text(x + w / 2, y + h / 2 - 4 * k, txt, 9.5 * k, (1, 1, 1, 0.95), "C")
        elif t == "keys":
            tr = ts[it["i"]]
            on = L.show_keys(tr)
            col = L.color(tr, it["i"]) + (1.0,)
            dia = D.rdiamond(it["cx"], it["cy"], 7.5 * k, 0.12)
            if on:
                cv.fill(dia, col, 4)
                cv.outline(dia, (1, 1, 1, 0.9), 1.2, 5)
            else:
                cv.outline(dia, (0.6, 0.6, 0.62, 1) if not hv else (1, 1, 1, 1), 1.4, 4)
        elif t == "solo":
            tr = ts[it["i"]]
            x, y, w, h = it["rect"]
            on = tr.is_solo
            cv.fill(D.rrect(x, y, w, h, 4 * k), ACCENT if on else (1, 1, 1, 0.14 if hv else 0.06), 3)
            cv.text(x + w / 2, y + h / 2 - 4.5 * k, "S", 11 * k, (0.08, 0.08, 0.08, 1) if on else DIM_TEXT, "C")
        elif t == "start":
            x, y, w, h = it["rect"]
            cv.fill(D.rrect(x, y, w, h, 5 * k), D.mix(ACCENT, (1, 1, 1, 1), 0.15 if hv else 0.0), 3)
            cv.text(x + w / 2, y + h / 2 - 4.5 * k, "Start Layers", 12 * k, (0.08, 0.08, 0.08, 1), "C")
            cv.text(F.x + F.w / 2, y - 16 * k, "Your current animation becomes the Base layer", 10 * k, DIM_TEXT, "C")
        elif t == "foot":
            x, y, w, h = it["rect"]
            dis = not ts and it["key"] != "add"
            fill = (1, 1, 1, 0.20 if hv and not dis else 0.09)
            if it["key"] == "add":
                fill = D.with_alpha(D.mix(ACCENT, (0, 0, 0, 1), 0.15 if hv else 0.35), 0.95)
            cv.fill(D.rrect(x, y, w, h, 4 * k), fill, 3)
            cv.text(x + w / 2, y + h / 2 - 4.5 * k, it["label"], 11 * k,
                    (0.5, 0.5, 0.5, 1) if dis else ICON_TEXT, "C")
    gx, gy = F.x + F.w - 4 * k, F.y + 4 * k
    for i in (1, 2, 3):
        cv.line((gx - 4 * i * k, gy), (gx, gy + 4 * i * k), (1, 1, 1, 0.3), 1.2, 3)
    cv.text(F.x + F.pad, F.y + 5 * k, status_text(ob, ts, act, hover), 10.5 * k, (0.72, 0.72, 0.74, 1))
    cv.flush(region.width, region.height)


def status_text(ob, ts, act, hover):
    if STATE["status"]:
        return STATE["status"]
    tips = {
        "eye": "Show / hide this layer (mute)", "solo": "Solo: play only this layer",
        "keys": "Show this layer's keys on the Timeline / Dope Sheet",
        "infl": "Drag to set how strongly this layer applies · double-click: 100%",
        "blend": "Blend mode: Combine (layer on top) · Add · Replace",
        "row": "Click to edit this layer · double-click to rename",
        "add": "New layer above the one you're editing", "dup": "Copy the layer you're editing",
        "del": "Delete the layer you're editing (Ctrl+Z to undo)", "up": "Move layer up", "down": "Move layer down",
        "start": "Turn the current animation into the Base layer",
    }
    if hover:
        key = hover[2] if hover[0] == "foot" else hover[0]
        if key in tips:
            return tips[key]
    if ob is None:
        return ""
    if ts and act is None:
        return "Click a layer to start editing it"
    if act is not None:
        return f"Keys go into: {act.name}"
    return "Animate as normal, then add layers on top"


def draw_callback():
    if not STATE["show"]:
        return
    try:
        ctx = bpy.context
        area, region = ctx.area, ctx.region
        if area is None or region is None or region.type != "WINDOW":
            return
        ta = target_area(ctx.screen)
        if ta is None or ta.as_pointer() != area.as_pointer():
            return
        if window_region(area).as_pointer() != region.as_pointer():
            return
        draw_panel(ctx, region)
    except Exception:
        traceback.print_exc()


# ---------------------------------------------------------------- actions

def do_foot(context, ob, key):
    if ob is None:
        return "Select an object first"
    if key == "add":
        t = L.add_layer(context, ob)
        undo("Add Animation Layer")
        return f"Added '{t.name}' — keys now go into it"
    ts = L.tracks(ob)
    if not ts:
        return "Press Start Layers first"
    cur = L.active_track(ob) or ts[-1]
    if key == "dup":
        t = L.duplicate_layer(context, ob, cur)
        undo("Duplicate Animation Layer")
        return f"Duplicated as '{t.name}'" if t else ""
    if key == "del":
        name = cur.name
        L.delete_layer(context, ob, cur)
        undo("Delete Animation Layer")
        return f"Deleted '{name}' (Ctrl+Z to undo)"
    if key in ("up", "down"):
        ok = L.move_layer(context, ob, cur, 1 if key == "up" else -1)
        if ok:
            undo("Move Animation Layer")
        return "" if ok else "Can't move further"
    return ""


# ---------------------------------------------------------------- modal operator

class ANIMLAYERS_OT_toggle(bpy.types.Operator):
    """Show or hide the floating Anim Layers panel in this 3D View"""
    bl_idname = "animlayers.toggle"
    bl_label = "Toggle Layers Panel"

    def invoke(self, context, event):
        if STATE["show"] and op_alive():
            if context.area and context.area.type == "VIEW_3D" and context.area.as_pointer() != STATE["area_ptr"]:
                STATE["area_ptr"] = context.area.as_pointer()
            else:
                STATE["show"] = False
            redraw_all(context.screen)
            return {"FINISHED"}
        if context.area and context.area.type == "VIEW_3D":
            STATE["area_ptr"] = context.area.as_pointer()
        else:
            target_area(context.screen)
        STATE.update(show=True, op=self, hover=None, drag=None)
        context.window_manager.modal_handler_add(self)
        redraw_all(context.screen)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if not STATE["show"]:
            STATE["op"] = None
            STATE["drag"] = None
            redraw_all(context.screen)
            return {"CANCELLED"}
        try:
            return handle_event(context, event)
        except Exception:
            traceback.print_exc()
            STATE["drag"] = None
            return {"PASS_THROUGH"}


PASS = {"PASS_THROUGH"}
EAT = {"RUNNING_MODAL"}


def handle_event(context, event):
    screen = context.window.screen if context.window else None
    area = target_area(screen)
    if area is None:
        return PASS
    region = window_region(area)
    if region is None:
        return PASS
    mx, my = event.mouse_x - region.x, event.mouse_y - region.y
    drag = STATE["drag"]
    inside = 0 <= mx <= region.width and 0 <= my <= region.height
    if drag is None and not inside:
        if STATE["hover"] is not None:
            STATE["hover"] = None
            area.tag_redraw()
        return PASS

    ob = context.active_object
    F = make_frame(region.width, region.height, ob)
    items = build_items(F, ob)
    k = F.k

    if drag is not None:
        if event.type in ("MOUSEMOVE", "INBETWEEN_MOUSEMOVE"):
            if drag["kind"] == "panel":
                STATE["pos"] = [drag["pos0"][0] + (mx - drag["m0"][0]), drag["pos0"][1] - (my - drag["m0"][1])]
            elif drag["kind"] == "scale":
                p = prefs()
                p.scale = min(2.5, max(0.6, drag["scale0"] * max(0.3, (mx - F.x) / max(1, drag["w0"]))))
            elif drag["kind"] == "infl" and ob is not None:
                ts = L.tracks(ob)
                if abs(mx - drag["m0"]) > 3 * k:
                    drag["moved"] = True
                if drag["moved"] and drag["i"] < len(ts):
                    x, _, w, _ = drag["rect"]
                    v = round(min(1.0, max(0.0, (mx - x) / w)) * 100) / 100
                    L.set_influence(context, ts[drag["i"]], v)
                    STATE["status"] = f"Influence {round(v * 100)}%"
                redraw_all(context.screen)
            area.tag_redraw()
            return EAT
        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if drag["kind"] == "infl" and drag.get("moved"):
                undo("Layer Influence")
            elif drag["kind"] == "scale":
                context.preferences.is_dirty = True
            STATE["drag"] = None
            area.tag_redraw()
            return EAT
        return EAT

    over = in_rect(mx, my, (F.x, F.y, F.w, F.h))
    target = hit(items, mx, my) if over else None
    key = item_key(target)
    if key != STATE["hover"]:
        STATE["hover"] = key
        STATE["status"] = ""
        area.tag_redraw()
    if not over:
        return PASS

    if event.type in ("WHEELUPMOUSE", "WHEELDOWNMOUSE") and event.ctrl:
        p = prefs()
        p.scale = min(2.5, max(0.6, p.scale * (1.08 if event.type == "WHEELUPMOUSE" else 1 / 1.08)))
        area.tag_redraw()
        return EAT

    if event.type == "LEFTMOUSE" and event.value in ("PRESS", "DOUBLE_CLICK"):
        STATE["status"] = ""
        if target is None:
            return EAT
        t = target["type"]
        ts = L.tracks(ob) if ob is not None else []
        i = target.get("i")
        if t == "hdr":
            if target["key"] == "close":
                STATE["show"] = False
            else:
                STATE["collapsed"] = not STATE["collapsed"]
            redraw_all(context.screen)
            return EAT
        if t == "grip":
            STATE["drag"] = dict(kind="scale", scale0=prefs().scale, w0=F.w)
            return EAT
        if t == "header":
            STATE["drag"] = dict(kind="panel", m0=(mx, my), pos0=tuple(STATE["pos"]))
            return EAT
        if t == "start" and ob is not None:
            L.start_layers(context, ob)
            undo("Start Animation Layers")
            STATE["status"] = "Base layer created. Add a layer on top with + Layer"
        elif t == "foot":
            STATE["status"] = do_foot(context, ob, target["key"])
        elif t == "eye":
            L.toggle_mute(ts[i])
            undo("Layer Visibility")
        elif t == "solo":
            L.toggle_solo(ts[i])
            undo("Layer Solo")
        elif t == "keys":
            L.set_meta(ts[i], "al_keys", not L.show_keys(ts[i]))
            undo("Layer Show Keys")
        elif t == "blend":
            nxt = L.cycle_blend(ts[i])
            undo("Layer Blend")
            STATE["status"] = f"Blend: {nxt.title()}"
        elif t == "infl":
            now = time.monotonic()
            last = STATE["last_click"]
            STATE["last_click"] = (("infl", i), now)
            if last and last[0] == ("infl", i) and now - last[1] < 0.45:
                L.set_influence(context, ts[i], 1.0)
                undo("Layer Influence")
                STATE["status"] = "Influence reset to 100%"
            else:
                STATE["drag"] = dict(kind="infl", i=i, rect=target["rect"], m0=mx, moved=False)
        elif t == "row":
            now = time.monotonic()
            last = STATE["last_click"]
            STATE["last_click"] = (i, now)
            if last and last[0] == i and now - last[1] < 0.45:
                STATE["last_click"] = None
                with context.temp_override(window=context.window, area=area, region=region):
                    bpy.ops.animlayers.rename("INVOKE_DEFAULT", index=i)
                return EAT
            if L.active_track(ob) != ts[i]:
                L.enter_tweak(context, ob, ts[i])
                undo("Edit Layer")
                STATE["status"] = f"Editing '{ts[i].name}'"
        redraw_all(context.screen)
        return EAT

    if event.type == "LEFTMOUSE":
        return EAT
    return PASS


# ---------------------------------------------------------------- file load

def reopen_after_load():
    for win in bpy.context.window_manager.windows:
        area = target_area(win.screen)
        if area is None:
            continue
        try:
            with bpy.context.temp_override(window=win, area=area, region=window_region(area)):
                bpy.ops.animlayers.toggle("INVOKE_DEFAULT")
        except Exception:
            traceback.print_exc()
        break
    return None


@bpy.app.handlers.persistent
def on_load_post(*_a):
    was = STATE["show"]
    STATE.update(show=False, op=None, drag=None, hover=None, area_ptr=0)
    if was and prefs().reopen_on_load:
        bpy.app.timers.register(reopen_after_load, first_interval=0.3)
