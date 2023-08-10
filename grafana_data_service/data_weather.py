import pandas as pd
import logging

from functools import cache
from .grafana import Target, Range, Timeserie

CSV_URL = 'https://opendata-download.smhi.se/stream?type=metobs&parameterIds=1&stationId=74300&period=latest-months'

log = logging.getLogger(__name__)

def _weather_data() -> pd.DataFrame:
    log.info("Fetching weather data")
    data = pd.read_csv(CSV_URL,
            delimiter=';',
            skiprows=9,
            parse_dates=[[0,1]],
            usecols=[0, 1, 2],
            index_col=0).tz_localize('Europe/Stockholm')
    data = data.rename(columns={
        'Datum_Tid (UTC)': 'time',
        'Lufttemperatur': 'temperature'})
    #data['time'] = pd.to_datetime(data['time']).tz_convert('Europe/Stockholm')
    return data

def weather(target: Target, timerange: Range) -> Timeserie:
    data = _weather_data()
    q = ((data.index >= pd.to_datetime(timerange.start)) &
         (data.index <= pd.to_datetime(timerange.end)))
    r = data.loc[q].to_dict('series')['temperature']
    points = [(v, t) for (t, v) in r.items()]
    #r = data[['temperature', 'time']]
    #r['time'] = (r['time'].astype('int64')/1000).astype('int64')

    return Timeserie(target=target.target, datapoints=points)


