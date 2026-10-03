"""Nested rolling-origin hindcasts; a locked family choice precedes holdout years."""
import argparse
import csv
import json
import time
import warnings

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, mean_squared_error

from .common import PROCESSED, REPORTS, MODELS, SEED, setup, save_json, sha, utc
from .modelling import (TARGETS, KINDS, Bundle, available, origin, baseline_predictions,
                        select_features, matrix)

DEVELOPMENT=list(range(2012,2016))
HOLDOUT=list(range(2018,2023))
OOF_YEARS=list(range(2009,2023))
STACK_BASES=['lightgbm','xgboost','catboost']
FIELDS=['stage','model','year','config','status','rows','positives','brier','rmse_pct','seconds','details']


def log(**row):
    path=REPORTS/'results.csv'
    with path.open('a',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS)
        if stream.tell()==0:writer.writeheader()
        if 'details' in row:row['details']=json.dumps(row['details'],default=str)
        writer.writerow(row)


def load_panel():
    df=pd.read_csv(PROCESSED/'panel.csv')
    df['row_id']=df.district+'|'+df.crop_year.astype(str)+'|'+df.season
    if df.row_id.duplicated().any():raise ValueError('Duplicate panel keys')
    return df.set_index('row_id',drop=False).loc[lambda x:x.label15.notna()].copy()


def metrics(test,pred,label='label15'):
    valid=pred.p.notna() & test[label].notna()
    reg=pred.pred_anomaly_pct.notna() & test.anomaly_pct.notna()
    return {'rows':int(valid.sum()),'positives':int(test.loc[valid,label].sum()),
            'brier':float(brier_score_loss(test.loc[valid,label],pred.loc[valid,'p'])) if valid.any() else None,
            'rmse_pct':float(np.sqrt(mean_squared_error(test.loc[reg,'anomaly_pct'],pred.loc[reg,'pred_anomaly_pct']))) if reg.any() else None}


def tune(panel,kind,year,label='label15',exclude=()):
    # Both inner validation harvests are released before the outer issue date.
    scores=[]
    configs=[0] if kind=='mixed' else [0,1]
    for config in configs:
        losses=[]
        for inner in [year-4,year-3]:
            train=available(panel,inner);validation=panel[panel.crop_year.eq(inner)]
            if len(train)<80 or not len(validation):continue
            started=time.monotonic()
            bundle=Bundle(kind,inner,config,label,exclude).fit(train,[label,'anomaly_pct'])
            prediction=bundle.predict(validation);score=metrics(validation,prediction,label)
            # All candidates need >=90% risk coverage; no cherry-picking easy rows.
            ok=score['brier'] is not None and score['rows']>=.9*len(validation)
            log(stage='inner',model=kind,year=year,config=config,status='OK' if ok else 'INELIGIBLE',
                **score,seconds=round(time.monotonic()-started,3),
                details={'inner_year':inner,'label':label,'excluded_groups':exclude,'fits':bundle.diagnostics})
            if ok:losses.append(score['brier'])
        scores.append((float(np.mean(losses)) if losses else np.inf,config))
    best=min(scores)
    # Early auxiliary OOF folds may lack inner history. This is a declared default,
    # not a tuned result; those folds are not the locked held-out evaluation.
    return best[1],{'inner_scores':scores,'default_without_valid_inner':not np.isfinite(best[0])}


def annotate(test,pred,model):
    columns=['row_id','district','season','crop_year','cutoff','harvest','label_available_at',
             'label10','label15','label20']+TARGETS+['cyclone_150km','spi3']
    out=test[columns].copy()
    for col in pred:out[col]=pred[col]
    out['model']=model
    return out


def fit_outer(panel,kind,year,label='label15',exclude=(),persist=False):
    config,tuning=tune(panel,kind,year,label,exclude)
    started=time.monotonic();train=available(panel,year);test=panel[panel.crop_year.eq(year)]
    bundle=Bundle(kind,year,config,label,exclude).fit(train)
    prediction=bundle.predict(test);score=metrics(test,prediction,label)
    log(stage='outer' if not exclude else 'ablation',model=kind,year=year,config=config,
        status='OK' if score['rows'] else 'FAILED',**score,seconds=round(time.monotonic()-started,3),
        details={'label':label,'excluded_groups':exclude,'as_of':origin(year),'fits':bundle.diagnostics,'tuning':tuning})
    if persist:
        joblib.dump(bundle,MODELS/f'{kind}_{year}.joblib',compress=3)
    return bundle,prediction


