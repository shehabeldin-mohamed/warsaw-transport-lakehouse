select
    stop_id,
    stop_name,
    stop_code,
    cast(stop_lat as double) as stop_lat,
    cast(stop_lon as double) as stop_lon
from {{ read_gtfs('stops.txt') }}
