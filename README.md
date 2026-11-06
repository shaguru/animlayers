# Anim Layers

Simple animation layers for Blender, in a floating panel you can drag around the 3D View.
Works on **any object**: armatures (CloudRig, Rigify, your own rigs), props, cameras, lights.

Version 0.1.0. Tested in Blender 5.1. Requires Blender 4.4+.

## Install

1. Download **[anim_layers-0.1.0.zip](https://github.com/shaguru/animlayers/raw/main/dist/anim_layers-0.1.0.zip)** (also in the `dist` folder).
2. In Blender: **Edit ▸ Preferences ▸ Get Extensions ▸ ⌄ (top-right) ▸ Install from Disk…** and pick the zip.
   (You can also drag the zip onto the Blender window.)

## Use

1. Select the object you animate (for a rig, the armature) and click **Layers** in the 3D View header.
2. Click **Start Layers**. Your existing animation becomes the **Base** layer.
3. Click **+ Layer**. New keys now go into that layer as offsets on top of everything below it.
   Example: block a walk in Base, then add an "Arms" layer and push the arms further without touching the walk.
4. Click any layer to edit it (✎ marks the one receiving keys).

| Control | What it does |
| --- | --- |
| 👁 Eye | Show / hide the layer (mute) |
| Name | Click to edit this layer · double-click to rename |
| COMB / ADD / REPL | Blend mode. **Combine** (default) layers offsets on top and handles rotations properly; **Add** adds values; **Replace** overrides what's below (Base uses this) |
| Influence bar | Drag to fade the layer in or out · double-click resets to 100% |
| ◆ Keys | Show this layer's keys as a coloured lane at the bottom of the **Timeline / Dope Sheet**, even when you're editing another layer |
| S | Solo: play only this layer |
| + Layer · Duplicate · Delete · ▲ · ▼ | Add above the current layer, copy, delete (Ctrl+Z undoes), reorder |

Drag the title bar to move the panel, use the corner grip or Ctrl+Wheel to resize it, and – / × to collapse or close.
A simpler version of the same controls is in **Sidebar (N) ▸ Layers**.

**Tip:** make the Timeline a little taller so the key lanes have room under Blender's own key row.
Keys from layers you're *not* editing only appear in the lanes; the normal Timeline/Dope Sheet shows the layer you're editing.

## How it works (and why it's safe)

Each layer is an ordinary **NLA track** with one strip holding that layer's action. The layer you edit is opened in
NLA *tweak mode* with the full stack evaluated, so you always see the final result. Nothing is hidden or proprietary:
the animation plays without this add-on, and you can open the NLA Editor to see exactly what it built.
Layer colours and the "show keys" setting are stored as custom properties on each layer's action.

**Limits in 0.1:** influence can't be animated from the panel (if you key it in the NLA editor, the panel shows "~" and
leaves it alone) · no merge/bake button yet (use **NLA ▸ Edit ▸ Bake Action**) · shape keys and material animation
aren't layered (object/armature animation only).

## Build the zip yourself

```
cd anim_layers
zip -r ../dist/anim_layers-0.1.0.zip . -x "__pycache__/*"
```

## License

GPL-3.0-or-later (see `LICENSE`), as required for Blender add-ons.
