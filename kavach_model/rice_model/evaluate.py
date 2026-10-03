"""Measured comparisons, block uncertainty, diagnostics, explanations and release report."""
import json
import importlib.metadata
import platform
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score,average_precision_score,r2_score

from .common import ROOT,MODELS,REPORTS,PROCESSED,SEED,save_json,sha,utc
from .modelling import TARGETS,KINDS,available,baseline_predictions
from .train import HOLDOUT,load_panel,log
from .gate import release_gate


def scores(data,label='label15'):
    out={};valid=data.dropna(subset=['p',label])
    if len(valid):
        y=valid[label].to_numpy();p=valid.p.to_numpy()
        out.update(rows=len(y),positives=int(y.sum()),brier=float(np.mean((p-y)**2)),
                   auc=float(roc_auc_score(y,p)) if len(np.unique(y))==2 else np.nan,
                   ap=float(average_precision_score(y,p)) if y.sum()>0 else np.nan)
        if 'p_base' in valid:
            base=float(np.mean((valid.p_base.to_numpy()-y)**2));out['base_brier']=base
            out['brier_skill']=1-out['brier']/base if base>0 else np.nan
            out['persistence_brier']=float(np.mean((valid.p_persistence.to_numpy()-y)**2))
            out['brier_gain_over_base']=base-out['brier']
    else:out.update(rows=0,positives=0,brier=np.nan,auc=np.nan,ap=np.nan)
    for target in TARGETS:
        if 'pred_'+target in data:
            x=data.dropna(subset=[target,'pred_'+target])
            if len(x):
                error=x['pred_'+target]-x[target]
                out.update({target+'_mae':float(np.abs(error).mean()),target+'_rmse':float(np.sqrt(np.mean(error**2))),
                            target+'_r2':float(r2_score(x[target],x['pred_'+target])) if len(x)>1 else np.nan,
                            target+'_rows':len(x)})
        if target+'_low' in data:
            x=data.dropna(subset=[target,target+'_low',target+'_high'])
            if len(x):
                out[target+'_coverage']=float(((x[target]>=x[target+'_low'])&(x[target]<=x[target+'_high'])).mean())
                out[target+'_width']=float((x[target+'_high']-x[target+'_low']).mean())
    return out


def block_intervals(data,label='label15',replicates=500):
    frame=data.reset_index(drop=True)
    blocks=list(frame.groupby(['district','crop_year']).indices.values())
    rng=np.random.default_rng(SEED);samples=[]
    for _ in range(replicates):
        indices=np.concatenate([blocks[i] for i in rng.integers(0,len(blocks),len(blocks))])
        samples.append(scores(frame.iloc[indices],label))
    sample=pd.DataFrame(samples)
    result={}
    for metric in sample:
        valid=sample[metric].dropna()
        result[metric]={'lower':float(valid.quantile(.025)) if len(valid) else None,
                        'upper':float(valid.quantile(.975)) if len(valid) else None,'valid_replicates':len(valid)}
    return result


def reference_probabilities(panel,threshold):
    refs=[]
    for year in HOLDOUT:
        test=panel[panel.crop_year.eq(year)];prediction=baseline_predictions(available(panel,year),test,f'label{threshold}')
        refs.append(pd.DataFrame({'row_id':test.row_id,'p_base':prediction['base_rate'].p,
                                 'p_persistence':prediction['persistence'].p}))
    return pd.concat(refs,ignore_index=True)


def calibration(data):
    x=data.dropna(subset=['p','label15']).copy()
    # Fixed equal-width bins, with genuinely empty bins retained as empty.
    x['bin']=pd.cut(x.p,bins=np.linspace(0,1,11),include_lowest=True)
    table=x.groupby('bin',observed=False).agg(rows=('label15','size'),positives=('label15','sum'),
              mean_probability=('p','mean'),observed_rate=('label15','mean')).reset_index()
    table['bin']=table['bin'].astype(str)
    table.to_csv(REPORTS/'calibration_bins.csv',index=False)
    good=table[table.rows>0]
    fig,ax=plt.subplots(figsize=(5,4));ax.plot([0,1],[0,1],'--',color='gray')
    ax.plot(good.mean_probability,good.observed_rate,'o-');ax.set(xlabel='Predicted probability',ylabel='Observed fraction',title='Held-out calibration (fixed bins)',xlim=(0,1),ylim=(0,1))
    fig.tight_layout();fig.savefig(REPORTS/'calibration.png',dpi=160);plt.close(fig)


