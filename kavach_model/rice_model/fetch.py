"""Bounded real-source downloads; exact attempts and snapshot checksums are logged."""
import argparse
import gzip
import io
import json
import shutil
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

from .common import RAW, REPORTS, setup, sha, save_json, utc

MANIFEST = REPORTS / 'source_manifest.json'
LOCK = threading.Lock()
ATTEMPTS = []


def record(**entry):
    with LOCK:
        ATTEMPTS.append({'checked_at': utc(), **entry})
        save_json(MANIFEST, ATTEMPTS)
    print(entry.get('source'), entry.get('status'), entry.get('error', ''), flush=True)


def download(name, url, filename, licence, params=None, kind='data', max_bytes=90_000_000):
    start = time.monotonic()
    path = RAW / filename
    try:
        with requests.get(url, params=params, timeout=(10, 60), stream=True,
                          headers={'User-Agent': 'KavachRiceResearch/1.0'}) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > max_bytes or time.monotonic()-start > 150:
                    raise ValueError('Download exceeded size or wall-time budget')
            if kind == 'data' and ('text/html' in response.headers.get('Content-Type', '')
                                   or bytes(content[:100]).lstrip().lower().startswith((b'<!doctype', b'<html'))):
                raise ValueError('HTTP 200 returned HTML rather than the requested dataset')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            record(source=name, url=response.url, status='FETCHED' if kind=='data' else 'PORTAL_ONLY',
                   http_status=response.status_code, bytes=len(content), licence=licence,
                   path=str(path.relative_to(RAW.parent.parent)), sha256=sha(path),
                   seconds=round(time.monotonic()-start, 3))
            return path
    except Exception as exc:
        record(source=name, url=requests.Request('GET', url, params=params).prepare().url,
               status='FAILED', licence=licence, error=f'{type(exc).__name__}: {exc}',
               http_status=getattr(getattr(exc,'response',None),'status_code',None),
               seconds=round(time.monotonic()-start, 3))
        return None


def import_snapshots(root):
    report = json.loads((root/'rice_yield_experiment/training_report.json').read_text())
    apy = root/'kaggle_raw/crop_production/crop-wise-area-production-yield.csv'
    expected = report['source_checksums_sha256']['apy_csv']
    if sha(apy) != expected:
        raise ValueError('Existing APY snapshot checksum mismatch')
    # Retain only real WB rows, not prior features, labels, model or metrics.
    df = pd.read_csv(apy, low_memory=False)
    wb = df[df.state_name.str.casefold().eq('west bengal')]
    wb.to_csv(RAW/'apy_wb.csv', index=False)
    record(source='APY verified local snapshot', url='https://indiadataportal.com/', status='REUSED_SNAPSHOT',
           licence='Original ministry data: GODL-India; IDP snapshot redistribution terms require verification',
           upstream_sha256=expected, sha256=sha(RAW/'apy_wb.csv'), rows=len(wb),
           years=sorted(wb.year.unique().tolist()), wb_districts=sorted(wb.district_name.unique().tolist()),
           path='data/raw/apy_wb.csv', original_release_timestamp='not supplied')
    parts=[]
    for filename, expected in report['source_checksums_sha256']['weather_chunks'].items():
        p=root/'rice_yield_experiment/weather_chunks'/filename
        if sha(p) != expected:
            raise ValueError(f'Weather snapshot checksum mismatch: {filename}')
        parts.append(pd.read_csv(p))
    weather=pd.concat(parts, ignore_index=True)
    weather=weather[weather.district.ne('Kolkata')].drop_duplicates(['district','date'])
    weather.to_csv(RAW/'weather_existing.csv.gz', index=False, compression='gzip')
    points=weather[['district','latitude','longitude']].drop_duplicates('district')
    points.to_csv(RAW/'centroids.csv',index=False)
    record(source='Open-Meteo verified local snapshot',url='https://archive-api.open-meteo.com/v1/archive',
           status='REUSED_SNAPSHOT', licence='CC BY 4.0; Open-Meteo / underlying ERA5 attribution',
           rows=len(weather),years=[weather.date.min(),weather.date.max()],wb_districts=points.district.tolist(),
           path='data/raw/weather_existing.csv.gz',sha256=sha(RAW/'weather_existing.csv.gz'),
           note='Original request omitted models=era5; log as archive best-match, not guaranteed exclusively ERA5.')


