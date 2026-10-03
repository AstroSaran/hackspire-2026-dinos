"""Audited historical replay with out-of-time artifacts; no current-year outcomes as inputs."""
import argparse
import json

import joblib
import numpy as np
import pandas as pd

from .common import MODELS, REPORTS, PROCESSED, clean, sha
from .features import DISTRICTS, SEASONS, canonical, window, GROUPS
from .modelling import TARGETS,matrix

DESCRIPTIONS={
    'rain_total':'Rain observed before the cutoff', 'rain_z':'Rainfall relative to earlier seasons',
    'dry_spell':'Longest observed dry spell', 'heavy_days':'Days with at least 50 mm rain',
    'extreme_days':'Days with at least 100 mm rain', 'hot35':'Days above 35°C', 'hot38':'Days above 38°C',
    'gdd10':'Accumulated temperature above a 10°C base', 'diurnal_range':'Day–night temperature difference',
    'oni_lag':'Previously published El Niño index', 'dmi_lag':'Previously published Indian Ocean Dipole index',
    'yield_trend':'Trend in previously available district yields', 'previous_residual':'Last available yield deviation from trend',
    'area_change':'Change in previously available rice area','cyclone_150km':'Observed cyclone proximity before cutoff',
    'cyclone_days':'Observed nearby cyclone days','district_code':'District-specific model effect','season_code':'Rice-season model effect',
    'onset_seen':'Whether the rainfall-onset proxy has been observed','onset_delay':'Observed rainfall-onset delay',
    'spi1':'One-month rainfall drought index','spi3':'Three-month rainfall drought index','spi6':'Six-month rainfall drought index'}


class Engine:
    def __init__(self):
        self.manifest=json.loads((MODELS/'manifest.json').read_text())
        if self.manifest.get('schema_version')!=1:raise ValueError('Unsupported model schema')
        if sha(PROCESSED/'panel.csv')!=self.manifest['panel_sha256']:raise ValueError('Panel checksum mismatch: retrain and evaluate')
        if sha(MODELS/'selection.json')!=self.manifest['selection_sha256']:raise ValueError('Model selection checksum mismatch')
        if sha(REPORTS/'source_manifest.json')!=self.manifest['source_manifest_sha256']:raise ValueError('Sources changed since training: retrain and evaluate')
        self.selection=json.loads((MODELS/'selection.json').read_text())
        self.panel=pd.read_csv(PROCESSED/'panel.csv')
        self.cache={}

    def load(self,name):
        if name not in self.cache:
            expected=self.manifest['artifacts'].get(name)
            if not expected or sha(MODELS/name)!=expected:raise ValueError(f'Artifact checksum mismatch: {name}')
            self.cache[name]=joblib.load(MODELS/name)
        return self.cache[name]

    def base_risk(self,kind,year,frame):
        bundle=self.load(f'{kind}_{year}.joblib');out=pd.Series(np.nan,index=frame.index)
        for season,models in bundle.members.items():
            data=frame if season=='pooled' else frame[frame.season.eq(season)]
            if bundle.label in models and len(data):out.loc[data.index]=models[bundle.label].predict(data)
        return out.to_numpy()

    def risk(self,frame,year,choice=None):
        choice=choice or self.selection['classifier'];kind=choice.removesuffix('_isotonic')
        if kind=='stack':
            stack=self.load(f'stack_{year}.joblib')
            x=pd.DataFrame({k:self.base_risk(k,year,frame) for k in stack['bases']})
            out=np.full(len(frame),np.nan);valid=x.notna().all(axis=1)
            if stack['meta'] is not None and valid.any():out[valid]=stack['meta'].predict_proba(x.loc[valid])[:,1]
            iso=stack['isotonic'] if choice.endswith('_isotonic') else None
        else:
            out=self.base_risk(kind,year,frame)
            iso=self.load(f'{kind}_isotonic_{year}.joblib') if choice.endswith('_isotonic') else None
        if iso is not None:
            valid=np.isfinite(out);out[valid]=iso.predict(out[valid])
        return out

    def regression(self,frame,year):
        kind=self.selection['regressor']
        if kind!='stack':return self.load(f'{kind}_{year}.joblib').predict(frame)
        stack=self.load(f'stack_{year}.joblib');out=pd.DataFrame(index=frame.index)
        bases={k:self.load(f'{k}_{year}.joblib').predict(frame) for k in stack['bases']}
        for target in TARGETS:
            x=pd.DataFrame({k:bases[k]['pred_'+target] for k in stack['bases']})
            valid=x.notna().all(axis=1);out['pred_'+target]=np.nan
            if target in stack['regmeta'] and valid.any():out.loc[valid,'pred_'+target]=stack['regmeta'][target].predict(x.loc[valid])
        return out

    def intervals(self,frame,year):
        artifact=self.load(f'quantile_{year}.joblib');x,_=matrix(frame,artifact['features'],'lightgbm')
        out={}
        for target,models in artifact['models'].items():
            values=np.sort(np.column_stack([models[q].booster_.predict(x) for q in [.1,.5,.9]]),axis=1)
            radius=artifact['radii'][target]
            out[target]=np.column_stack([values[:,0]-radius,values[:,1],values[:,2]+radius])
        return out

    def explanation_inputs(self,year):
        kind=self.selection['classifier'].removesuffix('_isotonic')
        bases=self.load(f'stack_{year}.joblib')['bases'] if kind=='stack' else [kind]
        features=[];background=[]
        for base in bases:
            bundle=self.load(f'{base}_{year}.joblib')
            for models in bundle.members.values():
                model=models.get(bundle.label)
                if model is not None:
                    features.extend(model.features);background.append(model.background)
        columns=sorted(set(features))+['district_code','season_code']
        data=pd.concat(background).drop_duplicates(['district','crop_year','season'])
        data=data[columns].dropna().tail(20)
        if len(data)<5:raise ValueError('Too few complete observed background rows for SHAP')
        return columns,data

    def explain(self,frame,year):
        import shap
        columns,background=self.explanation_inputs(year)
        def predict_matrix(values):
            data=pd.DataFrame(values,columns=columns)
            data['district']=data.district_code.map(dict(enumerate(DISTRICTS)))
            data['season']=data.season_code.map(dict(enumerate(SEASONS)))
            return self.risk(data,year)
        explainer=shap.Explainer(predict_matrix,background,algorithm='permutation',seed=20261003)
        explanation=explainer(frame[columns],max_evals=2*len(columns)+1,silent=True)
        return columns,np.asarray(explanation.values),np.asarray(explanation.base_values)


