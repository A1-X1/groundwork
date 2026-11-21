# Globe textures

- `earth-blue-marble-2k.jpg`: NASA Visible Earth "Blue Marble" composite. Public domain (NASA imagery
  is not copyrighted). Downscaled to 2048×1024 from the copy shipped in the `three-globe` npm package
  (`example/img/earth-blue-marble.jpg`).
- `earth-blue-marble-4k.jpg`: the same image at full 4096×2048, loaded only when the globe zooms
  in towards country level (level of detail).
- `earth-bump-1k.png`: topography height map from the same package (NASA-derived, public domain),
  downscaled to 1024×512. Used as a subtle bump map.

Bundled so the globe works offline. NASA GIBS WMTS can replace them for higher zoom.
