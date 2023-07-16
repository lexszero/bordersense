#!/usr/bin/env python3
import geojson
import itertools

power_areas = [
        'NORTH',
        'SOUTH',
        'Barn_and_the_hill'
        ]

def load_geojson(name, rename=None, style=None):
    j: geojson.FeatureCollection = geojson.load(open(f"BL_2023_power_grid_offline/{name}.geojson"))

    if style:
        j.style = style
    for feature in j.features:
        feature.properties = {k: v for k, v in feature.properties.items() if v is not None}
        if rename:
            feature.properties[rename] = feature.properties['Name']
            del(feature.properties['Name'])

    del(j.crs)

    return j

def gen_layer(name, items, style={}, **kwargs):
    geo = {
            'type': 'FeatureCollection',
            'crs': { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" } },
            'features': list(itertools.chain(*[x.features for x in items])),
            'style': style
            }
    objname = '__Layer_'+name
    m = {'overlay': name, 'geojson': geo, 'fit': True}
    return {
            'command': {
                'map': m,
                'lat': 57.621546,
                'lon': 14.926020
                }
            }

style = {
        "stroke-width": "16",
        "stroke": "#ff00ff",
        "fill-color": "#808080",
        "fill-opacity": 0.2
        }

layer_basemap = gen_layer('Areas',
        [
            load_geojson('Sections_2023', rename='Area'),
            load_geojson('Roads', rename='Road')
        ],
        style=style,
        clickable=False
        )

layer_power = gen_layer('Power',
        map(load_geojson, ['NORTH', 'SOUTH', 'Barn_and_the_hill']))

print(geojson.dumps([layer_basemap, layer_power]))
