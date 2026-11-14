with positions as (
    select *
    from {{ ref('stg_vehicle_positions') }}
    where not is_stale and is_in_warsaw_area
),

pairs as (
    select
        vehicle_type,
        vehicle_number,
        line,
        brigade,
        lag(reported_at_utc) over run as from_at_utc,
        lag(lat) over run as from_lat,
        lag(lon) over run as from_lon,
        reported_at_utc as to_at_utc,
        lat as to_lat,
        lon as to_lon
    from positions
    window run as (
        partition by vehicle_type, vehicle_number, line, brigade
        order by reported_at_utc
    )
),

measured as (
    select
        *,
        epoch(to_at_utc - from_at_utc) as seconds,
        {{ haversine_m('from_lat', 'from_lon', 'to_lat', 'to_lon') }} as distance_raw_m,
        {{ bearing_deg('from_lat', 'from_lon', 'to_lat', 'to_lon') }} as bearing_raw_deg
    from pairs
    where from_at_utc is not null
)

select
    vehicle_type,
    vehicle_number,
    line,
    brigade,
    from_at_utc,
    to_at_utc,
    from_lat,
    from_lon,
    to_lat,
    to_lon,
    seconds,
    round(distance_raw_m, 1) as distance_m,
    round(distance_raw_m / seconds * 3.6, 1) as speed_kmh,
    round(bearing_raw_deg, 1) as bearing_deg,
    distance_raw_m / seconds * 3.6 <= {{ var('max_plausible_speed_kmh', 90) }} as is_plausible
from measured
where seconds between {{ var('min_segment_seconds', 10) }} and {{ var('max_segment_seconds', 300) }}
