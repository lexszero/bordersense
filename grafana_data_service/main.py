from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from .grafana import Query, Search
from .data_map_entities import camp_power_need
from .data_weather import weather

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

targets = {
        'camp_power_need': camp_power_need,
        'weather': weather
        }

@app.get("/")
def read_root():
    return {}

@app.post("/search")
def grafana_search(search: Search):
    return list(targets.keys())

@app.post("/query")
def grafana_query(query: Query):
    print(query)
    response = []
    for target in query.targets:
        if target.target in targets:
            response.append(targets[target.target](target, query.range))
    return response

@app.post("/annotations")
def grafana_annotations():
    pass