def weather_download():
    points=pd.read_csv(RAW/'centroids.csv')
    variables='precipitation_sum,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration'
    # Single-location bounded requests are easier to resume and audit.
    for row in points.itertuples():
        filename=f'weather/{row.district.replace(" ","_")}.json'
        if (RAW/filename).exists():
            continue
        result=download('Open-Meteo ERA5 '+row.district,'https://archive-api.open-meteo.com/v1/archive',filename,
                 'CC BY 4.0', params={'latitude':round(row.latitude,4),'longitude':round(row.longitude,4),
                 'start_date':'1997-01-01','end_date':'2025-12-31','daily':variables,'timezone':'Asia/Kolkata',
                  'models':'era5'})
        if result is None and any(a.get('http_status')==429 for a in ATTEMPTS[-2:]):
            record(source='Open-Meteo remaining weather/soil',status='BLOCKED',error='Rate limit: stopping this provider; resume in a later quota window.')
            return
        time.sleep(.3)
    # ERA5-Land daily soil mean queried separately to keep spatial/temporal provenance.
    for row in points.itertuples():
        filename=f'soil/{row.district.replace(" ","_")}.json'
        if (RAW/filename).exists():
            continue
        result=download('ERA5-Land soil '+row.district,'https://archive-api.open-meteo.com/v1/archive',filename,
                 'CC BY 4.0',params={'latitude':round(row.latitude,4),'longitude':round(row.longitude,4),
                 'start_date':'1997-01-01','end_date':'2025-12-31','daily':'soil_moisture_0_to_7cm_mean',
                  'timezone':'Asia/Kolkata','models':'era5_land'})
        if result is None and any(a.get('http_status')==429 for a in ATTEMPTS[-2:]):
            record(source='ERA5-Land remaining soil',status='BLOCKED',error='Rate limit: stopping this provider; resume in a later quota window.')
            return
        time.sleep(.3)


def cross_checks():
    points=pd.read_csv(RAW/'centroids.csv'); p=points[points.district.eq('South 24 Parganas')].iloc[0]
    download('NASA POWER cross-check','https://power.larc.nasa.gov/api/temporal/daily/point','power.json',
             'NASA open data, attribution requested', params={'parameters':'PRECTOTCORR,T2M_MAX,T2M_MIN',
             'community':'AG','longitude':p.longitude,'latitude':p.latitude,'start':'20200101','end':'20201231','format':'JSON'})
    tif=download('CHIRPS rainfall cross-check',
        'https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/chirps-v2.0.2020.06.tif.gz',
        'chirps_2020_06.tif.gz','CHC: public domain / attribution requested',max_bytes=40_000_000)
    if tif:
        try:
            import rasterio
            from rasterio.io import MemoryFile
            with MemoryFile(gzip.decompress(tif.read_bytes())) as memory:
                with memory.open() as dataset:
                    value=float(next(dataset.sample([(p.longitude,p.latitude)]))[0])
            weather=pd.read_csv(RAW/'weather_existing.csv.gz')
            x=weather[weather.district.eq(p.district)&weather.date.str.startswith('2020-06')]
            save_json(REPORTS/'rainfall_crosscheck.json',{'district':p.district,'month':'2020-06',
                       'chirps_mm':value,'archive_snapshot_mm':x.rainfall_mm.sum(min_count=30),
                       'days':len(x),'method':'One centroid, one month; not bias correction or statewide validation.'})
        except Exception as exc:
            record(source='CHIRPS extraction',status='FAILED',error=f'{type(exc).__name__}: {exc}')