def predict(district,season,cutoff_date,require_released=False):
    engine=Engine();district=canonical(district)
    if district not in DISTRICTS:raise ValueError('District outside the 18-district Census-2011 WB domain')
    if season not in SEASONS:raise ValueError('Season must be Autumn, Winter, or Summer')
    date=pd.Timestamp(cutoff_date)
    if pd.isna(date):raise ValueError('A valid cutoff calendar date is required')
    if date.tz is not None or date!=date.normalize():raise ValueError('Use a local calendar date YYYY-MM-DD')
    crop_year=date.year-1 if season=='Summer' else date.year
    _,cutoff,harvest=window(crop_year,season)
    if date!=cutoff:raise ValueError(f'The fixed {season} cutoff is {cutoff.date()}')
    data=engine.panel[(engine.panel.district==district)&(engine.panel.season==season)&(engine.panel.crop_year==crop_year)]
    if crop_year not in engine.manifest['holdout_years'] or len(data)!=1:
        raise ValueError('No audited out-of-time replay for this district/season/date. Supported crop-years: 2018–2022; missing district components are excluded.')
    report_path=REPORTS/'model_release_report.json'
    gate=json.loads(report_path.read_text()) if report_path.exists() else {'status':'unevaluated','failed_checks':['evaluation_not_run']}
    if report_path.exists() and gate.get('model_manifest_sha256')!=sha(MODELS/'manifest.json'):
        gate={'status':'unevaluated','failed_checks':['stale_release_report']}
    if require_released and gate['status']!='released':raise ValueError('Model release is withheld: '+', '.join(gate['failed_checks']))
    probability=engine.risk(data,crop_year)[0];reg=engine.regression(data,crop_year).iloc[0]
    intervals=engine.intervals(data,crop_year)
    columns,values,base=engine.explain(data,crop_year)
    contributions=values[0];order=np.argsort(-np.abs(contributions))[:5]
    drivers=[{'feature':columns[i],'description':DESCRIPTIONS.get(columns[i],columns[i].replace('_',' ')),
              'observed_value':float(data.iloc[0][columns[i]]),'probability_contribution':float(contributions[i]),
              'direction':'increases predicted risk' if contributions[i]>0 else 'decreases predicted risk' if contributions[i]<0 else 'no contribution'} for i in order]
    missing=[c for c in columns if pd.isna(data.iloc[0][c])]
    return clean({'district':district,'season':season,'cutoff_date':date.date().isoformat(),'crop_year':crop_year,
        'shortfall_probability':probability,'shortfall_definition':'Yield <85% of previous five consecutive years mean',
        'expected_anomaly_pct':reg.pred_anomaly_pct,'expected_anomaly_t_ha':reg.pred_anomaly,
        'interval_80_pct':{'lower':intervals['anomaly_pct'][0,0],'upper':intervals['anomaly_pct'][0,2]},
        'interval_80_t_ha':{'lower':intervals['anomaly'][0,0],'upper':intervals['anomaly'][0,2]},
        'top_five_drivers':drivers,'shap_baseline_probability':base[0],
        'explanation_method':'Permutation SHAP of the selected calibrated probability; observed training background; one permutation; associations, not causal effects.',
        'lead_time_days':(harvest-cutoff).days,'lead_time_basis':'Assumed typical harvest, not observed farm harvest date',
        'data_quality_flags':['retrospective_reanalysis','APY_release_vintages_unverified','boro_calendar_unverified',
                              'centroid_weather_not_district_average','unverified_source_redistribution_terms']+
                             (['missing_model_features:'+','.join(missing)] if missing else []),
        'model':engine.selection['classifier'],'regressor':engine.selection['regressor'],
        'model_status':'research_only' if gate['status']!='released' else 'released','gate_status':gate['status'],
        'failed_release_checks':gate['failed_checks'],'inference_mode':'out_of_time_historical_replay'})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--district',required=True)
    parser.add_argument('--season',required=True);parser.add_argument('--cutoff-date',required=True)
    parser.add_argument('--require-released',action='store_true');args=parser.parse_args()
    try:result=predict(args.district,args.season,args.cutoff_date,args.require_released)
    except (ValueError,FileNotFoundError) as exc:parser.exit(2,json.dumps({'status':'unavailable','error':str(exc)})+'\n')
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':main()
