+++
title = "Borderland 2023 Power report"
date = "2023-08-09"
author = "LexsZero"
+++

# Overview


This year's electric power were supplied primarily from the Swedish electrical grid
by means of 200kVA transformer installed in Alversjö about month before the event.
Diesel generators were used in areas too remote to be efficiently covered by the main
grid (Muumimaa and Hidden Meadow), and as a backup source for Sanctuary.

Also, this year we had deployed experimental sensor network for realtime monitoring
of the power grid and work vehicles. It proved to be extremely useful in
troubleshooting and fault prevention, as well as time-saving during build and
strike when locating the vehicles.


# The Grid

This year the grid consisted of at least **6,186m of cable** (probably more, as
some smaller ad-hoc 16A lines remained uncharted, and individual cables chunks round
the lines length up - it could be over **seven kilometers!**), of which
125A - 490m, 63A - 1,607m, 32A - 2,818m, 16A - 985m, single-phase: 286m

There are a total of at least **87 PDUs**: 125A - 2pcs, 63A - 20pcs, 32A - 44pcs, 16A - 21pcs.

## Grid layout & power needs

Legend: Stars mark centers of camps, size and color depend on announced power
need.
The power grid consists of PDUs (circles) and cables (lines). Color depends on
capacity of the line/PDU (more red == more thicc).

{{< grafana_plot
  url="https://bl.skookum.cc/grafana/d-solo/a86f2d75-5d63-45dc-990f-f1eee27aef38/power-grid?orgId=1&from=1691588654969&to=1691610254969&panelId=2"
  height=1000
  >}}


# Power grid monitoring insights

## Power zones legend

* North Field: Highlands NorthWest and NorthEast, all Slices (Top, Center and Broken),
    Dee, Farflung Fringe, Silence Peak
* South Field: Highlands South, Aaah, Bee, See
* SouthEast: The Garden, The What?, Downtown, The Look and The Nookout
* Barn & Hill: most of The Hill of the Lake and couple of camps around the barn (The Church
    and Ice Castle)
* Grove: Grove of the Green and southeastern part of The Hill

_Unaccounted_: The Villa, Muumimaa, The Triangle Of (Threshold and The Port),
    Hidden Meadow - either running on generators or low load.

## Total energy consumption by zones

* North Field: **5,515 kWh**
* South Field: **4,252 kWh**
* SouthEast: **2,012 kWh**
* Barn & Hill + Grove: **1,579 kWh**

**Total: 13,358 kWh**

## Cool graphs

_Hover over the graphs to see measurements at specific time, blue ticks are
comments about specific events, hover over little triangle mark at the bottom.
Click and drag to select time period to zoom in, click "Explore" to open the
plot on a separate page_

### Power usage during the event

As the power sensors were gradually deployed and moved around, the data we have
is not covering all areas at all times, but we captured the end of the week in
full glory of our **peak power usage** at about **150 kW**.

{{<grafana_plot url="https://bl.skookum.cc/grafana/d-solo/a86d109c-8e52-47d5-9ef9-a025875ee923/power-report-graphs?orgId=1&var-aggregate_fn=max&var-aggregate_period=5m&var-extra_metrics=Abuze&from=1690146000000&to=1690750799000&panelId=1">}}

[Explore](https://bl.skookum.cc/grafana/d/a86d109c-8e52-47d5-9ef9-a025875ee923/power-report-graphs?orgId=1&var-aggregate_fn=max&var-aggregate_period=5m&var-extra_metrics=Abuze&from=1690146000000&to=1690750799000&viewPanel=1)

### Load per zone

{{<grafana_plot url="https://bl.skookum.cc/grafana/d/bd4b25e9-a7b5-4f48-91c1-68c98f5854bb/power-per-zone?orgId=1&var-extra_metrics=None&from=1690146000000&to=1690750799000&kiosk" height=1000 >}}

[Explore](https://bl.skookum.cc/grafana/d/bd4b25e9-a7b5-4f48-91c1-68c98f5854bb/power-per-zone?orgId=1&from=1690146000000&to=1690750799000)

### Phase load disbalance

3-phase power distribution systems work most efficiently when the load is
evenly distributed on all three phases. In our case, this was not true,
especially in sparsely populated areas. People tend to plug their
single-phase cable drums to the first socket on the PDU, which results in
higher load on phase 1 wire, while the other two phases stay underused. We had to
invent a special Abuze metric and encourage people to use sockets other than the
first one. Here's the worst area by this parameter:

{{<grafana_plot url="https://bl.skookum.cc/grafana/d-solo/bd4b25e9-a7b5-4f48-91c1-68c98f5854bb/power-per-zone?orgId=1&from=1690146000000&to=1690750799000&var-aggregate_fn=max&var-aggregate_period=5m&panelId=3">}}

_TODO: to be continued: maps, vehicle trackers, pics of trench-digging with champagne, yada yada..._
