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
comments about specific events, hover over little triangle mark at the bottom_

### Power usage during the event

As the power sensors were gradually deployed and moved around, the data we have
is not covering all areas at all times, but we captured the end of the week in
full glory of our **peak power usage** at about **150 kW**.

{{< grafana_plot "https://bl.skookum.cc/grafana/d-solo/a86d109c-8e52-47d5-9ef9-a025875ee923/power?orgId=1&var-aggregate_fn=max&from=1690146000000&to=1690750799000&panelId=1" >}}

### Phase load disbalance

3-phase power distribution systems work most efficiently when the load is
evenly distributed on all three phases. In our case, this was not true,
especially in sparsely populated areas. People tend to plug their
single-phase cable drums to the first socket on the PDU, which results in
higher load on phase 1 wire, while the other two phases stay underused. We had to
invent a special Abuze metric and encourage people to use sockets other than the
first one. Here's the worst area by this parameter:

{{< grafana_plot "https://bl.skookum.cc/grafana/d-solo/a86d109c-8e52-47d5-9ef9-a025875ee923/power?orgId=1&var-aggregate_fn=max&from=1690059600000&to=1690750799000&panelId=2" >}}

_TODO: to be continued: maps, vehicle trackers, pics of trench-digging with champagne, yada yada..._
