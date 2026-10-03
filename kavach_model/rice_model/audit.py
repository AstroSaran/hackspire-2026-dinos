"""Content-level source inventory: observed counts, units, coverage and lineage."""
import json

import numpy as np
import pandas as pd

from .common import RAW,PROCESSED,REPORTS,save_json,sha,utc
from .features import canonical,DISTRICTS,load_weather,climate_indices,cyclone_data


def main():
    attempts=json.loads((REPORTS/'source_manifest.json').read_text())
    inventory=[]
    def entry(name,path,**details):
        source=[a for a in attempts if a.get('path')==str(path.relative_to(RAW.parent.parent))]
        latest=source[-1] if source else {}
        inventory.append({'dataset':name,'path':str(path.relative_to(RAW.parent.parent)),
            'sha256':sha(path),'downloaded_at':latest.get('checked_at'),'url':latest.get('url'),
            'licence_as_recorded':latest.get('licence'),'independent_licence_verification':False,**details})
    apy=pd.read_csv(RAW/'apy_wb.csv');rice=apy[apy.crop_name.eq('Rice')]
    entry('APY WB imported raw snapshot',RAW/'apy_wb.csv',rows=len(apy),rice_rows=len(rice),
          first_year=rice.year.min(),last_year=rice.year.max(),raw_districts=sorted(rice.district_name.unique()),
          units={'area':rice.area_unit.unique().tolist(),'production':rice.production_unit.unique().tolist(),'reported_yield':rice.yield_unit.unique().tolist()},
          training_use='Area and production recompute t/ha labels after audited aggregation; Total excluded')
    weather=load_weather()
    observed_weather=weather.groupby('district').agg(first_date=('date','min'),last_date=('date','max'),
                    rows=('date','size'),rain_days=('rainfall_mm','count'),tmax_days=('tmax_c','count'),
                    tmin_days=('tmin_c','count'),et0_days=('et0','count'),soil_days=('soil','count'))
    observed_weather.to_csv(REPORTS/'weather_coverage_by_district.csv')
    for folder,name in [('weather','Explicit ERA5'),('power','NASA POWER')]:
        for path in sorted((RAW/folder).glob('*.json')):
            p=json.loads(path.read_text());district=path.stem.replace('_',' ')
            if folder=='power':
                data=pd.DataFrame(p['properties']['parameter'])
                dates=pd.to_datetime(data.index,format='%Y%m%d');units=p.get('parameters',{})
                invalid=int(data.eq(-999).sum().sum());standard=p.get('header',{}).get('time_standard','not supplied')
                use='Temperature only, where a complete explicit ERA5 district series is absent'
            else:
                data=pd.DataFrame(p['daily']);dates=pd.to_datetime(data.time);units=p.get('daily_units',{})
                invalid=int(data.drop(columns='time').isna().sum().sum());standard=p.get('timezone')
                use='District-series rainfall, temperature, ET0; observed columns only'
            entry(name,path,district=district,rows=len(data),first_date=str(dates.min().date()),
                  last_date=str(dates.max().date()),units=units,time_standard=standard,
                  missing_provider_values=invalid,training_use=use)
    for feature,values in climate_indices().items():
        path=RAW/('oni.txt' if feature=='oni_lag' else 'dmi.txt')
        entry(feature,path,observed_monthly_values=len(values),first_assumed_available=str(values.index.min().date()),
              last_assumed_available=str(values.index.max().date()),units='degrees C sea-surface-temperature anomaly',
              training_use='Latest finite observation whose assumed release date precedes cutoff')
    storms=cyclone_data()
    if storms is not None:
        entry('IBTrACS NI valid coordinates',RAW/'ibtracs.csv',track_rows=len(storms),storms=storms.SID.nunique(),
              first_date=str(storms.date.min()),last_date=str(storms.date.max()),units='WGS84 degrees; derived distance km',
              training_use='Observed pre-cutoff tracks within 150 km; no future tracks')
    census=RAW/'census_india-districts-census-2011.csv'
    if census.exists():
        frame=pd.read_csv(census);wb=frame[frame['State name'].str.casefold().eq('west bengal')]
        entry('Census 2011 district mirror',census,rows=len(frame),wb_rows=len(wb),year=2011,
              wb_districts=sorted(wb['District name'].map(canonical).tolist()),units='Persons/workers/households counts',
              training_use='Excluded: conservative post-2014 availability gives <60% coverage',
              parent_archive_sha256=sha(RAW/'census.zip'),licence_note='Transport archive manifest contains provisional terms; extracted CSV has no separate licence')
    if (RAW/'wfp.csv').exists():
        data=pd.read_csv(RAW/'wfp.csv',low_memory=False)
        wb=data[data.admin1.str.contains('West Bengal',case=False,na=False)]
        entry('WFP prices cross-check only',RAW/'wfp.csv',rows=len(data),wb_rows=len(wb),
              first_date=data.date.min(),last_date=data.date.max(),wb_markets=sorted(wb.market.unique().tolist()),
              units=sorted(wb.unit.unique().tolist()),training_use='Not used. No matched AGMARKNET export to perform price comparison.')
    failures=[{'source':a['source'],'status':a['status'],'url':a.get('url'),'error':a.get('error')}
              for a in attempts if a['status'] in ['FAILED','BLOCKED','SKIPPED','PORTAL_ONLY']]
    save_json(REPORTS/'data_inventory.json',{'checked_at':utc(),'datasets':inventory,'unusable_or_failed_attempts':failures,
        'notes':['Counts are parsed from downloaded content, not HTTP success alone.',
                 'Checksums establish local lineage, not authenticity or historical as-of availability.',
                 'NASA POWER may use local solar time; ERA5 requests use Asia/Kolkata civil dates. No subdaily alignment was performed.',
                 'Rainfall CHIRPS point check is in rainfall_crosscheck.json; global raster rows are not district observations.']})
    pd.DataFrame(inventory).to_csv(REPORTS/'data_inventory.csv',index=False)
    print(json.dumps({'parsed_datasets':len(inventory),'observed_weather_rows':len(weather),
                      'districts':weather.district.nunique(),'recorded_unusable_or_failed_attempts':len(failures)}))


if __name__=='__main__':main()
