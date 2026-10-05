"""Space Race kit palette: material names, box-map tile sizes (metres per texture
repeat) and emissive twins. Import-free so Blender's Python can load it."""

TILE = {
    'sr_concrete': 12.0, 'sr_scorch': 10.0, 'sr_white': 4.0, 'sr_grey': 3.0, 'sr_green': 3.0,
    'sr_red': 3.0, 'sr_stripes': 8.0, 'sr_glass': 14.4, 'sr_stucco': 14.4, 'sr_brick': 2.4,
    'sr_roof': 8.0, 'sr_asphalt': 10.0, 'sr_ground': 16.0, 'sr_metal': 2.0, 'sr_dark': 2.0,
    'sr_glow': 1.0, 'sr_corr': 2.0, 'sr_hazard': 2.0, 'sr_titanium': 6.0, 'sr_frost': 3.0,
    'sr_blue': 3.0,
}
MATS = list(TILE.keys())
# emissive twin for the _e.mtl: lit windows at night, the glow material itself, black otherwise
EMISSIVE = {'sr_glow': 'sr_glow', 'sr_glass': 'sr_glass_e', 'sr_stucco': 'sr_stucco_e'}
