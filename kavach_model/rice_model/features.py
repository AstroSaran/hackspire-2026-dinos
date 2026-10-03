"""Cutoff-safe feature engineering. No filling/interpolation/synthetic training rows."""
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import gamma, norm, fisk

from .common import RAW, PROCESSED, REPORTS, setup, save_json, sha

ALIASES={'Alipurduar':'Jalpaiguri','Kalimpong':'Darjeeling','Jhargram':'Paschim Medinipur',
         'Paschim Bardhaman':'Bardhaman','Purba Bardhaman':'Bardhaman',
         'Burdwan':'Bardhaman','Burdwan (Bardhaman)':'Bardhaman', 'Hugli':'Hooghly',
         'Haora':'Howrah','Puruliya':'Purulia','Koch Bihar':'Cooch Behar', 'Maldah':'Malda',
         'Darjiling':'Darjeeling','North Twenty Four Parganas':'North 24 Parganas',
         'South Twenty Four Parganas':'South 24 Parganas'}
DISTRICTS=['Bankura','Bardhaman','Birbhum','Cooch Behar','Dakshin Dinajpur','Darjeeling',
           'Hooghly','Howrah','Jalpaiguri','Malda','Murshidabad','Nadia','North 24 Parganas',
           'Paschim Medinipur','Purba Medinipur','Purulia','South 24 Parganas','Uttar Dinajpur']
SEASONS=['Autumn','Winter','Summer']
GROUPS={
 'weather':['rain_total','rain_z','dry_spell','heavy_days','extreme_days','hot35','hot38',
            'gdd10','diurnal_range','et0_total','water_balance','spi1','spi3','spi6',
            'spei1','spei3','spei6','onset_delay','onset_seen'],
 'soil':['soil_mean','soil_anomaly'], 'vegetation':['ndvi_anomaly','evi_anomaly'],
 'climate':['oni_lag','dmi_lag'], 'cyclone':['cyclone_150km','cyclone_days'],
 'market':['price_deviation','price_volatility','arrivals'], 'water':['groundwater_change'],
 'vulnerability':['agri_labourer_share','cultivator_share','literacy_share','irrigation_share'],
 'employment':['households_demanded'],
    'memory_spatial':['previous_shortfall','yield_trend','previous_residual','area_change','neighbour_anomaly']}


def canonical(name):
    text=' '.join(str(name).strip().split())
    for candidate in DISTRICTS+list(ALIASES):
        if text.casefold()==candidate.casefold():
            return ALIASES.get(candidate,candidate)
    return text


def window(year, season):
    """APY July–June crop-year: Summer/boro harvested in its ENDING year."""
    if season=='Autumn':
        start,cut,harvest=f'{year}-04-01',f'{year}-06-30',f'{year}-09-30'
    elif season=='Winter':
        start,cut,harvest=f'{year}-06-01',f'{year}-07-31',f'{year}-12-15'
    elif season=='Summer':
        start,cut,harvest=f'{year}-12-01',f'{year+1}-03-15',f'{year+1}-05-31'
    else:
        raise ValueError(f'Unknown rice season: {season}')
    return tuple(pd.Timestamp(v) for v in (start,cut,harvest))


def labels(values, years):
    lookup=dict(zip(years,values)); output=[]
    for year,value in zip(years,values):
        prior=[lookup.get(y,np.nan) for y in range(year-5,year)]
        baseline=float(np.mean(prior)) if np.isfinite(prior).all() else np.nan
        if not np.isfinite(baseline) or baseline<=0:
            baseline=np.nan
        hist=[(y,v) for y,v in lookup.items() if y<year and np.isfinite(v)]
        trend=np.polyval(np.polyfit([x[0] for x in hist],[x[1] for x in hist],1),year) if len(hist)>=5 else np.nan
        row={'baseline':baseline,'anomaly':value-baseline,'anomaly_pct':100*(value/baseline-1),
             'detrended_anomaly':value-trend,'detrended_pct':100*(value/trend-1) if trend>0 else np.nan}
        for threshold in (10,15,20):
            row[f'label{threshold}']=float(value<(1-threshold/100)*baseline) if np.isfinite(baseline) else np.nan
        output.append(row)
    return pd.DataFrame(output)