def probes():
    sources=[
        ('APY IDP dataset','https://data.indiadataportal.com/dataset/crop-wise-area-production-yield','apy_portal.html','IDP terms / GODL-India','portal'),
        ('APY ministry calendar','https://data.desagri.gov.in/website/crops-apy-report-web','apy_ministry.html','Government of India','portal'),
        ('IDP documentation','https://docs.indiadataportal.com/','idp_docs.html','IDP terms','portal'),
        ('ONI','https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt','oni.txt','US NOAA public domain','data'),
        ('DMI','https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data','dmi.txt','NOAA distribution; underlying HadISST attribution','data'),
        ('IBTrACS NI','https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.NI.list.v04r01.csv','ibtracs.csv','NOAA public domain; cite IBTrACS v4r01','data'),
        ('CEDA Agri-Market','https://agmarknet.ceda.ashoka.edu.in/','ceda.html','CEDA source-specific terms; not verified','portal'),
        ('IDP AGMARKNET','https://indiadataportal.com/p/agmarknet','idp_market.html','IDP terms / GODL-India','portal'),
        ('CGWB','https://cgwb.gov.in/en/ground-water-level-monitoring','cgwb.html','Government data; export licence not verified','portal'),
        ('India-WRIS','https://indiawris.gov.in/wris/','wris.html','Government data; export licence not verified','portal'),
        ('Census PCA','https://censusindia.gov.in/nada/index.php/catalog/40699','census.html','Census India; licence to be verified','portal'),
        ('MGNREGA','https://nrega.nic.in/','mgnrega.html','Government data; export licence not verified','portal'),
        ('MODIS AppEEARS','https://appeears.earthdatacloud.nasa.gov/api/product','appeears.json','NASA LP DAAC free data; Earthdata login required for extraction','data'),
        ('WFP India metadata','https://data.humdata.org/api/3/action/package_show?id=wfp-food-prices-for-india','wfp_metadata.json','WFP/HDX CC BY IGO; cross-check only','data'),
        ('Rice calendar','https://riceknowledgebank.irri.org/step-by-step-production/pre-planting/crop-calendar','rice_calendar.html','IRRI reference, not training data','portal'),
    ]
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda args: download(*args[:4],kind=args[4]),sources))
    # Public Census mirror is a transport option, not an invented PCA substitute.
    p=download('Census Kaggle mirror','https://www.kaggle.com/api/v1/datasets/download/danofer/india-census',
               'census.zip','Kaggle card licence must be checked; original Census India')
    if p:
        try:
            with zipfile.ZipFile(p) as archive:
                for name in archive.namelist():
                    if name.lower().endswith('.csv'):
                        (RAW/('census_'+Path(name).name)).write_bytes(archive.read(name))
        except Exception as exc:
            record(source='Census zip parse',status='FAILED',error=repr(exc))
    if (RAW/'wfp_metadata.json').exists():
        try:
            info=json.loads((RAW/'wfp_metadata.json').read_text())['result']
            for r in info['resources']:
                if 'wfp_food_prices_ind.csv' in r.get('url',''):
                    download('WFP India retail prices',r['url'],'wfp.csv',info.get('license_title','not supplied'))
                    break
        except Exception as exc:
            record(source='WFP export discovery',status='FAILED',error=repr(exc))
    record(source='MODIS NDVI/EVI extraction',status='SKIPPED',
           error='No Earthdata login/token supplied; product catalogue is not district NDVI/EVI data.')
    for source in ['CEDA/AGMARKNET export','CGWB district export','MGNREGA district-month export']:
        record(source=source,status='BLOCKED',error='No authenticated or documented downloadable district-period export discovered; no HTML used as training data.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--import-snapshots',type=Path)
    parser.add_argument('--probes-only',action='store_true')
    args=parser.parse_args(); setup()
    if MANIFEST.exists():
        ATTEMPTS.extend(json.loads(MANIFEST.read_text()))
    if args.import_snapshots:
        import_snapshots(args.import_snapshots)
    probes()
    if not args.probes_only:
        with ThreadPoolExecutor(max_workers=2) as executor:
            jobs=[executor.submit(weather_download),executor.submit(cross_checks)]
            for job in jobs:
                job.result()


if __name__=='__main__':
    main()
