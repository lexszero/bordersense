import json, requests
from shapely.geometry import shape
from .grafana import Table, TableColumn

def normalize_number(x):
    if not x:
        return 0
    elif isinstance(x, str):
        return float(x)
    else:
        return x

def camp_power_need() -> Table:
    table = Table(columns=[
        TableColumn(type='string', text='name'),
        TableColumn(type='number', text='lat'),
        TableColumn(type='number', text='lon'),
        TableColumn(type='number', text='power')
        ])

    mapentities = requests.get('https://placement.freaks.se/api/v1/mapentities').json()
    for entity in mapentities:
        if entity['isDeleted']:
            continue
        gj = json.loads(entity['geoJson'])
        props = gj['properties']
        poly = shape(gj['geometry'])
        centroid = poly.centroid
        watts = min(normalize_number(props.get('powerNeed')), 50000)/1000
        table.rows.append([
            props['name'],
            str(centroid.y),
            str(centroid.x),
            watts
            ])

    return table
