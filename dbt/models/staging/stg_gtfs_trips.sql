select
    trip_id,
    route_id,
    service_id,
    cast(direction_id as integer) as direction_id,
    trip_headsign as headsign,
    nullif(trim(block_short_name), '') as brigade
from {{ read_gtfs('trips.txt') }}
