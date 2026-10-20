# Background music

This folder holds the background-music tracks offered in the web UI and CLI
(`--bgm-name <file.mp3>`).

## Bundled royalty-free tracks

Three ambient tracks are generated from scratch by
[`scripts/generate_music.py`](../../scripts/generate_music.py) and ship with the
project. They are **synthesized** (simple chord pads), so they carry **no
licensing restrictions** — use them freely in your videos:

- `ambient_calm.mp3`
- `uplifting_pad.mp3`
- `lofi_mellow.mp3`

Regenerate them any time with:

```bash
python scripts/generate_music.py
```

## Adding your own

Drop additional royalty-free `.mp3` files in this folder and they appear
automatically. Make sure anything you add is licensed for your intended use
(e.g. from the YouTube Audio Library, Pixabay Music, or Free Music Archive).
