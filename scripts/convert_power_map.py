#!/usr/bin/env python3
import logging, coloredlogs
import geojson
import itertools
import re

log = logging.getLogger('convert_map')
coloredlogs.install(
        fmt="%(name)s %(levelname)s: %(message)s",
        level=logging.DEBUG
        )


power_areas = [
        'NORTH',
        'SOUTH',
        'Barn_and_the_hill'
        ]

def load_geojson(name, rename=None, style=None):
    j: geojson.FeatureCollection = geojson.load(open(f"BL_2023_power_grid/{name}.geojson"))

    if style:
        j.style = style
    for feature in j.features:
        feature.properties = {k: v for k, v in feature.properties.items() if v is not None}
        if rename:
            #feature.properties[rename] = feature.properties['Name']
            feature['id'] = feature.properties['Name']
            del(feature.properties['Name'])
    del(j.crs)

    return j

def flatten(l):
    return [item for sublist in l for item in sublist]

def update_areas(j):
    result = []
    for feature in j['features']:
        log.debug(f'Area: {feature}')
        name = feature.properties.get('Name')
        desc = feature.properties.get('description')
        if ((name == '1.2ha') or
            (desc and ('1ha' in desc))):
            log.debug(f"skip {name} / {desc}")
            continue
        result.append(feature)
    return geojson.FeatureCollection(result)


def update_power_properties(j):
    result = []
    for feature in j['features']:
        log.debug(f'Power: {feature}')
        name = feature.properties['Name']
        desc = feature.properties.get('description')
        if ((name == '1.2ha') or
            (desc and ('1ha' in desc))):
            log.debug(f"skip {name} / {desc}")
            continue
        if feature.geometry.type == 'Point':
            m = re.match(r'^(\d+)\s?A?', feature.properties['Name'])
            if m:
                amps = m.groups(1)[0]
                if int(amps) == 64:
                    amps = 63
                log.info(f'PDU: {amps}')
                feature.properties['power_size'] = amps
        if feature.geometry.type == 'LineString':
            m = re.match(r'(\d+)\s*A?', name)
            if not m:
                m = re.match(r'(\d+)\s*A?', feature.properties.get('description', ''))
            if m:
                amps = m.groups(1)[0]
                if amps == '64':
                    amps = 63
                log.info(f'Line {name}: {amps}')
                feature.properties['power_size'] = amps
            elif name == 'Garden Line':
                feature.properties['power_size'] = 63
            else:
                feature.properties['power_size'] = 'unknown'
        result.append(feature)
    return geojson.FeatureCollection(result)


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

basemap_areas = {
        'type': 'FeatureCollection',
        'features': flatten([x.features for x in [
            load_geojson('areas', rename='Area'),
            load_geojson('Roads', rename='Road')
    ]])}
basemap_areas = update_areas(basemap_areas)

basemap_power = {
        'type': 'FeatureCollection',
        'features': flatten([x.features for x in [load_geojson(part) for part in power_areas]])
        }
basemap_power = update_power_properties(basemap_power)
#layer_power = gen_layer('Power',
#        map(load_geojson, ['NORTH', 'SOUTH', 'Barn_and_the_hill']))

geojson.dump(basemap_areas, open('power_areas.geojson', 'w'), indent=2)
geojson.dump(basemap_power, open('power_grid.geojson', 'w'), indent=2)
