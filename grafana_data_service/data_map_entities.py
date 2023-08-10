import json, requests
from shapely.geometry import shape
from .grafana import Table, TableColumn, Target, Range

def normalize_number(x):
    if not x:
        return 0
    elif isinstance(x, str):
        return float(x)
    else:
        return x

def camp_power_need(target: Target, timerange: Range) -> Table:
    table = Table(columns=[
        TableColumn(type='string', text='name'),
        TableColumn(type='number', text='lat'),
        TableColumn(type='number', text='lon'),
        TableColumn(type='number', text='power'),
        TableColumn(type='string', text='powerLabel')
        ])

    mapentities = requests.get('https://placement.freaks.se/api/v1/mapentities').json()
    for entity in mapentities:
        if entity['isDeleted']:
            continue
        gj = json.loads(entity['geoJson'])
        props = gj['properties']
        poly = shape(gj['geometry'])
        centroid = poly.centroid
        pwr = min(normalize_number(props.get('powerNeed')), 50000)/1000
        pwrLabel = None
        if pwr > 0.05:
            if abs(round(pwr) - pwr) < 0.1:
                pwrLabel= f'{pwr:.0f}'
            else:
                pwrLabel = f'{pwr:.1f}'
        table.rows.append([
            props['name'],
            str(centroid.y),
            str(centroid.x),
            pwr,
            pwrLabel
            ])

    return table
