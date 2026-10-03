import json

import numpy as np
import pandas as pd
import pytest

from rice_model.common import MODELS,REPORTS,PROCESSED
from rice_model.gate import release_gate
from rice_model.inference import Engine,predict
from rice_model.modelling import origin,TARGETS

HAS_LOCAL_ARTIFACTS=(PROCESSED/'panel.csv').exists() and (MODELS/'catboost_2022.joblib').exists()
requires_local_artifacts=pytest.mark.skipif(not HAS_LOCAL_ARTIFACTS,
    reason='Requires the local real-data panel and fitted artifacts; these are not distributed in GitHub')


def test_release_is_conjunctive_and_fails_on_missing_evidence():
    m={'brier':.04,'base_brier':.05,'persistence_brier':.06,'brier_skill':.2}
    assert release_gate(m,.6,25,.8,5)['status']=='released'
    assert release_gate(m,.6,24,.8,5)['status']=='withheld'
    assert release_gate(m,.55,25,.8,5)['status']=='withheld'
    assert release_gate(m,.6,25,.851,5)['status']=='withheld'
    assert release_gate(m,.6,25,.8,5,['unknown APY release vintage'])['status']=='withheld'
    assert release_gate(m,np.nan,25,.8,5)['status']=='withheld'
    assert release_gate(m,.6,25,.8,3)['status']=='withheld'


@pytest.fixture(scope='module')
def engine():
    if not HAS_LOCAL_ARTIFACTS:
        pytest.skip('Requires local data and fitted model artifacts')
    return Engine()


def test_all_saved_models_precede_their_issue_dates(engine):
    for name in engine.manifest['artifacts']:
        if name.startswith(('quantile_','stack_')) or '_isotonic_' in name:continue
        bundle=engine.load(name)
        for members in bundle.members.values():
            for model in members.values():
                assert model.diagnostics['last_label_available_at']<origin(bundle.year)


def test_quantile_training_and_calibration_are_disjoint(engine):
    for year in engine.manifest['holdout_years']:
        model=engine.load(f'quantile_{year}.joblib')
        assert not set(model['train_ids'])&set(model['calibration_ids'])
        assert model['last_training_label_available_at']<origin(model['calibration_year'])
        assert model['calibration_year']<year


def test_prediction_never_uses_current_outcome_columns(engine):
    data=engine.panel[(engine.panel.crop_year==2022)&(engine.panel.season=='Winter')].copy()
    before=engine.risk(data,2022);reg=engine.regression(data,2022)
    data[['area','production','yield_t_ha','baseline','label15']+TARGETS]=999999.
    np.testing.assert_allclose(engine.risk(data,2022),before)
    pd.testing.assert_frame_equal(engine.regression(data,2022),reg)


def test_inference_matches_saved_out_of_time_predictions(engine):
    stored=pd.read_csv(REPORTS/'selected_predictions.csv')
    for year in engine.manifest['holdout_years']:
        data=engine.panel[engine.panel.crop_year==year].copy()
        data['row_id']=data.district+'|'+data.crop_year.astype(str)+'|'+data.season
        expected=stored.set_index('row_id').loc[data.row_id]
        np.testing.assert_allclose(engine.risk(data,year),expected.p,atol=1e-10)
        actual=engine.regression(data,year)
        np.testing.assert_allclose(actual.pred_anomaly_pct,expected.pred_anomaly_pct,atol=1e-10)
        interval=engine.intervals(data,year)['anomaly_pct']
        np.testing.assert_allclose(interval[:,0],expected.anomaly_pct_low,atol=1e-10)
        assert np.all(interval[:,0]<=interval[:,1]) and np.all(interval[:,1]<=interval[:,2])


@requires_local_artifacts
def test_corrupted_artifact_checksum_is_rejected():
    engine=Engine();name='catboost_2022.joblib'
    engine.manifest['artifacts'][name]='0'*64
    with pytest.raises(ValueError,match='checksum mismatch'):engine.load(name)


@requires_local_artifacts
def test_rejects_unvalidated_dates_and_missing_components():
    for district,season,date in [('Kolkata','Winter','2022-07-31'),
                                 ('Bankura','Winter','2022-08-01'),
                                 ('Bankura','Winter','2026-07-31'),
                                 ('Bankura','Winter','NaT'),
                                 ('Darjeeling','Autumn','2022-06-30')]:
        with pytest.raises(ValueError):predict(district,season,date)


@requires_local_artifacts
def test_research_response_and_gate_enforcement():
    result=predict('South 24 Parganas','Winter','2022-07-31')
    report=json.loads((REPORTS/'model_release_report.json').read_text())
    assert result['gate_status']==report['status']
    assert 0<=result['shortfall_probability']<=1
    assert len(result['top_five_drivers'])==5
    reconstructed=result['shap_baseline_probability']+sum(
        r['probability_contribution'] for r in result['top_five_drivers'])
    # Top five are a subset: full additivity is checked on all SHAP columns in evaluation.
    assert np.isfinite(reconstructed)
    assert result['lead_time_days']>0
    if report['status']!='released':
        with pytest.raises(ValueError,match='withheld'):
            predict('South 24 Parganas','Winter','2022-07-31',require_released=True)
