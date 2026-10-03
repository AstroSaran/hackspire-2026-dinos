"""Fold-local, no-imputation estimators and explicit temporal availability rules."""
from dataclasses import dataclass, field
import warnings

import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression, Ridge, ElasticNet

from .common import SEED
from .features import DISTRICTS, SEASONS, GROUPS, covered_columns, window

TARGETS=['anomaly','anomaly_pct','detrended_anomaly','detrended_pct']
KINDS=['linear','elastic','lightgbm','xgboost','catboost','mixed','lightgbm_season']
NATIVE={'lightgbm','xgboost','catboost'}


def origin(year):
    # Freeze the pooled crop-year model at the earliest seasonal issue date.
    return window(int(year),'Autumn')[1].date().isoformat()


def available(frame,year):
    return frame[(frame.crop_year<int(year)) & (frame.label_available_at<origin(year))].copy()


def select_features(train,exclude=()):
    groups={g:covered_columns(train,cols) for g,cols in GROUPS.items() if g not in exclude}
    columns=[c for cols in groups.values() for c in cols]
    if not columns:raise ValueError('No feature group meets training-fold coverage threshold')
    return columns,groups


def matrix(frame,features,kind):
    numeric=frame[features].to_numpy(dtype=float)
    names=list(features)
    if kind in NATIVE:
        extra=frame[['district_code','season_code']].to_numpy(dtype=float)
        return np.column_stack([numeric,extra]),names+['district_code','season_code']
    pieces=[numeric]
    if kind!='mixed':
        pieces.append(np.column_stack([frame.district.eq(d) for d in DISTRICTS[1:]]).astype(float))
        names.extend('district='+d for d in DISTRICTS[1:])
    pieces.append(np.column_stack([frame.season.eq(s) for s in SEASONS[1:]]).astype(float))
    names.extend('season='+s for s in SEASONS[1:])
    return np.column_stack(pieces),names


@dataclass
class FittedModel:
    kind: str
    target: str
    features: list
    config: int=0
    estimator: object=None
    scaler: object=None
    columns: list=field(default_factory=list)
    random_effects: dict=field(default_factory=dict)
    diagnostics: dict=field(default_factory=dict)
    background: object=None

    @property
    def classifier(self):return self.target.startswith('label')

    def fit(self,frame):
        x,self.columns=matrix(frame,self.features,self.kind)
        valid=np.isfinite(frame[self.target].to_numpy())
        if self.kind not in NATIVE:valid &= np.isfinite(x).all(axis=1)
        data=frame.loc[valid]; x=x[valid]; y=data[self.target].to_numpy()
        if len(y)<25:raise ValueError(f'Only {len(y)} complete training observations')
        if self.classifier and len(np.unique(y))<2:raise ValueError('Training outcome has only one class')
        self.diagnostics={'train_rows':len(frame),'fitted_rows':len(data),'complete_case_exclusions':len(frame)-len(data),
                          'positive_rows':int(y.sum()) if self.classifier else None,
                          'last_label_available_at':data.label_available_at.max()}
        self.background=data.tail(40).copy()
        if self.kind not in NATIVE:
            self.scaler=StandardScaler().fit(x);x=self.scaler.transform(x)
        c=self.config
        if self.kind=='linear':
            self.estimator=LogisticRegression(C=[.1,1.0][c],max_iter=2000,random_state=SEED) if self.classifier else Ridge(alpha=[10.,100.][c])
        elif self.kind=='elastic':
            self.estimator=LogisticRegression(C=[.1,1.0][c],penalty='elasticnet',solver='saga',l1_ratio=.5,
                                              max_iter=4000,random_state=SEED) if self.classifier else ElasticNet(alpha=[.05,.5][c],l1_ratio=.5,max_iter=4000,random_state=SEED)
        elif self.kind=='lightgbm':
            from lightgbm import LGBMClassifier,LGBMRegressor
            cls=LGBMClassifier if self.classifier else LGBMRegressor
            self.estimator=cls(n_estimators=[100,180][c],num_leaves=[5,9][c],learning_rate=.04,
                               min_child_samples=25,reg_lambda=5,n_jobs=2,random_state=SEED,verbosity=-1)
        elif self.kind=='xgboost':
            from xgboost import XGBClassifier,XGBRegressor
            cls=XGBClassifier if self.classifier else XGBRegressor
            self.estimator=cls(n_estimators=[100,180][c],max_depth=[2,3][c],learning_rate=.035,
                               min_child_weight=8,reg_lambda=10,n_jobs=2,random_state=SEED,tree_method='hist')
        elif self.kind=='catboost':
            from catboost import CatBoostClassifier,CatBoostRegressor
            cls=CatBoostClassifier if self.classifier else CatBoostRegressor
            self.estimator=cls(iterations=[100,180][c],depth=[3,4][c],learning_rate=.04,l2_leaf_reg=8,
                               thread_count=2,random_seed=SEED,verbose=False,allow_writing_files=False)
        elif self.kind=='mixed':
            # Genuine district random intercept, with fixed weather/season effects.
            from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
            from statsmodels.regression.mixed_linear_model import MixedLM
            # Remove constant columns to avoid singular fixed-effects designs.
            active=np.std(x,axis=0)>1e-10
            self.diagnostics['active_columns']=active.tolist()
            design=np.column_stack([np.ones(len(x)),x[:,active]])
            districts=sorted(data.district.unique())
            if self.classifier:
                np.random.seed(SEED) # statsmodels variational initialization uses NumPy's global RNG
                z=np.column_stack([data.district.eq(d) for d in districts]).astype(float)
                result=BinomialBayesMixedGLM(y,design,z,np.zeros(len(districts),dtype=int),vcp_p=.5,fe_p=2).fit_vb(
                    minim_opts={'maxiter':150})
                self.estimator=result.fe_mean
                self.random_effects=dict(zip(districts,result.vc_mean))
                self.diagnostics['converged']=bool(result.optim_retvals.success)
            else:
                result=MixedLM(y,design,groups=data.district.to_numpy()).fit(reml=False,method='powell',maxiter=80,disp=False)
                self.estimator=np.asarray(result.fe_params)
                self.random_effects={d:float(np.asarray(v)[0]) for d,v in result.random_effects.items()}
                self.diagnostics['converged']=bool(result.converged)
            if not self.diagnostics['converged']:raise ValueError('Mixed-effects optimization did not converge')
            return self
        else:raise ValueError(f'Unknown estimator: {self.kind}')
        self.estimator.fit(x,y)
        return self

    def predict(self,frame):
        x,_=matrix(frame,self.features,self.kind)
        valid=np.ones(len(frame),dtype=bool) if self.kind in NATIVE else np.isfinite(x).all(axis=1)
        out=np.full(len(frame),np.nan)
        if not valid.any():return out
        x=x[valid]
        if self.scaler is not None:x=self.scaler.transform(x)
        if self.kind=='mixed':
            active=np.array(self.diagnostics['active_columns'])
            design=np.column_stack([np.ones(len(x)),x[:,active]])
            pred=design@self.estimator+frame.loc[valid,'district'].map(self.random_effects).to_numpy()
            out[valid]=expit(pred) if self.classifier else pred
        elif self.kind=='lightgbm':out[valid]=self.estimator.booster_.predict(x)
        elif self.classifier:out[valid]=self.estimator.predict_proba(x)[:,1]
        else:out[valid]=self.estimator.predict(x)
        return out