def conformal_radius(scores,coverage=.8):
    values=np.asarray(scores,dtype=float);values=values[np.isfinite(values)]
    if not len(values):raise ValueError('No observed calibration scores')
    rank=int(np.ceil((len(values)+1)*coverage))
    if rank>len(values):raise ValueError('Insufficient calibration observations for finite interval')
    return float(np.sort(values)[rank-1])


def quantiles(panel,year):
    """Frozen predictors and disjoint temporal calibration; never refit on calibration."""
    calibration_year=year-2
    train=available(panel,calibration_year)
    calibration=panel[panel.crop_year.eq(calibration_year)&(panel.label_available_at<origin(year))]
    test=panel[panel.crop_year.eq(year)]
    features,groups=select_features(train)
    x,_=matrix(train,features,'lightgbm');xc,_=matrix(calibration,features,'lightgbm');xt,_=matrix(test,features,'lightgbm')
    result=pd.DataFrame(index=test.index);saved={'year':year,'calibration_year':calibration_year,'features':features,'models':{},'radii':{},
        'train_ids':train.index.tolist(),'calibration_ids':calibration.index.tolist(),'groups':groups,
        'last_training_label_available_at':train.label_available_at.max()}
    for target in TARGETS:
        models={};cal_pred=[];test_pred=[]
        for level in [.1,.5,.9]:
            valid=train[target].notna()
            model=LGBMRegressor(objective='quantile',alpha=level,n_estimators=140,num_leaves=5,
                  min_child_samples=25,learning_rate=.035,reg_lambda=5,n_jobs=2,verbosity=-1,random_state=SEED)
            model.fit(x[valid],train.loc[valid,target])
            models[level]=model;cal_pred.append(model.booster_.predict(xc));test_pred.append(model.booster_.predict(xt))
        cp=np.sort(np.column_stack(cal_pred),axis=1);tp=np.sort(np.column_stack(test_pred),axis=1)
        scores=np.maximum.reduce([cp[:,0]-calibration[target].to_numpy(),calibration[target].to_numpy()-cp[:,2],np.zeros(len(calibration))])
        radius=conformal_radius(scores)
        for i,name in enumerate(['low','median','high']):result[f'{target}_{name}']=tp[:,i]+(-radius if i==0 else radius if i==2 else 0)
        saved['models'][target]=models;saved['radii'][target]=radius
        log(stage='quantile',model='lightgbm_CQR',year=year,status='OK',rows=len(test),
            details={'target':target,'calibration_year':calibration_year,'train_rows':len(train),
                     'calibration_rows':int(np.isfinite(scores).sum()),'radius':radius,'nominal_coverage':.8})
    joblib.dump(saved,MODELS/f'quantile_{year}.joblib',compress=3)
    return annotate(test,result,'quantile_CQR')


