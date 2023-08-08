BorderSense
===========

Software to support realtime sensors of the Borderland

# Install dependencies

    $ pipenv install

# How to ...?

## Convert power grid map to GeoJSON to be used with Grafana

* Export [actual power map](https://www.google.com/maps/d/u/0/viewer?mid=1zD_Jj58_9Lq29tYEz6X6zSc2Ag2NSP0) ("Download KML" in the menu, default options)
* Convert to GeoJSON using [this online tool](https://mygeodata.cloud/converter/kml-to-geojson)
* Unzip downloaded file to the root directory (it should create `BL_2023_power_grid` directory)
* Run `scripts/convert_power_map.py`
* Upload produced `power_areas.geojson` and `power_grid.geojson` to your web server
* Use URLs of those files in grafana Geomap panel GeoJSON layers
