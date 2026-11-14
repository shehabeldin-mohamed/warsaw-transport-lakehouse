select
    trip_id,
    cast(stop_sequence as integer) as stop_sequence,
    stop_id,
    {{ gtfs_time_to_seconds('arrival_time') }} as arrival_seconds,
    {{ gtfs_time_to_seconds('departure_time') }} as departure_seconds
from {{ read_gtfs('stop_times.txt') }}
