"""Tests for API route handlers."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# ── GET /predictionWindow ────────────────────────────────────────────────


def test_prediction_window(client):
    resp = client.get('/predictionWindow')
    assert resp.status_code == 200
    assert resp.json()['windowLengthHours'] == 168


# ── GET /locations ───────────────────────────────────────────────────────


def test_get_locations(client):
    resp = client.get('/locations')
    assert resp.status_code == 200
    locations = resp.json()
    assert isinstance(locations, list)
    assert len(locations) > 0
    assert all('id' in loc and 'name' in loc for loc in locations)


def test_get_locations_only_active(client):
    import db_utils

    db_utils.set_datacenter_active('Data-Center-1', False)
    resp = client.get('/locations')
    ids = [loc['id'] for loc in resp.json()]
    assert 'Data-Center-1' not in ids


# ── GET /datacenters ─────────────────────────────────────────────────────


def test_get_datacenters_returns_all(client):
    resp = client.get('/datacenters')
    assert resp.status_code == 200
    dcs = resp.json()
    assert len(dcs) == 14
    assert any(dc['active'] for dc in dcs)
    assert any(not dc['active'] for dc in dcs)


def test_datacenter_has_full_schema(client):
    resp = client.get('/datacenters')
    first = resp.json()[0]
    for key in ('id', 'region_id', 'name', 'active', 'latitude', 'longitude'):
        assert key in first


# ── PATCH /datacenters/{id} ──────────────────────────────────────────────


def test_patch_activate(client):
    resp = client.patch('/datacenters/Data-Center-6', json={'active': True})
    assert resp.status_code == 200
    assert resp.json()['active'] is True
    assert resp.json()['id'] == 'Data-Center-6'


def test_patch_deactivate(client):
    resp = client.patch('/datacenters/Data-Center-1', json={'active': False})
    assert resp.status_code == 200
    assert resp.json()['active'] is False


def test_patch_not_found(client):
    resp = client.patch('/datacenters/nonexistent', json={'active': True})
    assert resp.status_code == 404


def test_patch_missing_body(client):
    resp = client.patch('/datacenters/Data-Center-1')
    assert resp.status_code == 422


# ── GET forecast_load ────────────────────────────────────────────────────


def test_load_forecast_success(client):
    mock_data = {
        'location_id': 'Data-Center-1',
        'metric': 'forecast_load',
        'unit': 'FLOs',
        'data': [
            {
                'timestamp': '2026-03-18T12:00:00',
                'value': 100.0,
                'is_forecast': True,
                'capacity': 9.84e17,
            }
        ],
    }
    with patch('routes.get_load_time_series', return_value=mock_data):
        resp = client.get('/locations/Data-Center-1/metrics/forecast_load')
    assert resp.status_code == 200
    body = resp.json()
    assert body['location_id'] == 'Data-Center-1'
    assert len(body['data']) == 1


def test_load_forecast_start_after_end(client):
    with patch(
        'routes.get_load_time_series',
        return_value={'location_id': 'Data-Center-1', 'metric': 'forecast_load', 'unit': 'FLOs', 'data': []},
    ):
        resp = client.get(
            '/locations/Data-Center-1/metrics/forecast_load',
            params={
                'start_time': '2026-03-20T00:00:00Z',
                'end_time': '2026-03-18T00:00:00Z',
            },
        )
        assert resp.status_code == 422


def test_load_forecast_end_beyond_window(client):
    far = (datetime.now(timezone.utc) + timedelta(hours=200)).isoformat()
    with patch(
        'routes.get_load_time_series',
        return_value={'location_id': 'Data-Center-1', 'metric': 'forecast_load', 'unit': 'FLOs', 'data': []},
    ):
        resp = client.get(
            '/locations/Data-Center-1/metrics/forecast_load',
            params={'end_time': far},
        )
        assert resp.status_code == 422


def test_load_forecast_404_on_value_error(client):
    with patch(
        'routes.get_load_time_series',
        side_effect=ValueError('No history'),
    ):
        resp = client.get('/locations/nope/metrics/forecast_load')
    assert resp.status_code == 404


def test_load_forecast_500_on_exception(client):
    with patch(
        'routes.get_load_time_series',
        side_effect=RuntimeError('boom'),
    ):
        resp = client.get('/locations/Data-Center-1/metrics/forecast_load')
    assert resp.status_code == 500


# ── GET forecast_carbon_intensity ────────────────────────────────────────


def test_carbon_forecast_success(client):
    mock_data = {
        'location_id': 'Data-Center-1',
        'metric': 'forecast_carbon_intensity',
        'unit': 'gCO2/kWh',
        'data': [
            {
                'timestamp': '2026-03-18T12:00:00',
                'value': 200.0,
                'is_forecast': True,
            }
        ],
    }
    with patch('routes.get_carbon_intensity_time_series', return_value=mock_data):
        resp = client.get('/locations/Data-Center-1/metrics/forecast_carbon_intensity')
    assert resp.status_code == 200
    assert resp.json()['metric'] == 'forecast_carbon_intensity'


def test_carbon_forecast_start_after_end(client):
    with patch(
        'routes.get_carbon_intensity_time_series',
        return_value={
            'location_id': 'Data-Center-1',
            'metric': 'forecast_carbon_intensity',
            'unit': 'gCO2/kWh',
            'data': [],
        },
    ):
        resp = client.get(
            '/locations/Data-Center-1/metrics/forecast_carbon_intensity',
            params={
                'start_time': '2026-03-20T00:00:00Z',
                'end_time': '2026-03-18T00:00:00Z',
            },
        )
        assert resp.status_code == 422


def test_carbon_forecast_404_on_value_error(client):
    with patch(
        'routes.get_carbon_intensity_time_series',
        side_effect=ValueError('No data'),
    ):
        resp = client.get('/locations/nonexistent/metrics/forecast_carbon_intensity')
    assert resp.status_code == 404


def test_carbon_forecast_invalid_timestamp_422(client):
    """Invalid timestamps should be caught by FastAPI validation."""
    resp = client.get(
        '/locations/Data-Center-1/metrics/forecast_carbon_intensity',
        params={'start_time': 'garbage', 'end_time': 'also-garbage'},
    )
    assert resp.status_code == 422
