# Mewgenics AAF tool

Prototype tool for reconstructing Mewgenics active ability UI icons.

This project is separate from `Mewgenics PAF tool` and only reads shared game exports.

## Findings

- Active ability definitions live in `gpak-all/data/abilities/*_abilities.gon`.
- Display text keys live in `gpak-all/data/text/abilities.csv`.
- The active icon label to SVG id map lives in `OtherGameFiles/UnpackedImportant/DefineSprite(AbilityIcon)/frames.xml`.
- `FrameLabelTag name="HogRush"` maps to a timeline frame; the main picture is normally the object at depth `3`.
- The full UI shell is `OtherGameFiles/UnpackedImportant/ABILITYICONSHELL_161/frames.xml`.

## Prototype workflow

Generate the active manifest:

```powershell
python scripts\extract_active_manifest.py
```

Generate a single HogRush-style SVG:

```powershell
python scripts\generate_from_rules.py `
  --main-svg "H:\Mewgenics Projects\Passive Abilities Frame\OtherGameFiles\UnpackedImportant\Ability Passive Svg\shapes\941.svg" `
  --class-name butcher `
  --output output\hog_rush.svg
```

Open the manual layout editor:

```text
H:\Mewgenics Projects\Active Abilities Frame\Mewgenics AAF tool\tools\active_layout_editor.html
```

Export the real game frame assets from `ABILITYICONSHELL_161`:

```powershell
python scripts\export_shell_frame_assets.py
```

This creates:

- `assets/shell_shapes/*.svg`
- `rules/frame_variants.json`
- `rules/frame_1_manual.json` through `rules/frame_6_manual.json`

Open the frame layout editor:

```text
H:\Mewgenics Projects\Active Abilities Frame\Mewgenics AAF tool\tools\frame_layout_editor.html
```

If the browser blocks local JSON loading, select `rules/frame_variants.json` in the editor's file picker.

Generate cost/damage metadata without drawing numbers into the SVG:

```powershell
python scripts\extract_active_numbers.py
```

The result is `rules/active_numbers.json`.

Generate all rows with known SVG ids:

```powershell
python scripts\generate_all_actives.py
```

The current `rules/active_manual.json` is a first-pass icon-frame layout. It uses the `AbilityIcon` background, main art, frame, and a temporary class color strip. The next pass should replace the placeholder class strip with the real `ABILITYICONSHELL_161` layers once the visual reference is matched.

The real shell currently exposes six frame variants from sprite `2832`. They differ by the presence and layout of damage, mana, upgrade overlays, type icons, elements, and compact frame parts. The manual frame rules intentionally do not render text values yet; number slots and values live in JSON for the future GUI.