def load_apy():
    raw=pd.read_csv(RAW/'apy_wb.csv'); raw['source_row']=raw.index
    rows=raw[raw.crop_name.str.casefold().eq('rice') & raw.state_name.str.casefold().eq('west bengal')].copy()
    rows['district']=rows.district_name.map(canonical)
    rows['crop_year']=rows.year.astype(str).str[:4].astype(int)
    rows['reason']=''
    def mark(mask,reason):
        rows.loc[mask & rows.reason.eq(''),'reason']=reason
    mark(~rows.season.isin(SEASONS),'non-season/Total excluded to avoid double counting')
    mark(~rows.district.isin(DISTRICTS),'outside 2011 district domain / Kolkata excluded')
    mark(~rows.crop_year.between(1997,2023),'outside requested APY years')
    for col in ['area','production','yield']:
        rows[col]=pd.to_numeric(rows[col],errors='coerce')
    mark(rows.area_unit.ne('Hectare')|rows.production_unit.ne('Tonnes'),'unexpected units')
    mark(~np.isfinite(rows.area)|~np.isfinite(rows.production)|(rows.area<=0)|(rows.production<0),'invalid area/production')
    calculated=rows.production/rows.area
    mark(~calculated.between(0,15),'implausible rice yield outside 0–15 t/ha (audit rule)')
    # No dropping low genuine yields merely because they are adverse outcomes.
    # Determine expected split components from the source's district/year domain,
    # across all seasons. Missing child seasons are unknown, not zero production.
    expected=rows.groupby(['district','crop_year']).district_name.agg(set).to_dict()
    valid=rows[rows.reason.eq('')]
    incomplete=[]
    for (district,year,season),group in valid.groupby(['district','crop_year','season']):
        if set(group.district_name)!=expected[(district,year)]:
            incomplete.extend(group.index)
    mark(rows.index.isin(incomplete),'incomplete split-district components; absent child is not zero')
    rows[rows.reason.ne('')].to_csv(REPORTS/'apy_drop_audit.csv',index=False)
    rows=rows[rows.reason.eq('')]
    if rows.duplicated(['district_name','crop_year','season']).any():
        raise ValueError('Duplicate original district/year/season source rows; review rather than average.')
    panel=rows.groupby(['district','crop_year','season'],as_index=False).agg(
        area=('area','sum'),production=('production','sum'),source_rows=('source_row','size'))
    panel['yield_t_ha']=panel.production/panel.area
    parts=[]
    for (district,season),series in panel.groupby(['district','season']):
        series=series.sort_values('crop_year').reset_index(drop=True)
        parts.append(pd.concat([series,labels(series.yield_t_ha,series.crop_year)],axis=1))
    panel=pd.concat(parts,ignore_index=True)
    # Preserve APY baseline solely for labels; it is not automatically a predictor.
    panel['cutoff']=[window(y,s)[1].date().isoformat() for y,s in zip(panel.crop_year,panel.season)]
    panel['harvest']=[window(y,s)[2].date().isoformat() for y,s in zip(panel.crop_year,panel.season)]
    # Conservative historical availability policy. Actual APY vintage dates are unavailable.
    panel['label_available_at']=[(pd.Timestamp(h)+pd.DateOffset(months=12)).date().isoformat() for h in panel.harvest]
    panel.to_csv(PROCESSED/'apy_clean.csv',index=False)
    return panel


