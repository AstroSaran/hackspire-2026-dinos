import numpy as np
import pandas as pd
import pytest

from rice_model.features import labels,canonical,window,covered_columns,raw_weather_features
from rice_model.modelling import available,select_features
from rice_model.train import conformal_radius,load_panel
from rice_model.common import PROCESSED


def test_strict_shortfall_and_future_invariance():
    years=list(range(2000,2008));values=[2.,2.,2.,2.,2.,1.7,1.6,99.]
    first=labels(values,years)
    assert first.loc[5,'label15']==0 # strict <, not <=
    assert first.loc[6,'label15']==1
    values[-1]=0
    pd.testing.assert_frame_equal(first.iloc[:-1],labels(values,years).iloc[:-1])


def test_missing_baseline_year_is_not_imputed():
    result=labels([2.]*6,[2000,2001,2002,2004,2005,2006])
    assert result.label15.isna().all()


def test_districts_and_boro_window():
    assert canonical('Alipurduar')=='Jalpaiguri'
    assert canonical('purba bardhaman')=='Bardhaman'
    start,cut,harvest=window(2021,'Summer')
    assert str(start.date())=='2021-12-01'
    assert str(cut.date())=='2022-03-15'
    assert cut<harvest
    with pytest.raises(ValueError):window(2020,'Total')


def test_complete_weather_window_and_cutoff():
    dates=pd.date_range('2020-04-01','2020-07-31')
    data=pd.DataFrame({'rainfall_mm':1.,'tmax_c':34.,'tmin_c':24.,'et0':3.,'soil':.3},index=dates)
    start,cut,_=window(2020,'Autumn')
    before=raw_weather_features(data,start,cut)
    data.loc[cut-pd.Timedelta(days=6):,'rainfall_mm']=999
    assert raw_weather_features(data,start,cut)==before
    data.loc['2020-04-05','rainfall_mm']=np.nan
    assert np.isnan(raw_weather_features(data,start,cut)['rain_total'])


def test_coverage_is_training_only():
    train=pd.DataFrame({'a':[1.,2.,np.nan,np.nan],'b':[1.,2.,3.,4.]})
    assert covered_columns(train,['a','b'])==['b']


@pytest.mark.skipif(not (PROCESSED/'panel.csv').exists(),reason='Requires the local real-data panel; datasets are not distributed in GitHub')
def test_real_panel_split_and_feature_allowlist():
    panel=load_panel();train=available(panel,2018)
    assert (train.label_available_at<'2018-06-30').all()
    assert train.crop_year.max()<=2016
    features,_=select_features(train)
    assert not set(features)&{'yield_t_ha','production','area','baseline','label15','anomaly','anomaly_pct'}
    assert panel.loc[(panel.district=='Darjeeling')&(panel.crop_year>=2016),'season'].eq('Winter').all()


def test_finite_sample_conformal_rank():
    assert conformal_radius(np.arange(9.))==7.
    with pytest.raises(ValueError):conformal_radius([1.])