def explain(panel,selected):
    from .inference import Engine,DESCRIPTIONS
    engine=Engine();rows=[];errors=[];pdp=[]
    for year in HOLDOUT:
        frame=panel[panel.crop_year.eq(year)]
        try:
            columns,values,baselines=engine.explain(frame,year)
            predicted=engine.risk(frame,year)
            residual=np.abs(baselines+values.sum(axis=1)-predicted)
            if not np.isfinite(values).all() or residual.max()>1e-5:raise ValueError('SHAP additivity/finite-value check failed')
            for j,(idx,row) in enumerate(frame.iterrows()):
                for i,col in enumerate(columns):
                    rows.append({'row_id':idx,'district':row.district,'season':row.season,'crop_year':year,
                        'feature':col,'description':DESCRIPTIONS.get(col,col.replace('_',' ')),
                        'observed_value':row[col],'shap_probability':values[j,i],'baseline_probability':baselines[j]})
        except Exception as exc:
            errors.append({'year':year,'error':f'{type(exc).__name__}: {exc}'})
            log(stage='explanation',model=selected,year=year,status='FAILED',details=errors[-1])
    if rows:
        values=pd.DataFrame(rows);values.to_csv(REPORTS/'shap_local.csv',index=False)
        global_values=values.assign(magnitude=lambda d:d.shap_probability.abs()).groupby('feature').agg(
            mean_absolute_probability_effect=('magnitude','mean'),rows=('magnitude','size')).sort_values('mean_absolute_probability_effect',ascending=False)
        global_values.to_csv(REPORTS/'shap_global.csv')
        best=global_values.head(15).sort_values('mean_absolute_probability_effect')
        fig,ax=plt.subplots(figsize=(8,5));ax.barh(best.index,best.mean_absolute_probability_effect)
        ax.set_xlabel('Mean |SHAP| in probability units');fig.tight_layout();fig.savefig(REPORTS/'shap_global.png',dpi=160);plt.close(fig)
        top=values.assign(magnitude=lambda d:d.shap_probability.abs()).sort_values('magnitude',ascending=False).groupby('row_id').head(5)
        top.to_csv(REPORTS/'shap_top_five.csv',index=False)
        # PDP only at observed training quantiles; these are model diagnostics,
        # not new observations or training data. District/season codes excluded.
        for year in HOLDOUT:
            frame=panel[panel.crop_year.eq(year)];columns,bg=engine.explanation_inputs(year)
            for feature in [f for f in global_values.index if f not in ['district_code','season_code']][:3]:
                if feature not in columns:continue
                for value in np.unique(bg[feature].quantile([.1,.25,.5,.75,.9]).to_numpy()):
                    perturbed=frame.copy();perturbed[feature]=value
                    pdp.append({'crop_year':year,'feature':feature,'value':value,'mean_probability':float(np.nanmean(engine.risk(perturbed,year)))})
        pd.DataFrame(pdp).to_csv(REPORTS/'partial_dependence.csv',index=False)
        if pdp:
            p=pd.DataFrame(pdp);fig,axes=plt.subplots(1,p.feature.nunique(),figsize=(12,4),squeeze=False)
            for ax,(feature,data) in zip(axes.flat,p.groupby('feature')):
                for year,sub in data.groupby('crop_year'):ax.plot(sub.value,sub.mean_probability,label=str(year))
                ax.set(title=feature,xlabel='Observed training quantile value',ylabel='Mean predicted risk')
            axes.flat[0].legend();fig.tight_layout();fig.savefig(REPORTS/'partial_dependence.png',dpi=160);plt.close(fig)
    save_json(REPORTS/'explanation_status.json',{'status':'complete' if not errors else 'partial_or_failed','errors':errors,
        'method':'Permutation SHAP of selected probability, actual training background (up to 20 rows), one permutation; not causal.',
        'local_rows':len(set(r['row_id'] for r in rows)),'pdp_warning':'Marginal perturbations can break weather correlations. No perturbed rows were used in training.'})


