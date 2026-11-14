select
    route_id,
    route_short_name as line,
    route_long_name,
    cast(route_type as integer) as route_type
from {{ read_gtfs('routes.txt') }}