def load_weather():
    existing=pd.read_csv(RAW/'weather_existing.csv.gz',parse_dates=['date'])
    frames=[]; source_rows=[]
    for district,old in existing.groupby('district'):
        path=RAW/'weather'/f'{district.replace(" ","_")}.json'
        if path.exists():
            payload=json.loads(path.read_text()); daily=payload.get('daily',{})
            if daily.get('time'):
                frame=pd.DataFrame(daily).rename(columns={'time':'date','precipitation_sum':'rainfall_mm',
                     'temperature_2m_max':'tmax_c','temperature_2m_min':'tmin_c','et0_fao_evapotranspiration':'et0'})
                frame['date']=pd.to_datetime(frame.date);frame['district']=district
                frames.append(frame)
                source_rows.append({'district':district,'source':'Open-Meteo explicitly ERA5','rows':len(frame),'sha256':sha(path)})
                continue
        power=RAW/'power'/f'{district.replace(" ","_")}.json'
        if power.exists():
            payload=json.loads(power.read_text())['properties']['parameter']
            extra=pd.DataFrame(payload).rename_axis('date').reset_index()
            extra['date']=pd.to_datetime(extra.date,format='%Y%m%d')
            # Use complete NASA temperature series for this district; don't fill individual gaps.
            old=old.drop(columns=['tmax_c']).merge(extra[['date','T2M_MAX','T2M_MIN']].rename(
                columns={'T2M_MAX':'tmax_c','T2M_MIN':'tmin_c'}),on='date',how='left',validate='one_to_one')
            source_rows.append({'district':district,'temperature_source':'NASA POWER MERRA-2',
                                'sha256':sha(power)})
        frames.append(old)
        source_rows.append({'district':district,'source':'verified archive best-match snapshot','rows':len(old)})
    df=pd.concat(frames,ignore_index=True).sort_values(['district','date'])
    for col in ['tmin_c','et0']:
        if col not in df: df[col]=np.nan
    # Invalid provider sentinels remain missing, never filled from adjacent days.
    for col,lo,hi in [('rainfall_mm',0,2000),('tmax_c',-30,60),('tmin_c',-40,50),('et0',0,30)]:
        df.loc[~df[col].between(lo,hi),col]=np.nan
    soil_parts=[]
    for path in (RAW/'soil').glob('*.json'):
        p=json.loads(path.read_text());daily=p.get('daily',{})
        if 'soil_moisture_0_to_7cm_mean' in daily:
            s=pd.DataFrame({'date':pd.to_datetime(daily['time']),'soil':daily['soil_moisture_0_to_7cm_mean'],
                            'district':path.stem.replace('_',' ')})
            s.loc[~s.soil.between(0,1),'soil']=np.nan;soil_parts.append(s)
    if soil_parts:
        df=df.merge(pd.concat(soil_parts),on=['district','date'],how='left',validate='one_to_one')
    else: df['soil']=np.nan
    save_json(REPORTS/'weather_sources_used.json',source_rows)
    return df


def climate_indices():
    result={}
    if (RAW/'oni.txt').exists():
        oni=pd.read_csv(RAW/'oni.txt',sep=r'\s+')
        month={name:i+1 for i,name in enumerate(['DJF','JFM','FMA','MAM','AMJ','MJJ','JJA','JAS','ASO','SON','OND','NDJ'])}
        dates=[pd.Timestamp(year=int(r.YR),month=month[r.SEAS],day=1)+pd.offsets.MonthEnd(2)+pd.Timedelta(days=45) for r in oni.itertuples()]
        result['oni_lag']=pd.Series(oni.ANOM.to_numpy(),index=pd.DatetimeIndex(dates)).sort_index()
    if (RAW/'dmi.txt').exists():
        entries={}
        for line in (RAW/'dmi.txt').read_text().splitlines()[1:]:
            parts=line.split()
            if len(parts)!=13 or not re.fullmatch(r'\d{4}',parts[0]):continue
            for month,val in enumerate(parts[1:],1):
                value=float(val)
                if abs(value)<20:
                    date=pd.Timestamp(year=int(parts[0]),month=month,day=1)+pd.offsets.MonthEnd(1)+pd.Timedelta(days=45)
                    entries[date]=value
        result['dmi_lag']=pd.Series(entries).sort_index()
    return result


