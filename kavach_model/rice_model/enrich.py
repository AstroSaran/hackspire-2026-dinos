"""Complement archive snapshots with a second weather source and verified geography."""
import json
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .common import RAW, REPORTS, setup, save_json
from .fetch import download, ATTEMPTS, MANIFEST, record
from .features import canonical


def power(row):
    path=RAW/'power'/f'{row.district.replace(" ","_")}.json'
    if path.exists():return
    download('NASA POWER daily '+row.district,'https://power.larc.nasa.gov/api/temporal/daily/point',
             str(path.relative_to(RAW)), 'NASA open data; MERRA-2 meteorology attribution',
             params={'parameters':'PRECTOTCORR,T2M_MAX,T2M_MIN','community':'AG',
                     'longitude':row.longitude,'latitude':row.latitude,'start':'19970101','end':'20251231','format':'JSON'})


def main():
    setup();ATTEMPTS.extend(json.loads(MANIFEST.read_text()))
    points=pd.read_csv(RAW/'centroids.csv')
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(power,points.itertuples()))
    boundary=download('Official WB district boundaries',
        'https://mapservice.gov.in/gismapservice/rest/services/BharatMapService/Admin_Boundary_District/MapServer/1/query',
        'boundaries.json','Government of India GIS service; redistribution licence not supplied',
        params={'where':"stname='West Bengal'",'outFields':'dtname,stname,dtcode11,year_stat','returnGeometry':'true','outSR':4326,'f':'json'})
    if boundary:
        try:
            from shapely.geometry import Polygon
            from shapely.ops import unary_union
            payload=json.loads(boundary.read_text());districts={}
            for feature in payload['features']:
                name=canonical(feature['attributes']['dtname'])
                polygons=[Polygon(r).buffer(0) for r in feature['geometry']['rings'] if len(r)>=4]
                districts.setdefault(name,[]).extend(polygons)
            shapes={d:unary_union(p) for d,p in districts.items()}
            # Tiny tolerance addresses vector boundary precision, not distance-neighbour fabrication.
            adjacent={d:[n for n,p in shapes.items() if n!=d and shape.distance(p)<1e-6]
                      for d,shape in shapes.items() if d!='Kolkata'}
            save_json(RAW/'adjacency.json',adjacent)
            record(source='WB adjacency extraction',status='DERIVED',rows=len(adjacent),
                   note='Polygon boundary touching at 1e-6 degrees tolerance; harmonised district unions.')
        except Exception as exc:record(source='WB adjacency extraction',status='FAILED',error=repr(exc))


if __name__=='__main__':main()