def temporal_postprocess(raw,panel):
    """Meta-models and isotonic fits see only released past OOF predictions."""
    output=[];stack_history=[]
    for year in OOF_YEARS:
        eligible=raw[(raw.crop_year<year)&(raw.label_available_at<origin(year))]
        for kind in KINDS:
            past=eligible[eligible.model.eq(kind)].dropna(subset=['p'])
            current=raw[raw.model.eq(kind)&raw.crop_year.eq(year)].copy()
            calibrator=None
            if len(past)>=80 and past.label15.sum()>=5 and past.label15.nunique()==2:
                calibrator=IsotonicRegression(out_of_bounds='clip').fit(past.p,past.label15)
                valid=current.p.notna();current.loc[valid,'p']=calibrator.predict(current.loc[valid,'p'])
            current['model']=kind+'_isotonic';output.append(current)
            if year in HOLDOUT:
                joblib.dump(calibrator,MODELS/f'{kind}_isotonic_{year}.joblib',compress=3)
            log(stage='calibration',model=kind+'_isotonic',year=year,status='OK' if calibrator else 'IDENTITY_INSUFFICIENT_OOF',
                rows=len(past),positives=int(past.label15.sum()),details={'past_years':sorted(past.crop_year.unique().tolist())})
        past=eligible[eligible.model.isin(STACK_BASES)].pivot(index='row_id',columns='model',values='p').reindex(columns=STACK_BASES).dropna()
        now=raw[(raw.model.isin(STACK_BASES))&raw.crop_year.eq(year)].pivot(index='row_id',columns='model',values='p').reindex(columns=STACK_BASES)
        current=raw[raw.model.eq('lightgbm')&raw.crop_year.eq(year)].copy().set_index('row_id',drop=False)
        current['p']=np.nan;meta=None
        if len(past)>=80 and panel.loc[past.index,'label15'].nunique()==2:
            meta=LogisticRegression(C=.5,random_state=SEED,max_iter=1000).fit(past,panel.loc[past.index,'label15'])
            valid=now.notna().all(axis=1)
            current.loc[now.index[valid],'p']=meta.predict_proba(now.loc[valid])[:,1]
        current['model']='stack';stack_history.append(current.copy());output.append(current.copy())
        # Continuous stack uses ridge on observed, temporally OOF base regressions.
        from sklearn.linear_model import Ridge
        regmeta={}
        for target in TARGETS:
            rp=eligible[eligible.model.isin(STACK_BASES)].pivot(index='row_id',columns='model',values='pred_'+target).reindex(columns=STACK_BASES).dropna()
            rn=raw[raw.model.isin(STACK_BASES)&raw.crop_year.eq(year)].pivot(index='row_id',columns='model',values='pred_'+target).reindex(columns=STACK_BASES)
            current['pred_'+target]=np.nan
            if len(rp)>=80:
                model=Ridge(alpha=10).fit(rp,panel.loc[rp.index,target]);regmeta[target]=model
                valid=rn.notna().all(axis=1);current.loc[rn.index[valid],'pred_'+target]=model.predict(rn.loc[valid])
        output[-1]=current.copy();stack_history[-1]=current.copy()
        history=pd.concat(stack_history)
        h=history[(history.crop_year<year)&(history.label_available_at<origin(year))].dropna(subset=['p'])
        iso=None
        if len(h)>=80 and h.label15.sum()>=5 and h.label15.nunique()==2:
            iso=IsotonicRegression(out_of_bounds='clip').fit(h.p,h.label15)
            valid=current.p.notna();current.loc[valid,'p']=iso.predict(current.loc[valid,'p'])
        current['model']='stack_isotonic';output.append(current)
        if year in HOLDOUT:joblib.dump({'meta':meta,'regmeta':regmeta,'isotonic':iso,'bases':STACK_BASES},MODELS/f'stack_{year}.joblib',compress=3)
        log(stage='stacking',model='stack',year=year,status='OK' if meta else 'INSUFFICIENT_OOF',rows=len(past),
            details={'bases':STACK_BASES,'meta':'logistic C=.5; regression ridge alpha=10','calibration_rows':len(h)})
    return pd.concat(output,ignore_index=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-ablations',action='store_true');args=parser.parse_args()
    setup();panel=load_panel()
    if (REPORTS/'results.csv').exists():
        (REPORTS/'results.csv').rename(REPORTS/f'results_previous_{int(time.time())}.csv')
    (REPORTS/'results.csv').write_text('')
    save_json(REPORTS/'experiment_protocol.json',{'created_at':utc(),'seed':SEED,'panel_sha256':sha(PROCESSED/'panel.csv'),
        'development_years':DEVELOPMENT,'holdout_years':HOLDOUT,'oof_years':OOF_YEARS,
        'selection':'Lowest development Brier among learned candidates with >=95% development coverage; locked for all holdout years.',
        'inner_validation':'outer year minus 4 and minus 3; Brier objective; grid indices 0,1 (mixed: 0).',
        'regression_tuning':'Shares risk-selected settings within each family; regression target not independently tuned.',
        'availability':'Training labels must be released strictly before 30 June of outer crop-year; assumed harvest+12 months.',
        'interval':'Frozen quantile predictor fitted before calibration crop-year (outer-2), calibrated on that year; no calibration-label refit.',
        'missing':'Native NaNs for boosting; complete-case exclusion for linear/mixed. Feature coverage selected using train only.',
        'split_warning':'Five annual origin folds; crop-year 2016/2017 not used for family selection but allowed as released training/calibration observations.'})
    outputs=[]
    for year in OOF_YEARS:
        test=panel[panel.crop_year.eq(year)]
        for name,prediction in baseline_predictions(available(panel,year),test).items():
            outputs.append(annotate(test,prediction,name));log(stage='baseline',model=name,year=year,status='OK',**metrics(test,prediction))
        for kind in KINDS:
            _,prediction=fit_outer(panel,kind,year,persist=year in HOLDOUT)
            outputs.append(annotate(test,prediction,kind))
            print(year,kind,metrics(test,prediction),flush=True)
        if year in HOLDOUT:outputs.append(quantiles(panel,year))
    raw=pd.concat(outputs,ignore_index=True);post=temporal_postprocess(raw,panel)
    predictions=pd.concat([raw,post],ignore_index=True)
    dev=predictions[predictions.crop_year.isin(DEVELOPMENT)]
    ranking=[]
    expected=int(panel.crop_year.isin(DEVELOPMENT).sum())
    for name,data in dev.groupby('model'):
        if name in ['base_rate','persistence','climatology','trailing_mean','quantile_CQR']:continue
        valid=data.dropna(subset=['p'])
        if len(valid)>=.95*expected:
            ranking.append({'model':name,'brier':float(brier_score_loss(valid.label15,valid.p)),'rows':len(valid)})
    ranking.sort(key=lambda x:(x['brier'],x['model']))
    if not ranking:raise RuntimeError('No learned candidate covers >=95% of development rows')
    selected=ranking[0]['model']
    # Regression family independently chosen on *development* anomaly-percent RMSE.
    regression=[]
    for name,data in dev.groupby('model'):
        if name not in KINDS+['stack']:continue
        valid=data.dropna(subset=['pred_anomaly_pct'])
        if len(valid)>=.95*expected:
            regression.append({'model':name,'rmse_pct':float(np.sqrt(mean_squared_error(valid.anomaly_pct,valid.pred_anomaly_pct))),'rows':len(valid)})
    regression.sort(key=lambda x:(x['rmse_pct'],x['model']))
    choice={'classifier':selected,'regressor':regression[0]['model'],'development_ranking':ranking,'regression_ranking':regression,
            'selection_years':DEVELOPMENT,'test_years':HOLDOUT,'locked_before':origin(min(HOLDOUT))}
    save_json(MODELS/'selection.json',choice)
    if not args.skip_ablations:
        # Controlled LightGBM group ablations; identical splits and new inner tuning.
        for group in __import__('rice_model.features',fromlist=['GROUPS']).GROUPS:
            for year in HOLDOUT:
                train=available(panel,year);_,eligible=select_features(train)
                if not eligible.get(group):
                    log(stage='ablation',model='lightgbm_without_'+group,year=year,status='SKIPPED_COVERAGE',
                        details={'reason':'No group feature reaches joint >=60% training coverage'})
                    continue
                _,prediction=fit_outer(panel,'lightgbm',year,exclude=(group,))
                outputs.append(annotate(panel[panel.crop_year.eq(year)],prediction,'lightgbm_without_'+group))
        for threshold in [10,20]:
            for year in HOLDOUT:
                _,prediction=fit_outer(panel,'lightgbm',year,label=f'label{threshold}')
                outputs.append(annotate(panel[panel.crop_year.eq(year)],prediction,f'lightgbm_label{threshold}'))
        predictions=pd.concat([pd.concat(outputs,ignore_index=True),post],ignore_index=True)
    log(stage='optional',model='graph_LSTM',status='NOT_ATTEMPTED',details={
        'reason':'No verified adjacency; annual district-season panel and few shortfalls do not justify adding sequence/graph complexity before established baselines.'})
    predictions.to_csv(REPORTS/'predictions.csv',index=False)
    artifacts={p.name:sha(p) for p in MODELS.glob('*.joblib')}
    save_json(MODELS/'manifest.json',{'schema_version':1,'created_at':utc(),'panel_sha256':sha(PROCESSED/'panel.csv'),
        'source_manifest_sha256':sha(REPORTS/'source_manifest.json'),'selection_sha256':sha(MODELS/'selection.json'),
        'artifacts':artifacts,'holdout_years':HOLDOUT})
    print(json.dumps(choice,indent=2),flush=True)


if __name__=='__main__':main()