def complete(series,expected):
    return len(series)==expected and series.notna().all()


def raw_weather_features(frame,start,cutoff):
    # 7-day publication lag means no unreleased ERA5 days used at the cutoff.
    end=cutoff-pd.Timedelta(days=7)
    sub=frame.loc[start:end]; days=(end-start).days+1
    r=sub.rainfall_mm; t=sub.tmax_c; lo=sub.tmin_c; et=sub.et0
    out={name:np.nan for name in GROUPS['weather']+GROUPS['soil']}
    if complete(r,days):
        out.update(rain_total=float(r.sum()),heavy_days=int((r>=50).sum()),extreme_days=int((r>=100).sum()))
        longest=run=0
        for dry in r.lt(1):
            run=run+1 if dry else 0;longest=max(longest,run)
        out['dry_spell']=longest
    if complete(t,days):out.update(hot35=int((t>35).sum()),hot38=int((t>38).sum()))
    if complete(t,days) and complete(lo,days):
        out.update(gdd10=float(((t+lo)/2-10).clip(lower=0).sum()),diurnal_range=float((t-lo).mean()))
    if complete(et,days):out['et0_total']=float(et.sum())
    if complete(r,days) and complete(et,days):out['water_balance']=float(r.sum()-et.sum())
    if complete(sub.soil,days):out['soil_mean']=float(sub.soil.mean())
    # Onset proxy: first >=20 mm / 3 days after 15 May, confirmed by observed
    # subsequent 7 days with no >=5-day dry run. No look-ahead past data end.
    monsoon=frame.loc[pd.Timestamp(end.year,5,15):end,'rainfall_mm']
    if len(monsoon)>=10 and monsoon.notna().all():
        onset=None
        for i in range(len(monsoon)-9):
            if monsoon.iloc[i:i+3].sum()>=20:
                subsequent=monsoon.iloc[i+3:i+10].lt(1)
                if not any(subsequent.iloc[j:j+5].all() for j in range(3)):
                    onset=monsoon.index[i];break
        out['onset_seen']=int(onset is not None)
        out['onset_delay']=(onset-pd.Timestamp(end.year,6,1)).days if onset is not None else np.nan
    return out


def drought_index(frame,cutoff,months,balance=False):
    # Complete calendar months whose END + 7-day archive latency precedes cutoff.
    end=(cutoff-pd.Timedelta(days=7)).to_period('M').start_time-pd.Timedelta(days=1)
    values=[]
    for year in range(frame.index.min().year,end.year+1):
        e=pd.Timestamp(year,end.month,1)+pd.offsets.MonthEnd(0)
        s=(e.to_period('M')-(months-1)).start_time
        x=frame.loc[s:e]; expected=(e-s).days+1
        if complete(x.rainfall_mm,expected) and (not balance or complete(x.et0,expected)):
            values.append((year,float((x.rainfall_mm-x.et0 if balance else x.rainfall_mm).sum())))
    prior=[v for y,v in values if y<end.year]
    current=[v for y,v in values if y==end.year]
    if len(prior)<10 or not current or np.std(prior)<1e-8:return np.nan
    try:
        if balance:
            params=fisk.fit(prior);prob=fisk.cdf(current[0],*params)
        else:
            positives=[v for v in prior if v>0]
            if len(positives)<8:return np.nan
            params=gamma.fit(positives,floc=0);zero=1-len(positives)/len(prior)
            prob=zero+(1-zero)*gamma.cdf(current[0],*params)
        return float(norm.ppf(np.clip(prob,1e-5,1-1e-5)))
    except (ValueError,RuntimeError):return np.nan


