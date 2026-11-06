# Anim Layers — simple animation layers for any object, with a floating panel.
# Layers are ordinary NLA tracks, so your animation still plays without the add-on.

import bpy
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty

from . import layers as L
from . import panel, timeline
from .panel import STATE, ANIMLAYERS_OT_toggle


class ANIMLAYERS_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    scale: FloatProperty(name="Panel Size", default=1.0, min=0.6, max=2.5)
    opacity: FloatProperty(name="Background Opacity", default=0.9, min=0.2, max=1.0, subtype="FACTOR")
    col_bg: FloatVectorProperty(name="Background", subtype="COLOR_GAMMA", size=3, min=0, max=1,
                                default=(0.115, 0.12, 0.13))
    show_lanes: BoolProperty(name="Show Key Lanes", default=True,
                             description="Draw keys of layers with the diamond turned on at the bottom of the Timeline and Dope Sheet")
    lane_height: FloatProperty(name="Lane Height", default=16, min=10, max=30)
    reopen_on_load: BoolProperty(name="Re-open After Loading a File", default=True)

    def draw(self, context):
        draw_look(self.layout, self)


def draw_look(layout, p):
    col = layout.column(align=True)
    col.prop(p, "scale", slider=True)
    col.prop(p, "opacity", slider=True)
    layout.prop(p, "col_bg")
    row = layout.row(align=True)
    row.prop(p, "show_lanes", toggle=True)
    row.prop(p, "lane_height")
    layout.prop(p, "reopen_on_load")


# ---------------------------------------------------------------- operators (sidebar + rename)

def _ob(context):
    return context.active_object


class ANIMLAYERS_OT_rename(bpy.types.Operator):
    """Rename a layer"""
    bl_idname = "animlayers.rename"
    bl_label = "Rename Layer"
    bl_options = {"REGISTER", "UNDO"}
    index: IntProperty(default=-1, options={"HIDDEN", "SKIP_SAVE"})
    name: StringProperty(name="Name")

    def draw(self, context):
        row = self.layout.row()
        row.activate_init = True        # start typing straight away
        row.prop(self, "name", text="")

    def invoke(self, context, event):
        ts = L.tracks(_ob(context))
        if not (0 <= self.index < len(ts)):
            return {"CANCELLED"}
        self.name = ts[self.index].name
        return context.window_manager.invoke_props_dialog(self, width=260)

    def execute(self, context):
        ob = _ob(context)
        ts = L.tracks(ob)
        if 0 <= self.index < len(ts):
            L.rename_layer(ob, ts[self.index], self.name)
            panel.redraw_all(context.screen)
        return {"FINISHED"}


class ANIMLAYERS_OT_action(bpy.types.Operator):
    """Anim Layers action"""
    bl_idname = "animlayers.action"
    bl_label = "Anim Layers"
    bl_options = {"REGISTER", "UNDO"}
    action: StringProperty(options={"HIDDEN"})
    index: IntProperty(default=-1, options={"HIDDEN"})

    @classmethod
    def description(cls, context, props):
        return {
            "start": "Turn the current animation into the Base layer",
            "add": "Add a new layer above the one you're editing",
            "dup": "Duplicate the layer you're editing", "del": "Delete the layer you're editing",
            "up": "Move the layer you're editing up", "down": "Move the layer you're editing down",
            "edit": "Edit this layer (new keys go into it)", "mute": "Show / hide this layer",
            "solo": "Play only this layer", "keys": "Show this layer's keys on the Timeline",
            "blend": "Cycle blend mode: Combine, Add, Replace",
        }.get(props.action, "Anim Layers")

    def execute(self, context):
        ob = _ob(context)
        if ob is None:
            self.report({"WARNING"}, "Select an object first")
            return {"CANCELLED"}
        ts = L.tracks(ob)
        t = ts[self.index] if 0 <= self.index < len(ts) else None
        a = self.action
        if a == "start":
            L.start_layers(context, ob)
        elif a in ("add", "dup", "del", "up", "down"):
            msg = panel.do_foot(context, ob, a)
            if msg:
                self.report({"INFO"}, msg)
        elif t is None:
            return {"CANCELLED"}
        elif a == "edit":
            L.enter_tweak(context, ob, t)
        elif a == "mute":
            L.toggle_mute(t)
        elif a == "solo":
            L.toggle_solo(t)
        elif a == "keys":
            L.set_meta(t, "al_keys", not L.show_keys(t))
        elif a == "blend":
            L.cycle_blend(t)
        panel.redraw_all(context.screen)
        return {"FINISHED"}


