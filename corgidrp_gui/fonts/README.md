# Bundled fonts

All fonts here are licensed under the SIL Open Font License 1.1 (license text next to each
family as `LICENSE-<Family>-OFL.txt`). They were downloaded from the
[google/fonts](https://github.com/google/fonts) repository (`main` branch, `ofl/` directory) and
are registered at runtime by `corgidrp_gui.theming.register_fonts()` with
`QFontDatabase.addApplicationFont`. If a file is missing, the theme engine silently falls back
to the next family in the stack defined in `theming.FONT_FALLBACKS`.

| File | Family | Used by | Source | License |
|---|---|---|---|---|
| `Jost-Variable.ttf` | Jost (variable, wght 100-900) | Roman (UI, headings) | `ofl/jost/Jost[wght].ttf` | `LICENSE-Jost-OFL.txt` |
| `IBMPlexMono-Regular.ttf`, `IBMPlexMono-SemiBold.ttf` | IBM Plex Mono | Roman (data) | `ofl/ibmplexmono/` | `LICENSE-IBMPlexMono-OFL.txt` |
| `ShareTechMono-Regular.ttf` | Share Tech Mono | Neon (everything) | `ofl/sharetechmono/` | `LICENSE-ShareTechMono-OFL.txt` |
| `Silkscreen-Regular.ttf`, `Silkscreen-Bold.ttf` | Silkscreen | Homepage (headings) | `ofl/silkscreen/` | `LICENSE-Silkscreen-OFL.txt` |

Console (Helvetica/Arial, Courier New) and Homepage (Verdana, Courier New) use system fonts.