@dataclass
class Bundle:
    kind: str
    year: int
    config: int
    label: str='label15'
    exclude: tuple=()
    members: dict=field(default_factory=dict)
    diagnostics: list=field(default_factory=list)

    def fit(self,train,targets=None):
        if len(train) and (train.label_available_at>=origin(self.year)).any():
            raise ValueError('Label availability leakage in training split')
        targets=targets or [self.label]+TARGETS
        by_season=self.kind.endswith('_season');kind=self.kind.removesuffix('_season')
        subsets=train.groupby('season') if by_season else [('pooled',train)]
        for season,data in subsets:
            features,groups=select_features(data,self.exclude)
            if kind=='mixed':
                shortlist=['rain_z','dry_spell','hot35','oni_lag','dmi_lag','yield_trend','previous_residual','area_change']
                features=[c for c in features if c in shortlist]
            fitted={}
            for target in targets:
                diagnostic={'season':season,'target':target,'features':features,'groups':groups}
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    try:
                        model=FittedModel(kind,target,features,self.config).fit(data)
                        fitted[target]=model;diagnostic.update(status='OK',**model.diagnostics)
                    except Exception as exc:diagnostic.update(status='FAILED',error=f'{type(exc).__name__}: {exc}')
                diagnostic['warnings']=sorted({str(w.message) for w in caught})
                self.diagnostics.append(diagnostic)
            self.members[season]=fitted
        return self

    def predict(self,frame):
        out=pd.DataFrame(index=frame.index)
        for col in ['p']+['pred_'+t for t in TARGETS]:out[col]=np.nan
        for season,models in self.members.items():
            data=frame if season=='pooled' else frame[frame.season==season]
            if not len(data):continue
            for target,model in models.items():
                col='p' if target==self.label else 'pred_'+target
                out.loc[data.index,col]=model.predict(data)
        return out


def baseline_predictions(train,test,label='label15'):
    outputs={name:pd.DataFrame(index=test.index) for name in ['base_rate','persistence','climatology','trailing_mean']}
    for name,output in outputs.items():
        for idx,row in test.iterrows():
            history=train[(train.district==row.district)&(train.season==row.season)].sort_values('crop_year')
            if name=='base_rate':
                output.loc[idx,'p']=train[label].mean()
            elif name=='persistence':
                output.loc[idx,'p']=history.iloc[-1][label] if len(history) else np.nan
            elif name=='climatology':
                output.loc[idx,'p']=history[label].mean() if len(history) else np.nan
            else:output.loc[idx,'p']=0. # Yield equal to its trailing baseline implies no shortfall.
            for target in TARGETS:
                value=0. if name=='trailing_mean' else (train[target].mean() if name=='base_rate' else
                       (history.iloc[-1][target] if name=='persistence' and len(history) else history[target].mean()))
                output.loc[idx,'pred_'+target]=value
    return outputs