# ---------------------------------------------------------------- sidebar panel

class VIEW3D_PT_animlayers(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Layers"
    bl_label = "Anim Layers"

    def draw(self, context):
        layout = self.layout
        open_ = STATE["show"] and panel.op_alive()
        layout.operator("animlayers.toggle", text="Hide Floating Panel" if open_ else "Show Floating Panel",
                        icon="HIDE_ON" if open_ else "RENDERLAYERS", depress=open_)
        ob = _ob(context)
        if ob is None:
            layout.label(text="Select an object")
            return
        ts = L.tracks(ob)
        if not ts:
            layout.operator("animlayers.action", text="Start Layers", icon="ADD").action = "start"
            return
        act = L.active_track(ob)
        col = layout.column(align=True)
        for i in reversed(range(len(ts))):
            t = ts[i]
            row = col.row(align=True)
            op = row.operator("animlayers.action", text="", icon="HIDE_ON" if t.mute else "HIDE_OFF", emboss=False)
            op.action, op.index = "mute", i
            op = row.operator("animlayers.action", text=t.name, depress=t == act,
                              icon="GREASEPENCIL" if t == act else "BLANK1")
            op.action, op.index = "edit", i
            s = L.layer_strip(t)
            op = row.operator("animlayers.action", text=L.BLEND_SHORT.get(s.blend_type, "?") if s else "-")
            op.action, op.index = "blend", i
            op = row.operator("animlayers.action", text="", icon="KEYFRAME_HLT" if L.show_keys(t) else "KEYFRAME")
            op.action, op.index = "keys", i
            op = row.operator("animlayers.action", text="", icon="SOLO_ON" if t.is_solo else "SOLO_OFF", emboss=False)
            op.action, op.index = "solo", i
        layout.label(text="Influence: drag the bar in the floating panel", icon="INFO")
        row = layout.row(align=True)
        for a, icon in (("add", "ADD"), ("dup", "DUPLICATE"), ("del", "REMOVE"), ("up", "TRIA_UP"), ("down", "TRIA_DOWN")):
            row.operator("animlayers.action", text="", icon=icon).action = a


class VIEW3D_PT_animlayers_look(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Layers"
    bl_label = "Look"
    bl_parent_id = "VIEW3D_PT_animlayers"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_look(self.layout, panel.prefs())


def header_button(self, context):
    open_ = STATE["show"] and panel.op_alive()
    self.layout.operator("animlayers.toggle", text="Layers", icon="RENDERLAYERS", depress=open_)


classes = (ANIMLAYERS_Preferences, ANIMLAYERS_OT_toggle, ANIMLAYERS_OT_rename, ANIMLAYERS_OT_action,
           VIEW3D_PT_animlayers, VIEW3D_PT_animlayers_look)
_handles = []


def register():
    for c in classes:
        bpy.utils.register_class(c)
    _handles.append((bpy.types.SpaceView3D,
                     bpy.types.SpaceView3D.draw_handler_add(panel.draw_callback, (), "WINDOW", "POST_PIXEL")))
    _handles.append((bpy.types.SpaceDopeSheetEditor,
                     bpy.types.SpaceDopeSheetEditor.draw_handler_add(timeline.draw_lanes, (), "WINDOW", "POST_PIXEL")))
    bpy.types.VIEW3D_HT_header.append(header_button)
    for lst, fn in ((bpy.app.handlers.load_post, panel.on_load_post),
                    (bpy.app.handlers.depsgraph_update_post, timeline.on_depsgraph)):
        if fn not in lst:
            lst.append(fn)


def unregister():
    STATE["show"] = False
    for lst, fn in ((bpy.app.handlers.load_post, panel.on_load_post),
                    (bpy.app.handlers.depsgraph_update_post, timeline.on_depsgraph)):
        if fn in lst:
            lst.remove(fn)
    bpy.types.VIEW3D_HT_header.remove(header_button)
    for space, h in _handles:
        space.draw_handler_remove(h, "WINDOW")
    _handles.clear()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
