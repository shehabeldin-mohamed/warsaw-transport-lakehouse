with moving as (
    select
        *,
        date_trunc('minute', to_at_utc) as minute_utc
    from {{ ref('fct_segment_speed') }}
    where is_plausible and speed_kmh >= {{ var('bunching_min_speed_kmh', 5) }}
    qualify row_number() over (
        partition by vehicle_type, vehicle_number, minute_utc
        order by to_at_utc desc
    ) = 1
),

pairs as (
    select
        a.minute_utc,
        a.vehicle_type,
        a.line,
        a.vehicle_number as vehicle_a,
        b.vehicle_number as vehicle_b,
        {{ haversine_m('a.to_lat', 'a.to_lon', 'b.to_lat', 'b.to_lon') }} as distance_raw_m,
        abs(epoch(a.to_at_utc - b.to_at_utc)) as seconds_apart,
        {{ angle_between_deg('a.bearing_deg', 'b.bearing_deg') }} as heading_difference_deg
    from moving as a
    inner join moving as b
        on a.vehicle_type = b.vehicle_type
        and a.line = b.line
        and a.minute_utc = b.minute_utc
        and a.vehicle_number < b.vehicle_number
    where abs(epoch(a.to_at_utc - b.to_at_utc)) <= 30
)

select
    minute_utc,
    vehicle_type,
    line,
    vehicle_a,
    vehicle_b,
    round(distance_raw_m, 1) as distance_m,
    seconds_apart,
    round(heading_difference_deg, 1) as heading_difference_deg
from pairs
where distance_raw_m <= {{ var('bunching_max_distance_m', 200) }}
    and heading_difference_deg <= {{ var('bunching_max_heading_difference_deg', 45) }}