def main():
    panel=load_panel();all_predictions=pd.read_csv(REPORTS/'predictions.csv')
    choice=json.loads((MODELS/'selection.json').read_text());predictions=all_predictions[all_predictions.crop_year.isin(HOLDOUT)]
    references={t:reference_probabilities(panel,t) for t in [10,15,20]}
    summaries=[];cis={};per_year=[]
    for name,data in predictions.groupby('model'):
        threshold=10 if name.endswith('label10') else 20 if name.endswith('label20') else 15
        data=data.merge(references[threshold],on='row_id',validate='one_to_one')
        measured=scores(data,f'label{threshold}')
        summaries.append({'model':name,'label_threshold_pct':threshold,**measured})
        cis[name]=block_intervals(data,f'label{threshold}')
        for year,sub in data.groupby('crop_year'):per_year.append({'model':name,'crop_year':year,**scores(sub,f'label{threshold}')})
        log(stage='heldout_evaluation',model=name,status='OK',rows=measured['rows'],positives=measured['positives'],
            brier=measured['brier'],rmse_pct=measured.get('anomaly_pct_rmse'),details={'metrics':measured,'ci':cis[name]})
        print(name,measured,flush=True)
    summary=pd.DataFrame(summaries).sort_values('brier',na_position='last')
    summary.to_csv(REPORTS/'model_comparison.csv',index=False)
    pd.DataFrame(per_year).to_csv(REPORTS/'per_year_metrics.csv',index=False)
    save_json(REPORTS/'confidence_intervals.json',{'method':'District–crop-year paired block bootstrap; seasons within block kept together',
        'replicates':500,'seed':SEED,'limitation':'Does not fully represent common cross-district year shocks; only five held-out years.', 'models':cis})
    selected=predictions[predictions.model.eq(choice['classifier'])].merge(references[15],on='row_id',validate='one_to_one')
    regression=predictions[predictions.model.eq(choice['regressor'])].set_index('row_id')
    intervals=predictions[predictions.model.eq('quantile_CQR')].set_index('row_id')
    for target in TARGETS:
        selected['pred_'+target]=selected.row_id.map(regression['pred_'+target])
        for suffix in ['low','median','high']:selected[target+'_'+suffix]=selected.row_id.map(intervals[target+'_'+suffix])
    selected.to_csv(REPORTS/'selected_predictions.csv',index=False)
    calibration(selected)
    measured=scores(selected);ci=block_intervals(selected)
    evidence=['APY crop-calendar/year convention for boro not source-verified',
              'Historical APY/reanalysis/index release vintages not available; assumed publication lags',
              'APY/Census/boundary redistribution terms not independently verified',
              'Raw APY historical split-district geography before 2016 not independently validated']
    gate=release_gate(measured,ci['auc']['lower'],measured['positives'],measured.get('anomaly_pct_coverage'),len(HOLDOUT),evidence)
    gate.update(created_at=utc(),classifier=choice['classifier'],regressor=choice['regressor'],
        metrics=measured,confidence_intervals_95=ci,test_years=HOLDOUT,
        positives_by_year=selected.groupby('crop_year').label15.sum().astype(int).to_dict(),
        model_manifest_sha256=sha(MODELS/'manifest.json'),
        training_panel_sha256=sha(PROCESSED/'panel.csv'),predictions_sha256=sha(REPORTS/'predictions.csv'),
        selected_predictions_sha256=sha(REPORTS/'selected_predictions.csv'),
        next_evidence=['At least 25 observed held-out shortfalls under the unchanged 15% label',
                       'Document crop-year conventions, district mapping and actual historical publication vintages',
                       'AUC lower confidence bound >0.55 and positive Brier skill versus released-history baselines',
                       'Independent interval coverage within 75–85%; a prospective evaluation with fresh data'])
    save_json(REPORTS/'model_release_report.json',gate)
    details=[]
    for group in ['district','crop_year','season']:
        for key,sub in selected.groupby(group):details.append({'group':group,'value':key,**scores(sub)})
    pd.DataFrame(details).to_csv(REPORTS/'district_year_season_diagnostics.csv',index=False)
    worst=selected.assign(squared_probability_error=lambda d:(d.p-d.label15)**2,
                          absolute_anomaly_error=lambda d:np.abs(d.pred_anomaly_pct-d.anomaly_pct))
    worst.sort_values('absolute_anomaly_error',ascending=False).to_csv(REPORTS/'worst_cases.csv',index=False)
    stress={}
    for name,sub in [('observed_pre_cutoff_cyclone',selected[selected.cyclone_150km.eq(1)]),
                     ('pre_cutoff_spi3_below_minus1',selected[selected.spi3<-1]),
                     ('Aila_calendar_year_2009',selected[selected.crop_year.eq(2009)]),
                     ('Amphan_calendar_year_2020',selected[selected.crop_year.eq(2020)]),
                     ('Yaas_calendar_year_2021',selected[selected.crop_year.eq(2021)])]:
        stress[name]={'metrics':scores(sub),'note':'Empty means outside heldout or no observations; calendar-year tags are descriptive, not causal attribution.'}
    save_json(REPORTS/'stress_years.json',stress)
    explain(panel,choice['classifier'])
    manifest=json.loads((REPORTS/'source_manifest.json').read_text())
    pd.DataFrame(manifest).to_csv(REPORTS/'source_attempts.csv',index=False)
    packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()}
    save_json(REPORTS/'environment.json',{'python':platform.python_version(),'platform':platform.platform(),
        'packages':packages,
        'code_sha256':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'rice_model').glob('*.py')}})
    (ROOT/'requirements.lock.txt').write_text('# Executed Linux / Python 3.12 environment; generated from installed distributions.\n'+
        '\n'.join(f'{name}=={version}' for name,version in sorted(packages.items(),key=lambda x:x[0].lower()) if name.lower()!='pip')+'\n')
    from .documentation import write_reports
    write_reports(gate,summary)
    print(json.dumps({'release_status':gate['status'],'failed_checks':gate['failed_checks'],'metrics':measured},indent=2),flush=True)


if __name__=='__main__':main()