def cyclone_data():
    if not (RAW/'ibtracs.csv').exists():return None
    df=pd.read_csv(RAW/'ibtracs.csv',skiprows=[1],low_memory=False)
    df['date']=pd.to_datetime(df.ISO_TIME,errors='coerce',utc=True).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
    for col in ['LAT','LON']:df[col]=pd.to_numeric(df[col],errors='coerce')
    return df.dropna(subset=['date','LAT','LON'])


def haversine(lat,lon,lats,lons):
    p1,p2=np.radians(lat),np.radians(lats)
    a=np.sin((p2-p1)/2)**2+np.cos(p1)*np.cos(p2)*np.sin(np.radians(lons-lon)/2)**2
    return 6371*2*np.arcsin(np.sqrt(np.clip(a,0,1)))


def build():
    setup();panel=load_apy();weather=load_weather();indices=climate_indices();storms=cyclone_data()
    points=pd.read_csv(RAW/'centroids.csv').set_index('district')
    by_district={d:x.set_index('date').sort_index() for d,x in weather.groupby('district')}
    adjacency=json.loads((RAW/'adjacency.json').read_text()) if (RAW/'adjacency.json').exists() else {}
    census_path=RAW/'census_india-districts-census-2011.csv';census=None
    if census_path.exists():
        census=pd.read_csv(census_path)
        census=census[census['State name'].str.casefold().eq('west bengal')].copy()
        census['district']=census['District name'].map(canonical)
        census=census.set_index('district')
    baseline_cache={};records=[]
    for row in panel.itertuples():
        start,cut,harvest=window(row.crop_year,row.season);frame=by_district[row.district]
        values=raw_weather_features(frame,start,cut)
        priors=[]
        for y in range(1997,row.crop_year):
            key=(row.district,row.season,y)
            if key not in baseline_cache:
                s,c,_=window(y,row.season);baseline_cache[key]=raw_weather_features(frame,s,c)
            priors.append(baseline_cache[key])
        for col,out in [('rain_total','rain_z'),('soil_mean','soil_anomaly')]:
            history=[v[col] for v in priors if np.isfinite(v[col])]
            if len(history)>=5 and np.std(history,ddof=1)>1e-8 and np.isfinite(values[col]):
                values[out]=(values[col]-np.mean(history))/np.std(history,ddof=1)
        for length in (1,3,6):
            values[f'spi{length}']=drought_index(frame,cut,length)
            values[f'spei{length}']=drought_index(frame,cut,length,True)
        for col,series in indices.items():
            past=series[series.index<=cut]
            values[col]=float(past.iloc[-1]) if len(past) and (cut-past.index[-1]).days<=100 else np.nan
        if storms is not None:
            x=storms[(storms.date>=start)&(storms.date<=cut-pd.Timedelta(days=1))]
            p=points.loc[row.district]
            close=x[haversine(p.latitude,p.longitude,x.LAT,x.LON)<=150]
            values.update(cyclone_150km=int(len(close)>0),cyclone_days=close.date.dt.normalize().nunique())
        # Outcome-derived features only from seasons whose harvest+12mo precedes cutoff.
        past=panel[(panel.district==row.district)&(panel.season==row.season)&(panel.label_available_at<cut.date().isoformat())].sort_values('crop_year')
        if len(past)>=3:
            values['yield_trend']=float(np.polyfit(past.crop_year,past.yield_t_ha,1)[0])
            values['previous_residual']=float(past.iloc[-1].detrended_anomaly)
        previous=past[past.crop_year==row.crop_year-1]
        values['previous_shortfall']=float(previous.iloc[0].label15) if len(previous) else np.nan
        if len(past)>=2 and past.iloc[-1].crop_year==past.iloc[-2].crop_year+1:
            values['area_change']=float(past.iloc[-1].area/past.iloc[-2].area-1)
        neighbours=adjacency.get(row.district,[])
        # Most recent *available* neighbouring season per district, not future harvests.
        neighbour_rows=panel[panel.district.isin(neighbours)&(panel.label_available_at<cut.date().isoformat())].sort_values('harvest')
        latest=neighbour_rows.groupby('district').tail(1)
        if neighbours and len(latest)==len(neighbours) and latest.anomaly_pct.notna().all():
            values['neighbour_anomaly']=float(latest.anomaly_pct.mean())
        # Census-2011 is not backfilled into earlier years; use conservative 2014 availability.
        if census is not None and cut>=pd.Timestamp('2014-01-01') and row.district in census.index:
            c=census.loc[row.district]
            values.update(agri_labourer_share=float(c.Agricultural_Workers/c.Workers),
                          cultivator_share=float(c.Cultivator_Workers/c.Workers),
                          literacy_share=float(c.Literate/c.Population))
        records.append(values)
    features=pd.DataFrame(records)
    for cols in GROUPS.values():
        for col in cols:
            if col not in features:features[col]=np.nan
    result=pd.concat([panel.reset_index(drop=True),features],axis=1)
    result['district_code']=result.district.map({d:i for i,d in enumerate(DISTRICTS)})
    result['season_code']=result.season.map({s:i for i,s in enumerate(SEASONS)})
    labeled=result[result.label15.notna()].copy()
    coverage={}
    for name,columns in GROUPS.items():
        per_feature={c:float(labeled[c].notna().mean()) for c in columns}
        usable=covered_columns(labeled,columns)
        joint=float(labeled[usable].notna().all(axis=1).mean()) if usable else 0
        coverage[name]={'feature_coverage':per_feature,'eligible_features':usable,
                        'coverage':joint,'eligible':bool(usable) and joint>=.60,
                        'reason':None if usable and joint>=.60 else 'Below 60% coverage / no verified matched source'}
    save_json(REPORTS/'feature_coverage.json',coverage)
    save_json(REPORTS/'blockers.json',{
        'groups':{k:v for k,v in coverage.items() if not v['eligible']},
        'data_vintage':'Reanalysis and final revised APY are retrospective. No point-in-time release-vintage archives. 7-day weather, 45-day index and 12-month APY latency assumptions must be validated for prospective release.',
        'boro_calendar':'APY YYYY–YYYY is treated as July–June crop year: Summer/boro Dec(Y)–May(Y+1), cutoff 15 Mar(Y+1). Source-specific harvest-year metadata verification remains a release blocker.',
        'spatial':'Boundary adjacency '+('available' if adjacency else 'not verified; spatial lag stays missing')+'. Uses last available neighbouring outcome under the 12-month publication assumption.',
        'withdrawal':'Monsoon withdrawal after the fixed cutoff is not observable; deliberately excluded.',
        'vegetation':'AppEEARS catalogue alone is not an NDVI/EVI district time series.',
    })
    result.to_csv(PROCESSED/'panel.csv',index=False)
    save_json(REPORTS/'panel_summary.json',{'rows':len(result),'labeled_rows':len(labeled),
        'years':sorted(labeled.crop_year.unique().tolist()),'districts':sorted(labeled.district.unique().tolist()),
        'positives':int(labeled.label15.sum()),'columns':result.columns.tolist(),
        'by_season':labeled.groupby('season').label15.agg(['size','sum']).to_dict('index'),
        'panel_sha256':sha(PROCESSED/'panel.csv'),'groups':GROUPS})
    print(json.dumps({'labeled_rows':len(labeled),'positives':int(labeled.label15.sum()),
                      'eligible_groups':[k for k,v in coverage.items() if v['eligible']]}))


def covered_columns(frame,columns,minimum=.60):
    """Coverage is fitted on training rows only by every modelling fold.

    Prefer better-covered columns; retain a group subset only while joint observed
    coverage stays >=minimum. Full-data coverage files are descriptive, not inputs
    to model selection. No data are filled to meet the threshold.
    """
    selected=[]
    for col in sorted(columns,key=lambda c:(-frame[c].notna().mean(),c)):
        if frame[selected+[col]].notna().all(axis=1).mean()>=minimum:
            selected.append(col)
    return selected


if __name__=='__main__':build()
