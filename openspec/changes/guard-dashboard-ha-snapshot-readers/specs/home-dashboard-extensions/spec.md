## MODIFIED Requirements

### Requirement: Device Inventory Endpoint

The implementation SHALL provide the behavior described by this requirement.
A paginated endpoint listing all known HA devices with their current state, area, and health status.

#### Scenario: List all devices

- **WHEN** `GET /api/home/devices` is called with no filters
- **THEN** it SHALL return a paginated list of device entries from `ha_entity_snapshot` table
- **AND** each entry SHALL include `entity_id`, `state`, `friendly_name` (from attributes), `area_name` (from entity registry cache or attributes), `domain` (extracted from entity_id prefix), `last_updated`, and `health_status` (computed: `"healthy"` if state is not `unavailable`/`unknown`, `"offline"` otherwise)

#### Scenario: Filter by domain

- **WHEN** `GET /api/home/devices?domain=light` is called
- **THEN** only entities with `entity_id` starting with `light.` SHALL be returned

#### Scenario: Filter by area

- **WHEN** `GET /api/home/devices?area=kitchen` is called
- **THEN** only entities whose area matches the given area name SHALL be returned

#### Scenario: Filter by health status

- **WHEN** `GET /api/home/devices?health=offline` is called
- **THEN** only entities with state `unavailable` or `unknown` SHALL be returned

#### Scenario: Pagination

- **WHEN** `GET /api/home/devices?page=2&page_size=50` is called
- **THEN** the response SHALL be a page-based paginated wrapper (`DeviceInventoryResponse`) with `meta` (`DevicePaginationMeta`) containing `page`, `page_size`, `total_count`, `total_pages`, and `ha_source_available`

#### Scenario: HA source unmeasurable during an outage

- **WHEN** `GET /api/home/devices` is called while `ha_source_health` shows the
  `home_assistant` source is not `'healthy'` (an active outage) or has no
  recorded contact
- **THEN** the endpoint SHALL still return its (possibly stale) device rows
  rather than failing the request
- **AND** `meta.ha_source_available` SHALL be `false`, so a caller cannot
  treat the returned devices as a truthful current-state read
